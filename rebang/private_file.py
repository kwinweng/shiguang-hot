"""Open and write owner-only credential files without trusting HOME, symlinks or shared directories.

Only the Python standard library, so the Mac publisher can load this file by path for its preflight
and the collectors can use the same rules when they actually read.

Opening walks from ``/`` one component at a time with ``O_NOFOLLOW`` relative to the previous
directory's descriptor, and checks each descriptor with ``fstat`` (plus its ACL), so a path that is
swapped after a check can only make the open fail, never redirect it:

- every ancestor directory: owned by root or this account, not group/other writable, no allowing ACL
  entries (macOS home folders carry a harmless ``everyone deny delete`` entry);
- the directory holding the file: owned by this account, no group/other bits at all, no ACL;
- the file: a regular file of this account, no group/other bits, readable by the owner, exactly one
  hard link, no ACL.

Anything else raises ``PrivateFileError`` with a short code (never the contents); callers treat that as
"not configured".
"""
import ctypes
import ctypes.util
import errno
import os
import pwd
import secrets
import stat
import sys

_DIR_FLAGS = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
_FILE_FLAGS = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0)
               | getattr(os, 'O_NOCTTY', 0))
MAX_BYTES = 64 * 1024


class PrivateFileError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def account_home():
    """The account's home from the user database, not the inherited HOME variable."""
    return pwd.getpwuid(os.getuid()).pw_dir


def default_home():
    """For collector defaults only: the account home, or HOME when the user database has no entry.
    (The publisher always passes explicit paths and treats a missing entry as "no credentials".)"""
    try:
        return account_home()
    except (KeyError, OSError):
        return os.path.expanduser('~')


def account_problem(checkout=None):
    """Writers refuse to run as root or as an account that does not own the checkout (the publishing
    account owns its dedicated clone). Returns an error code, or None when this account is fine."""
    if os.getuid() == 0:
        return 'run_as_root'
    checkout = checkout or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.git')
    try:
        if os.lstat(checkout).st_uid != os.getuid():
            return 'not_checkout_owner'
    except OSError:
        return 'no_checkout'
    return None


# ---------- ACL ----------

_ACL_TYPE_EXTENDED = 0x00000100
_ACL_FIRST_ENTRY, _ACL_NEXT_ENTRY = 0, -1
_ACL_EXTENDED_DENY = 2
_libc = None


def _darwin_libc():
    global _libc
    if _libc is None:
        lib = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
        lib.acl_get_fd_np.restype = ctypes.c_void_p
        lib.acl_get_fd_np.argtypes = (ctypes.c_int, ctypes.c_int)
        lib.acl_get_entry.restype = ctypes.c_int
        lib.acl_get_entry.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
        lib.acl_get_tag_type.restype = ctypes.c_int
        lib.acl_get_tag_type.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
        lib.acl_free.restype = ctypes.c_int
        lib.acl_free.argtypes = (ctypes.c_void_p,)
        _libc = lib
    return _libc


def acl_tags(fd):
    """Tag of every extended ACL entry on fd (empty: no ACL). Raises PrivateFileError if it cannot tell."""
    if sys.platform == 'darwin':
        try:
            lib = _darwin_libc()
        except (OSError, AttributeError):
            raise PrivateFileError('acl_unknown') from None
        ctypes.set_errno(0)
        acl = lib.acl_get_fd_np(fd, _ACL_TYPE_EXTENDED)
        if not acl:
            if ctypes.get_errno() == errno.ENOENT:
                return []
            raise PrivateFileError('acl_unknown')
        try:
            tags, entry, which = [], ctypes.c_void_p(), _ACL_FIRST_ENTRY
            while lib.acl_get_entry(acl, which, ctypes.byref(entry)) == 0:
                tag = ctypes.c_int()
                if lib.acl_get_tag_type(entry, ctypes.byref(tag)) != 0:
                    raise PrivateFileError('acl_unknown')
                tags.append(tag.value)
                which = _ACL_NEXT_ENTRY
            return tags
        finally:
            lib.acl_free(acl)
    try:
        names = os.listxattr(fd)
    except OSError as exc:
        if exc.errno in (errno.ENOTSUP, getattr(errno, 'EOPNOTSUPP', errno.ENOTSUP)):
            return []
        raise PrivateFileError('acl_unknown') from None
    except AttributeError:   # no xattr support on this platform
        return []
    # POSIX ACLs only ever add access, so any of them counts as an allowing entry.
    return [1 for name in names if name in ('system.posix_acl_access', 'system.posix_acl_default')]


# ---------- checks ----------

def _check_ancestor(fd):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise PrivateFileError('not_directory')
    if info.st_uid not in (0, os.getuid()):
        raise PrivateFileError('directory_owner')
    if info.st_mode & 0o022:
        raise PrivateFileError('directory_shared')
    if any(tag != _ACL_EXTENDED_DENY for tag in acl_tags(fd)):
        raise PrivateFileError('directory_acl')


def _check_private_dir(fd):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise PrivateFileError('not_directory')
    if info.st_uid != os.getuid():
        raise PrivateFileError('directory_owner')
    if info.st_mode & 0o077 or info.st_mode & 0o700 != 0o700:
        raise PrivateFileError('directory_mode')
    if acl_tags(fd):
        raise PrivateFileError('directory_acl')


def _check_private_file(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise PrivateFileError('not_regular')
    if info.st_uid != os.getuid():
        raise PrivateFileError('file_owner')
    if info.st_mode & 0o077 or not info.st_mode & stat.S_IRUSR:
        raise PrivateFileError('file_mode')
    if info.st_nlink != 1:
        raise PrivateFileError('hard_link')
    if acl_tags(fd):
        raise PrivateFileError('file_acl')
    if info.st_size > MAX_BYTES:
        raise PrivateFileError('too_large')


def _split(path):
    path = os.path.abspath(os.fspath(path))
    parts = [part for part in path.split('/') if part]
    if not parts:
        raise PrivateFileError('bad_path')
    return parts[:-1], parts[-1]


def open_private_dir(path):
    """Descriptor of the verified owner-only directory at path (walk from / without following links)."""
    parents, name = _split(path)
    return _walk(parents + [name])


def _walk(components, create=False):
    """Open each component relative to its verified parent. create: make missing ones (0700) and
    tighten the last one to 0700 through its own descriptor (never through a name)."""
    try:
        fd = os.open('/', _DIR_FLAGS)
    except OSError:
        raise PrivateFileError('unreadable') from None
    try:
        _check_ancestor(fd)
        for index, part in enumerate(components):
            last = index == len(components) - 1
            try:
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise PrivateFileError('missing') from None
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    child = os.open(part, _DIR_FLAGS, dir_fd=fd)
                except OSError:
                    raise PrivateFileError('cannot_create') from None
            except OSError:
                raise PrivateFileError('unreadable') from None
            os.close(fd)
            fd = child
            if last and create:
                info = os.fstat(fd)
                if stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) != 0o700:
                    os.fchmod(fd, 0o700)
            (_check_private_dir if last else _check_ancestor)(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_private(path):
    """Read-only descriptor of the verified owner-only credential file at path."""
    parents, name = _split(path)
    if not parents:
        raise PrivateFileError('bad_path')
    folder = _walk(parents)
    try:
        try:
            fd = os.open(name, _FILE_FLAGS, dir_fd=folder)
        except OSError:
            raise PrivateFileError('unreadable') from None
    finally:
        os.close(folder)
    try:
        _check_private_file(fd)
        os.set_blocking(fd, True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def check_private(path):
    """Preflight only: True when open_private would succeed. Opens but never reads the contents."""
    try:
        os.close(open_private(path))
        return True
    except PrivateFileError:
        return False


def read_private(path):
    """Contents of the verified credential file as text."""
    fd = open_private(path)
    try:
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, MAX_BYTES + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_BYTES:
                raise PrivateFileError('too_large')
    except OSError:
        raise PrivateFileError('unreadable') from None
    finally:
        os.close(fd)
    try:
        return b''.join(chunks).decode('utf-8')
    except UnicodeDecodeError:
        raise PrivateFileError('not_utf8') from None


def write_private(path, text):
    """Atomically replace path with text: exclusive 0600 temp file in the same verified directory, then rename.

    Missing directories are created 0700 one by one under verified parents; the holding directory is
    tightened to 0700 through its descriptor. A symlinked or shared component makes it fail instead.
    """
    # Size first (UTF-8 bytes, newline included): an oversized value never touches directories or the old file.
    try:
        data = text.encode('utf-8')
    except (AttributeError, UnicodeError):
        raise PrivateFileError('not_utf8') from None
    if len(data) > MAX_BYTES:
        raise PrivateFileError('too_large')
    parents, name = _split(path)
    if not parents:
        raise PrivateFileError('bad_path')
    folder = _walk(parents, create=True)
    temp = None
    try:
        for _ in range(8):
            candidate = f'.{name}.{secrets.token_hex(8)}.tmp'
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                             | getattr(os, 'O_CLOEXEC', 0), 0o600, dir_fd=folder)
            except FileExistsError:
                continue
            temp = candidate
            break
        else:
            raise PrivateFileError('cannot_create')
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, name, src_dir_fd=folder, dst_dir_fd=folder)
        temp = None
        try:
            os.fsync(folder)
        except OSError:
            pass
    except OSError:
        raise PrivateFileError('cannot_write') from None
    finally:
        if temp is not None:
            try:
                os.unlink(temp, dir_fd=folder)
            except OSError:
                pass
        os.close(folder)
    if not check_private(path):
        raise PrivateFileError('not_private_after_write')

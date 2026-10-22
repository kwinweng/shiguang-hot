"""Publication: stage the whole site in a temporary tree, check it, then swap it in atomically.

`build()` is the one entry point. Pages themselves come from pages.py; this module owns the
staging, the content-hashed asset names and the public-build privacy check.
"""
import ctypes, fcntl, hashlib, os, shutil, signal, tempfile, threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from shiguang.config import ROOT, WEB, private_mode
from shiguang.ingest.feeds import load_issues
from shiguang.model import BEIJING
from shiguang.site.pages import write_pages
from shiguang.site.render import E
from shiguang.site.privacy import verify_source_markers
from shiguang.site.history import ALLOWED


@contextmanager
def staged_output(destination):
    """Keep live output untouched until a complete tree passes validation."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination.with_name(destination.name+'.build.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # SIGKILL cannot run cleanup; reclaim abandoned staging trees next build.
        for stale in destination.parent.glob(destination.name+'.tmp-*'):
            if stale.is_dir() and not stale.is_symlink(): shutil.rmtree(stale)
        temporary=Path(tempfile.mkdtemp(prefix=destination.name+'.tmp-', dir=destination.parent))
        handlers={}
        def interrupted(signum, frame):
            raise SystemExit(128+signum)
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                handlers[sig]=signal.signal(sig, interrupted)
        try:
            if destination.exists():
                shutil.copytree(destination, temporary, dirs_exist_ok=True, symlinks=True)
            yield temporary
            if destination.exists():
                # Linux RENAME_EXCHANGE keeps the served path present throughout.
                libc=ctypes.CDLL(None, use_errno=True)
                exchange=libc.renameat2
                exchange.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
                exchange.restype=ctypes.c_int
                if exchange(-100,os.fsencode(temporary),-100,os.fsencode(destination),2):
                    error=ctypes.get_errno()
                    raise OSError(error,os.strerror(error),str(destination))
            else:
                os.rename(temporary,destination)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
            for sig,handler in handlers.items(): signal.signal(sig,handler)

def build(rows, hot, now, entries=(), inbox_only=False):
    out = Path(os.getenv('SITE_OUT', ROOT/'site')).resolve()
    if out == ROOT or ROOT.is_relative_to(out): raise ValueError('SITE_OUT 不能覆盖仓库')
    with staged_output(out) as temporary:
        cfg = write_pages(rows, hot, now, temporary, publish_assets(temporary, not inbox_only), entries, inbox_only)
        if not private_mode():
            verify_public(temporary, cfg)
    print(f'built site -> {out}')


def publish_assets(out, full):
    """Copy style.css / app.js under content-hashed names so browsers can cache them safely.

    Inbox-only builds keep older hashed files: pages from the last full build still point at them.
    """
    names = {}
    for kind, source in (('css', WEB / 'style.css'), ('js', WEB / 'app.js')):
        data = source.read_bytes()
        names[kind] = f'{source.stem}.{hashlib.sha256(data).hexdigest()[:10]}{source.suffix}'
        # Historical HTML may still reference any earlier content hash.
        (out / names[kind]).write_bytes(data)
    icons = hashlib.sha256()
    for asset in sorted((WEB / 'assets').iterdir()):
        if asset.is_file(): icons.update(asset.read_bytes())
    names['version'] = icons.hexdigest()[:10]
    history = WEB / 'history.js'
    if history.is_file():
        data = history.read_bytes()
        names['history'] = f'history.{hashlib.sha256(data).hexdigest()[:10]}.js'
        (out / names['history']).write_bytes(data)
    return names


def verify_public(out, cfg):
    """Refuse to publish if anything from a private source leaked into the public tree."""
    forbidden = [s for s in cfg['sources'] if s['visibility'] == 'private' or s['id'] not in ALLOWED]
    for s in forbidden:
        if (out / s['id']).exists(): raise RuntimeError('公开产物存在 private 目录')
    private_text = []
    for source in forbidden:
        if source['type'] == 'inbox':
            for data, base in load_issues(source, True):
                for section in data.get('sections', []):
                    for item in section.get('items', []):
                        private_text.extend(E(item.get(field)) for field in ('title', 'body') if len(item.get(field) or '') >= 16)
                for block in data.get('blocks', []):
                    values = [block.get('title'), block.get('caption')]
                    for item in block.get('items', []) or []:
                        values.extend([item] if isinstance(item, str) else [item.get('title'), item.get('body')])
                    private_text.extend(E(value) for value in values if isinstance(value, str) and len(value) >= 16)
    for p in out.rglob('*'):
        if p.suffix in ('.html', '.json', '.webmanifest', '.svg', '.css', '.js'):
            text = p.read_text()
            verify_source_markers(p.relative_to(out), text, forbidden)
            if any(value in text for value in private_text): raise RuntimeError('公开产物存在 private 内容: ' + str(p))




if __name__ == '__main__':
    # Inbox columns only (no Telegram fetch); mailbuild.py runs this for the private site.
    build([], [], datetime.now(BEIJING), inbox_only=True)

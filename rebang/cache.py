"""Best-effort persistence for disposable collection caches."""
import sys


def save_cache(write, *args):
    try:
        write(*args)
    except OSError:
        print('采集缓存暂时无法保存。', file=sys.stderr)
        return False
    return True

"""python3 -m rebang.push --site site-v11 --now <ISO> --dry-run [--output FILE]"""
from .cli import main

if __name__ == '__main__':
    raise SystemExit(main())

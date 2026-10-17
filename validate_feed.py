#!/usr/bin/env python3
"""兼容入口：投递 bot 仍按旧路径调用。实现在 tools/validate_feed.py。"""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().parent / 'tools' / 'validate_feed.py'), run_name='__main__')

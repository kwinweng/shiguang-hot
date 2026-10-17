#!/usr/bin/env python3
"""兼容旧入口；仅重建内网 inbox 栏目，不抓取 Telegram。"""
import os, runpy
if __name__ == '__main__':
    os.environ['SITE_MODE']='private'
    runpy.run_module('sitebuild',run_name='__main__')

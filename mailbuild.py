#!/usr/bin/env python3
"""本机定时任务入口：只重建内网 inbox 栏目，不抓取 Telegram。"""
import os, runpy
if __name__ == '__main__':
    os.environ['SITE_MODE'] = 'private'
    runpy.run_module('shiguang.site.build', run_name='__main__')

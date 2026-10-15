#!/bin/sh
# 用法: ./mobile_shot.sh [页面相对 site/ 的路径，默认 index.html]
# 刷新数据 -> 构建 -> 390x844@2x 整页截图，超过 30000px 自动拆分
set -e
cd /workspace/tg-site
python3 pipeline.py
mkdir -p shots
python3 mshot.py "file:///workspace/tg-site/site/${1:-index.html}" "shots/mobile-$(date +%Y%m%d-%H%M%S)" | sed 's#^#/workspace/tg-site/#'

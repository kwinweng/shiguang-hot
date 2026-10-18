#!/usr/bin/env bash
# 每个任务完成前必须通过。
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests

"""拾光资讯 v1 新版静态站构建器（feat/rebang-v1-frontend-v11）。

`python3 -m rebang.site --out site-v11`：读 var/rebang/in/*.json（无数据时读契约 fixture），
合并去重、选 banner、按频道分页（每页 30）、写 data/meta.json 等，再拷贝 web-v11/ 前端。
"""
from .builder import build, select_banners, paginate, PAGE_SIZE, BANNER_MAX

__all__ = ['build', 'select_banners', 'paginate', 'PAGE_SIZE', 'BANNER_MAX']

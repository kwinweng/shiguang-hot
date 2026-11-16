"""公众号正文图片、微博图片存到本地，站上用自己的副本。

原因：公众号图床 mmbiz.qpic.cn 对外站引用（带别的网站 Referer）一律换成「未经允许不可引用」占位图；
Wechat2RSS 的 img-proxy 在 Cloudflare 验证后面，手机上常打不开。所以抓取时不带 Referer 下载原图，
转成 webp（GIF 保留原样以保住动图）放 var/rebang/media/wechat/，站点构建再复制进 site/media/。
下载失败的图：块里不写 local，前端如实显示「这张图没存下来，打开原文看」，不拿别的图顶替。

微博同理：sinaimg / weibocdn 对浏览器请求只认 weibo.com 的 Referer（不带 Referer 或带本站都回 403），
所以抓取时带 ``Referer: https://weibo.com/`` 下载图片、视频封面和头像（不带 Cookie），放 var/rebang/media/weibo/。
视频本体太大不存，站上播放会被拒，前端照常退回「打开原帖」。
"""
import hashlib
import io
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = ROOT / 'var' / 'rebang' / 'media'
MAX_SIDE = 1280


def _curl(url, referer=None):
    r = subprocess.run(['curl', '-sL', '--fail', '-m', '25', '-A', 'Mozilla/5.0'] + (['-e', referer] if referer else []) + [url],
                       capture_output=True)
    if r.returncode or not r.stdout:
        raise RuntimeError(f'curl {r.returncode}')
    return r.stdout


def _save(data, dest_base):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(data)) as im:
        if (im.format or '').upper() == 'GIF' and getattr(im, 'n_frames', 1) > 1:
            path = dest_base.with_suffix('.gif')
            path.write_bytes(data)
            return path, im.size
        im = ImageOps.exif_transpose(im)
        im = im.convert('RGBA' if im.mode in ('RGBA', 'LA', 'P') else 'RGB')
        im.thumbnail((MAX_SIDE, MAX_SIDE * 6))
        path = dest_base.with_suffix('.webp')
        im.save(path, format='WEBP', quality=80)
        return path, im.size


class _Local:
    """url → 本地副本 {path, rel, width, height}；同 url 同文件名（sha1），已有就复用。失败返回 None。"""

    def __init__(self, media_dir, platform, get):
        self.sub = Path(media_dir) / platform
        self.sub.mkdir(parents=True, exist_ok=True)
        self.platform, self.get = platform, get
        self.stats = {'saved': 0, 'reused': 0, 'failed': 0}
        self.cache = {}

    def __call__(self, url):
        if url in self.cache:
            return self.cache[url]
        key = hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]
        found = next((p for p in self.sub.glob(key + '.*') if p.suffix in ('.webp', '.gif')), None)
        result = None
        if found:
            try:
                from PIL import Image
                with Image.open(found) as im:
                    size = im.size
                result = found, size
                self.stats['reused'] += 1
            except Exception:
                found.unlink(missing_ok=True)
        if result is None:
            try:
                result = _save(self.get(url), self.sub / key)
                self.stats['saved'] += 1
            except Exception:
                self.stats['failed'] += 1
                result = None
        if result:
            path, (w, h) = result
            result = {'path': str(path), 'rel': f'{self.platform}/{path.name}', 'width': w, 'height': h}
        self.cache[url] = result
        return result


def localize(items, media_dir=MEDIA_DIR, get=_curl, platform='wechat'):
    """items 里 platform 的帖子：blocks 里每张图、封面 image 都存本地副本（block['local'] / item['image_local']）。
    返回 {'saved', 'reused', 'failed'}。"""
    local_for = _Local(media_dir, platform, get)
    for item in items:
        if (item.get('blogger') or {}).get('platform') != platform:
            continue
        for block in item.get('blocks') or []:
            if block.get('type') == 'img':
                loc = local_for(block['src'])
                if loc:
                    block['local'] = loc
                else:
                    block.pop('local', None)
        image = item.get('image') or {}
        if image.get('url'):
            from .common import unwrap_image_url
            loc = local_for(unwrap_image_url(image['url']))
            if loc:
                item['image_local'] = loc
                item['image'] = None
    return local_for.stats


def _weibo_get(url):
    return _curl(url, referer='https://weibo.com/')


def localize_weibo(items, media_dir=MEDIA_DIR, get=_weibo_get):
    """微博帖子：图片 → media[i].local；视频/GIF 封面 → media[i].preview_local；头像 → blogger.avatar_local；
    列表缩略图用第一张本地图（item.image_local）。原始 url 保留（契约要求 http(s)），建站时改写成站内地址。"""
    local_for = _Local(media_dir, 'weibo', get)

    def fresh(loc):
        return loc if isinstance(loc, dict) and Path(loc.get('path', '')).is_file() else None

    for item in items:
        b = item.get('blogger') or {}
        if b.get('platform') != 'weibo':
            continue
        first = None
        for m in b.get('media') or []:
            if m.get('type') == 'image':
                loc = fresh(m.get('local')) or local_for(m['url'])
                m.pop('local', None)
                if loc:
                    m['local'] = loc
            elif m.get('preview_url'):
                loc = fresh(m.get('preview_local')) or local_for(m['preview_url'])
                m.pop('preview_local', None)
                if loc:
                    m['preview_local'] = loc
            else:
                loc = None
            first = first or loc
        if b.get('avatar'):
            loc = fresh(b.get('avatar_local')) or local_for(b['avatar'])
            b.pop('avatar_local', None)
            if loc:
                b['avatar_local'] = loc
        first = fresh(item.get('image_local')) or first
        item.pop('image_local', None)
        if first:
            item['image_local'] = first
            item['image'] = None
    return local_for.stats


def prune(items, media_dir=MEDIA_DIR, platform='wechat'):
    """删掉当前条目都不再引用的本地图。"""
    keep = set()
    for item in items:
        b = item.get('blogger') or {}
        locs = [block.get('local') for block in item.get('blocks') or []] + [item.get('image_local'), b.get('avatar_local')]
        locs += [m.get(k) for m in b.get('media') or [] for k in ('local', 'preview_local')]
        keep.update(Path(loc['path']).name for loc in locs if isinstance(loc, dict) and loc.get('path'))
    removed = 0
    for path in (Path(media_dir) / platform).glob('*'):
        if path.is_file() and path.name not in keep:
            path.unlink()
            removed += 1
    return removed

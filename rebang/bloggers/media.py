"""公众号正文图片存到本地，站上用自己的副本。

原因：公众号图床 mmbiz.qpic.cn 对外站引用（带别的网站 Referer）一律换成「未经允许不可引用」占位图；
Wechat2RSS 的 img-proxy 在 Cloudflare 验证后面，手机上常打不开。所以抓取时不带 Referer 下载原图，
转成 webp（GIF 保留原样以保住动图）放 var/rebang/media/wechat/，站点构建再复制进 site/media/。
下载失败的图：块里不写 local，前端如实显示「这张图没存下来，打开原文看」，不拿别的图顶替。
"""
import hashlib
import io
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = ROOT / 'var' / 'rebang' / 'media'
MAX_SIDE = 1280


def _curl(url):
    r = subprocess.run(['curl', '-sL', '--fail', '-m', '25', '-A', 'Mozilla/5.0', url], capture_output=True)
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


def localize(items, media_dir=MEDIA_DIR, get=_curl, platform='wechat'):
    """items 里 platform 的帖子：blocks 里每张图、封面 image 都存本地副本（block['local'] / item['image_local']）。
    返回 {'saved', 'reused', 'failed'}。"""
    media_dir = Path(media_dir)
    sub = media_dir / platform
    sub.mkdir(parents=True, exist_ok=True)
    stats = {'saved': 0, 'reused': 0, 'failed': 0}
    cache = {}

    def local_for(url):
        if url in cache:
            return cache[url]
        key = hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]
        found = next((p for p in sub.glob(key + '.*') if p.suffix in ('.webp', '.gif')), None)
        result = None
        if found:
            try:
                from PIL import Image
                with Image.open(found) as im:
                    size = im.size
                result = found, size
                stats['reused'] += 1
            except Exception:
                found.unlink(missing_ok=True)
        if result is None:
            try:
                result = _save(get(url), sub / key)
                stats['saved'] += 1
            except Exception:
                stats['failed'] += 1
                result = None
        if result:
            path, (w, h) = result
            result = {'path': str(path), 'rel': f'{platform}/{path.name}', 'width': w, 'height': h}
        cache[url] = result
        return result

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
    return stats


def prune(items, media_dir=MEDIA_DIR, platform='wechat'):
    """删掉当前条目都不再引用的本地图。"""
    keep = set()
    for item in items:
        for block in item.get('blocks') or []:
            if block.get('local'):
                keep.add(Path(block['local']['path']).name)
        if item.get('image_local'):
            keep.add(Path(item['image_local']['path']).name)
    removed = 0
    for path in (Path(media_dir) / platform).glob('*'):
        if path.is_file() and path.name not in keep:
            path.unlink()
            removed += 1
    return removed

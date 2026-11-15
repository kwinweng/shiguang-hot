"""Resize the approved kangaroo artwork into 拾光热榜 v11 favicon, PWA, splash and share images."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'web-v11/brand/kangaroo-source.png'
OUT = ROOT / 'web-v11'


def _background_and_crop(im: Image.Image) -> tuple[Image.Image, tuple[int, int, int]]:
    rgb = im.convert('RGB')
    w, h = rgb.size
    samples: list[tuple[int, int, int]] = []
    for box in ((0, 0, 30, 30), (w - 30, 0, w, 30), (0, h - 30, 30, h), (w - 30, h - 30, w, h)):
        corner = rgb.crop(box)
        samples.extend(corner.getpixel((x, y)) for y in range(corner.height) for x in range(corner.width))
    n = len(samples)
    bg = tuple(int(round(sum(c[i] for c in samples) / n)) for i in range(3))
    px = rgb.load()
    threshold = 25 * 25
    minx, miny, maxx, maxy = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if (r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2 > threshold:
                if x < minx:
                    minx = x
                if y < miny:
                    miny = y
                if x > maxx:
                    maxx = x
                if y > maxy:
                    maxy = y
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    half = min(cx, cy, w - 1 - cx, h - 1 - cy)
    box = (int(round(cx - half)), int(round(cy - half)), int(round(cx + half)), int(round(cy + half)))
    return rgb.crop(box), bg


def _fit(src: Image.Image, size: int, scale: float, bg: tuple[int, int, int]) -> Image.Image:
    canvas = Image.new('RGB', (size, size), bg)
    inner = max(1, int(round(size * scale)))
    icon = src.resize((inner, inner), Image.Resampling.LANCZOS)
    canvas.paste(icon, ((size - inner) // 2, (size - inner) // 2))
    return canvas


def _sharpen(im: Image.Image, size: int) -> Image.Image:
    if size <= 64:
        return im.filter(ImageFilter.UnsharpMask(radius=0.6, percent=120, threshold=2))
    if size <= 192:
        return im.filter(ImageFilter.UnsharpMask(radius=0.8, percent=80, threshold=2))
    return im


def _save(im: Image.Image, path: Path) -> None:
    im.save(path, format='PNG', optimize=True)


def main() -> None:
    cropped, bg = _background_and_crop(Image.open(SRC))
    for name, size in {
        'favicon-16x16.png': 16,
        'favicon-32x32.png': 32,
        'apple-touch-icon.png': 180,
        'icon-192.png': 192,
        'icon-512.png': 512,
        'logo.png': 192,
    }.items():
        _save(_sharpen(_fit(cropped, size, 1.0, bg), size), OUT / name)
    ico = [_sharpen(_fit(cropped, s, 1.0, bg), s).convert('RGBA') for s in (16, 32, 48)]
    ico[-1].save(OUT / 'favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
    for size, name in ((192, 'icon-192-maskable.png'), (512, 'icon-512-maskable.png')):
        _save(_fit(cropped, size, 0.72, bg), OUT / name)
    og = Image.new('RGB', (1200, 630), bg)
    side = 520
    k = cropped.resize((side, side), Image.Resampling.LANCZOS)
    og.paste(k, ((1200 - side) // 2, (630 - side) // 2))
    _save(og, OUT / 'og-image.png')
    for sw, sh, name in (
        (1170, 2532, 'apple-splash-1170x2532.png'),
        (1179, 2556, 'apple-splash-1179x2556.png'),
        (1290, 2796, 'apple-splash-1290x2796.png'),
    ):
        canvas = Image.new('RGB', (sw, sh), bg)
        side = int(round(min(sw, sh) * 0.46))
        k = cropped.resize((side, side), Image.Resampling.LANCZOS)
        canvas.paste(k, ((sw - side) // 2, (sh - side) // 2))
        _save(canvas, OUT / name)
    manifest = {
        'name': '拾光热榜',
        'short_name': '拾光热榜',
        'description': '时事、博主与热搜',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#101114',
        'theme_color': '#101114',
        'lang': 'zh-CN',
        'icons': [
            {'src': 'icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': 'icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': 'icon-192-maskable.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'maskable'},
            {'src': 'icon-512-maskable.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    (OUT / 'manifest.webmanifest').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

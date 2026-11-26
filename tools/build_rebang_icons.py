"""Resize the approved 拾光资讯 Light/Dark artwork into v11 favicon, PWA, splash and share images."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC_LIGHT = ROOT / 'web-v11/brand/shiguang-logo-light-1024.png'
SRC_DARK = ROOT / 'web-v11/brand/shiguang-logo-dark-1024.png'
OUT = ROOT / 'web-v11'

SPLASH_SIZES = (
    (1170, 2532, '1170x2532'),
    (1179, 2556, '1179x2556'),
    (1290, 2796, '1290x2796'),
)


def _load_with_bg(path: Path) -> tuple[Image.Image, tuple[int, int, int]]:
    rgb = Image.open(path).convert('RGB')
    w, h = rgb.size
    samples: list[tuple[int, int, int]] = []
    for box in ((0, 0, 20, 20), (w - 20, 0, w, 20), (0, h - 20, 20, h), (w - 20, h - 20, w, h)):
        corner = rgb.crop(box)
        samples.extend(corner.getpixel((x, y)) for y in range(corner.height) for x in range(corner.width))
    n = len(samples)
    bg = tuple(int(round(sum(c[i] for c in samples) / n)) for i in range(3))
    return rgb, bg


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


def _hex(bg: tuple[int, int, int]) -> str:
    return '#{:02X}{:02X}{:02X}'.format(*bg)


def main() -> None:
    light, light_bg = _load_with_bg(SRC_LIGHT)
    dark, dark_bg = _load_with_bg(SRC_DARK)

    # Default (Light) icons: home screen, PWA, share image, and light-mode favicons
    for name, size in {
        'favicon-16x16.png': 16,
        'favicon-32x32.png': 32,
        'apple-touch-icon.png': 180,
        'icon-192.png': 192,
        'icon-512.png': 512,
        'logo.png': 192,
    }.items():
        _save(_sharpen(_fit(light, size, 1.0, light_bg), size), OUT / name)

    # Dark-mode adaptive favicons
    for name, size in {
        'favicon-dark-16x16.png': 16,
        'favicon-dark-32x32.png': 32,
    }.items():
        _save(_sharpen(_fit(dark, size, 1.0, dark_bg), size), OUT / name)

    ico = [_sharpen(_fit(light, s, 1.0, light_bg), s).convert('RGBA') for s in (16, 32, 48)]
    ico[-1].save(OUT / 'favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])

    for size, name in ((192, 'icon-192-maskable.png'), (512, 'icon-512-maskable.png')):
        _save(_fit(light, size, 0.78, light_bg), OUT / name)

    og = Image.new('RGB', (1200, 630), light_bg)
    side = 520
    k = light.resize((side, side), Image.Resampling.LANCZOS)
    og.paste(k, ((1200 - side) // 2, (630 - side) // 2))
    _save(og, OUT / 'og-image.png')

    for sw, sh, tag in SPLASH_SIZES:
        for prefix, src, bg in (
            ('apple-splash-', light, light_bg),
            ('apple-splash-dark-', dark, dark_bg),
        ):
            canvas = Image.new('RGB', (sw, sh), bg)
            side = int(round(min(sw, sh) * 0.46))
            k = src.resize((side, side), Image.Resampling.LANCZOS)
            canvas.paste(k, ((sw - side) // 2, (sh - side) // 2))
            _save(canvas, OUT / f'{prefix}{tag}.png')

    manifest = {
        'name': '拾光资讯',
        'short_name': '拾光资讯',
        'description': '时事、博主与热搜',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': _hex(light_bg),
        'theme_color': '#FFFFFF',
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

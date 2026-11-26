"""Resize approved 拾光资讯 Light/Dark artwork into the legacy web/assets icon set."""
import base64
import io
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'web/assets'
BRAND_LIGHT = ROOT / 'web-v11/brand/shiguang-logo-light-1024.png'
BRAND_DARK = ROOT / 'web-v11/brand/shiguang-logo-dark-1024.png'


def _png_b64(im: Image.Image, size: int) -> str:
    buf = io.BytesIO()
    im.resize((size, size), Image.Resampling.LANCZOS).save(buf, format='PNG', optimize=True)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def _adaptive_svg(light: Image.Image, dark: Image.Image, size: int = 128) -> str:
    b_light = _png_b64(light, size)
    b_dark = _png_b64(dark, size)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
        '<defs><clipPath id="r"><rect width="1024" height="1024" rx="228"/></clipPath></defs>'
        '<style>.d{display:none}@media(prefers-color-scheme:dark){.l{display:none}.d{display:inline}}</style>'
        f'<image class="l" width="1024" height="1024" clip-path="url(#r)" href="data:image/png;base64,{b_light}"/>'
        f'<image class="d" width="1024" height="1024" clip-path="url(#r)" href="data:image/png;base64,{b_dark}"/>'
        '</svg>\n'
    )


def _single_svg(im: Image.Image, size: int = 128) -> str:
    b = _png_b64(im, size)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
        '<defs><clipPath id="r"><rect width="1024" height="1024" rx="228"/></clipPath></defs>'
        f'<image width="1024" height="1024" clip-path="url(#r)" href="data:image/png;base64,{b}"/>'
        '</svg>\n'
    )


def main():
    light_src = BRAND_LIGHT if BRAND_LIGHT.exists() else (ASSETS / 'logo-d.png')
    dark_src = BRAND_DARK if BRAND_DARK.exists() else light_src
    source = Image.open(light_src).convert('RGBA')
    dark = Image.open(dark_src).convert('RGBA')
    for name, size in [('apple-touch-icon.png', 180), ('apple-touch-icon-precomposed.png', 180),
                       ('icon-192.png', 192), ('icon-512.png', 512), ('favicon-32x32.png', 32)]:
        source.resize((size, size), Image.Resampling.LANCZOS).save(ASSETS / name, optimize=True)
    source.resize((64, 64), Image.Resampling.LANCZOS).save(ASSETS / 'favicon.ico', sizes=[(16, 16), (32, 32), (64, 64)])
    (ASSETS / 'favicon.svg').write_text(_adaptive_svg(source, dark), encoding='utf-8')
    (ASSETS / 'logo-d-tab.svg').write_text(_single_svg(source), encoding='utf-8')
    manifest = dict(name='拾光资讯', short_name='拾光资讯', start_url='./index.html', display='standalone',
                    background_color='#DEE7ED', theme_color='#FFFFFF', icons=[
                        dict(src=f'icon-{s}.png', sizes=f'{s}x{s}', type='image/png', purpose='any') for s in (192, 512)])
    (ASSETS / 'manifest.webmanifest').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

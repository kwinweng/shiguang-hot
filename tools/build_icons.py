"""Resize approved Logo D artwork into the existing application icon set."""
import json
from pathlib import Path
from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / 'web/assets'


def main():
    source = Image.open(ASSETS / 'logo-d.png').convert('RGBA')
    for name, size in [('apple-touch-icon.png', 180), ('apple-touch-icon-precomposed.png', 180),
                       ('icon-192.png', 192), ('icon-512.png', 512), ('favicon-32x32.png', 32)]:
        source.resize((size, size), Image.Resampling.LANCZOS).save(ASSETS / name)
    source.resize((64, 64), Image.Resampling.LANCZOS).save(ASSETS / 'favicon.ico', sizes=[(16, 16), (32, 32), (64, 64)])
    manifest = dict(name='拾光热榜', short_name='拾光热榜', start_url='./index.html', display='standalone',
                    background_color='#FFFFFF', theme_color='#D7282F', icons=[
                        dict(src=f'icon-{s}.png', sizes=f'{s}x{s}', type='image/png', purpose='any') for s in (192, 512)])
    (ASSETS / 'manifest.webmanifest').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()

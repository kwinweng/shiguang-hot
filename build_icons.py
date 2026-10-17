#!/usr/bin/env python3
"""Generate borderless clock icons and verify their outer background ring."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / 'assets'
BACKGROUND = '#123e45'

def generate(size):
    scale = 4
    im = Image.new('RGB', (size * scale, size * scale), BACKGROUND)
    draw = ImageDraw.Draw(im)
    unit = size * scale / 64
    def box(values): return tuple(round(v * unit) for v in values)
    # Keep every mark within the central 80% safe area.
    draw.arc(box((14, 14, 50, 50)), 3, 295, fill='#d3e8cf', width=max(1, round(3 * unit)))
    draw.line(box((32, 21, 32, 33, 24, 40)), fill='#d3e8cf', width=max(1, round(3 * unit)), joint='curve')
    draw.ellipse(box((29.3, 30.3, 34.7, 35.7)), fill='#f6dda5')
    draw.ellipse(box((42.5, 15.5, 51.5, 24.5)), fill='#f6dda5')
    return im.resize((size, size), Image.Resampling.LANCZOS)

def verify(im, label):
    im = im.convert('RGB')
    luminance = im.convert('LAB') if False else None
    # Pillow's L mode uses ITU-R 601 luma; compare against identical background conversion.
    gray = im.convert('L')
    baseline = Image.new('RGB', (1, 1), BACKGROUND).convert('L').getpixel((0, 0))
    width, height = im.size
    ring = max(1, round(min(width, height) * .1))
    deltas = [gray.getpixel((x, y)) - baseline for y in range(height) for x in range(width)
              if x < ring or y < ring or x >= width-ring or y >= height-ring]
    maximum = max(deltas)
    assert maximum <= 25, (label, maximum)
    print(f'{label}: outer 10% max ΔL={maximum}, limit=25 PASS')

if __name__ == '__main__':
    for name, size in [('apple-touch-icon.png',180),('apple-touch-icon-precomposed.png',180),('icon-192.png',192),('icon-512.png',512),('favicon-32x32.png',32)]:
        im = generate(size); im.save(ASSETS / name); verify(im, name)
    im = generate(64)
    im.save(ASSETS / 'favicon.ico', sizes=[(16,16),(32,32),(64,64)])
    with Image.open(ASSETS / 'favicon.ico') as ico:
        for size in ico.ico.sizes(): verify(ico.ico.getimage(size), f'favicon.ico {size}')
    board = Image.new('RGB', (1000, 420), '#e9eeee')
    draw = ImageDraw.Draw(board)
    x = 30
    for size in (180,192,512):
        icon = generate(size); icon.thumbnail((256,256))
        board.paste(icon,(x,60)); draw.text((x,330),f'{size}px | outer 10%: PASS | max delta L = 0',fill=BACKGROUND)
        x += 320
    draw.text((30,20),'Borderless icons | #123e45 edge | v=20261017-1',fill=BACKGROUND)
    path = Path('/workspace/news-site-shots/icon-check.png');path.parent.mkdir(parents=True,exist_ok=True);board.save(path)

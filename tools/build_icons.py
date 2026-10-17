#!/usr/bin/env python3
"""Generate opaque, borderless gradient clock icons and verify the outer 10%."""
from pathlib import Path
import json
from PIL import Image, ImageDraw
ASSETS=Path(__file__).resolve().parent.parent/'web'/'assets'

def background(size):
    im=Image.new('RGBA',(size,size))
    pixels=im.load()
    for y in range(size):
        for x in range(size):
            t=(x+y)/(2*max(1,size-1))
            pixels[x,y]=tuple(round(a+(b-a)*t) for a,b in zip((250,246,239),(238,232,223)))+(255,)
    return im

def generate(size):
    scale=4; n=size*scale; im=background(n); draw=ImageDraw.Draw(im)
    def box(values): return tuple(round(v*n/64) for v in values)
    # Keep every mark within the central 80% safe area.
    draw.ellipse(box((20,20,44,44)),fill='#e3a01e')
    for ray in ((32,12,32,16),(32,48,32,52),(12,32,16,32),(48,32,52,32),(18,18,21,21),(43,43,46,46),(18,46,21,43),(43,21,46,18)):
        draw.line(box(ray),fill='#2b2100',width=max(1,round(n*1.75/64)))
    return im.resize((size,size),Image.Resampling.LANCZOS)

def verify(im,label):
    rgba=im.convert('RGBA'); gray=rgba.convert('L'); baseline=background(im.width).convert('L'); n=im.width; ring=max(1,round(n*.1))
    points=[(x,y) for y in range(n) for x in range(n) if x<ring or y<ring or x>=n-ring or y>=n-ring]
    delta=max(abs(gray.getpixel(p)-baseline.getpixel(p)) for p in points)
    opaque=all(rgba.getpixel(p)[3]==255 for p in points)
    assert opaque and delta<=25,(label,delta,opaque)
    print(f'{label}: outer 10% opaque={opaque}, max |delta L|={delta} <=25 PASS')
    return delta

def main():
    for name,size in [('apple-touch-icon.png',180),('apple-touch-icon-precomposed.png',180),('icon-192.png',192),('icon-512.png',512),('favicon-32x32.png',32)]:
        im=generate(size);im.save(ASSETS/name);verify(im,name)
    generate(64).save(ASSETS/'favicon.ico',sizes=[(16,16),(32,32),(64,64)])
    with Image.open(ASSETS/'favicon.ico') as ico:
        for size in ico.ico.sizes():verify(ico.ico.getimage(size),f'ico {size}')
    (ASSETS/'favicon.svg').write_text((ASSETS/'sun.svg').read_text())
    manifest={'name':'拾光热点','short_name':'拾光','start_url':'./','display':'standalone','background_color':'#eee8df','theme_color':'#eee8df','icons':[{'src':f'icon-{s}.png?v=20261017-4','sizes':f'{s}x{s}','type':'image/png','purpose':'any maskable'} for s in (192,512)]}
    (ASSETS/'manifest.webmanifest').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    board=Image.new('RGB',(1200,760),'white');d=ImageDraw.Draw(board)
    for j,bg in enumerate(('#f4f8fc','#0f1216')):
        d.rectangle((j*600,0,j*600+600,760),fill=bg)
        for i,size in enumerate((180,512)):
            pic=generate(size);pic.thumbnail((260,260));mask=Image.new('L',pic.size);ImageDraw.Draw(mask).rounded_rectangle((0,0,pic.width-1,pic.height-1),radius=pic.width*.2237,fill=255)
            x=j*600+40+i*280;y=130;board.paste(pic,(x,y),mask)
            d.text((x,440),f'{size}px / iOS radius 22.37%',fill='#6b7785')
        d.text((j*600+40,520),'Outer 10%: alpha=255; max |delta L| <= 1; PASS',fill='#6b7785')
    path=ASSETS/'icon-preview.png';board.save(path)
if __name__=='__main__':main()

"""Build-time photographic light, sampled as a 4 × 6 OKLab color grid."""
import math
from functools import lru_cache
from PIL import Image, ImageOps
from urllib.parse import quote

@lru_cache(maxsize=1024)
def photo_like(path):
    """Reject white text screenshots and low-colour images before sampling light."""
    try:
        with Image.open(path) as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((96,96))
            pixels=list(im.getdata())
            white=sum(min(rgb)>235 and max(rgb)-min(rgb)<20 for rgb in pixels)/len(pixels)
            chroma=sum(math.hypot(*oklab(tuple(v/255 for v in rgb))[1:]) for rgb in pixels)/len(pixels)
            return white<=.55 and chroma>=.02
    except (OSError,ValueError):
        return False

def oklab(rgb):
    r,g,b=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    l=(.4122214708*r+.5363325363*g+.0514459929*b)**(1/3)
    m=(.2119034982*r+.6806995451*g+.1073969566*b)**(1/3)
    s=(.0883024619*r+.2817188376*g+.6299787005*b)**(1/3)
    return .2104542553*l+.793617785*m-.0040720468*s,1.9779984951*l-2.428592205*m+.4505937099*s,.0259040371*l+.7827717662*m-.808675766*s

@lru_cache(maxsize=256)
def light_css(path=''):
    try:
        with Image.open(path) as im:
            grid=ImageOps.exif_transpose(im).convert('RGB').resize((4,6),Image.Resampling.BOX)
            colors=[oklab(tuple(v/255 for v in rgb)) for rgb in grid.getdata()]
    except (OSError,ValueError):
        colors=[(.8,.018*(1-y/5),.045-.09*y/5) for y in range(6) for x in range(4)]
    def gradients(dark):
        result=[]
        for i,(l,a,b) in enumerate(colors):
            hue=math.degrees(math.atan2(b,a))%360
            cap=(.13 if dark else .085)*(.5 if 180<=hue<=280 else 1)
            chroma=max(.04 if dark else .028,min(cap,math.hypot(a,b)*1.3))
            l=(.17+.30*l) if dark else (.77+.17*l)
            result.append(f'<rect x="{i%4}" y="{i//4}" width="1" height="1" fill="oklch({l:.4f} {chroma:.4f} {hue:.1f})"/>')
        # Disjoint grid cells keep all 24 hues; stacked radial layers hid lower rows.
        svg='<svg xmlns="http://www.w3.org/2000/svg" width="4" height="6" viewBox="0 0 4 6" preserveAspectRatio="none">'+''.join(result)+'</svg>'
        return 'url("data:image/svg+xml,'+quote(svg,safe='')+'")'
    return ':root{--light-image:'+gradients(False)+';--dark-image:'+gradients(True)+';}' + '''
.g-light{background:radial-gradient(ellipse at 100% 0,var(--beam),transparent 65%),linear-gradient(var(--veil),var(--veil)),var(--ground)}
.g-light:before,.g-light:after{inset:0;transform:scale(1.14);filter:blur(44px);transition:opacity 900ms;background:radial-gradient(ellipse at 100% 0,var(--beam),transparent 65%),linear-gradient(var(--veil),var(--veil)),var(--light-image);background-size:100% 100%}
.g-light:before{opacity:1}.g-light:after{background-image:radial-gradient(ellipse at 100% 0,var(--beam),transparent 65%),linear-gradient(var(--veil),var(--veil)),var(--dark-image);opacity:0}

@media(prefers-color-scheme:dark){html:not([data-theme=light]) .g-light:before{opacity:0}html:not([data-theme=light]) .g-light:after{opacity:1}}
html[data-theme=dark] .g-light:before{opacity:0}html[data-theme=dark] .g-light:after{opacity:1}
@media(prefers-reduced-motion:reduce){.g-light:before,.g-light:after{transition:none}}
'''

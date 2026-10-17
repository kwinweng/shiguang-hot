"""「光」: the page's ground colour, diffused from the lead photo. A Python port of the spec's
`Guang` (components/bundle.js in the 「光」 design system) so pages ship the finished light.

1. Shrink the photo to 16 × 24 and take its low-frequency colour: 4 × 6 cosine components
   (the same thing BlurHash stores).
2. Rebuild a 30 × 40 image from them and tone every cell in OKLab: lightness pressed into a fixed
   range, chroma multiplied then capped; blue and cyan get half the cap.
3. Ship it as a tiny PNG; the page stretches it 14% past every edge and lets the browser smooth it.
No photo (or one that cannot be read) gives the dawn sky: warm above, cool below.
"""
import base64, io, math
from functools import lru_cache
from PIL import Image, ImageOps

AMBIENT = (30, 40)
TONE = {
    'light': dict(lo=0.77, hi=0.94, gain=1.3, cap=0.085, lift=0.008),
    'dark': dict(lo=0.17, hi=0.47, gain=1.3, cap=0.13, lift=0.01),
}
COOL_HUE = 3.9
DAWN = [[0.86, 0.035, 0.07], [0.82, 0.03, 0.03], [0.74, -0.01, -0.035], [0.62, -0.015, -0.06]]
NX, NY = 4, 6


def _clamp(v):
    return min(1.0, max(0.0, v))


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _to_lab(r, g, b):
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s)


def _from_lab(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s)


def oklab(rgb):
    """OKLab of an sRGB triple in 0–1."""
    return _to_lab(*(_lin(v) for v in rgb))


def components_of_pixels(pixels, width, height, nx=NX, ny=NY):
    """Cosine components of an RGB pixel list (row by row), in linear light."""
    linear = [[_lin(c / 255) for c in px[:3]] for px in pixels]
    values = []
    for j in range(ny):
        for i in range(nx):
            total = [0.0, 0.0, 0.0]
            for y in range(height):
                down = math.cos(math.pi * j * (y + 0.5) / height)
                for x in range(width):
                    basis = math.cos(math.pi * i * (x + 0.5) / width) * down
                    px = linear[y * width + x]
                    total[0] += basis * px[0]; total[1] += basis * px[1]; total[2] += basis * px[2]
            scale = (2 if i or j else 1) / (width * height)
            values += [total[0] * scale, total[1] * scale, total[2] * scale]
    return dict(nx=nx, ny=ny, values=values)


def components_of_image(path):
    """Components of an image file, or None when it cannot be read."""
    try:
        with Image.open(path) as im:
            small = ImageOps.exif_transpose(im).convert('RGB').resize((16, 24), Image.Resampling.BICUBIC)
            return components_of_pixels(list(small.getdata()), 16, 24)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _toned(lab, tone):
    L, a, b = lab
    chroma = math.hypot(a, b)
    cool = max(0.0, math.cos(math.atan2(b, a) - COOL_HUE))
    k = min(chroma * tone['gain'] + tone['lift'], tone['cap'] * (1 - 0.5 * cool)) / chroma if chroma else 0
    rgb = _from_lab(tone['lo'] + (tone['hi'] - tone['lo']) * _clamp(L), a * k, b * k)
    return tuple(round(255 * _clamp(_gam(_clamp(v)))) for v in rgb)


def _dawn_at(u, v):
    t = min(0.999, v * 0.85 + (1 - u) * 0.15) * (len(DAWN) - 1)
    k = int(t); f = t - k
    lab = [x + (DAWN[k + 1][i] - x) * f for i, x in enumerate(DAWN[k])]
    return ((lab[0] - 0.62) / 0.24, lab[1], lab[2])


def ambient_pixels(components, scheme, width=AMBIENT[0], height=AMBIENT[1]):
    """RGB (0–255) of every cell of the light, row by row. components=None is the dawn sky."""
    base = TONE['dark' if scheme == 'dark' else 'light']
    tone = base if components else dict(base, gain=1.4 if scheme == 'dark' else 1, lift=0)
    out = []
    for y in range(height):
        for x in range(width):
            if not components:
                out.append(_toned(_dawn_at(x / (width - 1), y / (height - 1)), tone)); continue
            rgb = [0.0, 0.0, 0.0]
            for j in range(components['ny']):
                for i in range(components['nx']):
                    basis = math.cos(math.pi * i * (x + 0.5) / width) * math.cos(math.pi * j * (y + 0.5) / height)
                    at = (i + j * components['nx']) * 3
                    for c in range(3): rgb[c] += components['values'][at + c] * basis
            out.append(_toned(_to_lab(*(_clamp(c) for c in rgb)), tone))
    return out


def ambient_uri(components, scheme):
    image = Image.new('RGB', AMBIENT)
    image.putdata(ambient_pixels(components, scheme))
    buffer = io.BytesIO()
    image.save(buffer, 'PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()


@lru_cache(maxsize=512)
def ambient_uris(path=''):
    """(light, dark) data URIs of the light for one image; the dawn sky when it cannot be read.
    Cached: the same image is never toned twice in one build."""
    components = components_of_image(path) if path else None
    return ambient_uri(components, 'light'), ambient_uri(components, 'dark')


def light_css(path=''):
    """Per-page CSS: the light and dark versions of this page's light as custom properties."""
    light, dark = ambient_uris(path)
    return f':root{{--light-image:url("{light}");--dark-image:url("{dark}")}}'



@lru_cache(maxsize=1024)
def photo_like(path):
    """Reject white text screenshots and low-colour images: they make poor light and poor thumbnails."""
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((96, 96))
            pixels = list(im.getdata())
            white = sum(min(rgb) > 235 and max(rgb) - min(rgb) < 20 for rgb in pixels) / len(pixels)
            chroma = sum(math.hypot(*oklab(tuple(v / 255 for v in rgb))[1:]) for rgb in pixels) / len(pixels)
            return white <= .55 and chroma >= .02
    except (OSError, ValueError):
        return False

"""Icons, shipped once per page as an inline SVG sprite and referenced with <use>.

Two families, following the 「光」 spec:
- Function icons: Tabler Icons 3.48.0 outline (stroke 1.75 set in style.css), colour follows the
  text. Paths are copied verbatim from the @tabler/icons package. Licence (MIT) at the bottom.
- Status icons: the site's own 3D illustrations (volume, a little shadow), 58 in a lead block and
  15–22 in lists. One family; gradients are defined once in the sprite.

Generated from the package files by a script; edit the tables below, not the sprite output.
"""
import html

TABLER_VERSION = '3.48.0'
TABLER = {
 "search": [
  "M3 10a7 7 0 1 0 14 0a7 7 0 1 0 -14 0",
  "M21 21l-6 -6"
 ],
 "menu-2": [
  "M4 6l16 0",
  "M4 12l16 0",
  "M4 18l16 0"
 ],
 "x": [
  "M18 6l-12 12",
  "M6 6l12 12"
 ],
 "bookmark": [
  "M18 7v14l-6 -4l-6 4v-14a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4"
 ],
 "external-link": [
  "M12 6h-6a2 2 0 0 0 -2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-6",
  "M11 13l9 -9",
  "M15 4h5v5"
 ],
 "chevron-down": [
  "M6 9l6 6l6 -6"
 ],
 "home": [
  "M5 12l-2 0l9 -9l9 9l-2 0",
  "M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-7",
  "M9 21v-6a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v6"
 ],
 "flame": [
  "M12 10.941c2.333 -3.308 .167 -7.823 -1 -8.941c0 3.395 -2.235 5.299 -3.667 6.706c-1.43 1.408 -2.333 3.294 -2.333 5.588c0 3.704 3.134 6.706 7 6.706c3.866 0 7 -3.002 7 -6.706c0 -1.712 -1.232 -4.403 -2.333 -5.588c-2.084 3.353 -3.257 3.353 -4.667 2.235"
 ],
 "news": [
  "M16 6h3a1 1 0 0 1 1 1v11a2 2 0 0 1 -4 0v-13a1 1 0 0 0 -1 -1h-10a1 1 0 0 0 -1 1v12a3 3 0 0 0 3 3h11",
  "M8 8l4 0",
  "M8 12l4 0",
  "M8 16l4 0"
 ],
 "calendar": [
  "M4 7a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12",
  "M16 3v4",
  "M8 3v4",
  "M4 11h16",
  "M11 15h1",
  "M12 15v3"
 ],
 "message": [
  "M8 9h8",
  "M8 13h6",
  "M18 4a3 3 0 0 1 3 3v8a3 3 0 0 1 -3 3h-5l-5 3v-3h-2a3 3 0 0 1 -3 -3v-8a3 3 0 0 1 3 -3h12"
 ],
 "code": [
  "M7 8l-4 4l4 4",
  "M17 8l4 4l-4 4",
  "M14 4l-4 16"
 ],
 "world": [
  "M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0",
  "M3.6 9h16.8",
  "M3.6 15h16.8",
  "M11.5 3a17 17 0 0 0 0 18",
  "M12.5 3a17 17 0 0 1 0 18"
 ],
 "mail": [
  "M3 7a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-10",
  "M3 7l9 6l9 -6"
 ],
 "brand-telegram": [
  "M15 10l-4 4l6 6l4 -16l-18 7l4 2l2 6l3 -4"
 ],
 "sun": [
  "M8 12a4 4 0 1 0 8 0a4 4 0 1 0 -8 0",
  "M3 12h1m8 -9v1m8 8h1m-9 8v1m-6.4 -15.4l.7 .7m12.1 -.7l-.7 .7m0 11.4l.7 .7m-12.1 -.7l-.7 .7"
 ]
}
TABLER_FILLED = {
 "bookmark": [
  "M14 2a5 5 0 0 1 5 5v14a1 1 0 0 1 -1.555 .832l-5.445 -3.63l-5.444 3.63a1 1 0 0 1 -1.55 -.72l-.006 -.112v-14a5 5 0 0 1 5 -5h4z"
 ]
}

# Status icons on a 64 × 64 grid. Strokes and fills read the page tokens (--ink-2, --sun, --wash,
# --icon-light, --icon-shade), so one drawing works in light and dark.
STATUS = {
 "x": "<path d=\"M16 16h31a9 9 0 0 1 9 9v17a9 9 0 0 1-9 9H29L17 57l2-9a9 9 0 0 1-9-9V25a9 9 0 0 1 6-9Z\" fill=\"var(--icon-shade)\"/><path d=\"M16 11h29a9 9 0 0 1 9 9v17a9 9 0 0 1-9 9H27L14 53l3-10a9 9 0 0 1-9-9V20a9 9 0 0 1 8-9Z\" fill=\"url(#status-paper)\"/><path d=\"M18 23h17m-17 8h12\"/><path d=\"M43 22c3 5-3 6-1 10 2-1 3-3 3-4 6 6 3 11-2 11s-8-5-4-9c0 3 1 3 1 3-1-5 2-6 3-11Z\" fill=\"url(#status-sun)\" stroke=\"none\"/>",
 "code": "<rect x=\"9\" y=\"14\" width=\"46\" height=\"38\" rx=\"8\" fill=\"url(#status-paper)\"/><path d=\"m25 25-9 8 9 8m14-16 9 8-9 8m-4-20-6 24\" stroke=\"var(--sun)\" stroke-width=\"3\"/>",
 "home": "<circle cx=\"46\" cy=\"19\" r=\"10\" fill=\"url(#status-sun)\" stroke=\"none\"/><path d=\"M46 5V2m11 10 3-2M33 10l-2-2m27 16 3 1\" stroke=\"var(--sun)\"/><path d=\"m14 20 35 4 5 27-34 3Z\" fill=\"var(--icon-shade)\"/><path d=\"M10 19 43 16 46 49 15 53a4 4 0 0 1-4-4Z\" fill=\"url(#status-paper)\"/><path d=\"m43 16 7 7-6 1Z\" fill=\"var(--icon-light)\"/><path d=\"m16 26 21-2m-20 6 21-2\" stroke=\"var(--sun)\" stroke-width=\"3\"/><path d=\"m17 36 8-1 1 9-8 1Z\" fill=\"var(--sun)\" stroke=\"none\"/><path d=\"m30 35 8-1m-8 6 8-1m-8 6 8-1m-22 5 23-2\"/><path d=\"m46 30 2 18c0 3 4 3 5 1\" stroke=\"var(--icon-light)\"/>",
 "hot": "<path d=\"M35 8c4 15-12 17-5 28 5-2 9-8 9-13 18 18 12 32-7 32C12 55 9 37 21 24c-1 9 4 11 4 11-3-13 6-18 10-27Z\" fill=\"var(--sun)\"/><path d=\"M30 46c-5-6 1-12 4-15-1 8 8 9 5 15-2 5-7 5-9 0Z\" fill=\"url(#status-paper)\" stroke=\"none\"/>",
 "mail": "<rect x=\"11\" y=\"19\" width=\"43\" height=\"34\" rx=\"7\" fill=\"url(#status-paper)\"/><path d=\"m12 23 20 16 21-16M12 50l14-15m27 15L39 36\"/><rect x=\"37\" y=\"10\" width=\"17\" height=\"16\" rx=\"5\" fill=\"var(--sun)\" stroke=\"none\"/>",
 "world": "<circle cx=\"32\" cy=\"31\" r=\"23\" fill=\"url(#status-paper)\"/><ellipse cx=\"32\" cy=\"31\" rx=\"11\" ry=\"23\"/><path d=\"M10 31h44M14 18c11 6 25 6 36 0M14 44c11-6 25-6 36 0\"/><path d=\"m24 16 8-5 7 7-4 10-10-3-5 9-7-6 3-11Zm16 18 10 4-8 11-5-6Z\" fill=\"var(--sun)\" stroke=\"none\"/>",
 "archive": "<rect x=\"12\" y=\"14\" width=\"40\" height=\"40\" rx=\"8\" fill=\"url(#status-paper)\"/><path d=\"M12 24h40\"/><path d=\"M13 23v-3a6 6 0 0 1 6-6h26a6 6 0 0 1 6 6v3Z\" fill=\"var(--sun)\" stroke=\"none\"/><path d=\"M23 9v10m18-10v10M22 34h5m10 0h5m-20 9h5\"/><rect x=\"35\" y=\"39\" width=\"9\" height=\"9\" rx=\"3\" fill=\"var(--sun)\" stroke=\"none\"/>",
 "all": "<rect x=\"17\" y=\"12\" width=\"34\" height=\"38\" rx=\"7\" transform=\"rotate(10 34 31)\" fill=\"var(--wash)\"/><rect x=\"11\" y=\"18\" width=\"35\" height=\"36\" rx=\"7\" transform=\"rotate(-7 29 36)\" fill=\"url(#status-paper)\"/><path d=\"M19 37h19m-18 8h13\"/><rect x=\"19\" y=\"24\" width=\"19\" height=\"6\" rx=\"3\" fill=\"var(--sun)\" stroke=\"none\"/>",
 "bookmark": "<rect x=\"12\" y=\"12\" width=\"40\" height=\"42\" rx=\"8\" fill=\"url(#status-paper)\"/><path d=\"M24 8h16v26l-8-6-8 6Z\" fill=\"var(--sun)\" stroke=\"none\"/><path d=\"M21 42h22m-22 6h14\"/>"
}
STATUS_DEFS = '<linearGradient id="status-sun" x2=".6" y2="1"><stop stop-color="#ffe6a2"/><stop offset="1" stop-color="var(--sun)"/></linearGradient><linearGradient id="status-paper" x2=".7" y2="1"><stop stop-color="var(--icon-light)"/><stop offset="1" stop-color="var(--icon-shade)"/></linearGradient>'
STATUS_GROUND = '<ellipse cx="32" cy="56" rx="22" ry="4" fill="var(--wash)"/>'
STATUS_GROUP = '<g fill="none" stroke="var(--ink-2)" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'

# Names used by the templates -> Tabler names. sources.json icon keys map to the same words.
FUNCTION = {'search': 'search', 'menu': 'menu-2', 'close': 'x', 'bookmark': 'bookmark', 'external': 'external-link',
            'chevron': 'chevron-down', 'home': 'home', 'hot': 'flame', 'all': 'news', 'archive': 'calendar',
            'x': 'message', 'code': 'code', 'world': 'world', 'mail': 'mail', 'telegram': 'brand-telegram', 'sun': 'sun'}


def status_key(key):
    return key if key in STATUS else 'all'


def sprite():
    """Hidden <svg> with every symbol; emitted once at the top of <body>."""
    symbols = [f'<symbol id="t-{name}" viewBox="0 0 24 24">' + ''.join(f'<path d="{d}"/>' for d in ds) + '</symbol>'
               for name, ds in TABLER.items()]
    symbols += [f'<symbol id="tf-{name}" viewBox="0 0 24 24">' + ''.join(f'<path d="{d}"/>' for d in ds) + '</symbol>'
                for name, ds in TABLER_FILLED.items()]
    symbols += [f'<symbol id="s-{key}" viewBox="0 0 64 64">{STATUS_GROUND}{STATUS_GROUP}{shape}</g></symbol>'
                for key, shape in STATUS.items()]
    return ('<svg class="sprite" width="0" height="0" aria-hidden="true" focusable="false">'
            f'<!-- Tabler Icons {TABLER_VERSION} (MIT, Paweł Kuna) -->'
            f'<defs>{STATUS_DEFS}</defs>' + ''.join(symbols) + '</svg>')


def icon(key, cls=''):
    """A function icon (Tabler outline). A saved bookmark also carries the filled glyph, shown by CSS."""
    name = FUNCTION.get(key, 'news')
    classes = html.escape(('i ' + cls).strip(), quote=True)
    filled = f'<use class="i__fill" href="#tf-{name}"/>' if name in TABLER_FILLED else ''
    return f'<svg class="{classes}" aria-hidden="true" focusable="false"><use href="#t-{name}"/>{filled}</svg>'


def status_icon(key, size='lead'):
    """A 3D status icon: size 'lead' (58, the lead block) or 'list' (22, tiles and lists)."""
    return (f'<svg class="s-icon s-icon--{size}" data-section="{status_key(key)}" viewBox="0 0 64 64" aria-hidden="true" '
            f'focusable="false"><use href="#s-{status_key(key)}"/></svg>')


TABLER_LICENSE = 'MIT License\n\nCopyright (c) 2020-2026 Paweł Kuna\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.'

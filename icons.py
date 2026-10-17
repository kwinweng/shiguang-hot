"""One line-icon family for the whole site, shipped once per page as an inline SVG sprite.

Grid: 24 × 24, 1.75 stroke, round caps and joins (stroke settings live in style.css on `.i`).
Every icon has a *body* (its main closed shape) and optional *details*. The body is painted with
`--i-fill`, which is transparent by default; active and saved states set it, so one symbol serves
both the outline and the filled look. Pages reference symbols with <use href="#i-name">, which
keeps every card small and lets CSS colour icons through `currentColor`.
"""
import html


def _rrect(x, y, w, h, r):
    return (f'M{x + r} {y}h{w - 2 * r}a{r} {r} 0 0 1 {r} {r}v{h - 2 * r}a{r} {r} 0 0 1 -{r} {r}'
            f'h-{w - 2 * r}a{r} {r} 0 0 1 -{r} -{r}v-{h - 2 * r}a{r} {r} 0 0 1 {r} -{r}z')


def _circle(cx, cy, r):
    return f'M{cx} {cy - r}a{r} {r} 0 1 1 0 {2 * r}a{r} {r} 0 1 1 0 -{2 * r}z'


# name -> (body paths, detail paths)
GLYPHS = {
    'home': (['M4.5 10.3 12 4l7.5 6.3V19a1 1 0 0 1-1 1H15v-5a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v5H5.5a1 1 0 0 1-1-1z'], []),
    'flame': (['M12 3.5c.5 3 3.3 4.5 4.7 7.1A5.6 5.6 0 1 1 6.4 14c0-2 .9-3.6 2.2-4.8.2 1.4 1 2.4 2.1 2.8-.3-3.2.1-6 1.3-8.5z'], []),
    'list': ([_rrect(4, 4, 16, 16, 2.5)], ['M8 9h8M8 12.5h8M8 16h5']),
    'calendar': ([_rrect(4, 5.5, 16, 14.5, 2.5)], ['M4 10h16M8.5 3.5v4M15.5 3.5v4']),
    'bookmark': (['M7.5 4h9A1.5 1.5 0 0 1 18 5.5V20l-6-3.9L6 20V5.5A1.5 1.5 0 0 1 7.5 4z'], []),
    'mail': ([_rrect(3, 5.5, 18, 13, 2.5)], ['m3.6 7.6 8.4 6 8.4-6']),
    'globe': ([_circle(12, 12, 8.5)], ['M3.5 12h17M12 3.5c2.4 2.5 3.6 5.3 3.6 8.5s-1.2 6-3.6 8.5M12 3.5C9.6 6 8.4 8.8 8.4 12s1.2 6 3.6 8.5']),
    'chat': (['M6 4.5h12A2.5 2.5 0 0 1 20.5 7v8a2.5 2.5 0 0 1-2.5 2.5h-6.4L7 20.5v-3H6A2.5 2.5 0 0 1 3.5 15V7A2.5 2.5 0 0 1 6 4.5z'], ['M8 9.5h8M8 13h5']),
    'code': ([_rrect(3.5, 4.5, 17, 15, 2.5)], ['m10 9.5-2.5 2.5 2.5 2.5M14 9.5l2.5 2.5-2.5 2.5']),
    'send': (['M20.5 3.5 3.5 10.4l6.6 2.6 2.7 7.5z'], ['m20.5 3.5-10.4 9.5']),
    'search': ([_circle(10.8, 10.8, 6.3)], ['m15.5 15.5 4.5 4.5']),
    'grid': ([_rrect(4.5, 4.5, 6, 6, 1.6), _rrect(13.5, 4.5, 6, 6, 1.6), _rrect(4.5, 13.5, 6, 6, 1.6), _rrect(13.5, 13.5, 6, 6, 1.6)], []),
    'close': ([], ['M6.5 6.5l11 11M17.5 6.5l-11 11']),
    'external': ([], ['M13.5 5H19v5.5M19 5l-8 8M17 13.5V18a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h4.5']),
    'chevron': ([], ['m6.5 9.5 5.5 5.5 5.5-5.5']),
    'sun': ([_circle(12, 12, 4)], ['M12 2.8v2.1M12 19.1v2.1M2.8 12h2.1M19.1 12h2.1M5.5 5.5 7 7M17 17l1.5 1.5M5.5 18.5 7 17M17 7l1.5-1.5']),
}

# sources.json `icon` keys and page sections -> glyph names. Unknown keys fall back to list.
ALIASES = {'home': 'home', 'hot': 'flame', 'all': 'list', 'archive': 'calendar', 'mail': 'mail', 'world': 'globe',
           'x': 'chat', 'code': 'code', 'bookmark': 'bookmark', 'telegram': 'send'}


def glyph(key):
    key = ALIASES.get(key, key)
    return key if key in GLYPHS else 'list'


def sprite():
    """Hidden <svg> holding every symbol; emitted once at the top of <body>."""
    symbols = []
    for name, (bodies, details) in GLYPHS.items():
        paths = ''.join(f'<path class="i-body" style="fill:var(--i-fill,none)" d="{d}"/>' for d in bodies)
        paths += ''.join(f'<path d="{d}"/>' for d in details)
        symbols.append(f'<symbol id="i-{name}" viewBox="0 0 24 24">{paths}</symbol>')
    return ('<svg class="sprite" width="0" height="0" aria-hidden="true" focusable="false">'
            + ''.join(symbols) + '</svg>')


def icon(key, cls=''):
    name = glyph(key)
    classes = html.escape(('i ' + cls).strip(), quote=True)
    return f'<svg class="{classes}" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>'


def badge(key, size=''):
    """Section mark: a glass tile with the line icon and a small sun disc, the site's light motif."""
    modifier = f' badge--{size}' if size else ''
    return f'<span class="badge{modifier}" data-glyph="{glyph(key)}" aria-hidden="true">{icon(key)}</span>'

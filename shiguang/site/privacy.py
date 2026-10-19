"""Check source identity and local routes, rather than words in public stories."""
import json
import posixpath
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit


def verify_source_markers(path, text, forbidden):
    identities = {s['id'] for s in forbidden} | {s['name'] for s in forbidden}
    filters = identities | {s['channel'] for s in forbidden if s.get('channel')}
    private_ids = {s['id'] for s in forbidden}

    def reject(marker):
        # Report the output path and marker, never the private story itself.
        raise RuntimeError(f'公开产物存在 private 标记: {path} ({marker})')

    def local_url(value):
        parts = urlsplit(value)
        if parts.scheme or parts.netloc or not parts.path:
            return
        route = posixpath.normpath(posixpath.join(path.parent.as_posix(), unquote(parts.path)))
        if private_ids.intersection(route.split('/')):
            reject('private route')

    def structured(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('source', 'source_id', 'sourceId') and isinstance(child, str) and child in identities:
                    reject(key)
                if key == 'sources' and isinstance(child, list) and any(isinstance(v, str) and v in identities for v in child):
                    reject(key)
                if key in ('visibility', 'bookmark_scope') and child == 'private':
                    reject(key)
                if key in ('url', 'href', 'src', 'start_url', 'scope') and isinstance(child, str):
                    local_url(child)
                structured(child)
        elif isinstance(value, list):
            for child in value:
                structured(child)

    class Markup(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.json_script = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            for name in ('data-source', 'data-source-id', 'data-ch'):
                if attrs.get(name) in (filters if name == 'data-ch' else identities):
                    reject(name)
            for name in ('data-visibility', 'data-source-visibility', 'data-bookmark-scope'):
                if attrs.get(name) == 'private':
                    reject(name)
            for name in ('href', 'src', 'action', 'data-image', 'data-favorites'):
                if attrs.get(name):
                    local_url(attrs[name])
            if attrs.get('data-bookmark'):
                structured(json.loads(attrs['data-bookmark']))
            if tag == 'meta' and attrs.get('http-equiv', '').lower() == 'refresh':
                target = re.split(r'url\s*=', attrs.get('content', ''), flags=re.I)
                if len(target) == 2:
                    local_url(target[1].strip(' \t\'"'))
            if tag == 'script' and attrs.get('type') in ('application/json', 'application/ld+json'):
                self.json_script = []

        def handle_data(self, data):
            if self.json_script is not None:
                self.json_script.append(data)

        def handle_endtag(self, tag):
            if tag == 'script' and self.json_script is not None:
                structured(json.loads(''.join(self.json_script)))
                self.json_script = None

    if path.suffix in ('.json', '.webmanifest'):
        structured(json.loads(text))
    elif path.suffix in ('.html', '.svg'):
        parser = Markup()
        parser.feed(text)
        parser.close()

"""Build and locally serve the isolated /design/ playground; never deploy it."""
import argparse
import base64
import mimetypes
import re
import functools
import importlib.util
import json
import shutil
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def build(output):
    output = Path(output).resolve()
    # Disallow production destinations and accidental writes over repository sources.
    protected = {'site', 'site-private', 'public-feeds', 'private-feeds', 'web', 'design', 'shiguang', '.git', 'tools', 'tests'}
    if output == ROOT or output in ROOT.parents or any((ROOT / p).resolve() == output or (ROOT / p).resolve() in output.parents for p in protected):
        raise ValueError('Use a separate design output directory, outside production and source folders')
    data = json.loads((ROOT / 'design/samples.json').read_text())
    if data.get('example') is not True or any(i.get('fixture') is not True for i in data['items']):
        raise ValueError('Playground accepts explicit fixtures only')
    target = output / 'design'
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'design/assets', target / 'assets', dirs_exist_ok=True)
    shutil.copy(ROOT / 'web/assets/icon-512.png', target / 'assets/icon.png')
    shutil.copytree(ROOT / 'web/ui', target / 'ui', dirs_exist_ok=True)
    shutil.copy(ROOT / 'design/playground.js', target / 'playground.js')
    shutil.copy(ROOT / 'design/samples.json', target / 'samples.json')
    spec = importlib.util.spec_from_file_location('design_render', ROOT / 'design/render.py')
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    html = renderer.page(data)
    (target / 'index.html').write_text(html)
    # Public text guard applies only to authored demo assets, not source news.
    forbidden = '\u90ae\u4ef6'
    for path in target.rglob('*'):
        if path.is_file() and path.suffix in {'.html', '.js', '.css', '.json', '.svg', '.md'}:
            if forbidden in path.read_text():
                raise ValueError(f'Unexpected restricted demo text in {path.name}')
    return target


def standalone(target):
    """Portable review artifact for environments without development-port forwarding."""
    html = (target / 'index.html').read_text()
    data = json.loads((target / 'samples.json').read_text())
    for name in ['tokens.css', 'components.css']:
        html = html.replace(f'<link rel="stylesheet" href="/design/ui/{name}">', '<style>' + (target / 'ui' / name).read_text() + '</style>')
    html = html.replace('<script src="/design/ui/interactions.js" defer></script>', '')
    html = html.replace('<script src="/design/playground.js" defer></script>', '')
    objects = (target / 'assets/objects.svg').read_text()
    objects = objects.replace('<svg xmlns="http://www.w3.org/2000/svg">', '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" aria-hidden="true" style="position:absolute;overflow:hidden">', 1)
    html = html.replace('<body>', '<body>' + objects)
    html = html.replace('/design/assets/objects.svg#', '#')
    def embed(match):
        name = match.group(1)
        path = target / 'assets' / name
        if not path.is_file():
            raise ValueError('Missing standalone asset: ' + name)
        mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        return 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode()
    html = re.sub(r'/design/assets/([^"<> ]+)', embed, html)
    payload = json.dumps(data, ensure_ascii=False).replace('<', r'\u003c')
    scripts = '<script>window.__SHIGUANG_DESIGN_SAMPLES__=' + payload + ';</script>'
    scripts += '<script>' + (target / 'ui/interactions.js').read_text() + '</script>'
    scripts += '<script>' + (target / 'playground.js').read_text() + '</script>'
    result = target / 'standalone.html'
    result.write_text(html.replace('</body>', scripts + '</body>'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.design-preview')
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--standalone', action='store_true', help='Also build an offline interactive HTML file')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    target = build(args.output)
    print(f'Built isolated playground: {target}', flush=True)
    if args.standalone:
        print(f'Offline review file: {standalone(target)}', flush=True)
    if args.build_only:
        return
    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def do_GET(self):
            # Never serve the checkout, database, or a production output directory.
            if self.path.split('?', 1)[0] == '/':
                self.send_response(302)
                self.send_header('Location', '/design/')
                self.end_headers()
                return
            request_path = unquote(urlsplit(self.path).path)
            resolved = (args.output.resolve() / request_path.lstrip('/')).resolve()
            if not request_path.startswith('/design/') or not resolved.is_relative_to(target):
                self.send_error(404)
                return
            super().do_GET()

        def list_directory(self, path):
            self.send_error(404)
            return None
    server = ThreadingHTTPServer((args.host, args.port), functools.partial(Handler, directory=str(args.output.resolve())))
    print(f'Development URL: http://{args.host}:{args.port}/design/#screens', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

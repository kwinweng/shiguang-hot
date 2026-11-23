"""新版静态站构建。只用标准库。

输入（契约 rebang.items/1 与 rebang.hotsearch/1，见 docs/rebang-v1/CONTRACT.md）：
  var/rebang/in/*.json；该目录没有可用文件时改读 tests/fixtures/rebang/contract/。
输出（site-v11/）：
  index.html + 前端静态文件（拷自 web-v11/）
  data/meta.json、data/channel/<slug>/page-<n>.json（每页 30）、data/hotsearch.json（当前热搜）、
  data/hotsearch/index.json + data/hotsearch/<北京日期>.json（底栏「热搜」页按日期回看，每天最后一次成功抓取）、
  data/bloggers.json（平台/名单 + 每平台、每人最新几条）、data/blogger/<平台>/<all|h-xxxx>/page-<n>.json（「查看更多」全量分页）、
  data/id-index.json，以及 rebang.archive.build(items, out_dir) 产出的 search-index。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rebang.contract import schema

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN = ROOT / 'var' / 'rebang' / 'in'
FIXTURE_DIR = ROOT / 'tests' / 'fixtures' / 'rebang' / 'contract'
WEB_DIR = ROOT / 'web-v11'
BEIJING = timezone(timedelta(hours=8))
PAGE_SIZE = 30
BANNER_MAX = 5
BANNER_WINDOW = timedelta(hours=36)  # 「当天最新」：只从本频道最新一条往前 36 小时内挑大图
BLOGGER_PREVIEW = 10   # 博主页每个平台 / 每个人先放几条，其余进「查看更多」
HOT_ARCHIVE_DIR = ROOT / 'var' / 'rebang' / 'hotsearch-archive'
CHANNEL_DESC = {
    'current': '国内外正在发生的事',
    'world': '国际上正在发生的大事',
    'finance': '市场、公司与宏观经济',
    'tech-ai': '科技公司与人工智能动态',
    'digital': '手机、电脑和消费电子',
    'tools': '好用的开源项目和工具',
}


def parse_time(value):
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def _sort_key(item):
    return parse_time(item.get('published_at')) or datetime.min.replace(tzinfo=timezone.utc)


def is_good_image(image):
    """合格大图：有 http(s) 地址、已知宽高、短边 ≥240、宽高比 0.6–2.4（SPEC v0.10 §6.5）。"""
    if not isinstance(image, dict) or not image.get('url'):
        return False
    width, height = image.get('width'), image.get('height')
    if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        return False
    if min(width, height) < 240:
        return False
    return 0.6 <= width / height <= 2.4


def select_banners(items, limit=BANNER_MAX, window=BANNER_WINDOW):
    """items 已按时间倒序。从最新一条往前 window 内挑带合格大图的，同图不重复，不够就少。"""
    if not items:
        return []
    newest = _sort_key(items[0])
    out, seen = [], set()
    for item in items:
        if len(out) >= limit:
            break
        if newest - _sort_key(item) > window:
            break
        image = item.get('image')
        if not is_good_image(image) or image['url'] in seen:
            continue
        seen.add(image['url'])
        out.append(item)
    return out


def paginate(items, size=PAGE_SIZE):
    """返回页列表；没有条目也有第 1 页（空列表、has_more=false）。"""
    chunks = [items[i:i + size] for i in range(0, len(items), size)] or [[]]
    total = len(items)
    return [{'page': n, 'pages': len(chunks), 'total': total, 'has_more': n < len(chunks), 'items': chunk}
            for n, chunk in enumerate(chunks, 1)]


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return {'_error': f'{type(error).__name__}: {error}'}


def load_inputs(in_dir, use_fixture=False):
    """读输入目录里所有 json，按 schema 分成条目与热搜；目录没有可用条目时退回契约 fixture。"""
    report = {'dir': None, 'fallback_fixture': False, 'files': []}
    envelopes, hotsearch = [], None
    candidates = []
    if not use_fixture and in_dir and Path(in_dir).is_dir():
        candidates = sorted(Path(in_dir).glob('*.json'))
    usable = []
    for path in candidates:
        data = _read_json(path)
        if isinstance(data, dict) and data.get('schema') in (schema.ITEMS_SCHEMA, schema.HOTSEARCH_SCHEMA):
            usable.append((path, data))
        else:
            report['files'].append({'file': path.name, 'used': False,
                                    'error': data.get('_error') if isinstance(data, dict) else 'not an object'})
    if not any(d.get('schema') == schema.ITEMS_SCHEMA for _, d in usable):
        report['fallback_fixture'] = True
        usable = [(p, _read_json(p)) for p in sorted(FIXTURE_DIR.glob('*.json'))]
        report['dir'] = str(FIXTURE_DIR.relative_to(ROOT))
    else:
        report['dir'] = str(in_dir)
    for path, data in usable:
        if data.get('schema') == schema.ITEMS_SCHEMA:
            envelopes.append((path.name, data))
        elif data.get('schema') == schema.HOTSEARCH_SCHEMA:
            hotsearch = (path.name, data)
    return envelopes, hotsearch, report


def merge_items(envelopes, report):
    """校验 + 合并去重。同 id 取 fetched_at 较新的；同频道同 url 只留一条（保留 highlight 标）。"""
    by_id = {}
    for name, envelope in envelopes:
        entry = {'file': name, 'producer': envelope.get('producer'), 'generated_at': envelope.get('generated_at'),
                 'items': 0, 'dropped': 0, 'errors': []}
        report['files'].append(entry)
        for index, item in enumerate(envelope.get('items') or []):
            errors = schema.validate_item(item, f'{name}#{index}')
            if errors:
                entry['dropped'] += 1
                if len(entry['errors']) < 5:
                    entry['errors'] += errors[:2]
                continue
            entry['items'] += 1
            old = by_id.get(item['id'])
            if old is None or (parse_time(item.get('fetched_at')) or _sort_key(item)) >= \
                    (parse_time(old.get('fetched_at')) or _sort_key(old)):
                by_id[item['id']] = item
    items = sorted(by_id.values(), key=_sort_key, reverse=True)
    highlight_src = schema.load_channels()['highlights']['source_id']
    by_url, out = {}, []
    # 先放非「今日重点」条目，再让重点条目按 url 并进已有条目（只打标），找不到才单独成条。
    for item in [i for i in items if i['source_id'] != highlight_src] + [i for i in items if i['source_id'] == highlight_src]:
        key = (item['kind'], item.get('channel'), item.get('url'))
        if item.get('url') and key in by_url:
            kept = by_url[key]
            if item.get('highlight'):
                kept['highlight'] = True
                kept.setdefault('highlight_date', item.get('highlight_date'))
            continue
        if item.get('url'):
            by_url[key] = item
        out.append(item)
    return sorted(out, key=_sort_key, reverse=True)


def build_hotsearch(hotsearch, report):
    config = schema.load_hotsearch()
    enabled = sorted([p for p in config['providers'] if p.get('enabled', True)], key=lambda p: p.get('order', 99))
    payload, errors, name = None, [], None
    if hotsearch:
        name, payload = hotsearch
        errors = schema.validate_hotsearch(payload)
    report['hotsearch'] = {'file': name, 'errors': errors[:5]}
    providers_in = {p.get('id'): p for p in (payload or {}).get('providers') or []} if payload and not errors else {}
    providers = []
    for provider in enabled:
        got = providers_in.get(provider['id'])
        if got is None:
            providers.append({'id': provider['id'], 'name': provider['name'], 'status': 'empty' if not errors else 'error',
                              'fetched_at': None, 'items': [], **({'error': 'invalid_input'} if errors else {})})
        else:
            providers.append({**got, 'name': got.get('name') or provider['name']})
    return {'schema': schema.HOTSEARCH_SCHEMA, 'channel': config.get('channel', 'current'),
            'generated_at': (payload or {}).get('generated_at') if payload and not errors else None,
            'providers': providers}


def blogger_key(handle):
    """博主分页目录名：handle 里有中文、UUID 等，统一成 h-<sha1 前 10 位>；平台全部用 all。"""
    return 'h-' + hashlib.sha1(str(handle).encode('utf-8')).hexdigest()[:10]


def build_bloggers(posts, status=None, preview=BLOGGER_PREVIEW):
    """status：bloggers 生产者信封里的 platforms[]（每平台/每人 status、reason），有就并进来给前端显示真实空状态。
    返回 (bloggers.json 内容, 分页 {(平台, key): [帖子…]})。bloggers.json 只带每平台、每人最新 preview 条。"""
    status = {p.get('id'): p for p in (status or []) if isinstance(p, dict)}
    platforms, pages, keep = [], {}, set()
    for platform in schema.load_bloggers()['platforms']:
        mine = [p for p in posts if p['blogger']['platform'] == platform['id']]
        got = status.get(platform['id'], {})
        acc_status = {a.get('handle'): a for a in got.get('accounts') or [] if isinstance(a, dict)}
        pages[(platform['id'], 'all')] = mine
        keep.update(p['id'] for p in mine[:preview])
        accounts = []
        for a in platform.get('accounts', []):
            theirs = [p for p in mine if p['blogger']['handle'] == a['handle']]
            key = blogger_key(a['handle'])
            pages[(platform['id'], key)] = theirs
            keep.update(p['id'] for p in theirs[:preview])
            accounts.append({**{k: a[k] for k in ('handle', 'name', 'home') if k in a}, 'key': key, 'total': len(theirs),
                             **{k: acc_status[a['handle']][k] for k in ('status', 'count', 'error', 'reason', 'last_ok_at')
                                if k in acc_status.get(a['handle'], {})}})
        platforms.append({
            'id': platform['id'], 'name': platform['name'], 'login': bool(platform.get('login')),
            'icon': f'icons/{platform["id"]}.svg',
            'connected': bool(mine), 'count': len(mine), 'status': got.get('status') or ('ok' if mine else None),
            'reason': got.get('reason'), 'last_ok_at': got.get('last_ok_at'), 'accounts': accounts,
        })
    return ({'schema': 'rebang.site-bloggers/1', 'preview': preview, 'platforms': platforms,
             'items': [p for p in posts if p['id'] in keep]}, pages)


def build_hot_archive(current, hot_in, data, report, archive_dir, today):
    """把这次的热搜快照按北京日期入档，再写出 data/hotsearch/index.json 与每天一份。"""
    from rebang.hotsearch import archive as hot_archive
    saved = hot_archive.save_snapshot(hot_in[1], archive_dir) if (hot_in and archive_dir) else None
    days = hot_archive.load_days(archive_dir, today=today) if archive_dir else []
    index = []
    for day, payload in days:
        shown = build_hotsearch(('archive', payload), {})
        _write(data / 'hotsearch' / f'{day}.json', {**shown, 'date': day})
        index.append({'date': day, 'generated_at': shown['generated_at'],
                      'providers': [{'id': p['id'], 'name': p['name'], 'status': p['status'], 'count': len(p['items'])}
                                    for p in shown['providers']]})
    _write(data / 'hotsearch' / 'index.json', {'schema': 'rebang.hotsearch-index/1', 'timezone': 'Asia/Shanghai',
                                               'today': today, 'current_at': current.get('generated_at'),
                                               'dates': index})
    report['hotsearch_archive'] = {'saved': saved, 'days': [d for d, _ in days]}


def _resolve_local_path(local):
    """相对 path 按仓库根目录或当前目录解析，避免在别的 worktree 建站时把图丢掉。"""
    raw = Path(str((local or {}).get('path') or ''))
    rel = str((local or {}).get('rel') or '').replace('\\', '/').lstrip('/')
    candidates = [raw]
    if not raw.is_absolute():
        roots = [Path.cwd(), Path(__file__).resolve().parents[2]]
        candidates += [root / raw for root in roots]
        if rel and '..' not in rel.split('/'):
            candidates += [root / rel for root in roots]
    for cand in candidates:
        if cand.is_file():
            return cand
    return raw


def _copy_local(local, site):
    """bloggers 给的本地副本 {path, rel} → 复制进 site/media/<rel>，返回 (站内相对地址, 是否新复制)；不合法/文件不在返回 (None, 0)。"""
    if not isinstance(local, dict):
        return None, 0
    src = _resolve_local_path(local)
    rel = str(local.get('rel') or '').replace('\\', '/').lstrip('/')
    if not (src.is_file() and rel and '..' not in rel.split('/')):
        return None, 0
    rel = rel if rel.startswith('media/') else 'media/' + rel
    dest = site / rel
    if dest.exists():
        return rel, 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return rel, 1


def _localize_blogger_media(blogger, site):
    """微博：media[i].local（图）/ preview_local（视频封面）/ avatar_local（头像）→ 站内副本。
    没有本地副本的保持原地址（前端加载失败时按已有逻辑处理）。返回复制张数。"""
    if not isinstance(blogger, dict):
        return 0
    copied = 0
    for m in blogger.get('media') or []:
        for key, field in (('local', 'url'), ('preview_local', 'preview_url')):
            local = m.pop(key, None)
            rel, n = _copy_local(local, site)
            if rel:
                copied += n
                if field == 'url':
                    m['orig_url'] = m.get('url')
                m[field] = rel
                for dim in ('width', 'height'):
                    if field == 'url' and isinstance(local.get(dim), int) and local[dim] > 0:
                        m[dim] = local[dim]
    rel, n = _copy_local(blogger.pop('avatar_local', None), site)
    if rel:
        copied += n
        blogger['avatar'] = rel
    return copied


def localize_images(items, site):
    """ingest 给的本地图（image_local{path, rel?, width, height}）复制进 site/media/，改写成站内相对地址 image。
    已有网络图 image.url 的不动；文件不在就当无图（不编图）。返回复制张数。"""
    copied = 0
    for item in items:
        for block in item.get('blocks') or []:
            if block.get('type') != 'img':
                continue
            local = block.pop('local', None)
            src = _resolve_local_path(local)
            rel = str((local or {}).get('rel') or '').replace('\\', '/').lstrip('/')
            if local and src.is_file() and rel and '..' not in rel.split('/'):
                rel = rel if rel.startswith('media/') else 'media/' + rel
                dest = site / rel
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    copied += 1
                block['src'] = rel
                for dim in ('width', 'height'):
                    if isinstance(local.get(dim), int) and local[dim] > 0:
                        block[dim] = local[dim]
            elif 'mmbiz.qpic.cn' in str(block.get('src')):
                block['missing'] = True     # 公众号图床拒绝外站引用，没存下本地副本就如实说没有
        copied += _localize_blogger_media(item.get('blogger'), site)
        local = item.pop('image_local', None)
        if item.get('image') or not isinstance(local, dict):
            continue
        src = _resolve_local_path(local)
        if not src.is_file():
            continue
        rel = str(local.get('rel') or '').replace('\\', '/').lstrip('/')
        if not rel or '..' in rel.split('/'):
            rel = f'media/x/{hashlib.sha1(str(src).encode()).hexdigest()[:16]}{src.suffix.lower()}'
        if not rel.startswith('media/'):
            rel = 'media/' + rel
        dest = site / rel
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1
        image = {'url': rel}
        for dim in ('width', 'height'):
            if isinstance(local.get(dim), int) and local[dim] > 0:
                image[dim] = local[dim]
        if local.get('alt'):
            image['alt'] = str(local['alt'])
        item['image'] = image
    return copied


def source_status(envelopes):
    """生产者信封里的 sources[]（id/name/channel/status/error…）→ 频道 slug → 取不到的来源列表。"""
    out = {}
    for _, envelope in envelopes:
        for source in envelope.get('sources') or []:
            if not isinstance(source, dict) or not source.get('channel'):
                continue
            if source.get('status') in ('ok', 'empty', None):
                continue
            out.setdefault(source['channel'], []).append(
                {k: source[k] for k in ('id', 'name', 'status', 'error', 'fetched_at') if k in source})
    return out


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def _inject_features(site):
    """web-v11/features/*.js（history 分支）存在就按文件名顺序挂进 index.html，不存在就什么也不加。"""
    index = site / 'index.html'
    if not index.exists():
        return
    names = sorted(p.name for p in (site / 'features').glob('*.js')) if (site / 'features').is_dir() else []
    tags = '\n'.join(f'<script src="features/{n}"></script>' for n in names)
    index.write_text(index.read_text(encoding='utf-8').replace('<!--FEATURES-->', tags), encoding='utf-8')


def _run_archive(items, out_dir, report):
    try:
        import importlib
        archive = importlib.import_module('rebang.archive')  # history 分支提供
    except ImportError:
        report['archive'] = 'skipped: rebang.archive 未合入'
        return
    builder = getattr(archive, 'build', None)
    if not callable(builder):
        report['archive'] = 'skipped: rebang.archive.build 不存在'
        return
    builder(items, out_dir)
    report['archive'] = 'ok'


def build(out, in_dir=DEFAULT_IN, *, now=None, use_fixture=False, note=None, web_dir=WEB_DIR, public_base=None,
          hot_archive_dir=HOT_ARCHIVE_DIR):
    """构建到 out（先写临时目录再替换）。返回构建报告 dict。"""
    out = Path(out).resolve()
    now = (now or datetime.now(timezone.utc)).astimezone(BEIJING)
    if out.exists() and not (out / 'data' / 'meta.json').exists() and any(out.iterdir()):
        raise SystemExit(f'拒绝覆盖：{out} 已存在且不是 rebang.site 的构建产物')
    envelopes, hotsearch, report = load_inputs(in_dir, use_fixture)
    items = merge_items(envelopes, report)
    tmp = out.parent / f'{out.name}.tmp-{os.getpid()}'
    if tmp.exists():
        shutil.rmtree(tmp)
    if web_dir and Path(web_dir).is_dir():
        shutil.copytree(web_dir, tmp, ignore=shutil.ignore_patterns('*.test.js', '__pycache__'))
    else:
        tmp.mkdir(parents=True)
    data = tmp / 'data'
    report['media_copied'] = localize_images(items, tmp)
    bad_sources = source_status(envelopes)
    news = [i for i in items if i['kind'] == 'news']
    posts = [i for i in items if i['kind'] == 'post']
    channels_meta = []
    id_index = {}  # 条目 id → 所在数据文件；给 #/item/<id> 深链（8:30 私聊稿）直接打开详情用
    for channel in sorted(schema.load_channels()['channels'], key=lambda c: c['order']):
        mine = [i for i in news if i['channel'] == channel['slug']]
        banner = select_banners(mine)
        banner_ids = {i['id'] for i in banner}
        feed = [i for i in mine if i['id'] not in banner_ids]
        pages = paginate(feed)
        for item in banner:
            id_index[item['id']] = 'meta.json'
        for page in pages:
            for item in page['items']:
                id_index[item['id']] = f'channel/{channel["slug"]}/page-{page["page"]}.json'
            _write(data / 'channel' / channel['slug'] / f'page-{page["page"]}.json',
                   {'schema': 'rebang.page/1', 'channel': channel['slug'], **page})
        channels_meta.append({
            'slug': channel['slug'], 'name': channel['name'], 'order': channel['order'],
            'desc': CHANNEL_DESC.get(channel['slug'], ''),
            'sources': [s['name'] for s in channel['sources']],
            'unavailable': bad_sources.get(channel['slug'], []),
            'total': len(mine), 'feed_total': len(feed), 'pages': len(pages), 'banner': banner,
        })
    current_hot = build_hotsearch(hotsearch, report)
    _write(data / 'hotsearch.json', current_hot)
    build_hot_archive(current_hot, hotsearch if not report['hotsearch']['errors'] else None, data, report,
                      None if use_fixture else hot_archive_dir, now.date().isoformat())
    blogger_status = [p for _, e in envelopes for p in (e.get('platforms') or [])]
    bloggers, blogger_pages = build_bloggers(posts, blogger_status)
    for (platform_id, key), mine in blogger_pages.items():
        for page in paginate(mine):
            rel = f'blogger/{platform_id}/{key}/page-{page["page"]}.json'
            if key == 'all':
                for item in page['items']:
                    id_index.setdefault(item['id'], rel)
            _write(data / rel, {'schema': 'rebang.page/1', 'platform': platform_id, 'key': key, **page})
    _write(data / 'bloggers.json', bloggers)
    for item in bloggers['items']:
        id_index[item['id']] = 'bloggers.json'
    _write(data / 'id-index.json', id_index)
    _inject_features(tmp)
    input_times = [parse_time(e.get('generated_at')) for _, e in envelopes] + \
                  ([parse_time(hotsearch[1].get('generated_at'))] if hotsearch else [])
    input_times = [t for t in input_times if t]
    meta = {
        'schema': 'rebang.site-meta/1',
        'built_at': now.isoformat(timespec='seconds'),
        'data_at': max(input_times).astimezone(BEIJING).isoformat(timespec='seconds') if input_times else None,
        'today': now.date().isoformat(),
        'page_size': PAGE_SIZE,
        'note': note,
        'public_base': public_base,
        'fixture': report['fallback_fixture'],
        'counts': {'news': len(news), 'posts': len(posts)},
        'channels': channels_meta,
    }
    _write(data / 'meta.json', meta)
    _run_archive(items, tmp, report)
    if out.exists():
        shutil.rmtree(out)
    tmp.rename(out)
    report.update({'out': str(out), 'news': len(news), 'posts': len(posts),
                   'channels': {c['slug']: {'total': c['total'], 'banner': len(c['banner']), 'pages': c['pages']}
                                for c in channels_meta}})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python3 -m rebang.site', description='构建拾光热榜 v1 新版静态站')
    parser.add_argument('--out', default=str(ROOT / 'site-v11'))
    parser.add_argument('--in', dest='in_dir', default=str(DEFAULT_IN))
    parser.add_argument('--fixture', action='store_true', help='强制用契约 fixture')
    parser.add_argument('--note', default=None, help='页面顶部说明条（预览用）')
    parser.add_argument('--public-base', default=None, help='公开站地址（写进 meta.json，私聊稿深链用）')
    parser.add_argument('--now', default=None, help='构建时间（ISO，测试用）')
    parser.add_argument('--hot-archive', default=str(HOT_ARCHIVE_DIR), help='热搜按日归档目录（每天留最后一次成功抓取）')
    args = parser.parse_args(argv)
    now = parse_time(args.now) if args.now else None
    report = build(args.out, args.in_dir, now=now, use_fixture=args.fixture, note=args.note,
                   public_base=args.public_base, hot_archive_dir=args.hot_archive)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())

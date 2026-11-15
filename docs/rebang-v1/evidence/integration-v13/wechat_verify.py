"""v13 第 6 条核对：公众号文章正文块 vs 原文（Wechat2RSS 订阅源里的正文 HTML，是 mp.weixin.qq.com 原文的副本）。

mp.weixin.qq.com 原文页从这台机器抓不到（反爬返回空页），所以拿订阅源全文做「原文」。核对方法独立于 html_blocks：
  - 图片：原文里所有 <img>（去掉 Wechat2RSS 插的封面、1px 追踪图），按出现顺序的原图地址 == 正文块里图片顺序；
  - 文字：原文按块切开的每段文字，在正文块文字里按顺序都能找到（不漏、不乱序），且正文块里没有重复段；
  - 站点：每张图都已存到站点 media/ 下（不外链公众号图床）。
用法：python3 docs/rebang-v1/evidence/integration-v13/wechat_verify.py [bloggers.json] [站点目录]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from rebang.bloggers.common import unwrap_image_url  # noqa: E402
from rebang.bloggers.feed import parse_feed  # noqa: E402

FEED = 'https://wechat2rss.xlab.app/feed/a1cd365aa14ed7d64cabfc8aa086da40ecaba34d.xml'
OUT = Path(__file__).resolve().parent / 'wechat-verify.json'
norm = lambda s: re.sub(r'\s+', '', s or '')


HEAD_RE = re.compile(r'^(原创|\d{4}-\d{2}-\d{2}.*)$')
TAIL = ('跳转微信打开', '阅读原文')


def source_parts(html):
    """原文按文档顺序拆成图片列表和文字段；去掉 Wechat2RSS 加的东西：开头「原创/作者/日期/属地」那一行、
    紧跟其后的封面图（正文里第一段文字之前、没有 data-w 的那张）、结尾「跳转微信打开」。"""
    soup = BeautifulSoup(html, 'html.parser')
    for bad in soup.select('script, style, .mp-common-profile, mp-common-profile'):
        bad.decompose()
    first_p = soup.find('p')
    header = []
    if first_p is not None and len(first_p.get_text(' ', strip=True)) <= 60 and (
            first_p.get_text(strip=True).startswith('原创') or re.search(r'\d{4}-\d{2}-\d{2}', first_p.get_text())):
        header = [first_p.get_text(' ', strip=True)]
        first_p.decompose()
    imgs, texts, seen_text, cover = [], [], False, None
    for node in soup.descendants:
        if getattr(node, 'name', None) == 'img':
            src = unwrap_image_url(node.get('data-src') or node.get('src') or '')
            if not src or node.get('width') in ('1', '1px') or src.startswith('data:'):
                continue
            if not seen_text and not imgs and not node.get('data-w') and 'rich_pages' not in (node.get('class') or []):
                cover = src
                continue
            imgs.append(src)
        elif isinstance(node, str) and norm(node) and node.parent.name not in ('script', 'style'):
            seen_text = True
    allparts = [t for t in (norm(x) for x in soup.get_text('\n').split('\n')) if t and t not in TAIL]
    texts = [t for t in allparts if len(t) >= 2]
    return imgs, texts, header, cover, ''.join(allparts)


def main():
    bl = Path(sys.argv[1] if len(sys.argv) > 1 else 'var/rebang/in/bloggers.json')
    site = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    items = [i for i in json.loads(bl.read_text(encoding='utf-8'))['items'] if (i.get('blogger') or {}).get('platform') == 'wechat']
    body = subprocess.run(['curl', '-sSL', '--max-time', '40', FEED], capture_output=True, check=True).stdout
    entries = {e['url']: e for e in parse_feed(body)}
    site_items = {}
    if site:
        n = 1
        while (site / f'data/blogger/wechat/all/page-{n}.json').is_file():
            pg = json.loads((site / f'data/blogger/wechat/all/page-{n}.json').read_text(encoding='utf-8'))
            site_items.update({i['id']: i for i in pg['items']})
            if not pg.get('has_more'):
                break
            n += 1
    rows = []
    for it in items:
        e = entries.get(it['url'])
        if not e:
            rows.append({'id': it['id'], 'title': it['title'], 'ok': None, 'note': '订阅源里已没有这篇（只保留最近几篇），无法对照'})
            continue
        src_imgs, src_texts, header, cover, src_seq = source_parts(e['html'])
        blocks = it.get('blocks') or []
        blk_imgs = [b['src'] for b in blocks if b['type'] == 'img']
        seq = norm(''.join(b.get('text', '') or ''.join(b.get('items', [])) for b in blocks if b['type'] != 'img'))
        pos, missing = 0, []
        for t in src_texts:
            k = seq.find(t, pos)
            if k < 0:
                if seq.find(t) < 0:
                    missing.append(t[:30])
                continue
            pos = k + len(t)
        pos, in_order = 0, 0
        for t in src_texts:
            k = seq.find(t, pos)
            if k >= 0:
                in_order += 1; pos = k + len(t)
        found = sum(1 for t in src_texts if seq.find(t) >= 0)
        texts_b = [norm(b['text']) for b in blocks if b['type'] in ('p', 'h', 'quote') and len(norm(b['text'])) > 20]
        dup_text = len(texts_b) - len(set(texts_b))
        extra = [norm(b.get('text') or ''.join(b.get('items', [])))[:30] for b in blocks if b['type'] != 'img' and b['type'] != 'hr'
                 and norm(b.get('text') or ''.join(b.get('items', []))) not in src_seq]
        s_it = site_items.get(it['id'])
        site_imgs = [b for b in (s_it or {}).get('blocks', []) if b['type'] == 'img']
        local_ok = None if not site else all(b['src'].startswith('media/wechat/') and (site / b['src']).is_file() for b in site_imgs) and len(site_imgs) == len(blk_imgs)
        row = {'id': it['id'], 'title': it['title'], 'source_images': len(src_imgs), 'block_images': len(blk_imgs),
               'images_same_order': src_imgs == blk_imgs, 'dup_images': len(blk_imgs) - len(set(blk_imgs)),
               'source_text_parts': len(src_texts), 'text_found': found, 'text_in_order': in_order, 'text_missing': missing[:5],
               'dup_paragraphs': dup_text, 'block_text_not_in_source': extra[:5], 'site_images_local': local_ok,
               'removed_wechat2rss_header': header, 'removed_wechat2rss_cover': bool(cover)}
        row['ok'] = row['images_same_order'] and not row['dup_images'] and found == len(src_texts) and in_order == found and not dup_text and not extra and local_ok is not False
        rows.append(row)
    res = {'feed': FEED, 'note': 'mp.weixin.qq.com 原文页从本机抓取被反爬拦（空页），这里对照的是 Wechat2RSS 订阅源里的全文副本。',
           'articles': len(rows), 'ok': sum(1 for r in rows if r['ok']), 'rows': rows}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    for r in rows:
        print('OK  ' if r['ok'] else 'BAD ', r['title'][:30], {k: r[k] for k in r if k not in ('id', 'title', 'ok')})
    print(f"{res['ok']}/{res['articles']} articles match")
    return 0 if res['ok'] == res['articles'] else 1


if __name__ == '__main__':
    sys.exit(main())

"""Telegram: fetch the public t.me pages of each channel into tg.db, then read messages back.

Images are cached as webp under media/<channel>/ for 14 days (by message time); tg.db keeps the
text for good. With fetch=False (NO_FETCH=1) the database is opened read-only and nothing is fetched.
"""
import io, json, os, re, sqlite3, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image, ImageOps
from shiguang.config import ROOT
from shiguang.model import BEIJING

D = str(ROOT)
MEDIA = os.path.join(D, 'media')
MEDIA_DAYS = 14
GAP_PAGES = 20


def open_db(fetch):
    """tg.db, migrated to the current schema when writable. Returns (db, images_migrated)."""
    os.makedirs(MEDIA, exist_ok=True)
    db = sqlite3.connect(os.path.join(D, 'tg.db')) if fetch else sqlite3.connect('file:' + os.path.join(D, 'tg.db') + '?mode=ro&immutable=1', uri=True)
    if not fetch: db.execute('pragma query_only=on')
    cols = [r[1] for r in db.execute("pragma table_info(msg)")]
    if fetch and cols and "html" not in cols: db.execute("alter table msg add column html text")  # 保留旧库消息，兼容缺少 HTML 的历史结构
    if fetch: db.execute("create table if not exists msg(ch text,id int,ts text,text text,links text,html text,primary key(ch,id))")
    images_migrated = "images" not in [r[1] for r in db.execute("pragma table_info(msg)")]
    if images_migrated and fetch:
        db.execute("alter table msg add column images text not null default '[]'")
    if fetch: db.execute("create table if not exists status(ch text primary key,ok int,err text,at text)")
    if fetch: db.execute("create table if not exists gap(ch text,before int,newest int,at text,primary key(ch,before))")
    return db, images_migrated


def extract(tx):
    """根因修复：旧版 get_text("\\n") 会在每个内联元素(#话题链接/加粗/emoji)两侧插换行。
    这里只把 <br> 变成换行，其余内联元素无缝拼接。"""
    for br in tx.find_all("br"): br.replace_with("\n")
    t = tx.get_text("").replace("\xa0", " ")
    t = re.sub(r"[ \t]+\n", "\n", t); t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


class FetchError(Exception):
    pass


def get(u):
    result = subprocess.run(["curl", "-sL", "-m", "25", "-A", "Mozilla/5.0", u], capture_output=True, text=True)
    if result.returncode:
        raise FetchError(f"curl exit {result.returncode}: {result.stderr.strip()[:150]}")
    if not result.stdout.strip(): raise FetchError("页面为空")
    if not re.search(r'tgme_(?:channel|widget)', result.stdout): raise FetchError("非 Telegram 频道页面")
    return result.stdout


def image_urls(m):
    urls = []
    for node in m.select('.tgme_widget_message_photo_wrap, .tgme_widget_message_video_thumb, .link_preview_image'):
        match = re.search(r"background-image\s*:\s*url\(\s*(['\"]?)(.*?)\1\s*\)", node.get('style', ''), re.I)
        url = match.group(2) if match else node.get('src')
        if url:
            if url.startswith('//'): url = 'https:' + url
            if url.startswith('https://') and url not in urls: urls.append(url)
    return urls


def download_images(c, i, urls):
    def save(item):
        j, url = item; rel = f"media/{c}/{i}_{j}.webp"; path = os.path.join(D, rel)
        try:
            if not os.path.isfile(path):
                data = subprocess.run(['curl', '--fail', '-sL', '--max-time', '25', '-A', 'Mozilla/5.0', url], capture_output=True, check=True).stdout
                with Image.open(io.BytesIO(data)) as source:
                    image = ImageOps.exif_transpose(source).convert('RGB')
                    image.thumbnail((1200, 1200))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    image.save(path + '.tmp', format='WEBP', quality=78)
                    os.replace(path + '.tmp', path)
            return rel
        except Exception as ex:
            print(f'image {c}/{i}/{j}: {ex}', file=sys.stderr)
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        return [path for path in pool.map(save, enumerate(urls, 1)) if path]


def channel_text(c, t):
    if c != 'freechinese': return t
    if len(t) < 160 and re.search(r'@onelovecn\s*$', t, re.I): return None
    # Only explicit standalone promotion labels; news about advertising remains intact.
    if re.match(r'^\s*(?:【(?:广告|推广|赞助)】|\[(?:广告|推广|赞助)\])', t): return None
    # A terminal channel handle is attribution/traffic text, never remove inline quotations.
    return re.sub(r'(?:\n[ \t]*)+@(?:freechinese|onelovecn)\s*$', '', t, flags=re.I).strip()


def fetch(db, channels, now, images_migrated):
    """Page back through each channel until the newest stored message (or 72 hours on first run)."""
    media_floor = now - timedelta(days=MEDIA_DAYS)
    for c in channels:
        last = db.execute("select max(id) from msg where ch=?", (c,)).fetchone()[0]
        floor = now - timedelta(hours=72) if last is None else None
        # Revisit two weeks once after schema migration to populate images on existing messages.
        backfill = images_migrated or any(
            not os.path.isfile(os.path.join(D, path))
            for (stored,) in db.execute("select images from msg where ch=? and ts>=?", (c, media_floor.isoformat()))
            for path in json.loads(stored))
        before = None; n = 0; err = None; seen = set()
        # Only retry gaps from prior runs. newest is the stored id bound before the failed run;
        # at preserves that run's 72-hour floor when no stored id existed.
        gaps = db.execute("select before,newest,at from gap where ch=? order by before desc", (c,)).fetchall()

        def store_page(ms, last, floor, backfill, seen):
            nonlocal n
            ids = []; stop = False
            for m in ms:
                i = int(m["data-post"].split("/")[1]); ids.append(i)
                if i in seen: continue
                seen.add(i)
                tm = m.select_one("time[datetime]")
                if not tm: continue
                dt = datetime.fromisoformat(tm["datetime"]).astimezone(BEIJING)
                if (floor and dt < floor) or (not floor and backfill and dt < media_floor): stop = True; continue
                if last is not None and i <= last and not backfill: stop = True; continue
                tx = m.select_one(".tgme_widget_message_text")
                t = channel_text(c, extract(tx) if tx else '')
                if t is None: continue
                urls = image_urls(m)
                if not t and not urls: continue
                images = download_images(c, i, urls) if dt >= media_floor else []
                links = [a["href"] for a in tx.select("a[href]")] if tx else []
                cur = db.execute("insert or ignore into msg(ch,id,ts,text,links,html,images) values(?,?,?,?,?,?,?)", (c, i, dt.isoformat(), t or '[图片]', json.dumps(links), str(tx) if tx else '', json.dumps(images)))
                n += cur.rowcount
                if images: db.execute("update msg set images=? where ch=? and id=?", (json.dumps(images), c, i))
            return ids, stop

        try:
            for _ in range(200):
                s = BeautifulSoup(get(f"https://t.me/s/{c}" + (f"?before={before}" if before else "")), "html.parser")
                ms = s.select("div.tgme_widget_message[data-post]")
                if not ms: err = "页面无消息/打不开" if n == 0 and before is None else None; break
                ids, stop = store_page(ms, last, floor, backfill, seen)
                if stop or not ids: break
                next_before = min(ids)
                if before is not None and next_before >= before: break
                before = next_before
            else: err = "达到翻页上限，历史回填未完成"
        except Exception as ex:
            err = "页面无消息/打不开" if before is None else (str(ex)[:200] or type(ex).__name__)
            if before is not None:
                db.execute("insert or ignore into gap values(?,?,?,?)", (c, before, last, now.isoformat()))
                print(c, "gap", before, "bound", last, err, file=sys.stderr)
        for gap_before, gap_last, gap_at in gaps:
            cursor = gap_before; filled = False; gap_seen = set()
            gap_floor = datetime.fromisoformat(gap_at) - timedelta(hours=72) if gap_last is None else None
            try:
                for _ in range(GAP_PAGES):
                    s = BeautifulSoup(get(f"https://t.me/s/{c}?before={cursor}"), "html.parser")
                    ms = s.select("div.tgme_widget_message[data-post]")
                    if not ms: filled = True; break
                    ids, stop = store_page(ms, gap_last, gap_floor, False, gap_seen)
                    if stop or not ids: filled = True; break
                    next_before = min(ids)
                    if next_before >= cursor: raise FetchError("缺口翻页未前进")
                    cursor = next_before
                if not filled: err = err or "达到缺口回填上限，历史回填未完成"
            except Exception as ex: err = err or str(ex)[:200] or type(ex).__name__
            if filled:
                db.execute("delete from gap where ch=? and before=?", (c, gap_before))
            else:
                db.execute("update or ignore gap set before=? where ch=? and before=?", (cursor, c, gap_before))
                print(c, "gap", cursor, "bound", gap_last, err, file=sys.stderr)
        db.execute("insert or replace into status values(?,?,?,?)", (c, 0 if err else 1, err, now.isoformat()))
        print(c, "new", n, err or "", file=sys.stderr)


def expire_media(db, now):
    """Expire by message timestamp, not cache-restored filesystem modification time."""
    media_floor = now - timedelta(days=MEDIA_DAYS)
    for c, i, ts, images in db.execute("select ch,id,ts,images from msg where images!='[]'").fetchall():
        if datetime.fromisoformat(ts) < media_floor:
            db.execute("update msg set images='[]' where ch=? and id=?", (c, i))
    if db.execute("select 1 from sqlite_master where type='table' and name='entry'").fetchone():
        for source, i, ts, images in db.execute("select source,id,ts,images from entry where images!='[]'").fetchall():
            if datetime.fromisoformat(ts) < media_floor:
                db.execute("update entry set images='[]' where source=? and id=?", (source, i))
        retained = {path for (images,) in db.execute("select images from msg union all select images from entry") for path in json.loads(images)}
    else:
        retained = {path for (images,) in db.execute("select images from msg") for path in json.loads(images)}
    for path in Path(MEDIA).rglob('*'):
        if path.is_file() and path.relative_to(D).as_posix() not in retained: path.unlink()


def messages(db):
    """Every stored message, newest first: (channel, id, ts, text, html, image paths that exist)."""
    for ch, i, ts, t, raw, images in db.execute('select ch,id,ts,text,html,images from msg order by ts desc'):
        yield ch, i, ts, t, raw, [p for p in json.loads(images) if os.path.isfile(os.path.join(D, p))]

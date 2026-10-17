#!/usr/bin/env python3
"""按 sources.json 增量抓取 Telegram，聚合 inbox，生成静态站点 site/。"""
import subprocess,sqlite3,json,re,html,os,sys,collections,shutil,io
from pathlib import Path
from PIL import Image,ImageOps
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from bs4 import BeautifulSoup
BJ=timezone(timedelta(hours=8)); D=os.path.dirname(os.path.abspath(__file__))
from feeds import config, private_mode
CONFIG=config()
CH={s['channel']:s['name'] for s in CONFIG['sources'] if s['type']=='telegram' and (private_mode() or s['visibility']=='public')}
NO_FETCH=os.getenv('NO_FETCH')=='1'
db=sqlite3.connect('file:'+os.path.join(D,'tg.db')+'?mode=ro&immutable=1',uri=True) if NO_FETCH else sqlite3.connect(os.path.join(D,"tg.db"))
if NO_FETCH: db.execute('pragma query_only=on')
cols=[r[1] for r in db.execute("pragma table_info(msg)")]
if not NO_FETCH and cols and "html" not in cols: db.execute("alter table msg add column html text")  # 保留旧库消息，兼容缺少 HTML 的历史结构
if not NO_FETCH: db.execute("create table if not exists msg(ch text,id int,ts text,text text,links text,html text,primary key(ch,id))")
images_migrated="images" not in [r[1] for r in db.execute("pragma table_info(msg)")]
if images_migrated and not NO_FETCH:
  db.execute("alter table msg add column images text not null default '[]'")
if not NO_FETCH: db.execute("create table if not exists status(ch text primary key,ok int,err text,at text)")
now=datetime.now(BJ)
def extract(tx):
  """根因修复：旧版 get_text("\\n") 会在每个内联元素(#话题链接/加粗/emoji)两侧插换行。
  这里只把 <br> 变成换行，其余内联元素无缝拼接。"""
  for br in tx.find_all("br"): br.replace_with("\n")
  t=tx.get_text("").replace("\xa0"," ")
  t=re.sub(r"[ \t]+\n","\n",t); t=re.sub(r"\n{3,}","\n\n",t)
  return t.strip()
def get(u):
  return subprocess.run(["curl","-sL","-m","25","-A","Mozilla/5.0",u],capture_output=True,text=True).stdout
MEDIA=os.path.join(D,"media")
os.makedirs(MEDIA,exist_ok=True)
media_floor=now-timedelta(days=14)
def image_urls(m):
  urls=[]
  for node in m.select('.tgme_widget_message_photo_wrap, .tgme_widget_message_video_thumb, .link_preview_image'):
    match=re.search(r"background-image\s*:\s*url\(\s*(['\"]?)(.*?)\1\s*\)",node.get('style',''),re.I)
    url=match.group(2) if match else node.get('src')
    if url:
      if url.startswith('//'): url='https:'+url
      if url.startswith('https://') and url not in urls: urls.append(url)
  return urls
def download_images(c,i,urls):
  def save(item):
    j,url=item; rel=f"media/{c}/{i}_{j}.webp"; path=os.path.join(D,rel)
    try:
      if not os.path.isfile(path):
        data=subprocess.run(['curl','--fail','-sL','--max-time','25','-A','Mozilla/5.0',url],capture_output=True,check=True).stdout
        with Image.open(io.BytesIO(data)) as source:
          image=ImageOps.exif_transpose(source).convert('RGB')
          image.thumbnail((1200,1200))
          os.makedirs(os.path.dirname(path),exist_ok=True)
          image.save(path+'.tmp',format='WEBP',quality=78)
          os.replace(path+'.tmp',path)
      return rel
    except Exception as ex:
      print(f'image {c}/{i}/{j}: {ex}',file=sys.stderr)
      return None
  with ThreadPoolExecutor(max_workers=6) as pool:
    return [path for path in pool.map(save,enumerate(urls,1)) if path]
def channel_text(c,t):
  if c!='freechinese': return t
  if len(t)<160 and re.search(r'@onelovecn\s*$',t,re.I): return None
  # Only explicit standalone promotion labels; news about advertising remains intact.
  if re.match(r'^\s*(?:【(?:广告|推广|赞助)】|\[(?:广告|推广|赞助)\])',t): return None
  # A terminal channel handle is attribution/traffic text, never remove inline quotations.
  return re.sub(r'(?:\n[ \t]*)+@(?:freechinese|onelovecn)\s*$', '', t, flags=re.I).strip()
for c in ([] if NO_FETCH else CH):
  last=db.execute("select max(id) from msg where ch=?",(c,)).fetchone()[0]
  floor=now-timedelta(hours=72) if last is None else None
  # Revisit two weeks once after schema migration to populate images on existing messages.
  backfill=images_migrated or any(
    not os.path.isfile(os.path.join(D,path))
    for (stored,) in db.execute("select images from msg where ch=? and ts>=?",(c,media_floor.isoformat()))
    for path in json.loads(stored))
  before=None;n=0;err=None;seen=set()
  try:
    for _ in range(200):
      s=BeautifulSoup(get(f"https://t.me/s/{c}"+(f"?before={before}" if before else "")),"html.parser")
      ms=s.select("div.tgme_widget_message[data-post]")
      if not ms: err="页面无消息/打不开" if n==0 and before is None else None; break
      ids=[];stop=False
      for m in ms:
        i=int(m["data-post"].split("/")[1]);ids.append(i)
        if i in seen: continue
        seen.add(i)
        tm=m.select_one("time[datetime]")
        if not tm: continue
        dt=datetime.fromisoformat(tm["datetime"]).astimezone(BJ)
        if (floor and dt<floor) or (not floor and backfill and dt<media_floor): stop=True;continue
        if last is not None and i<=last and not backfill: stop=True;continue
        tx=m.select_one(".tgme_widget_message_text")
        t=channel_text(c,extract(tx) if tx else '')
        if t is None: continue
        urls=image_urls(m)
        if not t and not urls: continue
        images=download_images(c,i,urls) if dt>=media_floor else []
        links=[a["href"] for a in tx.select("a[href]")] if tx else []
        cur=db.execute("insert or ignore into msg(ch,id,ts,text,links,html,images) values(?,?,?,?,?,?,?)",(c,i,dt.isoformat(),t or '[图片]',json.dumps(links),str(tx) if tx else '',json.dumps(images)))
        n+=cur.rowcount
        if images: db.execute("update msg set images=? where ch=? and id=?",(json.dumps(images),c,i))
      if stop or not ids: break
      next_before=min(ids)
      if before is not None and next_before>=before: break
      before=next_before
    else: err="达到翻页上限，历史回填未完成"
  except Exception as ex: err=str(ex)[:200]
  db.execute("insert or replace into status values(?,?,?,?)",(c,0 if err else 1,err,now.isoformat()))
  print(c,"new",n,err or "",file=sys.stderr)
# Expire by message timestamp, not cache-restored filesystem modification time.
for c,i,ts,images in ([] if NO_FETCH else db.execute("select ch,id,ts,images from msg where images!='[]'").fetchall()):
  if datetime.fromisoformat(ts)<media_floor:
    db.execute("update msg set images='[]' where ch=? and id=?",(c,i))
retained={path for (images,) in db.execute("select images from msg") for path in json.loads(images)}
for path in ([] if NO_FETCH else Path(MEDIA).rglob('*')):
  if path.is_file() and path.relative_to(D).as_posix() not in retained: path.unlink()
db.commit()
# ---------- build ----------
from textclean import clean, headline
CATS=CONFIG['categories']
KW=['美联储','降息','关税','停火','战争','GDP','财报','AI','苹果','英伟达','OpenAI','特朗普','央行','芯片']
rows=[]
for ch,i,ts,t,raw,images in db.execute('select ch,id,ts,text,html,images from msg order by ts desc'):
  if ch not in CH: continue
  t=clean(t)
  if not t: continue
  title,body=headline(t,raw)
  cat=next((k for k,v in CATS.items() if re.search(v,t,re.I)), '综合')
  rows.append(dict(images=[p for p in json.loads(images) if os.path.isfile(os.path.join(D,p))],ch=ch,id=i,ts=ts,text=t,title=title,body=body,cat=cat,day=ts[:10],url=f'https://t.me/{ch}/{i}'))
def grams(t):
  t=re.sub(r'\W','',t.lower())[:180]
  return {t[i:i+3] for i in range(len(t)-2)}
recent=[r for r in rows if datetime.fromisoformat(r['ts'])>=now-timedelta(hours=48) and not re.search(r'早餐|新闻汇总|要闻汇总|日报|收评',r['title'])]
G=[grams(r['text']) for r in recent]
for i,r in enumerate(recent):
  sources={r['ch']}|{recent[j]['ch'] for j in range(len(recent)) if len(G[i]&G[j])>=8}
  r['sources']=len(sources)
  r['score']=len(sources)*4+sum(k.lower() in r['text'].lower() for k in KW)+min(len(r['text'])/240,2)
hot=[]
for r in sorted(recent,key=lambda r:r['score'],reverse=True):
  if any(len(grams(r['title'])&grams(x['title']))>=6 for x in hot): continue
  hot.append(r)
  if len(hot)==10: break
from sitebuild import build
build(rows, hot, now)
db.close()

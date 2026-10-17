#!/usr/bin/env python3
"""增量抓取 5 个 TG 公开频道 -> SQLite -> 静态站点 site/"""
import subprocess,sqlite3,json,re,html,os,sys,collections,shutil,io
from pathlib import Path
from PIL import Image,ImageOps
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from bs4 import BeautifulSoup
BJ=timezone(timedelta(hours=8)); D=os.path.dirname(os.path.abspath(__file__))
CH={"xhqcankao":"风向旗参考快讯","tnews365":"竹新社","FinanceNewsDaily":"华尔街见闻·财经时讯","CE_Observe":"每日消费电子观察","freechinese":"FREE 中文"}
db=sqlite3.connect(os.path.join(D,"tg.db"))
cols=[r[1] for r in db.execute("pragma table_info(msg)")]
if cols and "html" not in cols: db.execute("alter table msg add column html text")  # 保留旧库消息，兼容缺少 HTML 的历史结构
db.execute("create table if not exists msg(ch text,id int,ts text,text text,links text,html text,primary key(ch,id))")
images_migrated="images" not in [r[1] for r in db.execute("pragma table_info(msg)")]
if images_migrated:
  db.execute("alter table msg add column images text not null default '[]'")
db.execute("create table if not exists status(ch text primary key,ok int,err text,at text)")
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
for c in CH:
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
for c,i,ts,images in db.execute("select ch,id,ts,images from msg where images!='[]'").fetchall():
  if datetime.fromisoformat(ts)<media_floor:
    db.execute("update msg set images='[]' where ch=? and id=?",(c,i))
retained={path for (images,) in db.execute("select images from msg") for path in json.loads(images)}
for path in Path(MEDIA).rglob('*'):
  if path.is_file() and path.relative_to(D).as_posix() not in retained: path.unlink()
db.commit()
# ---------- build ----------
AD=re.compile(r'-{3,}\s*本条新闻由.*',re.S)
def clean(t):
  t=AD.sub('',t)
  # 华尔街见闻把话题写成 " #美国 "，去掉 # 和它两侧人为插入的空格，让中文连续成句
  t=re.sub(r'[ \t]*#(?:\s*#)*\s*([\w\u4e00-\u9fff]+)[ \t]*',r'\1',t)
  t=re.sub(r'[ \t]{2,}',' ',t); t=re.sub(r'\n{3,}','\n\n',t)
  return '\n'.join(l.strip() for l in t.split('\n')).strip()
e=html.escape
CATS={'全球':'国际|美国|俄罗斯|乌克兰|特朗普|以色列|战争|停火|总统|巴基斯坦|印度|联合国','财经':'市场|经济|股|央行|美联储|利率|美元|财报|GDP|CPI|关税|投资','科技':'AI|人工智能|芯片|苹果|手机|英伟达|OpenAI|谷歌|科技|电子|SpaceX'}
KW=['美联储','降息','关税','停火','战争','GDP','财报','AI','苹果','英伟达','OpenAI','特朗普','央行','芯片']
rows=[]
for ch,i,ts,t,raw,images in db.execute('select ch,id,ts,text,html,images from msg order by ts desc'):
  t=clean(t)
  if not t: continue
  bold=BeautifulSoup(raw or '', 'html.parser').select_one('b, strong')
  m=re.match(r'【([^】]+)】',t)
  bold_title=clean(bold.get_text('')) if bold else ''
  title=m.group(1) if m else (bold_title if len(bold_title)>=12 and t.startswith(bold_title) else re.split(r'[。！？\n]',t)[0])
  title=title.strip('【】 ')
  if len(title)<6: title=re.split(r'[。！？\n]',t)[0]
  title=title[:86]+('…' if len(title)>86 else '')
  body=t
  if t.startswith('【'+title+'】'): body=t[len(title)+2:].strip()
  elif t.startswith(title): body=t[len(title):].lstrip('。！？\n ')
  cat=next((k for k,v in CATS.items() if re.search(v,t,re.I)), '综合')
  rows.append(dict(images=[p for p in json.loads(images) if os.path.isfile(os.path.join(D,p))],ch=ch,id=i,ts=ts,text=t,title=title,body=body or t,cat=cat,day=ts[:10],url=f'https://t.me/{ch}/{i}'))
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
upd=now.strftime('%Y-%m-%d %H:%M');days=sorted({r['day'] for r in rows},reverse=True)
CSS=open(os.path.join(D,'style.css')).read();JS=open(os.path.join(D,'app.js')).read()
LOGO=open(os.path.join(D,'assets','favicon.svg')).read().replace('<svg ', '<svg class="brand-mark" aria-hidden="true" ' )
NAV_ICONS = {
  'home': '<path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"/>',
  'hot': '<path d="M13.3 3c.8 4-2.9 5.2-2.2 8.2 1.3-.5 2.2-1.5 2.8-2.7 2.8 2.3 4.6 4.5 4.6 7a6.5 6.5 0 0 1-13 0c0-3.1 2-5.4 4-7.2-.2 2 .2 2.9.7 3.3C9.4 7.4 13 6.2 13.3 3Z"/>',
  'all': '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  'archive': '<rect x="4" y="5" width="16" height="15" rx="3"/><path d="M8 3v4m8-4v4M4 10h16M8 14h2m4 0h2m-8 3h2"/>',
}
MAIL_ENABLED=os.environ.get('MAIL_DIGEST')=='1'
NAV_ICONS['mail']='<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m4 7 8 6 8-6"/>'
def nav(rel,active,bottom=False):
  entries=[('home','index.html','精选'),('hot','hot.html','热点'),('all','all.html','全部动态'),('archive','archive/index.html','日报')]
  if MAIL_ENABLED:
    if bottom: entries.pop()
    entries.append(('mail','mail/index.html','邮件'))
  return ''.join(f'<a class="{"active" if key==active else ""}" href="{rel}{path}"'+(' aria-current="page"' if key==active else '')+f'><span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{NAV_ICONS[key]}</svg></span>{label}</a>' for key,path,label in entries)
def sidebar(rel):
  counts=collections.Counter(r['ch'] for r in rows)
  return '<section class="sidebox"><div class="eyebrow">TRENDING NOW</div><h3>大家都在关注 <span>↗</span></h3>'+''.join(f'<a class="sidehot" href="{r["url"]}" target="_blank" rel="noopener"><b>{i:02}</b><span>{e(r["title"])}</span></a>' for i,r in enumerate(hot[:5],1))+'</section><section class="sidebox"><div class="eyebrow">OUR SOURCES</div><h3>五个视角，一个信息流</h3>'+''.join(f'<div class="channel" data-ch="{c}"><i>{["风","竹","华","电","F"][i]}</i><span>{name}<small>公开频道 · Telegram</small></span><b>{counts[c]}</b></div>' for i,(c,name) in enumerate(CH.items()))+f'</section><section class="sidebox about"><b>拾光热点 / 保持好奇，掌握此刻。</b><p>聚合公开频道资讯，每小时自动更新。<br>让重要的信息，先被看见。</p><p>最后更新：{upd}（北京时间）</p><a href="{rel}archive/index.html">浏览往期日报 ↗</a></section>'
def shell(title,rel,active,main):
  main=main.replace('src="media/',f'src="{rel}media/').replace('data-image="media/',f'data-image="{rel}media/')
  return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>{e(title)} · 拾光热点</title><meta name="theme-color" content="#123e45"><link rel="icon" href="{rel}favicon.ico?v=20261017-1" sizes="32x32"><link rel="icon" href="{rel}favicon.svg?v=20261017-1" type="image/svg+xml"><link rel="apple-touch-icon" href="{rel}apple-touch-icon.png?v=20261017-1" sizes="180x180"><link rel="manifest" href="{rel}manifest.webmanifest?v=20261017-1"><style>{CSS}</style></head><body><header><div class="top"><a class="brand" href="{rel}index.html">{LOGO}<span class="brand-name">拾光热点</span><span class="brand-note">拾起时光里的重要瞬间</span></a><nav>{nav(rel,active)}</nav><span class="live"><i></i> 每小时更新</span></div></header><div class="layout"><main>{main}</main><aside>{sidebar(rel)}</aside></div><footer>拾光热点 · 信息汇聚，视野更开阔 <span>最后更新：{upd}（北京时间）</span></footer><nav class="bottom">{nav(rel,active,True)}</nav><dialog class="lightbox" aria-label="图片查看器"><button class="lightbox-close" aria-label="关闭图片">×</button><img alt="放大图片"></dialog><script>{JS}</script></body></html>'''
def heading(kicker,title,desc):
  return f'<div class="pagehead"><div class="eyebrow">{kicker}</div><h1>{title}<span class="head-dot">.</span></h1><p>{desc}</p></div>'
def filters():
  return '<section class="filters"><div class="filterline" data-filter="cat">'+''.join(f'<button class="pill {"selected" if i==0 else ""}" data-value="{v}">{label}</button>' for i,(v,label) in enumerate([('','全部'),('全球','全球视野'),('财经','财经市场'),('科技','科技数码'),('综合','综合资讯')]))+'</div><div class="tools"><label class="search"><span>⌕</span><input id="q" type="search" placeholder="搜索资讯、关键词…" aria-label="搜索全文"></label><select id="channel" aria-label="筛选频道"><option value="">所有频道</option>'+''.join(f'<option value="{c}">{n}</option>' for c,n in CH.items())+'</select></div></section>'
def gallery(r):
  images=r['images']
  if not images: return ''
  return '<div class="gallery '+('single' if len(images)==1 else 'multiple')+'">'+''.join(f'<button class="photo" type="button" data-image="{e(path)}" aria-label="放大查看图片 {j}"><img src="{e(path)}" alt="{e(r["title"])} · 图片 {j}" loading="lazy" decoding="async"></button>' for j,path in enumerate(images,1))+'</div>'
def card(r,rank=None):
  body=''.join('<p>'+e(p).replace('\n','<br>')+'</p>' for p in r['body'].split('\n\n') if p.strip())
  return f'''<article class="news" data-ch="{r['ch']}" data-cat="{r['cat']}">{f'<div class="rank">{rank:02}</div>' if rank else ''}<div class="news-content"><div class="meta"><span class="category">{r['cat']}</span><span>{e(CH[r['ch']])}</span><time datetime="{r['ts']}">{r['ts'][11:16]}</time>{f'<span>{r.get("sources",1)} 个来源</span>' if rank else ''}</div><h2><a href="{r['url']}" target="_blank" rel="noopener">{e(r['title'])}</a></h2><div class="body">{body}</div>{gallery(r)}<div class="cardfoot"><button class="expand" aria-expanded="false">展开全文 ＋</button><a href="{r['url']}" target="_blank" rel="noopener">阅读原文 ↗</a></div></div></article>'''
def feed(rs,ranked=False):
  s='';day=None
  for i,r in enumerate(rs,1):
    if not ranked and day!=r['day']:
      day=r['day'];s+=f'<div class="dategroup"><b>{day.replace("-"," / ")}</b><span>实时资讯</span><i></i></div>'
    s+=card(r,i if ranked else None)
  return s+'<div id="none" class="empty" hidden>没有匹配的资讯，请尝试其他关键词。</div>'
def hotspots():
  return '<section class="hotpanel"><div class="sectionhead"><h2><span class="spark">✳</span> 当前热点</h2><a href="hot.html">查看排行 ↗</a></div>'+''.join(f'<a class="hotitem" href="{r["url"]}" target="_blank" rel="noopener"><span class="number">NO.{i:02}</span>{('<img class="hot-thumb" src="'+e(r['images'][0])+'" alt="" loading="lazy">') if r['images'] else ''}<b>{e(r["title"])}</b><em>{"热" if i==1 else "新"}</em></a>' for i,r in enumerate(hot[:3],1))+'<div class="hotnote">过去 48 小时 · 根据关键词与跨频道报道自动聚合</div></section>'
out=os.path.abspath(os.environ.get('SITE_OUT',os.path.join(D,'site')));os.makedirs(out+'/archive',exist_ok=True)
if not MAIL_ENABLED: shutil.rmtree(os.path.join(out,'mail'),ignore_errors=True)
shutil.copytree(MEDIA,os.path.join(out,'media'),dirs_exist_ok=True)
for path in Path(out,'media').rglob('*'):
  if path.is_file() and not os.path.isfile(os.path.join(MEDIA,path.relative_to(os.path.join(out,'media')))): path.unlink()
for asset in ('favicon.svg','favicon.ico','favicon-32x32.png','apple-touch-icon.png','apple-touch-icon-precomposed.png','icon-192.png','icon-512.png','manifest.webmanifest'):
  shutil.copyfile(os.path.join(D,'assets',asset),os.path.join(out,asset))
def write(path,content):
  with open(out+'/'+path,'w') as f:f.write(content)
write('index.html',shell('精选','', 'home',heading('THE WORLD, AT A GLANCE','信息很多，重要的在这里','从 5 个频道发现值得关注的事。保持好奇，不错过每一个变化。')+hotspots()+filters()+'<div class="feedhead"><h2>最新精选</h2><span>按时间排序 · <b id="n"></b> 条资讯</span></div>'+feed(rows[:100])))
write('all.html',shell('全部动态','','all',heading('LIVE NEWS FEED','世界正在发生','全部频道，完整收录。用分类、频道和关键词找到你关心的信息。')+filters()+'<div class="feedhead"><h2>全部动态</h2><span><b id="n"></b> 条资讯</span></div>'+feed(rows)))
write('hot.html',shell('热点排行','','hot',heading('THE TRENDING TEN','热点，值得多看一眼','过去 48 小时 Top 10 · 综合关键词、内容长度与跨频道报道排序。')+feed(hot,True)))
for day in days:
  rs=[r for r in rows if r['day']==day]
  write(f'archive/{day}.html',shell(day+' 日报','../','archive',heading('DAILY DIGEST',day+' 日报',f'当天共 {len(rs)} 条资讯 · 按北京时间归档')+filters()+feed(rs)))
lst=''.join(f'<a class="archive-row" href="{d}.html"><span class="archive-icon">▦</span><div><b>{d}</b><small>每日资讯汇总</small></div><span>{sum(r["day"]==d for r in rows)} 条资讯 ↗</span></a>' for d in days)
write('archive/index.html',shell('日报存档','../','archive',heading('THE DAILY ARCHIVE','每一天，都有迹可循',f'{len(days)} 份日报 · 回看世界变化的每一个切片')+lst))
write('.nojekyll','')
print('built',len(rows),'msgs,',len(days),'days ->',out,file=sys.stderr)

if MAIL_ENABLED:
  from mailbuild import build
  build(out)

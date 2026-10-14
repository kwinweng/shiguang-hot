#!/usr/bin/env python3
"""增量抓取 4 个 TG 公开频道 -> SQLite -> 静态站点 site/"""
import subprocess,sqlite3,json,re,html,os,sys,collections
from datetime import datetime,timezone,timedelta
from bs4 import BeautifulSoup
BJ=timezone(timedelta(hours=8)); D=os.path.dirname(os.path.abspath(__file__))
CH={"xhqcankao":"风向旗参考快讯","tnews365":"竹新社","FinanceNewsDaily":"华尔街见闻·财经时讯","CE_Observe":"每日消费电子观察"}
db=sqlite3.connect(os.path.join(D,"tg.db"))
cols=[r[1] for r in db.execute("pragma table_info(msg)")]
if cols and "html" not in cols: db.execute("drop table msg")  # 旧库正文断行已损坏，重建
db.execute("create table if not exists msg(ch text,id int,ts text,text text,links text,html text,primary key(ch,id))")
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
for c in CH:
  last=db.execute("select max(id) from msg where ch=?",(c,)).fetchone()[0]
  floor=now-timedelta(hours=72) if last is None else None
  before=None;n=0;err=None
  try:
    for _ in range(20):
      s=BeautifulSoup(get(f"https://t.me/s/{c}"+(f"?before={before}" if before else "")),"html.parser")
      ms=s.select("div.tgme_widget_message[data-post]")
      if not ms: err="页面无消息/打不开" if n==0 and before is None else None; break
      ids=[];stop=False
      for m in ms:
        i=int(m["data-post"].split("/")[1]);ids.append(i)
        if last is not None and i<=last: stop=True;continue
        tm=m.select_one("time[datetime]")
        if not tm: continue
        dt=datetime.fromisoformat(tm["datetime"]).astimezone(BJ)
        if floor and dt<floor: stop=True;continue
        tx=m.select_one(".tgme_widget_message_text")
        if not tx: continue
        links=[a["href"] for a in tx.select("a[href]")]
        db.execute("insert or ignore into msg values(?,?,?,?,?,?)",(c,i,dt.isoformat(),extract(tx),json.dumps(links),str(tx)));n+=1
      if stop: break
      before=min(ids)
  except Exception as ex: err=str(ex)[:200]
  db.execute("insert or replace into status values(?,?,?,?)",(c,0 if err else 1,err,now.isoformat()))
  print(c,"new",n,err or "",file=sys.stderr)
db.commit()
# ---------- build ----------
AD=re.compile(r'-{3,}\s*本条新闻由.*',re.S)
def clean(t):
  t=AD.sub('',t)
  # 华尔街见闻把话题写成 " #美国 "，去掉 # 和它两侧人为插入的空格，让中文连续成句
  t=re.sub(r'[ \t]*#(?:\s*#)*\s*([\w\u4e00-\u9fff]+)[ \t]*',r'\1',t)
  t=re.sub(r'[ \t]{2,}',' ',t); t=re.sub(r'\n{3,}','\n\n',t)
  return '\n'.join(l.strip() for l in t.split('\n')).strip()
def title_body(t):
  m=re.match(r'【([^】]+)】\s*',t)
  if m: return m.group(1).replace('#',''),t[m.end():]
  first,_,rest=t.partition('\n')
  if len(first)<=60 and rest.strip(): return first.replace('#',''),rest
  return '',t
rows=[]
for r in db.execute("select ch,id,ts,text,links from msg order by ts desc"):
  t=clean(r[3]); ti,bo=title_body(t)
  rows.append(dict(ch=r[0],id=r[1],ts=r[2],title=ti,body=bo.strip(),day=r[2][:10],hm=r[2][11:16],hh=r[2][11:13],url=f"https://t.me/{r[0]}/{r[1]}"))
st={r[0]:dict(ok=r[1],err=r[2]) for r in db.execute("select * from status")}
KW=["CPI","美联储","加息","降息","关税","停火","战争","GDP","出口","财报","发布","裁员","IPO","AI","苹果","英伟达","OpenAI","谷歌","特朗普","央行","芯片","SpaceX"]
SKIP=re.compile(r'早餐|要闻|汇总|提醒|日报|收评|收盘')
def grams(s): s=re.sub(r'[\W_]','',s); return {s[i:i+3] for i in range(len(s)-2)}
def pick(day):
  rs=[r for r in rows if r["day"]==day and r["title"] and not SKIP.search(r["title"])]
  G=[grams(r["title"]+r["body"][:80]) for r in rs]; sc=[]
  for i,r in enumerate(rs):
    chs={rs[j]["ch"] for j in range(len(rs)) if len(G[i]&G[j])>=4}-{r["ch"]}
    sc.append((3*len(chs)+sum(1 for k in KW if k in r["title"]),-i,i))
  out=[];used=[]
  for s,_,i in sorted(sc,reverse=True):
    if s<2 or len(out)>=6: break
    if any(len(G[i]&G[u])>=5 for u in used): continue
    used.append(i); out.append(rs[i])
  return out
e=html.escape
URL=re.compile(r'https?://[^\s<>"）】，。]+')
def rich(t):
  out=[];p=0
  for m in URL.finditer(t):
    out.append(e(t[p:m.start()])); u=m.group(0); out.append(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(u)}</a>'); p=m.end()
  out.append(e(t[p:])); s=''.join(out)
  s=re.sub(r'#([\w\u4e00-\u9fff]+)',r'<span class="ht">#\1</span>',s)
  return ''.join(f'<p>{x.replace(chr(10),"<br>")}</p>' for x in s.split('\n\n') if x.strip())
COL={"xhqcankao":"#e8590c","tnews365":"#2f9e44","FinanceNewsDaily":"#1c7ed6","CE_Observe":"#ae3ec9"}
upd=now.strftime("%Y-%m-%d %H:%M"); days=sorted({r["day"] for r in rows},reverse=True)
CSS=open(os.path.join(D,"style.css")).read(); JS=open(os.path.join(D,"app.js")).read()
def shell(title,rel,side,main):
  return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>{e(title)}</title><style>{CSS}</style></head><body>
<header class="bar"><a class="brand" href="{rel}index.html"><span class="logo">T</span>TG 快讯</a><nav><a href="{rel}index.html">今天</a><a href="{rel}archive/index.html">归档</a></nav><div class="search"><input id="q" type="search" placeholder="搜索标题与正文…" autocomplete="off"></div><div class="upd">最后更新 <b>{upd}</b> 北京时间</div></header>
<div class="layout"><aside class="side">{side}</aside><main class="main">{main}</main></div><script>{JS}</script></body></html>'''
def page(day,rel,is_index):
  rs=[r for r in rows if r["day"]==day]; cnt=collections.Counter(r["ch"] for r in rs)
  side='<div class="sh">频道</div>'+''.join(f'<label class="ch"><input class="chk" type="checkbox" value="{c}" checked><i style="background:{COL[c]}"></i><span>{CH[c]}</span><em>{cnt.get(c,0)}</em>'+(f'<b class="bad" title="{e(st[c]["err"] or "")}">打不开</b>' if c in st and not st[c]["ok"] else '')+'</label>' for c in CH)
  side+=f'<div class="cnt">显示 <b id="n">{len(rs)}</b> / {len(rs)} 条</div><div class="sh">归档</div>'+''.join(f'<a class="day{" on" if d==day else ""}" href="{rel}archive/{d}.html">{d}</a>' for d in days[:14])+f'<a class="day" href="{rel}archive/index.html">全部日期 →</a>'
  hl=pick(day)
  m=f'<div class="ph"><h1>{"今日快讯" if is_index else "归档"}</h1><span>{day} · {len(rs)} 条</span></div>'
  if hl: m+='<section class="hl"><div class="hlh">今日重点<small>按跨频道热度与关键词自动挑选</small></div><div class="hlg">'+''.join(f'<a class="hc" href="{r["url"]}" target="_blank" rel="noopener" style="--c:{COL[r["ch"]]}"><span class="src">{CH[r["ch"]]} · {r["hm"]}</span><b>{e(r["title"])}</b></a>' for r in hl)+'</div></section>'
  cur=None
  for r in rs:
    if r["hh"]!=cur: cur=r["hh"]; m+=f'<div class="hr"><span>{cur}:00</span></div>'
    m+=f'''<article class="it" data-ch="{r['ch']}" style="--c:{COL[r['ch']]}"><div class="meta"><span class="tag">{CH[r['ch']]}</span><time>{r['hm']}</time><a href="{r['url']}" target="_blank" rel="noopener">原帖 ↗</a></div>{f'<h3>{e(r["title"])}</h3>' if r["title"] else ''}<div class="body">{rich(r['body'])}</div><button class="more" hidden>展开全文</button></article>'''
  if not rs: m+='<p class="empty">今天暂时还没有消息。</p>'
  m+='<div class="empty" id="none" hidden>没有匹配的消息</div>'
  return shell(f"TG 快讯 · {day}",rel,side,m)
out=os.path.join(D,"site");os.makedirs(out+"/archive",exist_ok=True)
today=now.strftime("%Y-%m-%d")
open(out+"/index.html","w").write(page(today,"",True))
for d in days: open(f"{out}/archive/{d}.html","w").write(page(d,"../",False))
lst=''.join(f'<a class="arow" href="{d}.html"><b>{d}</b><span>{sum(1 for r in rows if r["day"]==d)} 条</span></a>' for d in days)
open(out+"/archive/index.html","w").write(shell("TG 快讯 · 归档","../",'<div class="sh">说明</div><p class="note">每小时自动抓取 4 个公开频道。</p>',f'<div class="ph"><h1>归档</h1><span>{len(days)} 天</span></div><div class="alist">{lst}</div>'))
open(out+"/.nojekyll","w").close()
print("built",len(rows),"msgs,",len(days),"days ->",out,file=sys.stderr)

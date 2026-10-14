#!/usr/bin/env python3
"""增量抓取 4 个 TG 公开频道 -> SQLite -> 静态站点 site/"""
import subprocess,sqlite3,json,re,html,os,sys,collections
from datetime import datetime,timezone,timedelta
from bs4 import BeautifulSoup
BJ=timezone(timedelta(hours=8)); D=os.path.dirname(os.path.abspath(__file__))
CH={"xhqcankao":"风向旗参考快讯","tnews365":"竹新社","FinanceNewsDaily":"华尔街见闻·财经时讯","CE_Observe":"每日消费电子观察"}
db=sqlite3.connect(os.path.join(D,"tg.db"))
db.execute("create table if not exists msg(ch text,id int,ts text,text text,links text,primary key(ch,id))")
db.execute("create table if not exists status(ch text primary key,ok int,err text,at text)")
now=datetime.now(BJ)
def get(u):
  return subprocess.run(["curl","-sL","-m","25","-A","Mozilla/5.0",u],capture_output=True,text=True).stdout
for c in CH:
  last=db.execute("select max(id) from msg where ch=?",(c,)).fetchone()[0]
  floor=now-timedelta(hours=48) if last is None else None
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
        db.execute("insert or ignore into msg values(?,?,?,?,?)",(c,i,dt.isoformat(),tx.get_text("\n").strip(),json.dumps(links)));n+=1
      if stop: break
      before=min(ids)
  except Exception as ex: err=str(ex)[:200]
  db.execute("insert or replace into status values(?,?,?,?)",(c,0 if err else 1,err,now.isoformat()))
  print(c,"new",n,err or "",file=sys.stderr)
db.commit()
# ---------- build ----------
def clean(t): t=re.sub(r'\s*#\s*','',t); return re.sub(r'---\s*本条新闻由.*','',t,flags=re.S).strip()
def title(t):
  m=re.match(r'【([^】]+)】',t); return m.group(1) if m else t.split('\n')[0][:80]
rows=[dict(ch=r[0],id=r[1],ts=r[2],text=clean(r[3]),links=[l for l in json.loads(r[4]) if l.startswith('http') and '//t.me' not in l][:3]) for r in db.execute("select * from msg order by ts desc")]
for r in rows: r["title"]=title(r["text"]); r["day"]=r["ts"][:10]; r["hm"]=r["ts"][11:16]; r["url"]=f"https://t.me/{r['ch']}/{r['id']}"
st={r[0]:dict(ok=r[1],err=r[2]) for r in db.execute("select * from status")}
# 今日重点启发式: 标题 bigram 在多频道出现 + 关键词加分
KW=["CPI","美联储","加息","降息","关税","停火","战争","GDP","出口","财报","发布","裁员","IPO","AI","苹果","英伟达","OpenAI","谷歌","特朗普","央行","芯片"]
def grams(s): s=re.sub(r'[\W_]','',s); return {s[i:i+3] for i in range(len(s)-2)}
def pick(day):
  rs=[r for r in rows if r["day"]==day]; G=[grams(r["title"]) for r in rs]
  sc=[]
  for i,r in enumerate(rs):
    chs={rs[j]["ch"] for j in range(len(rs)) if j!=i and len(G[i]&G[j])>=2}-{r["ch"]}
    s=3*len(chs)+sum(1 for k in KW if k in r["title"])+(1 if r["text"].startswith('【') else 0)
    sc.append((s,i))
  out=[];used=[]
  for s,i in sorted(sc,reverse=True):
    if s<2 or len(out)>=8: break
    if any(len(G[i]&G[u])>=3 for u in used): continue
    used.append(i); out.append(rs[i])
  return out
upd=now.strftime("%Y-%m-%d %H:%M")
days=sorted({r["day"] for r in rows},reverse=True)
CSS="""body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f3f4f6;color:#222}
.top{background:#1f3b8a;color:#fff;padding:14px 32px;display:flex;align-items:center;gap:24px}.top h1{font-size:20px;margin:0}.top a{color:#cfe0ff;text-decoration:none}.upd{margin-left:auto;font-size:13px;opacity:.9}
.wrap{max-width:1200px;margin:20px auto;display:grid;grid-template-columns:260px 1fr;gap:20px;padding:0 20px}
aside,.card{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px #0001}aside{position:sticky;top:16px;align-self:start}
aside label{display:block;margin:6px 0;cursor:pointer}input[type=search]{width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;box-sizing:border-box}
.it{border-top:1px solid #eee;padding:12px 0}.t{font-weight:600;font-size:16px}.m{font-size:12px;color:#888;margin:3px 0}.b{font-size:14px;color:#444;white-space:pre-wrap;max-height:6.5em;overflow:hidden}
.tag{display:inline-block;font-size:12px;padding:1px 8px;border-radius:9px;background:#eef2ff;color:#3346c4;margin-right:6px}a{color:#2a5bd7}.err{color:#c0392b}ol li{margin:6px 0}h2{margin:0 0 10px;font-size:18px}"""
JS="""const q=document.getElementById('q');function f(){const on=[...document.querySelectorAll('.chk:checked')].map(e=>e.value),s=q.value.toLowerCase();let n=0;document.querySelectorAll('.it').forEach(e=>{const v=on.includes(e.dataset.ch)&&e.textContent.toLowerCase().includes(s);e.style.display=v?'':'none';n+=v});document.getElementById('n').textContent=n}document.querySelectorAll('.chk').forEach(e=>e.onchange=f);q.oninput=f;"""
e=html.escape
def page(day,rel,is_index):
  rs=[r for r in rows if r["day"]==day]; cnt=collections.Counter(r["ch"] for r in rs)
  side="<input id=q type=search placeholder='搜索…'><p><b>频道筛选</b></p>"+"".join(f"<label><input class=chk type=checkbox value={c} checked> {CH[c]} ({cnt.get(c,0)})"+(f" <span class=err title='{e(st[c]['err'] or '')}'>⚠打不开</span>" if c in st and not st[c]['ok'] else "")+"</label>" for c in CH)
  side+=f"<p style='font-size:13px'>显示 <span id=n>{len(rs)}</span> 条</p><p><b>归档</b></p>"+"".join(f"<div><a href='{rel}archive/{d}.html'>{d}</a></div>" for d in days[:60])+f"<div><a href='{rel}archive/index.html'>全部日期…</a></div>"
  hl=pick(day)
  hlh=("<div class=card style='margin-bottom:16px'><h2>⭐ 重点（自动挑选）</h2><ol>"+"".join(f"<li>{e(r['title'])} <span class=tag>{CH[r['ch']]}</span><a href='{r['url']}' target=_blank>原帖</a></li>" for r in hl)+"</ol></div>") if hl else ""
  items="".join(f"<div class=it data-ch={r['ch']}><div class=t>{e(r['title'])}</div><div class=m><span class=tag>{CH[r['ch']]}</span>{r['day']} {r['hm']} · <a href='{r['url']}' target=_blank>原帖</a>"+"".join(f" · <a href='{e(l)}' target=_blank>外链</a>" for l in r['links'][:1])+f"</div><div class=b>{e(r['text'])}</div></div>" for r in rs)
  head="今天的消息流" if is_index else f"{day} 归档"
  return f"<!doctype html><html lang=zh-CN><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>TG 快讯 · {day}</title><style>{CSS}</style></head><body><div class=top><h1>📰 TG 快讯汇总</h1><a href='{rel}index.html'>今天</a><a href='{rel}archive/index.html'>归档</a><span class=upd>最后更新：{upd}（北京时间）</span></div><div class=wrap><aside>{side}</aside><main>{hlh}<div class=card><h2>{head} · {day}</h2>{items or '<p>今天暂无消息</p>'}</div></main></div><script>{JS}</script></body></html>"
out=os.path.join(D,"site");os.makedirs(out+"/archive",exist_ok=True)
today=now.strftime("%Y-%m-%d")
open(out+"/index.html","w").write(page(today,"",True))
for d in days: open(f"{out}/archive/{d}.html","w").write(page(d,"../",False))
open(out+"/archive/index.html","w").write(f"<!doctype html><meta charset=utf-8><title>归档</title><style>{CSS}</style><div class=top><h1>📰 归档</h1><a href='../index.html'>今天</a><span class=upd>最后更新：{upd}</span></div><div class=wrap style='display:block'><div class=card>"+"".join(f"<div><a href='{d}.html'>{d}</a>（{sum(1 for r in rows if r['day']==d)} 条）</div>" for d in days)+"</div></div>")
open(out+"/.nojekyll","w").close()
print("built",len(rows),"msgs,",len(days),"days ->",out,file=sys.stderr)

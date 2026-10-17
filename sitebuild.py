"""Static presentation shared by Telegram and configured inbox sources."""
import html, json, os, re, shutil
from pathlib import Path
from urllib.parse import urlsplit
from feeds import ROOT, config, private_mode, load_issues, compress_images
E = lambda v: html.escape(str(v or ''), quote=True)
ICONS = {'home':'<path d="m3 10 9-7 9 7v11H6V10M9 21v-8h6v8"/>','hot':'<path d="M13 3c2 6-3 6-1 10 2-1 3-3 3-4 7 7 4 12-3 12S3 14 8 8c0 4 2 4 2 4-1-5 3-6 3-9Z"/>','all':'<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h8m-8 4h8m-8 4h5"/>','archive':'<rect x="4" y="5" width="16" height="16" rx="3"/><path d="M8 3v4m8-4v4M4 10h16"/>','mail':'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m3 7 9 6 9-6"/>','world':'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>'}
def icon(key): return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+ICONS.get(key, ICONS['all'])+'</svg>'
def link(url): return str(url or '') if urlsplit(str(url or '')).scheme in ('http','https') else ''

def build(rows, hot, now, inbox_only=False):
    cfg = config(); private = private_mode()
    sources = [s for s in cfg['sources'] if private or s['visibility']=='public']
    by_id = {s['id']:s for s in sources}; by_channel = {s['channel']:s for s in sources if s['type']=='telegram'}
    rows = [dict(r, name=by_channel[r['ch']]['name'], source_id=by_channel[r['ch']]['id']) for r in rows if r['ch'] in by_channel]
    hot = [dict(r, name=by_channel[r['ch']]['name'], source_id=by_channel[r['ch']]['id']) for r in hot if r['ch'] in by_channel]
    if not private:
        # Public copy uses 电邮 for ordinary Telegram news, keeping the private column marker absent.
        for r in rows + hot:
            for field in ('title', 'body'):
                r[field] = r[field].replace('电子邮件', '电邮').replace('邮件', '电邮')
    out = Path(os.getenv('SITE_OUT', ROOT/'site')).resolve()
    if out == ROOT or ROOT.is_relative_to(out): raise ValueError('SITE_OUT 不能覆盖仓库')
    if not inbox_only: shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True,exist_ok=True)
    issues = {}; latest_cards=[]
    def inbox_rows(data,s):
        return [dict(title=i.get('title') or '未命名条目', body=i.get('body') or '', images=[im['file'] for im in i.get('images',[]) or [] if isinstance(im,dict) and im.get('file')], name=i.get('source') or ' / '.join(str(x) for x in i.get('sources',[]) or []) or s['name'], cat=s['name'], source_id=s['id'], ch=s['id'], day=data['date'], ts=i.get('date') or data['date'], url=link(i.get('link'))) for section in data.get('sections',[]) for i in section['items']]
    for s in sources:
        if s['type']!='inbox': continue
        loaded=load_issues(s,private)
        shutil.rmtree(out/s['id'],ignore_errors=True)
        if not loaded: continue
        issues[s['id']]=[(compress_images(d,base,out/s['id']/'img',s['id']+'/img/'),base) for d,base in loaded]
        latest_cards.extend(inbox_rows(issues[s['id']][0][0],s))
    entries=[('home','index.html','首页','home'),('hot','hot.html','热点','hot'),('all','all.html','全部','all'),('archive','archive/index.html','日报','archive')]
    entries += [(s['id'],s['id']+'/index.html',s['name'],s['icon']) for s in sorted(sources,key=lambda s:s['nav'].get('order',100)) if (s['type']=='telegram' and any(r['source_id']==s['id'] for r in rows) or s['id'] in issues) and s['nav'].get('enabled')]
    def nav(rel,active,bottom=False):
        chosen=entries if not bottom or len(entries)<=5 else entries[:4]
        result=''.join(f'<a href="{rel}{path}" class="{"active" if active==key else ""}"'+(' aria-current="page"' if active==key else '')+f'>{icon(ic)}<span>{E(name)}</span></a>' for key,path,name,ic in chosen)
        if bottom and len(entries)>5: result+=f'<button id="more-toggle" class="{"active" if active in [x[0] for x in entries[4:]] else ""}" aria-expanded="false">'+icon('all')+'<br>更多</button>'
        return result
    def sidebar(rel):
        return '<aside><section class="sidebox"><div class="eyebrow">ON THE RADAR</div><h2>此刻，大家在看</h2>'+''.join(f'<a class="rank" href="{E(r["url"])}"><b>{n:02}</b><span>{E(r["title"])}</span></a>' for n,r in enumerate(hot[:5],1))+'</section><section class="sidebox"><div class="eyebrow">YOUR SOURCES</div><h2>消息从这里来</h2>'+''.join(f'<div class="source"><i style="color:{E(s["color"])}">{icon(s["icon"])}</i><span>{E(s["name"])}</span><small>{"TG" if s["type"]=="telegram" else "INBOX"}</small></div>' for s in sources if s['type']=='telegram' or s['id'] in issues)+'</section></aside>'
    css=(ROOT/'style.css').read_text(); js=(ROOT/'app.js').read_text(); logo=(ROOT/'assets/favicon.svg').read_text().replace('<svg ','<svg class="brand-mark" aria-hidden="true" ')
    def shell(title,rel,active,body):
        # All card media paths are root-relative to the generated tree, never host-root URLs.
        body=re.sub(r'(src|data-image)="(?!https?://)([^"]+)"',lambda m:f'{m[1]}="{rel}{m[2]}"',body)
        more='<div class="more-nav" id="more-nav" hidden>'+''.join(f'<a href="{rel}{p}">{E(n)}</a>' for k,p,n,ic in entries[4:])+'</div>'
        return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="theme-color" content="#3b8ef0"><title>{E(title)} · 拾光热点</title><link rel="icon" href="{rel}favicon.ico?v=20261017-2"><link rel="icon" type="image/svg+xml" href="{rel}favicon.svg?v=20261017-2"><link rel="apple-touch-icon" href="{rel}apple-touch-icon.png?v=20261017-2"><link rel="manifest" href="{rel}manifest.webmanifest?v=20261017-2"><style>{css}</style></head><body><header><div class="top"><a class="brand" href="{rel}index.html">{logo}拾光热点<span>SHIGUANG</span></a><nav>{nav(rel,active)}</nav><div class="tools"><button id="theme" aria-label="切换主题">◐</button>{'<span class="private">内网版</span>' if private else ''}</div></div></header><div class="layout"><main>{body}<p id="none" hidden>没有匹配的资讯。</p><footer>今日信息，留一份清晰。<span>{now.strftime('%m-%d %H:%M')} 北京时间</span></footer></main>{sidebar(rel)}</div><nav class="bottom">{nav(rel,active,True)}</nav>{more}<dialog class="lightbox" aria-label="图片查看器"><button class="lightbox-close" aria-label="关闭">×</button><img alt="放大图片"></dialog><script>{js}</script></body></html>'''
    def heading(title,desc): return f'<div class="page-intro"><div><div class="eyebrow">{now.strftime("%Y / %m / %d")} · YOUR DAILY PERSPECTIVE</div><h1>{E(title)}<span class="dot">.</span></h1><p>{E(desc)}</p></div></div>'
    def card(r,kind=None):
        imgs=r.get('images',[]); kind=kind or ('multi' if len(imgs)>1 else 'side' if imgs else 'text')
        url=link(r.get('url')); title=f'<a href="{E(url)}" target="_blank" rel="noopener noreferrer">{E(r["title"])}</a>' if url else E(r['title'])
        pictures=''.join(f'<button class="photo" data-image="{E(p)}" aria-label="放大图片"><img src="{E(p)}" alt="{E(r["title"])}" loading="lazy"></button>' for p in imgs[:4])
        source=by_id[r['source_id']]
        return f'<article class="card news {kind}" data-cat="{E(r["cat"])}" data-ch="{E(r["ch"])}" style="--source:{E(source["color"])}"><div class="copy"><div class="meta"><span>{E(r["cat"])}</span><span class="source-label">{E(r["name"])}</span><time>{E(r["ts"][11:16] or r["day"])}</time></div><h2>{title}</h2><p>{E(r["body"])}</p></div>{f"<div class='pictures'>{pictures}</div>" if pictures else ""}<div class="foot"><span>{E(r["day"])}</span><button class="expand" aria-expanded="false">展开全文 ＋</button>{f"<a href='{E(url)}' target='_blank' rel='noopener noreferrer'>阅读原文 ↗</a>" if url else ""}</div></article>'
    def filters():
        cats=['推荐']+list(cfg['categories'])+['综合']+[s['name'] for s in sources if s['id'] in issues]
        return '<div class="filters">'+''.join(f'<button class="pill {"selected" if i==0 else ""}" data-value="{E(c if i else "")}">{E(c)}</button>' for i,c in enumerate(cats))+'</div><div class="searchline"><input id="q" type="search" placeholder="搜索资讯" aria-label="搜索资讯"><select id="channel" aria-label="筛选来源"><option value="">全部来源</option>'+''.join(f'<option value="{E(s.get("channel",s["id"]))}">{E(s["name"])}</option>' for s in sources if s['type']=='telegram' or s['id'] in issues)+'</select></div>'
    def write(path,text):
        p=out/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    def blocks(data):
        result=''
        for b in data.get('blocks',[]):
            kind=b.get('type'); title=b.get('title') or {'oneliner':'一句话速览','markets':'市场看板','chart':'一张图','tomorrow':'明日看点'}.get(kind,'')
            content=''
            if kind in ('oneliner','tomorrow'):
                content='<ul>'+''.join('<li>'+E(x if isinstance(x,str) else x.get('title') or x.get('body'))+'</li>' for x in b.get('items',[]))+'</ul>'
            elif kind=='markets':
                content='<div class="markets">'+''.join(f'<div class="market">{E(m.get("name"))}<strong>{E(m.get("value"))}</strong><span class="{"down" if str(m.get("change","")).startswith("-") else "up"}">{"↓" if str(m.get("change","")).startswith("-") else "↑"} {E(m.get("change"))}</span><small>{E(m.get("note"))}</small></div>' for m in b.get('items',[]))+'</div>'
            elif kind=='chart':
                image=b.get('image'); image=image.get('file') if isinstance(image,dict) else image
                content=(f'<img src="{E(image)}" alt="{E(title)}">' if image else '')+f'<p>{E(b.get("caption"))}</p>'
            else: continue
            result+=f'<section class="block"><h2>{E(title)}</h2>{content}</section>'
        return result
    for id,loaded in issues.items():
        s=by_id[id]; archives='<div class="archives" aria-label="往期列表">'+''.join(f'<a href="{d["date"]}.html">{d["date"]}</a>' for d,base in loaded)+'</div>'
        for n,(d,base) in enumerate(loaded):
            content=heading(s['name'],d['date']+' · '+('仅内网可见' if s['visibility']=='private' else '每日精选'))+archives+blocks(d)
            for section in d.get('sections',[]):
                content+='<section class="mail-section"><h2 class="sticky-title">'+E(section.get('title'))+'</h2>'+''.join(card(r) for r in inbox_rows(dict(d,sections=[section]),s))+'</section>'
            document=shell(s['name'],'../',id,content); write(f'{id}/{d["date"]}.html',document)
            if n==0: write(f'{id}/index.html',document)
    if not inbox_only:
        shutil.copytree(ROOT/'media',out/'media',dirs_exist_ok=True)
        for asset in (ROOT/'assets').iterdir():
            if asset.is_file(): shutil.copyfile(asset,out/asset.name)
        hero=next((r for r in rows[:100] if r['images']),None)
        stream=[r for r in rows[:100] if r is not hero]
        for n,r in enumerate(latest_cards[:12]): stream.insert(min(2+n*5,len(stream)),r)
        content=heading('世界在发生，重点在这里','从资讯到订阅，拾起时光里的重要瞬间。')
        if hero: content+='<div class="section-label"><b>要闻</b><span>EDITOR’S PICK / 01</span></div>'+card(hero,'hero')
        content+=filters()+'<div class="stream-title"><h2>最新动态</h2><span>实时收录 · 持续更新</span></div>'+''.join(card(r) for r in stream)
        write('index.html',shell('首页','','home',content))
        write('all.html',shell('全部','','all',heading('全部动态','完整收录，按来源和分类查找。')+filters()+''.join(card(r) for r in rows+latest_cards)))
        write('hot.html',shell('热点','','hot',heading('此刻热点','过去 48 小时 · 跨频道报道与关键词聚合。')+''.join(card(r) for r in hot)))
        for source in sources:
            if source['type']=='telegram':
                source_rows=[r for r in rows if r['source_id']==source['id']]
                if source_rows: write(source['id']+'/index.html',shell(source['name'],'../',source['id'],heading(source['name'],'Telegram 频道资讯')+''.join(card(r) for r in source_rows)))
        days=sorted({r['day'] for r in rows},reverse=True)
        for day in days:
            write(f'archive/{day}.html',shell(day+' 日报','../','archive',heading(day+' 日报','按北京时间归档')+filters()+''.join(card(r) for r in rows if r['day']==day)))
        write('archive/index.html',shell('日报归档','../','archive',heading('每一天，都有迹可循','回看世界变化的每个切片。')+''.join(f'<p><a href="{d}.html">{d} 日报 ↗</a></p>' for d in days)))
        write('.nojekyll','')
    if not private:
        forbidden=[s for s in cfg['sources'] if s['visibility']=='private']
        for s in forbidden:
            if (out/s['id']).exists(): raise RuntimeError('公开产物存在 private 目录')
        private_text=[]
        for source in forbidden:
            if source['type']=='inbox':
                for data,base in load_issues(source,True):
                    for section in data.get('sections',[]):
                        for item in section.get('items',[]):
                            private_text.extend(E(item.get(field)) for field in ('title','body') if len(item.get(field) or '')>=16)
                    for block in data.get('blocks',[]):
                        values=[block.get('title'),block.get('caption')]
                        for item in block.get('items',[]) or []:
                            values.extend([item] if isinstance(item,str) else [item.get('title'),item.get('body')])
                        private_text.extend(E(value) for value in values if isinstance(value,str) and len(value)>=16)
        for p in out.rglob('*'):
            if p.suffix in ('.html','.json','.webmanifest','.svg'):
                text=p.read_text()
                if any(s['name'] in text or f'{s["id"]}/' in text for s in forbidden): raise RuntimeError('公开产物存在 private 标记: '+str(p))
                if '邮件' in text: raise RuntimeError('公开产物存在私有栏目字样')
                if any(value in text for value in private_text): raise RuntimeError('公开产物存在 private 内容: '+str(p))
    print(f'built {len(rows)} TG, {len(issues)} inbox sources -> {out}')

if __name__=='__main__':
    from datetime import datetime
    from zoneinfo import ZoneInfo
    build([],[],datetime.now(ZoneInfo('Asia/Shanghai')),inbox_only=True)

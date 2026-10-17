"""Static presentation shared by Telegram and configured inbox sources."""
import html, json, os, re, shutil
from pathlib import Path
from urllib.parse import urlsplit
from feeds import ROOT, config, private_mode, load_issues, compress_images
from light import light_css, photo_like
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
E = lambda v: html.escape(str(v or ''), quote=True)
ICONS = {'home':'<path d="m3 10 9-7 9 7v11H6V10M9 21v-8h6v8"/>','hot':'<path d="M13 3c2 6-3 6-1 10 2-1 3-3 3-4 7 7 4 12-3 12S3 14 8 8c0 4 2 4 2 4-1-5 3-6 3-9Z"/>','all':'<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h8m-8 4h8m-8 4h5"/>','archive':'<rect x="4" y="5" width="16" height="16" rx="3"/><path d="M8 3v4m8-4v4M4 10h16"/>','mail':'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m3 7 9 6 9-6"/>','world':'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>'}
ICONS['x'] = '<path d="M5 4h14a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3h-8l-6 3 1-4a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z"/><path d="M7 9h10M7 13h6"/>'
def icon(key): return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+ICONS.get(key, ICONS['all'])+'</svg>'
def link(url): return str(url or '') if urlsplit(str(url or '')).scheme in ('http','https') else ''

def section_icon(key):
    shapes = {
        'x':'<path d="M16 16h31a9 9 0 0 1 9 9v17a9 9 0 0 1-9 9H29L17 57l2-9a9 9 0 0 1-9-9V25a9 9 0 0 1 6-9Z" fill="var(--icon-shade)"/><path d="M16 11h29a9 9 0 0 1 9 9v17a9 9 0 0 1-9 9H27L14 53l3-10a9 9 0 0 1-9-9V20a9 9 0 0 1 8-9Z" fill="url(#status-paper)"/><path d="M18 23h17m-17 8h12"/><path d="M43 22c3 5-3 6-1 10 2-1 3-3 3-4 6 6 3 11-2 11s-8-5-4-9c0 3 1 3 1 3-1-5 2-6 3-11Z" fill="url(#status-sun)" stroke="none"/>',
        'code':'<rect x="9" y="14" width="46" height="38" rx="8" fill="url(#status-paper)"/><path d="m25 25-9 8 9 8m14-16 9 8-9 8m-4-20-6 24" stroke="var(--sun)" stroke-width="3"/>',
        'home':'<circle cx="46" cy="19" r="10" fill="url(#status-sun)" stroke="none"/><path d="M46 5V2m11 10 3-2M33 10l-2-2m27 16 3 1" stroke="var(--sun)"/><path d="m14 20 35 4 5 27-34 3Z" fill="var(--icon-shade)"/><path d="M10 19 43 16 46 49 15 53a4 4 0 0 1-4-4Z" fill="url(#status-paper)"/><path d="m43 16 7 7-6 1Z" fill="var(--icon-light)"/><path d="m16 26 21-2m-20 6 21-2" stroke="var(--sun)" stroke-width="3"/><path d="m17 36 8-1 1 9-8 1Z" fill="var(--sun)" stroke="none"/><path d="m30 35 8-1m-8 6 8-1m-8 6 8-1m-22 5 23-2"/><path d="m46 30 2 18c0 3 4 3 5 1" stroke="var(--icon-light)"/>',
        'hot':'<path d="M35 8c4 15-12 17-5 28 5-2 9-8 9-13 18 18 12 32-7 32C12 55 9 37 21 24c-1 9 4 11 4 11-3-13 6-18 10-27Z" fill="var(--sun)"/><path d="M30 46c-5-6 1-12 4-15-1 8 8 9 5 15-2 5-7 5-9 0Z" fill="url(#status-paper)" stroke="none"/>',
        'mail':'<rect x="11" y="19" width="43" height="34" rx="7" fill="url(#status-paper)"/><path d="m12 23 20 16 21-16M12 50l14-15m27 15L39 36"/><rect x="37" y="10" width="17" height="16" rx="5" fill="var(--sun)" stroke="none"/>',
        'world':'<circle cx="32" cy="31" r="23" fill="url(#status-paper)"/><ellipse cx="32" cy="31" rx="11" ry="23"/><path d="M10 31h44M14 18c11 6 25 6 36 0M14 44c11-6 25-6 36 0"/><path d="m24 16 8-5 7 7-4 10-10-3-5 9-7-6 3-11Zm16 18 10 4-8 11-5-6Z" fill="var(--sun)" stroke="none"/>',
        'archive':'<rect x="12" y="14" width="40" height="40" rx="8" fill="url(#status-paper)"/><path d="M12 24h40"/><path d="M13 23v-3a6 6 0 0 1 6-6h26a6 6 0 0 1 6 6v3Z" fill="var(--sun)" stroke="none"/><path d="M23 9v10m18-10v10M22 34h5m10 0h5m-20 9h5"/><rect x="35" y="39" width="9" height="9" rx="3" fill="var(--sun)" stroke="none"/>',
        'all':'<rect x="17" y="12" width="34" height="38" rx="7" transform="rotate(10 34 31)" fill="var(--wash)"/><rect x="11" y="18" width="35" height="36" rx="7" transform="rotate(-7 29 36)" fill="url(#status-paper)"/><path d="M19 37h19m-18 8h13"/><rect x="19" y="24" width="19" height="6" rx="3" fill="var(--sun)" stroke="none"/>'
    }
    return '<svg class="status-icon" data-section="'+key+'" viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="status-sun" x2=".6" y2="1"><stop stop-color="#ffe6a2"/><stop offset="1" stop-color="var(--sun)"/></linearGradient><linearGradient id="status-paper" x2=".7" y2="1"><stop stop-color="var(--icon-light)"/><stop offset="1" stop-color="var(--icon-shade)"/></linearGradient></defs><ellipse cx="32" cy="56" rx="22" ry="4" fill="var(--wash)"/><g fill="none" stroke="var(--ink-2)" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'+shapes.get(key,shapes['all'])+'</g></svg>'

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
    def image_path(image):
        return out/image if (out/image).is_file() else ROOT/image
    def qualifying(items):
        for item in items:
            for image in item.get('images',[]):
                if photo_like(str(image_path(image))): return item,image
        return None,''
    def newest(items):
        return sorted(items,key=lambda r:r['ts'],reverse=True)
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
    columns=[s for s in sorted(sources,key=lambda s:s['nav'].get('order',100)) if s['id'] in issues and s['nav'].get('enabled')]
    entries=[('home','index.html','首页','home'),('hot','hot.html','热点','hot'),('all','all.html','全部','all'),('archive','archive/index.html','日报','archive')]
    entries += [(s['id'],s['id']+'/index.html',s['name'],s['icon']) for s in sources if s['type']=='telegram' and any(r['source_id']==s['id'] for r in rows)]
    entries += [(s['id'],s['id']+'/index.html',s['name'],s['icon']) for s in columns]
    def nav(rel,active,bottom=False):
        core=[entries[0],entries[1],next((x for x in entries if x[0]=='mail'),entries[2]) if private else entries[2],entries[3]]
        extra=next((s for s in columns if s['id'] not in {x[0] for x in core}),None)
        chosen=entries if not bottom else core+([(extra['id'],extra['id']+'/index.html',extra['name'],extra['icon'])] if extra else [])
        result=''.join(f'<a href="{rel}{path}" class="{"active" if active==key else ""}"'+(' aria-current="page"' if active==key else '')+f'>{icon(ic)}<span>{E(name)}</span></a>' for key,path,name,ic in chosen)
        return result.replace('邮件精华','邮件').replace('环球要闻','环球').replace('GitHub 热门','GitHub') if bottom else result
    def column_row():
        cards=[]
        for s in columns:
            data=issues[s['id']][0][0]
            count=sum(len(section['items']) for section in data.get('sections',[]))
            lead=next((item if isinstance(item,str) else item.get('title') or item.get('body') for b in data.get('blocks',[]) if b.get('type')=='oneliner' for item in b.get('items',[]) if item),None)
            lead=lead or f'{data["date"]} · {count} 条'
            cards.append(f'<a class="column-entry g-card" href="{s["id"]}/index.html">{section_icon(s["icon"])}<span class="column-copy"><b>{E(s["name"])}</b><span>{E(lead)}</span></span></a>')
        return '<section class="columns" aria-label="栏目"><div class="section-label"><b>栏目</b></div><div class="column-row">'+''.join(cards)+'</div></section>' if cards else ''
    def sidebar(rel):
        return '<aside><section class="sidebox"><div class="eyebrow">ON THE RADAR</div><h2>此刻，大家在看</h2>'+''.join(f'<a class="rank" href="{E(r["url"])}"><b>{n:02}</b><span>{E(r["title"])}</span></a>' for n,r in enumerate(hot[:5],1))+'</section><section class="sidebox"><div class="eyebrow">YOUR SOURCES</div><h2>消息从这里来</h2>'+''.join(f'<div class="source"><i style="color:{E(s["color"])}">{icon(s["icon"])}</i><span>{E(s["name"])}</span><small>{"TG" if s["type"]=="telegram" else "INBOX"}</small></div>' for s in sources if s['type']=='telegram' or s['id'] in issues)+'</section></aside>'
    css=(ROOT/'style.css').read_text(); js=(ROOT/'app.js').read_text()
    logo=''
    def shell(title,rel,active,body,hero_image=None):
        section=by_id.get(active,{}).get('icon',active)
        body=re.sub(r'<svg class="status-icon".*?</svg>',lambda _:section_icon(section),body,count=1)
        body='<svg class="glass-filters" aria-hidden="true" width="0" height="0"><defs><filter id="lg" x="0%" y="0%" width="100%" height="100%" color-interpolation-filters="sRGB"><feTurbulence type="fractalNoise" baseFrequency=".012 .018" numOctaves="1" seed="7" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="16" xChannelSelector="R" yChannelSelector="G" result="lens"/><feImage href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%27100%27 height=%27100%27%3E%3Crect width=%27100%27 height=%27100%27 fill=%27white%27/%3E%3Crect x=%278%27 y=%278%27 width=%2784%27 height=%2784%27 rx=%2716%27 fill=%27black%27/%3E%3C/svg%3E" preserveAspectRatio="none" result="rim"/><feColorMatrix in="rim" type="luminanceToAlpha" result="rim-alpha"/><feComposite in="lens" in2="rim-alpha" operator="in" result="edge"/><feComposite in="SourceGraphic" in2="rim-alpha" operator="out" result="center"/><feMerge><feMergeNode in="center"/><feMergeNode in="edge"/></feMerge></filter></defs></svg>'+body
        # All card media paths are root-relative to the generated tree, never host-root URLs.
        body=re.sub(r'(src|data-image)="(?!https?://)([^"]+)"',lambda m:f'{m[1]}="{rel}{m[2]}"',body)
        more='<dialog class="more-nav" id="more-nav" aria-label="全部导航">'+''.join(f'<a href="{rel}{p}">{E(n)}</a>' for k,p,n,ic in entries)+'</dialog>'
        candidates=[p[len(rel):] if rel and p.startswith(rel) else p for p in re.findall(r'<img src="([^"]+)"',body)]
        image=hero_image if hero_image is not None else next((p for p in candidates if photo_like(str(image_path(p)))), '')
        if rel and image.startswith(rel): image=image[len(rel):]
        photo=(out/image) if image and (out/image).is_file() else ROOT/image
        illumination=light_css(str(photo) if image else '')
        theme="const t=new URLSearchParams(location.search).get('theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;"
        search_icon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></svg>'
        menu_icon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M5 7h14M5 12h14M5 17h14"/></svg>'
        return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="theme-color" content="#eee8df"><title>{E(title)} · 拾光热点</title><link rel="icon" href="{rel}favicon.ico?v=20261017-4"><link rel="icon" type="image/svg+xml" href="{rel}favicon.svg?v=20261017-4"><link rel="apple-touch-icon" href="{rel}apple-touch-icon.png?v=20261017-4"><link rel="manifest" href="{rel}manifest.webmanifest?v=20261017-4"><script>{theme}</script><style>{css}{illumination}</style></head><body data-light-source="{E(image or 'fallback-sky')}"><div class="g-light" aria-hidden="true"></div><header><div class="top g-column"><a class="brand" href="{rel}index.html">{logo}拾光热点</a><nav class="desktop-nav g-seg" aria-label="主导航">{nav(rel,active,True)}</nav><div class="tools"><button id="search-toggle" aria-label="搜索">{search_icon}</button><button id="more-toggle" aria-label="菜单" aria-expanded="false">{menu_icon}</button></div></div></header><div class="layout g-column"><main>{body}<p id="none" hidden>换个词，再找找。</p><footer>今日信息，留一份清晰。<span>{now.strftime('%m-%d %H:%M')} 北京时间</span></footer></main></div><nav class="bottom" aria-label="主导航">{nav(rel,active,True)}</nav>{more}<dialog class="lightbox" aria-label="图片查看器"><button class="lightbox-close" aria-label="关闭">×</button><img alt="放大图片"></dialog><script>{js}</script></body></html>'''
    def heading(title,desc):
        status='<svg class="status-icon"></svg>'
        return f'<div class="page-intro">{status}<h1>{E(title)}</h1><p>{E(desc)}</p></div>'
    def card(r,kind=None,reading=False):
        imgs=r.get('images',[]); kind=kind or ('multi' if len(imgs)>1 else 'side' if imgs else 'text')
        url=link(r.get('url')); title=f'<a href="{E(url)}" target="_blank" rel="noopener noreferrer">{E(r["title"])}</a>' if url else E(r['title'])
        pictures=''.join(f'<button class="photo {"screenshot" if not photo_like(str(image_path(p))) else ""}" data-image="{E(p)}" aria-label="放大图片"><img src="{E(p)}" alt="{E(r["title"])}" loading="lazy"></button>' for p in imgs[:4])
        source=by_id[r['source_id']]
        surface='g-sheet mail-reading' if reading and source.get('adapter')=='mail' else 'g-card'
        labels=''.join(f'<span class="source-label g-wash">{E(part.strip())}</span>' for part in re.split(r'[|｜]',r['name']) if part.strip())
        return f'<article class="card news {surface} {kind}" data-cat="{E(r["cat"])}" data-ch="{E(r["ch"])}"><div class="copy"><div class="meta"><span class="g-wash">{E(r["cat"])}</span>{labels}<time>{E(r["ts"][11:16] or r["day"])}</time></div><h2>{title}</h2><p>{E(r["body"])}</p></div>{f"<div class='pictures'>{pictures}</div>" if pictures else ""}<div class="foot"><span>{E(r["day"])}</span><button class="expand" aria-expanded="false">展开全文 ＋</button>{f"<a href='{E(url)}' target='_blank' rel='noopener noreferrer'>阅读原文 ↗</a>" if url else ""}</div></article>'
    def filters(items):
        present={r['source_id'] for r in items}
        cats=['推荐']+list(cfg['categories'])+['综合']+[s['name'] for s in sources if s['id'] in issues and s['id'] in present]
        return '<div class="filters">'+''.join(f'<button class="pill {"selected" if i==0 else ""}" data-value="{E(c if i else "")}">{E(c)}</button>' for i,c in enumerate(cats))+'</div><div class="searchline"><input id="q" type="search" placeholder="搜索资讯" aria-label="搜索资讯"><select id="channel" aria-label="筛选来源"><option value="">全部来源</option>'+''.join(f'<option value="{E(s["channel"] if s["type"]=="telegram" else s["id"])}">{E(s["name"])}</option>' for s in sources if s['id'] in present)+'</select></div>'
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
        s=by_id[id]; archives=('<div class="archives g-seg" aria-label="往期列表">'+''.join(f'<a href="{d["date"]}.html">{d["date"]}</a>' for d,base in loaded)+'</div>') if len(loaded)>1 else ''
        for n,(d,base) in enumerate(loaded):
            count=sum(len(section['items']) for section in d.get('sections',[]))
            lead=f'今天邮箱里 {count} 封值得看' if s.get('adapter')=='mail' else '看看今天世界发生了什么' if s.get('adapter')=='world' else s['name']
            note=d['date']+' · '+s['name']+' · '+('仅内网可见' if s['visibility']=='private' else '每日精选')
            if s.get('adapter')=='x':
                count=sum(len(section['items']) for section in d.get('sections',[]) if section['title']=='推特爆款')
                lead=f'今天推特上 {count} 条爆款'; note=d['date']+' · 来自 X 公开帖'
            content=heading(lead,note)+archives+blocks(d)
            for section in d.get('sections',[]):
                section_title=''.join('<span class="g-wash">'+E(part.strip())+'</span>' for part in re.split(r'[|｜]',section.get('title') or '') if part.strip())
                content+='<section class="mail-section"><h2 class="sticky-title">'+section_title+'</h2>'+''.join(card(r,reading=True) for r in inbox_rows(dict(d,sections=[section]),s))+'</section>'
            first=inbox_rows(d,s)
            _,first_image=qualifying(first)
            document=shell(s['name'],'../',id,content,first_image); write(f'{id}/{d["date"]}.html',document)
            if n==0: write(f'{id}/index.html',document)
    if not inbox_only:
        shutil.copytree(ROOT/'media',out/'media',dirs_exist_ok=True)
        for asset in (ROOT/'assets').iterdir():
            if asset.is_file(): shutil.copyfile(asset,out/asset.name)
        local_now=now.astimezone(ZoneInfo('Asia/Shanghai'))
        def in_last_day(r):
            stamp=datetime.fromisoformat(r['ts'])
            if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
            return local_now-timedelta(hours=24)<=stamp<=local_now
        light_item,home_image=qualifying(r for r in hot if in_last_day(r))
        hero=light_item or next(iter(hot),None)
        if light_item:
            hero['images']=[home_image]+[p for p in hero['images'] if p!=home_image]
        stream=[r for r in rows[:100] if r is not hero]
        for n,r in enumerate(latest_cards[:12]): stream.insert(min(2+n*5,len(stream)),r)
        today=now.date().isoformat()
        count=sum(r['day']==today for r in rows+latest_cards)
        note=f'{now.month}月{now.day}日 周{"一二三四五六日"[now.weekday()]} · 更新于 {now:%H:%M} · {len({r["source_id"] for r in rows+latest_cards})} 个来源'
        content=heading(f'今天 {count} 条要闻',note)
        if hero: content+='<div class="section-label"><b>此刻要闻</b><span>精选</span></div>'+card(hero,'hero')
        content+=column_row()+filters(stream+([hero] if hero else []))+'<div class="stream-title"><h2>最新动态</h2><span>实时收录 · 持续更新</span></div>'+''.join(card(r) for r in stream)
        write('index.html',shell('首页','','home',content,home_image))
        write('all.html',shell('全部','','all',heading('全部动态','完整收录，按来源和分类查找。')+filters(rows+latest_cards)+''.join(card(r) for r in rows+latest_cards)))
        write('hot.html',shell('热点','','hot',heading('这几条大家都在说','过去 48 小时 · 多个来源共同关注')+''.join(f'<div class="ordinal">{n:02}</div>'+card(r) for n,r in enumerate(hot,1))))
        for source in sources:
            if source['type']=='telegram':
                source_rows=[r for r in rows if r['source_id']==source['id']]
                if source_rows: write(source['id']+'/index.html',shell(source['name'],'../',source['id'],heading('看看'+source['name']+'的新消息','Telegram 频道资讯')+''.join(card(r) for r in source_rows),qualifying(newest(source_rows))[1]))
        days=sorted({r['day'] for r in rows},reverse=True)
        for day in days:
            day_rows=[r for r in rows if r['day']==day]
            write(f'archive/{day}.html',shell(day+' 日报','../','archive',heading(day+' 日报','按北京时间归档')+filters(day_rows)+''.join(card(r) for r in day_rows)))
        write('archive/index.html',shell('日报归档','../','archive',heading('每一天，都有迹可循','回看世界变化的每个切片。')+''.join(f'<a class="g-card archive-entry" href="{d}.html">{d} 日报 ↗</a>' for d in days)))
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

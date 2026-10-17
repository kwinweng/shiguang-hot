"""Static presentation shared by Telegram and configured inbox sources."""
import html, json, os, re, shutil, hashlib
import ctypes, fcntl, signal, tempfile, threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from feeds import ROOT, config, private_mode, load_issues, compress_images
from light import light_css, photo_like
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
E = lambda v: html.escape(str(v or ''), quote=True)
ICONS = {'home':'<path d="m3 10 9-7 9 7v11H6V10M9 21v-8h6v8"/>','hot':'<path d="M13 3c2 6-3 6-1 10 2-1 3-3 3-4 7 7 4 12-3 12S3 14 8 8c0 4 2 4 2 4-1-5 3-6 3-9Z"/>','all':'<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h8m-8 4h8m-8 4h5"/>','archive':'<rect x="4" y="5" width="16" height="16" rx="3"/><path d="M8 3v4m8-4v4M4 10h16"/>','mail':'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m3 7 9 6 9-6"/>','world':'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>'}
ICONS['x'] = '<path d="M5 4h14a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3h-8l-6 3 1-4a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z"/><path d="M7 9h10M7 13h6"/>'
ICONS['film'] = '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>'
ICONS['note'] = '<path d="M4 20l4-1L19.5 7.5a2.12 2.12 0 0 0-3-3L5 16l-1 4Z"/><path d="m13.5 6.5 4 4"/>'
def icon(key): return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+ICONS.get(key, ICONS['all'])+'</svg>'
def link(url): return str(url or '') if urlsplit(str(url or '')).scheme in ('http','https') else ''

def visible(item, private):
    """Visibility gate; the dict form reserves per-user lists like {"users": [...]}."""
    value = item.get('visibility', 'public')
    if isinstance(value, dict): return private and bool(value.get('users'))
    return value == 'public' or (value == 'private' and private)

def entry_url(value):
    """App/entry links may be external HTTP(S) or an in-page anchor."""
    value = str(value or '')
    return value if value.startswith('#') or urlsplit(value).scheme in ('http', 'https') else ''

def read_json(path):
    try: data = json.loads(Path(path).read_text())
    except (OSError, ValueError): return {}
    return data if isinstance(data, dict) else {}

def world_oneliners(day):
    root = Path(os.getenv('WORLD_BRIEF_DIR', '/workspace/world-brief'))
    items = read_json(root / day / 'brief.json').get('oneliner') or []
    result = []
    for item in items:
        text = (item.get('title') or item.get('body')) if isinstance(item, dict) else item
        if text: result.append(str(text))
    return result[:4]

def open_todos(day, private):
    if not private: return []
    root = Path(os.getenv('TODO_DIR', '/workspace/feeds-inbox/todo'))
    items = read_json(root / day / 'todo.json').get('items') or []
    return [item for item in items if isinstance(item, dict) and item.get('status') == 'open' and item.get('title')][:5]

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

@contextmanager
def staged_output(destination):
    """Keep live output untouched until a complete tree passes validation."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination.with_name(destination.name+'.build.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # SIGKILL cannot run cleanup; reclaim abandoned staging trees next build.
        for stale in destination.parent.glob(destination.name+'.tmp-*'):
            if stale.is_dir() and not stale.is_symlink(): shutil.rmtree(stale)
        temporary=Path(tempfile.mkdtemp(prefix=destination.name+'.tmp-', dir=destination.parent))
        handlers={}
        def interrupted(signum, frame):
            raise SystemExit(128+signum)
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                handlers[sig]=signal.signal(sig, interrupted)
        try:
            if destination.exists():
                shutil.copytree(destination, temporary, dirs_exist_ok=True, symlinks=True)
            yield temporary
            if destination.exists():
                # Linux RENAME_EXCHANGE keeps the served path present throughout.
                libc=ctypes.CDLL(None, use_errno=True)
                exchange=libc.renameat2
                exchange.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
                exchange.restype=ctypes.c_int
                if exchange(-100,os.fsencode(temporary),-100,os.fsencode(destination),2):
                    error=ctypes.get_errno()
                    raise OSError(error,os.strerror(error),str(destination))
            else:
                os.rename(temporary,destination)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
            for sig,handler in handlers.items(): signal.signal(sig,handler)

def build(rows, hot, now, inbox_only=False):
    out = Path(os.getenv('SITE_OUT', ROOT/'site')).resolve()
    if out == ROOT or ROOT.is_relative_to(out): raise ValueError('SITE_OUT 不能覆盖仓库')
    with staged_output(out) as temporary:
        _build(rows, hot, now, temporary, inbox_only)
    print(f'built site -> {out}')

def _build(rows, hot, now, out, inbox_only=False):
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
    if not private:
        for source in cfg['sources']:
            if source['visibility']=='private': shutil.rmtree(out/source['id'],ignore_errors=True)
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
        result=[dict(title=i.get('title') or '未命名条目', body=i.get('body') or '', images=[im['file'] for im in i.get('images',[]) or [] if isinstance(im,dict) and im.get('file')], name=i.get('source') or ' / '.join(str(x) for x in i.get('sources',[]) or []) or s['name'], cat=s['name'], source_id=s['id'], ch=s['id'], day=data['date'], ts=i.get('date') or data['date'], url=link(i.get('link'))) for section in data.get('sections',[]) for i in section['items']]
        # Block-only issues still join the common home candidate pool.
        if not result:
            for b in data.get('blocks',[]):
                for item in b.get('items',[]) if b.get('type') in ('oneliner','tomorrow') else []:
                    title=item if isinstance(item,str) else item.get('title') or item.get('body')
                    if title: result.append(dict(title=title,body='' if isinstance(item,str) else item.get('body',''),images=[],name=s['name'],cat=s['name'],source_id=s['id'],ch=s['id'],day=data['date'],ts=data['date'],url=''))
            if not result and data.get('blocks'):
                result.append(dict(title=data.get('title') or s['name'],body=' · '.join(b.get('title') or {'markets':'市场看板','chart':'一张图'}.get(b.get('type'),'') for b in data['blocks']),images=[],name=s['name'],cat=s['name'],source_id=s['id'],ch=s['id'],day=data['date'],ts=data['date'],url=f'{s["id"]}/{data["date"]}.html'))
        return result
    for s in sources:
        if s['type']!='inbox': continue
        loaded=load_issues(s,private)
        # Preserve adapter-owned media and other files; regenerate only pages.
        for page in (out/s['id']).glob('*.html'): page.unlink()
        if not loaded: continue
        issues[s['id']]=[(compress_images(d,base,out/s['id']/'img',s['id']+'/img/'),base) for d,base in loaded]
        latest_cards.extend(inbox_rows(issues[s['id']][0][0],s))
    columns=[s for s in sorted(sources,key=lambda s:s['nav'].get('order',100)) if s['id'] in issues and s['nav'].get('enabled')]
    entries=[('home','index.html','首页','home'),('news','hot.html','资讯','hot'),('all','all.html','全部','all'),('daily','archive/index.html','日报','archive')]
    favorites=cfg.get('nav',{}).get('favorites',{'enabled':True,'label':'收藏','path':'favorites.html','column':True})
    if favorites.get('enabled'):
        entries.append(('favorites',favorites['path'],favorites['label'],'all'))
    entries += [(s['id'],s['id']+'/index.html',s['name'],s['icon']) for s in sources if s['type']=='telegram' and any(r['source_id']==s['id'] for r in rows)]
    entries += [(s['id'],s['id']+'/index.html',s['name'],s['icon']) for s in columns]
    def nav(rel,active,bottom=False):
        mode='private' if private else 'public'
        slots=cfg.get('nav',{}).get('tabs',{}).get(mode,['mail' if private else 'all','daily','home','news','x'])
        if len(slots)!=5 or slots[2]!='home' or len(set(slots))!=5:
            raise ValueError('nav.tabs 必须为五个不同槽位，首页居中')
        lookup={entry[0]:entry for entry in entries}
        labels={'mail':'邮件','all':'全部','favorites':favorites['label'],'daily':'日报','home':'首页','news':'资讯','x':'推特爆款'}
        result=''
        for key in slots if bottom else lookup:
            name=labels.get(key,by_id.get(key,{}).get('name',key))
            if key not in lookup:
                result+=f'<span class="nav-unavailable" aria-disabled="true">{E(name)}</span>'
                continue
            _,path,_,ic=lookup[key]
            classes=('active ' if active==key else '')+('home-slot' if key=='home' else '')
            content='<svg class="home-dot" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/></svg>' if key=='home' else f'{icon(ic)}<span>{E(name)}</span>'
            result+=f'<a href="{rel}{path}" class="{classes.strip()}"'+(' aria-label="首页"' if key=='home' else '')+(' aria-current="page"' if active==key else '')+f'>{content}</a>'
        return result
    def column_row():
        cards=[]
        if favorites.get('enabled') and favorites.get('column'):
            cards.append(f'<a class="column-entry g-card" href="{E(favorites["path"])}"><span class="column-copy"><b>{E(favorites["label"])}</b><span>留住想再读的内容</span></span></a>')
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
        section=by_id.get(active,{}).get('icon',{'daily':'archive','news':'hot'}.get(active,active))
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
        page_title='拾光 · 今天' if active=='home' else f'{E(title)} · 拾光'
        return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="theme-color" content="#eee8df"><title>{page_title}</title><link rel="icon" href="{rel}favicon.ico?v=20261017-8"><link rel="icon" type="image/svg+xml" href="{rel}favicon.svg?v=20261017-8"><link rel="apple-touch-icon" href="{rel}apple-touch-icon.png?v=20261017-8"><link rel="manifest" href="{rel}manifest.webmanifest?v=20261017-8"><script>{theme}</script><style>{css}{illumination}</style></head><body data-bookmark-scope="{'private' if private else 'public'}" data-light-source="{E(image or 'fallback-sky')}"><div class="g-light" aria-hidden="true"></div><header><div class="top g-column"><a class="brand" href="{rel}index.html">{logo}拾光</a><nav class="desktop-nav g-seg" aria-label="主导航">{nav(rel,active,True)}</nav><div class="tools"><button id="search-toggle" aria-label="搜索">{search_icon}</button><button id="more-toggle" aria-label="菜单" aria-expanded="false">{menu_icon}</button></div></div></header><div class="layout g-column"><main>{body}<p id="none" hidden>换个词，再找找。</p><footer>今日信息，留一份清晰。<span>{now.strftime('%m-%d %H:%M')} 北京时间</span></footer></main></div><nav class="bottom" aria-label="主导航">{nav(rel,active,True)}</nav>{more}<dialog class="lightbox" aria-label="图片查看器"><button class="lightbox-close" aria-label="关闭">×</button><img alt="放大图片"></dialog><script>{js}</script></body></html>'''
    def heading(title,desc):
        status='<svg class="status-icon"></svg>'
        return f'<div class="page-intro">{status}<h1>{E(title)}</h1><p>{E(desc)}</p></div>'
    def card(r,kind=None,reading=False):
        imgs=r.get('images',[]); kind=kind or ('multi' if len(imgs)>1 else 'side' if imgs else 'text')
        url=link(r.get('url')); title=f'<a href="{E(url)}" target="_blank" rel="noopener noreferrer">{E(r["title"])}</a>' if url else E(r['title'])
        pictures=''.join(f'<button class="photo {"screenshot" if not photo_like(str(image_path(p))) else ""}" data-image="{E(p)}" aria-label="放大图片"><img src="{E(p)}" alt="{E(r["title"])}" loading="lazy"></button>' for p in imgs[:4])
        source=by_id[r['source_id']]
        surface='g-sheet mail-reading' if reading and source.get('adapter')=='mail' else 'g-card'
        labels=f'<span class="source-label g-wash" data-source="{E(source["id"])}">{E(source["name"])}</span>'
        if r['name']!=source['name']:
            labels+=''.join(f'<span class="source-label g-wash">{E(part.strip())}</span>' for part in re.split(r'[|｜]',r['name']) if part.strip())
        identity=json.dumps([r['source_id'],r.get('id') or url or r['title'],r['ts']],ensure_ascii=False)
        saved=dict(id=hashlib.sha256(identity.encode()).hexdigest(),title=r['title'],url=url,source=source['name'],time=r['ts'],snippet=r['body'][:500])
        bookmark=f'<button class="bookmark" data-bookmark="{E(json.dumps(saved,ensure_ascii=False))}" aria-pressed="false" aria-label="收藏"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M6 4h12v17l-6-4-6 4Z"/></svg></button>'
        labels+=bookmark
        return f'<article class="card news {surface} {kind}" data-cat="{E(r["cat"])}" data-ch="{E(r["ch"])}"><div class="copy"><div class="meta"><span class="g-wash">{E(r["cat"])}</span>{labels}<time>{E(r["ts"][11:16] or r["day"])}</time></div><h2>{title}</h2><p>{E(r["body"])}</p></div>{f"<div class='pictures'>{pictures}</div>" if pictures else ""}<div class="foot"><span>{E(r["day"])}</span><button class="expand" aria-expanded="false">展开全文 ＋</button>{f"<a href='{E(url)}' target='_blank' rel='noopener noreferrer'>阅读原文 ↗</a>" if url else ""}</div></article>'
    def filters(items):
        present={r['source_id'] for r in items}
        cats=['推荐']+list(cfg['categories'])+['综合']+[s['name'] for s in sources if s['id'] in issues and s['id'] in present]
        return '<div class="filters">'+''.join(f'<button class="pill {"selected" if i==0 else ""}" data-value="{E(c if i else "")}" aria-pressed="{"true" if i==0 else "false"}">{E(c)}</button>' for i,c in enumerate(cats))+'</div><div class="searchline"><input id="q" type="search" placeholder="搜索资讯" aria-label="搜索资讯"><select id="channel" aria-label="筛选来源"><option value="">全部来源</option>'+''.join(f'<option value="{E(s["channel"] if s["type"]=="telegram" else s["id"])}">{E(s["name"])}</option>' for s in sources if s['id'] in present)+'</select></div>'
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
        if favorites.get('enabled'):
            write(favorites['path'],shell(favorites['label'],'','favorites',heading('留住想再读的内容','收藏保存在这台设备上。')+'<div id="favorites-list"></div><p id="favorites-empty" class="g-card favorites-empty">还没有收藏，点卡片上的书签收藏</p><p id="favorites-status" role="status" aria-live="polite"></p>'))
        shutil.copytree(ROOT/'media',out/'media',dirs_exist_ok=True)
        for asset in (ROOT/'assets').iterdir():
            if asset.is_file(): shutil.copyfile(asset,out/asset.name)
        local_now=now.astimezone(ZoneInfo('Asia/Shanghai'))
        def rank(r):
            try: stamp=datetime.fromisoformat(r['ts'].replace('Z','+00:00'))
            except ValueError: stamp=datetime.fromisoformat(r['day'])
            stamp=stamp.replace(tzinfo=stamp.tzinfo or ZoneInfo('Asia/Shanghai'))
            age=max(0,(local_now-stamp).total_seconds()/3600)
            return by_id[r['source_id']].get('home_weight',1)/(1+age/24)
        # Round-based ranking gives each source a turn before a source repeats.
        buckets={}
        for s in sources:
            candidates=[r for r in rows+latest_cards if r['source_id']==s['id']]
            buckets[s['id']]=sorted(candidates,key=lambda r:(rank(r),r['ts']),reverse=True)[:s.get('home_cap',4 if s['type']=='telegram' else 8)]
        ranked=[]
        for n in range(max((len(v) for v in buckets.values()),default=0)):
            ranked.extend(sorted((v[n] for v in buckets.values() if len(v)>n),key=rank,reverse=True))
        hero=next(iter(ranked),None)
        home_image=qualifying([hero] if hero else [])[1]
        stream=ranked[1:]
        today=local_now.date().isoformat()
        today_items=[r for r in rows+latest_cards if r['day']==today]
        count=len(today_items)
        def today_card(r):
            source=by_id[r['source_id']]; url=link(r.get('url'))
            title=f'<a href="{E(url)}" target="_blank" rel="noopener noreferrer">{E(r["title"])}</a>' if url else E(r['title'])
            note=f'<p class="note">{E(r["body"][:120])}</p>' if r.get('body') else ''
            return f'<article class="g-card news today-card"><div class="meta"><span class="g-wash">{E(source["name"])}</span><time>{E(r["ts"][11:16] or r["day"])}</time></div><h3>{title}</h3>{note}</article>'
        def today_picks():
            hot_first=next((r for r in today_items if r['source_id']=='hot-daily'),None)
            picks=[hot_first] if hot_first else []
            candidates=[]
            for s in sources:
                if hot_first and s['id']=='hot-daily': continue
                options=[r for r in today_items if r['source_id']==s['id']]
                if options: candidates.append(max(options,key=lambda r:(rank(r),r['ts'])))
            candidates.sort(key=lambda r:(rank(r),r['ts']),reverse=True)
            return (picks+candidates)[:5]
        def today_section():
            parts=''
            picks=today_picks()
            if picks: parts+='<div class="today-list">'+''.join(today_card(r) for r in picks)+'</div>'
            oneliners=world_oneliners(today)
            if oneliners:
                more='<a class="card-more" href="world/index.html">环球要闻 →</a>' if 'world' in issues else ''
                parts+='<article class="g-card today-brief"><div class="card-head"><h3>环球早知道</h3></div><ul class="points">'+''.join(f'<li><span class="dot"></span><span>{E(text)}</span></li>' for text in oneliners)+'</ul>'+more+'</article>'
            todos=open_todos(today,private)
            if todos:
                items_html=''
                for item in todos:
                    url=entry_url(item.get('link'))
                    title=f'<a href="{E(url)}">{E(item["title"])}</a>' if url else E(item['title'])
                    due=f'<span class="todo-due">{E(item["due"])}</span>' if item.get('due') else ''
                    items_html+=f'<li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/></svg><span class="todo-title">{title}</span>{due}</li>'
                parts+='<article class="g-card today-todo"><div class="card-head"><h3>待办</h3><span class="badge">私密</span></div><ul class="todos">'+items_html+'</ul></article>'
            if not parts: return ''
            return '<section class="today" aria-label="今日"><div class="section-label"><b>今日</b></div><div class="today-stack">'+parts+'</div></section>'
        def apps_section():
            apps=sorted((a for a in cfg.get('apps',[]) if visible(a,private) and entry_url(a.get('url'))),key=lambda a:(a.get('order',100),str(a.get('id',''))))
            if not apps: return ''
            cards=''
            for app in apps:
                url=entry_url(app['url']); external=' target="_blank" rel="noopener noreferrer"' if url.startswith('http') else ''
                tile_icon=icon(app.get('icon') or 'all').replace('<svg ','<svg class="tile-ico" ',1)
                cards+=f'<a class="g-tile" href="{E(url)}"{external}>{tile_icon}<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg><span class="tile-title">{E(app.get("name"))}</span><span class="tile-note">{E(app.get("note"))}</span></a>'
            return '<section class="apps" aria-label="常用"><div class="section-label"><b>常用</b></div><div class="tiles">'+cards+'</div></section>'
        note=f'{now.month}月{now.day}日 周{"一二三四五六日"[now.weekday()]} · 更新于 {now:%H:%M} · {len({r["source_id"] for r in rows+latest_cards})} 个来源'
        content=heading(f'今天 {count} 件值得看' if count else '今天值得看',note)
        content+=today_section()
        content+=column_row()+apps_section()
        if hero: content+='<div class="section-label"><b>此刻要闻</b><span>精选</span></div>'+card(hero,'hero')
        content+=filters(stream+([hero] if hero else []))+'<div class="stream-title"><h2>最新动态</h2><span>实时收录 · 持续更新</span></div>'+''.join(card(r) for r in stream)
        write('index.html',shell('首页','','home',content,home_image))
        write('all.html',shell('全部','','all',heading('全部动态','完整收录，按来源和分类查找。')+filters(rows+latest_cards)+''.join(card(r) for r in rows+latest_cards)))
        write('hot.html',shell('资讯','','news',heading('这几条大家都在说','过去 48 小时 · 多个来源共同关注')+''.join(f'<div class="ordinal">{n:02}</div>'+card(r) for n,r in enumerate(hot,1))))
        for source in sources:
            if source['type']=='telegram':
                source_rows=[r for r in rows if r['source_id']==source['id']]
                if source_rows: write(source['id']+'/index.html',shell(source['name'],'../',source['id'],heading('看看'+source['name']+'的新消息','Telegram 频道资讯')+''.join(card(r) for r in source_rows),qualifying(newest(source_rows))[1]))
        days=sorted({r['day'] for r in rows}|{d['date'] for loaded in issues.values() for d,_ in loaded},reverse=True)
        def digest(day):
            content=''
            ordered=sorted(sources,key=lambda s:(s.get('daily_order',50 if s['type']=='telegram' else 45),s.get('nav',{}).get('order',100),s['id']))
            telegram=[s for s in ordered if s['type']=='telegram']
            for s in [s for s in ordered if s['type']=='inbox']:
                data=next((d for d,_ in issues.get(s['id'],[]) if d['date']==day),None)
                if data:
                    content+=f'<section class="digest-source" data-source="{E(s["id"])}"><h2 class="sticky-title">{E(s["name"])}</h2>'+blocks(data)+''.join(card(r) for r in inbox_rows(dict(data,blocks=[]),s))+'</section>'
            tg=[r for s in telegram for r in rows if r['source_id']==s['id'] and r['day']==day]
            if tg:
                content+='<section class="digest-source"><h2 class="sticky-title">TG 资讯</h2>'
                for topic in list(cfg['categories'])+['综合']:
                    group=[r for r in tg if r['cat']==topic]
                    if group: content+=f'<h3 class="sticky-title">{E(topic)}</h3>'+''.join(card(r) for r in group)
                content+='</section>'
            return content
        for day in days:
            write(f'archive/{day}.html',shell(day+' 日报','../','daily',heading(day+' 日报','按北京时间汇集各来源精选')+digest(day)))
        write('archive/index.html',shell('日报','../','daily',heading('每一天，都有迹可循','回看世界变化的每个切片。')+('<div class="archives">'+''.join(f'<a href="{d}.html">{d} 日报</a>' for d in days)+'</div>'+digest(days[0]) if days else '')))
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

"""Standalone review page. Not imported by the production site builder."""
from shiguang.site.ui import e, icon, news_card, media_card, bottom_nav, fold_run
from shiguang.site.phosphor import license_notice

PLAY_GROUPS = ['北京', '全国和世界', '线上', '看·读']
BUY_GROUPS = ['数码', '家居户外', '3D 打印', '狗狗', '大促']
CATEGORY_ICONS = {
    '全部': 'grid', '北京': 'pin', '全国和世界': 'globe', '线上': 'monitor',
    '看·读': 'book', '数码': 'devices', '家居户外': 'tent', '3D 打印': 'cube',
    '狗狗': 'paw', '大促': 'tag', '科技': 'cpu', '社会': 'users',
    '环球': 'globe', '开发者': 'code',
}


def note(tokens, do='用同一套组件保持一致。', dont='不要单独改组件里的色值。'):
    return f'<div class="token-caption">{e(tokens)}</div><div class="do-dont"><b>Do</b>{e(do)}<br><b>Don’t</b>{e(dont)}</div>'


def specimen(title, body, tokens, do='真实交互可用，状态有文字。', dont='不要只用颜色表达状态。'):
    return f'<article class="specimen"><h3>{title}</h3>{body}{note(tokens,do,dont)}</article>'


def heading(index, title, subtitle):
    return f'<header class="review-intro"><div><span class="eyebrow muted">SHIGUANG / DESIGN SYSTEM · {index}</span><h1>{title}</h1><p>{subtitle}</p></div><span class="review-badge">v0.5 · 待视觉评审</span></header>'


def section_heading(title, index='', meta='', action=''):
    return f'<div class="section-heading"><span class="index">{index}</span><h2>{title}</h2><small>{meta}</small>{action}</div>'


def search(scope, placeholder='搜索标题、来源或关键词'):
    return f'<label class="search-field">{icon("search")}<input type="search" data-search="{scope}" aria-label="{placeholder}" placeholder="{placeholder}"><button class="icon-button" type="button" data-clear-search="{scope}" aria-label="清空搜索">{icon("x")}</button></label>'


def filters(scope, labels, *, dog=False):
    buttons = ''.join(f'<button class="chip" data-filter-scope="{scope}" data-filter="{e(label)}" aria-pressed="{"true" if label == "全部" else "false"}">{icon(CATEGORY_ICONS[label])}<span>{e(label)}</span></button>' for label in labels)
    if dog:
        buttons += f'<button class="chip dog-filter" data-dog="{scope}" aria-pressed="false">{icon("paw")}<span>带狗</span></button>'
    return '<div class="filter-row" aria-label="分类筛选">' + buttons + '</div>'


def app_header(title, subtitle, mark, *, discovery=False):
    description = f'<p class="subtitle">{subtitle}</p>' if subtitle else ''
    if discovery:
        return f'<header class="app-heading discovery-heading"><h1>{title}</h1>{description}</header>'
    return f'''<header class="app-heading"><div class="date"><span>2026 年 10 月 20 日 · 周二</span><span class="mark">{mark}</span></div><h1>{title}</h1>{description}</header>'''


def screen_pages(data):
    items=data['items']; look=[x for x in items if x['kind']=='look']; play=[x for x in items if x['kind']=='play']; buy=[x for x in items if x['kind']=='buy']
    today = app_header('给今天，一点新鲜。','','今日')
    today += section_heading('资讯','01','把世界慢慢读完')+'<div class="horizontal-cards news-carousel" data-carousel="look" tabindex="0" role="region" aria-label="今日资讯，左右滑动">'+news_card(look[0],hero=True,layout='feature')+''.join(news_card(i,layout='feature') for i in look[1:4])+'</div>'
    today += f'<button class="button quiet see-all" data-page="look">看全部 {len(look)} 条{icon("arrow")}</button>'
    for kind,label,seq,index in [('play','好玩',play,'02'),('buy','好买',buy,'03')]:
        today+=section_heading(label,index,'值得花一点时间')+f'<div class="horizontal-cards" data-carousel="{kind}" tabindex="0" role="region" aria-label="今日{label}，左右滑动">'+''.join(media_card(i) for i in seq[:4])+'</div>'
        today+=f'<button class="button quiet see-all" data-page="{kind}">看全部 {len(seq)} 条{icon("arrow")}</button>'
    lookbody = app_header('资讯','顺着时间，读今天的世界。','READ',discovery=True)
    lookbody += '<div class="mode-tabs" role="tablist" aria-label="资讯视角">'+''.join(f'<button role="tab" id="tab-{key}" aria-controls="mode-{key}" class="mode-tab" data-mode="{key}" aria-selected="{"true" if key=="brief" else "false"}" tabindex="{0 if key=="brief" else -1}">{label}</button>' for key,label in [('brief','速览'),('hot','热点'),('columns','栏目')])+'</div>'
    lookbody += '<div class="sticky-filters"><div class="news-search-tools">'+search('look','搜索资讯')+'<select aria-label="筛选资讯来源" data-source><option value="全部">全部来源</option>'+''.join(f'<option>{e(s)}</option>' for s in dict.fromkeys(i['source'] for i in look))+'</select></div>'+filters('look',['全部','科技','社会','环球','开发者','数码'])+'</div>'
    lookbody += '<div id="mode-brief" role="tabpanel" aria-labelledby="tab-brief" data-look-view="brief">'+news_card(look[0],hero=True)+news_card(look[1])+fold_run(look[2:7])+''.join(news_card(i) for i in look[7:])+'</div>'
    hot = '<p class="sample-note">示例时间轴 · 每小时刷新 · 按首次报道小时分段，小时内按热度排序。</p><div class="hour-map" aria-label="24 小时示例时间轴">'
    for h in range(24):
        hot += f'<button data-hour="{h:02d}" style="--bar-height:{36 if h in (9,10) else 4}px" aria-label="{h:02d} 点，{"有示例热点" if h in (9,10) else "无示例热点"}"></button>'
    hot += '</div><div class="hour-map-caption"><span>00:00</span><span>12:00</span><span>23:00</span></div>'
    for hour in ['10','09']:
        hot+=f'<h3 class="timeline-hour" data-hour-heading="{hour}">10 月 20 日 · {hour}:00</h3>'
        hot+=''.join(news_card(i) for i in sorted((i for i in look if i['time'].startswith(hour)),key=lambda i:(i['heat'],i['time']),reverse=True))
    lookbody+=f'<div id="mode-hot" role="tabpanel" aria-labelledby="tab-hot" data-look-view="hot" hidden>{hot}</div>'
    columns='<p class="sample-note">栏目入口示例 · 正式版由来源注册自动扩展。</p>'
    for label,desc,url in [('GitHub 热门','项目按自己的发布时间进入速览。','https://github.com/trending'),('环球要闻','新闻类内容参与热点候选。','https://example.org/'),('推特爆款','保留在资讯，排除在热点之外。','https://example.org/')]:
        columns+=f'<article class="news-card"><h3>{label}</h3><p class="news-summary">{desc}</p><a class="source-link" target="_blank" rel="noopener noreferrer" href="{url}">打开栏目来源 {icon("external-link")}</a></article>'
    lookbody+=f'<div id="mode-columns" role="tabpanel" aria-labelledby="tab-columns" data-look-view="columns" hidden>{columns}</div><div class="empty-state" data-no-results="look" hidden><h3>换个词，再看看</h3><p>试试清除筛选，找回全部示例。</p><button class="button" data-reset="look">清除筛选</button></div>'
    pages={'today':today,'look':lookbody}
    for kind,title,desc,seq,groups in [('play','好玩','好奇心，总要有个去处。',play,PLAY_GROUPS),('buy','好买','一些值得了解的新东西。',buy,BUY_GROUPS)]:
        body=app_header(title,desc,'DISCOVER' if kind=='play' else 'CURATED',discovery=True)
        body+='<p class="sample-note">示例数据 · '+('图像用于排版，不代表真实活动或作品。' if kind=='play' else '无品牌虚构物件与价格格式，不是真实商品报价。')+'</p>'
        body+='<div class="sticky-filters">'+search(kind,'搜索感兴趣的发现')+filters(kind,['全部']+groups,dog=True)+'</div>'
        for n,group in enumerate(groups):
            grid = 'equal-cards' if kind == 'buy' else 'masonry'
            body+=f'<section class="group-section" data-group-section="{kind}" data-group="{group}">'+section_heading(group,f'{n+1:02d}')+f'<div class="{grid}">'+''.join(media_card(i) for i in seq if i['group']==group)+'</div></section>'
        if kind=='buy': body+='<p class="reference-note">只做参考。来源页含购买链接，我们不下单、不进购物车。</p>'
        body+=f'<div class="empty-state" data-no-results="{kind}" hidden><h3>换个方向，继续发现</h3><p>清除筛选，看看其他示例。</p><button class="button" data-reset="{kind}">清除筛选</button></div>'
        pages[kind]=body
    pages['saved']=app_header('留给以后。','喜欢的东西，在这里慢慢积攒。','COLLECTION')+'<p class="sample-note">收藏只保存在这台设备上；示例收藏与正式站隔离。</p><div class="sticky-filters"><div class="filter-row" data-saved-filters></div></div><div class="collection" data-saved-list></div><div class="empty-state" data-saved-empty>'+icon('bookmark')+'<h3>还没有收藏</h3><p>点卡片上的书签收藏。</p><button class="button" data-page="play">去好玩逛逛</button></div>'
    return ''.join(f'<section class="app-panel" data-panel="{key}" {"" if key=="today" else "hidden"}>{body}<p class="screen-footer">拾光热榜 · 示例数据 · 视觉评审</p></section>' for key,body in pages.items())


def foundations():
    colors=''.join(f'<div class="swatch"><i style="--swatch:var({t})"></i><span>{label}<code>{t}</code></span></div>' for t,label in [('--page','页面'),('--surface','内容表面'),('--text','主文字'),('--muted','次文字'),('--action','交互蓝'),('--accent','暖光点')])
    statuses=''.join(f'<p class="button" style="background:var(--{k}-bg);color:var(--{k});border:0">{icon("check" if k=="success" else "spark")} {label}</p>' for k,label in [('success','已核实'),('warning','未核实'),('danger','加载失败')])
    themes='<div class="theme-pair"><div class="theme-swatch" style="--preview-bg:var(--palette-light-page);--preview-text:var(--palette-light-text)">亮色<br>安静、明晰<br><small>日常阅读</small></div><div class="theme-swatch" style="--preview-bg:var(--palette-dark-page);--preview-text:var(--palette-dark-text)">暗色<br>柔和、克制<br><small>夜间浏览</small></div></div>'
    fonts=''.join(f'<div style="font-size:var({t})">{text}<small>{t} / {size}px</small></div>' for t,size,text in [('--font-3xl',34,'给今天一点新鲜'),('--font-2xl',28,'读一点世界'),('--font-xl',22,'发现一点生活'),('--font-lg',18,'此刻要闻'),('--font-body',16,'正文，读得从容一点。'),('--font-label',14,'卡片标题与操作'),('--font-sm',13,'一句值得看的理由'),('--font-xs',12,'来源 · 时间')])
    spaces=''.join(f'<div><code>{x:02d}px</code><i style="--n:{x}px"></i></div>' for x in [4,8,12,16,24,32,48])
    icons=''.join(icon(k) for k in ['home','news','compass','spark','bookmark','paw','search','external-link'])
    return heading('01','从一点光，开始。','蓝白表盘与暖色光点是全 App 的共同起点。语义 token 连接不同的内容气质。')+f'''<section class="lab-section"><h2>颜色与语义</h2><p>顶部主题切换会同步改变组件和五页 Screens。</p><div class="lab-grid">{specimen('品牌与表面',colors,'--page · --surface · --text · --action · --accent')}{specimen('亮暗映射',themes,'--page · --text · --border','使用成对的语义映射。','不要简单反相。')}{specimen('有文字的状态',statuses,'--success / --warning / --danger + -bg')}</div></section><section class="lab-section"><h2>字、空间与秩序</h2><div class="lab-grid">{specimen('统一系统字体',f'<div class="type-ladder">{fonts}</div>','--font-ui · --font-xs…--font-3xl','标题600，正文400；资讯行高1.8。','不要依赖在线字体服务。')}{specimen('间距与圆角',f'<div class="space-ladder">{spaces}</div><div class="specimen-row"><button class="button">10px 控件</button><div class="button" style="border-radius:var(--radius-card)">16px 卡片</div></div>','--space-1…12 · --radius-control/card/panel/pill')}{specimen('栅格与图标',f'<div class="specimen-row">{icons}</div><p class="small muted">手机2列 · 平板3列 · 宽屏4列<br>阅读区最大760 · 页面最大1200<br>手机边距16 · 列间12 · 触控44</p>','--grid-gap · --reading-max · --shell-max · --touch','线性图标与文字一起表意。','不要用购物车表达好买。')}</div></section><section class="lab-section"><h2>动效，有来有回</h2><div class="lab-grid two">{specimen('状态与面板', '<div class="motion-demo" data-motion-box>'+icon('spark')+'</div><button class="button" data-motion style="margin-top:24px">演示动效</button>','--duration-press:100ms · --duration-state:160ms · --duration-panel:220ms · --ease','响应系统减少动态偏好。','不要自动播放媒体。')}{specimen('圆角与阴影','<div class="news-card"><h3>轻轻托住内容</h3><p class="news-summary">实底卡片，低强度静态阴影。</p></div>','--radius-card · --shadow · --shadow-panel')}</div></section>'''


def components(data):
    look=[x for x in data['items'] if x['kind']=='look']; play=next(x for x in data['items'] if x['kind']=='play'); buy=next(x for x in data['items'] if x['kind']=='buy')
    buttons='<div class="specimen-row"><button class="button primary" data-demo-toast>默认</button><button class="button state-pressed" data-demo-toast>按下示例</button><button class="button state-focused" data-demo-toast>聚焦示例</button></div><div class="specimen-row"><button class="button" disabled>禁用</button><button class="button" disabled aria-busy="true">正在加载…</button><button class="button" data-demo-error>演示失败与重试</button></div><small class="muted">标记的按下/聚焦为状态示例。用 Tab 或鼠标体验真实状态。</small>'
    srch=search('gallery','试着输入一个词')+'<p data-gallery-feedback class="small muted">输入后显示反馈，不影响 Screens。</p><div class="search-field error-field"><input aria-label="错误状态示例" aria-invalid="true" aria-describedby="search-error" value="状态示例" readonly></div><p class="error-text" id="search-error">无法读取来源，请稍后重试。</p>'
    empt='<div class="empty-state">'+icon('bookmark')+'<h3>还没有收藏</h3><p>点卡片上的书签收藏。</p></div>'
    skeleton='<div class="skeleton" aria-label="内容加载中" aria-busy="true"><i></i><i></i><i></i></div>'
    fail='<div class="placeholder" data-placeholder>'+icon('image')+'<span>图片暂时打不开</span><button class="button quiet" data-retry-image>重试样例</button></div>'
    return heading('02','组件，是共同语言。','同一套组件拼出不同页面。状态示例与真实交互并列，不用图片替代行为。')+f'''<section class="lab-section"><h2>操作与筛选</h2><div class="lab-grid two">{specimen('按钮 · 状态矩阵',buttons,'--touch · --radius-control · --action · --focus')}{specimen('搜索 · 默认 / 输入 / 清空 / 错误',srch,'--surface · --border · --danger · --focus')}{specimen('筛选与模式 Tab',filters('gallery',['全部','北京','线上','看·读'])+'<div class="mode-tabs"><button class="mode-tab" data-demo-tab aria-selected="true">速览</button><button class="mode-tab" data-demo-tab aria-selected="false">热点</button><button class="mode-tab" disabled>禁用示例</button></div>','--selected · --action · --filter-bg')}{specimen('收藏 · 弹层 · Toast', '<div class="specimen-row">'+bookmark_for(look[0])+'<button class="button" data-detail="look-0">打开详情</button><button class="button" data-demo-toast>显示 Toast</button></div><p class="small muted">收藏状态同步至所有同条目卡片。弹层支持 Esc 与焦点恢复。</p>','--radius-panel · --scrim · --shadow-panel')}</div></section><section class="lab-section"><h2>阅读与发现</h2><div class="lab-grid two">{specimen('此刻要闻 / 资讯卡',news_card(look[0],hero=True)+news_card(look[-1]),'--news-bg · --font-2xl · --card-padding')}{specimen('同源折叠 · 前3条 + 原位展开',fold_run(look[2:7]),'--border · --radius-card','展开后保持时间与位置。','不要把其余条目移走。')}{specimen('好玩 · 图片卡',media_card(play),'--radius-card · --grid-gap · --font-label')}{specimen('好买 · 官方价格式',media_card(buy),'--price-color · --font-lg','仅此虚构样例演示价格格式。','不要将示意物件当真实商品报价。')}</div></section><section class="lab-section"><h2>空、慢与失败</h2><div class="lab-grid">{specimen('收藏空态',empt,'--muted · --space-12')}{specimen('内容骨架',skeleton,'--surface-quiet · --radius-card')}{specimen('图片占位 / 错误 / 重试',fail,'--surface-quiet · --muted','保留图片比例和重试入口。','不要拿别的产品图替补。')}</div></section>'''


def bookmark_for(item):
    from shiguang.site.ui import bookmark
    return bookmark(item)


def patterns(data):
    cards=[x for x in data['items'] if x['kind']=='play'][:4]
    sticky='<div class="pattern-demo"><div class="sticky-filters">'+filters('gallery',['全部','北京','线上','看·读'])+'</div>'+''.join(news_card(i) for i in data['items'][:5])+'</div>'
    return heading('03','把组件，放进生活。','吸顶栏用实底隔开文字；布局保留阅读顺序。切换窗口宽度，检查内容怎样自然变化。')+f'''<section class="lab-section"><div class="lab-grid two">{specimen('统一底栏',bottom_nav(),'--nav-bg · --selected · --touch','页面直接从内容标题开始，底栏统一导航。','不要重复添加品牌栏。')}{specimen('吸顶筛选 · 向下滚动检查',sticky,'--filter-bg · --border','吸顶背景为不透明实底。','不要让下方卡片文字透上来。')}{specimen('分组与瀑布流',section_heading('全国和世界','02')+'<div class="masonry">'+''.join(media_card(i) for i in cards)+'</div>','--grid-gap · --radius-card','保持DOM和键盘阅读顺序。','不要用dense回填改变顺序。')}{specimen('三好汇总模式',section_heading('资讯','01')+news_card(data['items'][0],hero=True)+section_heading('好玩','02')+'<div class="horizontal-cards">'+''.join(media_card(i) for i in cards)+'</div>','--reading-max · --space-8','今日依次资讯→好玩→好买。','当天不够不拿别的内容凑。')}</div></section>'''


def page(data):
    nav=''.join(f'<a href="#{key}" data-section="{key}" aria-current="{"page" if key=="screens" else "false"}">{n}　{label}</a>' for n,key,label in [('01','foundations','Foundations'),('02','components','Components'),('03','patterns','Patterns'),('04','screens','Screens')])
    jumps=''.join(f'<button data-page="{key}" aria-current="{"page" if key=="today" else "false"}">{icon(ico)}{label}</button>' for key,label,ico in [('today','今日','home'),('look','资讯','news'),('play','好玩','compass'),('buy','好买','spark'),('saved','收藏','bookmark')])
    controls=''.join(f'<div class="segmented" aria-label="{label}">'+''.join(f'<button data-control="{key}" data-value="{v}" aria-pressed="{"true" if i==0 else "false"}">{text}</button>' for i,(v,text) in enumerate(opts))+'</div>' for key,label,opts in [('theme','主题',[('light','亮色'),('dark','暗色')]),('viewport','预览宽度',[('desktop','桌面'),('phone','iPhone')]),('density','密度',[('comfortable','舒适'),('compact','紧凑')])])
    screens=heading('04','一点资讯，一点好奇心。','五页真实组件，点底栏开始逛。收藏、筛选和展开都在这里发生。')+f'''<div class="screen-workspace"><aside class="screen-notes"><h2>一天的三种发现</h2><p>资讯偏柔和杂志感。<br>好玩与好买，以图片为主。<br>用同一套蓝白与暖光串联。</p><div class="screen-jumps">{jumps}</div><p>全部为示例。价格演示使用无品牌虚构物件，非真实报价。</p>{note('--page · --surface · --action · --radius-card','点按、筛选、收藏并滚动检查。','不要将示例当成正式内容。')}<a class="button" href="?focus=1#screens/today" data-focus-link>全屏体验五页</a><p class="small muted">浏览器返回可回到视觉系统。</p><button class="button quiet" data-reset-demo>重置示例收藏</button></aside><div class="device-stage"><div class="device" data-viewport="desktop"><div class="device-status"><span>9:41</span><span>●●● ▰</span></div><div class="app-scroll" tabindex="0" aria-label="App 页面滚动区"><div class="app-content">{screen_pages(data)}</div></div>{bottom_nav()}</div></div></div>'''
    return f'''<!doctype html><html lang="zh-CN" data-theme="light" data-density="comfortable"><head>{license_notice()}<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow"><meta name="color-scheme" content="light dark"><title>拾光热榜 · 视觉系统</title><link rel="icon" href="/design/assets/icon.png"><link rel="stylesheet" href="/design/ui/tokens.css"><link rel="stylesheet" href="/design/ui/components.css"><script src="/design/ui/interactions.js" defer></script><script src="/design/playground.js" defer></script></head><body><a class="skip-link" href="#main">跳到内容</a><header class="review-header"><div class="review-brand"><img src="/design/assets/icon.png" alt=""><div><strong>拾光热榜 · 视觉系统</strong><small>DESIGN SYSTEM PLAYGROUND</small></div></div><div class="review-controls">{controls}<button class="button" data-token-toggle aria-expanded="false">{icon('sliders')} Tokens</button></div></header><nav class="review-nav" aria-label="视觉系统章节">{nav}<span class="version">REVIEW BUILD / 0.5</span></nav><main id="main" class="review-content"><section class="review-panel" id="foundations" hidden>{foundations()}</section><section class="review-panel" id="components" hidden>{components(data)}</section><section class="review-panel" id="patterns" hidden>{patterns(data)}</section><section class="review-panel" id="screens">{screens}</section></main><aside class="token-editor" hidden aria-label="本地 token 编辑器"><h2>试着改一点</h2><small>仅保存在本机的设计预览中；不影响正式站。切换主题后可分别修改。</small><label>交互色 <input type="color" data-token="--action" value="#1e5fa8"></label><label>页面色 <input type="color" data-token="--page" value="#f4f8fd"></label><label>卡片色 <input type="color" data-token="--surface" value="#ffffff"></label><label>卡片圆角 <input type="range" min="0" max="28" value="16" data-token="--radius-card" data-unit="px"></label><label>正文字号 <input type="range" min="14" max="20" value="16" data-token="--font-body" data-unit="px"></label><label>卡片内边距 <input type="range" min="12" max="28" value="20" data-token="--card-padding" data-unit="px"></label><div class="specimen-row"><button class="button" data-token-reset>重置本主题</button><button class="button primary" data-token-export>导出 CSS</button></div><small>Do：修改语义 token 检查同步。<br>Don’t：导出值未经评审不直接用于生产。</small></aside><dialog data-detail-dialog aria-labelledby="detail-title"><header class="dialog-header"><span class="eyebrow muted">示例详情</span><button class="icon-button" data-dialog-close aria-label="关闭详情">{icon('x')}</button></header><div class="dialog-body"></div></dialog><div class="toast" role="status" aria-live="polite" hidden><span></span><button hidden>撤销</button></div><noscript><p class="sample-note">请启用 JavaScript 体验页面切换与收藏；当前今日示例和折叠组件仍可阅读。</p></noscript></body></html>'''

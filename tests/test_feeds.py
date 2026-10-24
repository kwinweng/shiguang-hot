"""Focused regression checks for ingestion and privacy boundaries."""
import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from shiguang.config import ROOT, prepare
from shiguang.ingest import feeds
from shiguang.site import build as sitebuild, pages

class FeedTests(unittest.TestCase):
    def test_hot_daily_registration(self):
        cfg=json.loads((ROOT/'sources.json').read_text())
        source=next(s for s in cfg['sources'] if s['id']=='hot-daily')
        self.assertEqual(source['type'],'inbox')
        self.assertEqual(source['visibility'],'public')
        self.assertEqual(source['order'],0)
        self.assertEqual(cfg['hot']['source'],'hot-daily')
        self.assertEqual(source['adapter'],'native')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=dict(id='sample',adapter='native',directory=str(self.root),filename='feed.json')
        self.feed=dict(schema='shiguang.feed/1',source='sample',date='2026-10-17',sections=[dict(title='测试',items=[dict(title='标题',body='正文')])],blocks=[])

    def test_bad_shapes_are_errors(self):
        for field,value in [('sections',{}),('blocks',{}),('date','wrong'),('source','other')]:
            self.assertTrue(feeds.validate(dict(self.feed,**{field:value}),self.root,'sample')[0])

    def test_path_escape_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            file=Path(outside)/'private.png';Image.new('RGB',(20,20)).save(file)
            (self.root/'escape.png').symlink_to(file)
            self.assertIsNone(feeds.safe_image(self.root,'escape.png'))
            self.assertIsNone(feeds.safe_image(self.root,str(file)))
            self.assertIsNone(feeds.safe_image(self.root,'../private.png'))

    def test_image_conversion_and_missing_image(self):
        Image.new('RGB',(1800,900)).save(self.root/'picture.png')
        self.feed['sections'][0]['items'][0]['images']=[dict(file='picture.png',alt='说明'),dict(file='missing.png')]
        result=feeds.compress_images(self.feed,self.root,self.root/'out','img/')
        images=result['sections'][0]['items'][0]['images']
        with Image.open(self.root/'out'/Path(images[0]['file']).name) as image:
            self.assertEqual(image.size,(1200,600));self.assertEqual(image.format,'WEBP')
        self.assertEqual(images[1]['file'],'')
        self.assertEqual(self.feed['sections'][0]['items'][0]['images'][0]['file'],'picture.png')

    def test_world_and_mail_adapters(self):
        world=feeds.normalize(dict(date='2026-10-17',sections=[],oneliner=['速览'],markets=[dict(name='市场',value='1',change='-1')],chart=dict(title='图',image='chart.png'),tomorrow=['明日']),dict(id='world',adapter='world'))
        self.assertEqual([b['type'] for b in world['blocks']],['oneliner','markets','chart','tomorrow'])
        self.assertEqual(world['source'],'world')
        mail=feeds.normalize(dict(date='2026-10-17',sections=self.feed['sections']),dict(id='mail',adapter='mail'))
        self.assertFalse(feeds.validate(mail,self.root,'mail')[0])

    def test_unknown_block_is_warning(self):
        self.feed['blocks']=[dict(type='future')]
        errors,warnings=feeds.validate(self.feed,self.root,'sample')
        self.assertFalse(errors);self.assertTrue(warnings)

    def test_x_mapping_and_flat_loading(self):
        source=dict(self.source,id='x',adapter='x',filename='{date}.json')
        raw=dict(date='2026-10-17',generated_at='2026-10-17T01:00:00Z',
                 kol_posts=[dict(author_name='作者',handle='writer',who='',zh_summary='摘要',why_hot='原因',likes=181543,reposts=11978,url='https://x.com/post',created_at='2026-10-16T16:24:26Z')],
                 debates=[dict(title='争论',zh_summary='背景',sides=['支持','反对'],urls=['https://x.com/debate'])],
                 threads=[dict(author_name='长帖作者',handle='thread',zh_summary='长帖',url='javascript:bad')],
                 overseas=[dict(title='忽略')],markets=[dict(title='忽略')])
        feed=feeds.normalize(raw,source)
        self.assertFalse(feeds.validate(feed,self.root,'x')[0])
        self.assertEqual([s['title'] for s in feed['sections']],['推特爆款','推特今日吵什么','值得一读'])
        post=feed['sections'][0]['items'][0]
        self.assertEqual(post['title'],'作者（@writer）')
        self.assertEqual(post['body'],'摘要\n原因\n♥ 181,543 · ↻ 11,978')
        self.assertEqual(post['date'],'2026-10-17 00:24')
        self.assertEqual(post['link'],'https://x.com/post')
        self.assertEqual(feed['sections'][1]['items'][0]['body'],'背景\n支持\n反对')
        self.assertEqual(feed['sections'][2]['items'][0]['title'],'长帖作者（@thread）')
        self.assertEqual(feed['sections'][2]['items'][0]['link'],'')
        self.assertFalse(list(feeds.image_refs(feed)))
        dated=self.root/'2026-10-17.json';dated.write_text(json.dumps(raw))
        (self.root/'latest.json').write_text(json.dumps(dict(raw,kol_posts=[])))
        (self.root/'notes.md').write_text('ignore')
        with patch.object(feeds,'ROOT',self.root/'repo'):
            self.assertEqual(len(feeds.load_issues(source,True)[0][0]['sections']),3)
            self.assertFalse(feeds.load_issues(source,False))
            dated.unlink()
            self.assertEqual(len(feeds.load_issues(source,True)[0][0]['sections']),2)
            (self.root/'latest.json').write_text(json.dumps(dict(raw,kol_posts=[],debates=[],threads=[])))
            self.assertFalse(feeds.load_issues(source,True))

    def test_local_precedence_and_public_does_not_load_local(self):
        local=self.root/'local'/'2026-10-17';local.mkdir(parents=True)
        public=self.root/'repo'/'public-feeds'/'sample'/'2026-10-17';public.mkdir(parents=True)
        (local/'feed.json').write_text(json.dumps(dict(self.feed,title='local')))
        (public/'feed.json').write_text(json.dumps(dict(self.feed,title='public')))
        source=dict(self.source,directory=str(local.parent))
        with patch.object(feeds,'ROOT',self.root/'repo'):
            self.assertEqual(feeds.load_issues(source,True)[0][0]['title'],'local')
            self.assertEqual(feeds.load_issues(source,False)[0][0]['title'],'public')

class ConfigTests(unittest.TestCase):
    def test_old_field_names_still_work(self):
        cfg=prepare(dict(categories={'科技':'AI'},sources=[dict(id='a',type='inbox',name='A',visibility='public',daily_order=7,home_weight=2,home_cap=3,color='#123456',nav=dict(enabled=True,order=1))]))
        source=cfg['sources'][0]
        self.assertEqual(cfg['topics'],{'科技':'AI'})
        self.assertEqual((source['order'],source['home']),(7,dict(weight=2,cap=3)))
        self.assertNotIn('color',source)

    def test_defaults_and_bad_values(self):
        cfg=prepare(dict(topics={},sources=[dict(id='t',type='telegram',channel='t',name='T',visibility='public'),dict(id='i',type='inbox',name='I',visibility='public')]))
        self.assertEqual([(s['order'],s['home']['cap']) for s in cfg['sources']],[(50,4),(45,8)])
        for bad in (dict(home=dict(cap=-1)),dict(order='1'),dict(id='columns')):
            with self.assertRaises(ValueError):
                prepare(dict(topics={},sources=[dict(dict(id='i',type='inbox',name='I',visibility='public'),**bad)]))
        with self.assertRaises(ValueError):
            prepare(dict(topics={},hot=dict(source='missing'),sources=[]))

    def test_topics_for_every_source(self):
        from shiguang.enrich.topics import assign
        from shiguang.model import Item
        topics=prepare(json.loads((ROOT/'sources.json').read_text()))['topics']
        make=lambda title,category='': Item(source_id='s',filter_key='s',category=category,title=title,body='',day='2026-10-17',ts='2026-10-17')
        items=assign([make('OpenAI 发布新模型'),make('Thailand said yes'),make('一个工具'),make('自定','财经')],topics,'开发者')
        self.assertEqual([i.category for i in items],['AI','开发者','开发者','财经'])
        self.assertEqual(assign([make('Thailand said yes')],topics)[0].topic,'')  # 其他 is never shown on a card
        from shiguang.enrich.topics import classify
        self.assertEqual(classify('DeepSeek 发布新模型。美国市场关注。',topics,'DeepSeek 发布新模型'),'AI')  # title first

    def test_legacy_feeds_module(self):
        import importlib, sys
        sys.path.insert(0,str(ROOT))
        legacy=importlib.import_module('feeds')
        source=next(s for s in legacy.config()['sources'] if s['id']=='x')
        self.assertTrue(source['nav']['enabled']); self.assertEqual(source['daily_order'],source['order'])
        self.assertIs(legacy.validate,feeds.validate)

class PrivacyBuildTests(unittest.TestCase):
    def test_today_hot_columns_and_tabs(self):
        from bs4 import BeautifulSoup
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for directory in ('assets','media'): (root/directory).mkdir()
            for file in ('style.css','app.js'): (root/file).write_text('')
            sources=[]; issues={}
            for order,id in enumerate(('hot-daily','mail','world','x','github','NewlearnerChannel')):
                sources.append(dict(id=id,type='inbox',name='邮件精华' if id=='mail' else id,visibility='private' if id=='mail' else 'public',icon='all',color='#123456',nav=dict(enabled=True,order=order),daily_order=order,home_cap=2,home_weight=100 if id=='future' else 1))
                issues[id]=[(dict(date='2026-10-17',blocks=[dict(type='oneliner',items=[id+' summary'])],sections=[dict(title='section',items=[dict(title=id+str(n),body='body') for n in range(5)])]),root)]
            # Future sources and dates enter without renderer changes; blocks alone count as data.
            issues['NewlearnerChannel'].append((dict(date='2026-10-16',sections=[],blocks=[dict(type='oneliner',items=['older future'])]),root))
            sources.append(dict(id='CE_Observe',channel='tg',type='telegram',name='TG',visibility='public',icon='all',color='#123456',nav=dict(enabled=False),home_cap=2))
            rows=[dict(ch='tg',title='TG '+str(n),body='body',images=[],ts='2026-10-17 10:00',day='2026-10-17',cat='其他',url='') for n in range(20)]
            cfg=prepare(dict(categories={},sources=sources,hot=dict(source='hot-daily')))
            with patch.object(pages,'ROOT',root),patch.object(pages,'WEB',root),patch.object(sitebuild,'WEB',root),patch.object(pages,'config',return_value=cfg),patch.object(pages,'load_issues',side_effect=lambda source,local: issues.get(source['id'],[])),patch.object(sitebuild,'load_issues',side_effect=lambda source,local: issues.get(source['id'],[])):
                for mode in ('private','public'):
                    target=root/mode
                    with patch.dict(os.environ,dict(SITE_MODE=mode,MAIL_DIGEST='0',SITE_OUT=str(target))):
                        sitebuild.build(rows,[],datetime(2026,10,17,12,tzinfo=ZoneInfo('Asia/Shanghai')))
                    # The legacy chronological template remains on standalone archive URLs.
                    # PR B's homepage now boots the dedicated live/source/review app.
                    landing=BeautifulSoup((target/'index.html').read_text(),'html.parser')
                    self.assertIsNotNone(landing.select_one('#news'))
                    self.assertFalse(landing.select('#news-calendar, #news-history'))
                    home=BeautifulSoup((target/'archive/2026-10-17.html').read_text(),'html.parser')
                    expected=set(issues)|{'CE_Observe'}
                    if mode=='public': expected.remove('mail')
                    stream=home.select('#news-fallback article [data-source]')
                    # r3: every story is chronological and reachable, with no global expansion gate.
                    self.assertFalse(home.select('article[data-more], .show-all'))
                    self.assertEqual({b['data-source'] for b in stream},expected)
                    self.assertEqual(len(home.select('#news-fallback article[data-ch="tg"]')),20)
                    world=home.select_one('.today-summaries section[data-source="world"]')
                    self.assertEqual(len(world.select('article')),4)
                    self.assertEqual(world.select_one('.more-link a')['href'],'../world/2026-10-17.html')
                    # The shared calendar gets its joint matching dates from the sidecar manifest.
                    self.assertIsNotNone(home.select_one('#news-calendar'))
                    self.assertEqual(set(json.loads((target/'archive/manifest.json').read_text())['days']),{'2026-10-17','2026-10-16'})
                    past=BeautifulSoup((target/'archive/2026-10-16.html').read_text(),'html.parser')
                    self.assertFalse(past.select('.today-summaries article'))
                    self.assertEqual(past.select_one('nav.bottom a.active').get_text(),'资讯')
                    # 「光」: the tab bar holds words only.
                    self.assertEqual([a.get_text() for a in home.select('nav.bottom a')],['资讯','探索','我的'])
                    self.assertIsNotNone(home.select_one('nav.bottom svg.phosphor'))
                    self.assertEqual(home.select_one('nav.bottom a.active')['aria-current'],'page')
                    self.assertTrue(home.select('article button.bookmark[aria-pressed="false"][aria-label="收藏"]'))
                    favorites=BeautifulSoup((target/'favorites.html').read_text(),'html.parser')
                    self.assertFalse(favorites.select('[data-bookmark]'))
                    self.assertFalse(favorites.select('[data-source]'))
                    self.assertEqual(favorites.body['data-bookmark-scope'],mode)
                    self.assertIn('还没有收藏',favorites.get_text())
                    self.assertIsNotNone(home.select_one('#more-nav a[href="../index.html#explore/play"]'))
                    self.assertFalse(home.select('#more-nav a[href="tg/index.html"]'))
                    # 栏目: by channel (grouped by platform), and by tag.
                    columns=BeautifulSoup((target/'columns.html').read_text(),'html.parser')
                    channel=columns.select_one('[data-panel="channel"]')
                    self.assertEqual([a['href'] for a in channel.select('a.column-entry')],
                                     ['hot-daily/2026-10-17.html']+[id+'/index.html' for id in issues if id in expected and id!='hot-daily']+['CE_Observe/index.html'])
                    self.assertEqual([h.get_text() for h in channel.select('.section-label h2')],['每日简报','Telegram'])
                    self.assertEqual([a['href'] for a in columns.select('[data-panel="tag"] a.column-entry')],['tag/other.html'])
                    self.assertIn('TG 0',(target/'tag/other.html').read_text())
                    # Tag pages have no password, so private mail never lands on them, in either mode;
                    # nor on the tag panel of 栏目, which quotes each tag's newest title.
                    for page in [*(target/'tag').glob('*.html'), target/'columns.html']:
                        text=page.read_text(); soup=BeautifulSoup(text,'html.parser')
                        if page.parent.name=='tag': self.assertTrue(soup.select('article [data-source]'),page.name)
                        self.assertFalse(soup.select('[data-source="mail"]'),page.name)
                        self.assertFalse([n for n in range(5) if f'mail{n}' in text],page.name)
                    hot=BeautifulSoup((target/'hot.html').read_text(),'html.parser')
                    self.assertIn('index.html#focus', hot.select_one('meta[http-equiv="refresh"]')['content'])
                    # Merged pages keep their addresses.
                    self.assertIn('url=../index.html"',(target/'hot-daily/index.html').read_text())
                    self.assertIn('url=../index.html"',(target/'archive/index.html').read_text())
                    self.assertIn('url=index.html"',(target/'all.html').read_text())
                    channel_page=BeautifulSoup((target/'CE_Observe/index.html').read_text(),'html.parser')
                    self.assertEqual(len(channel_page.select('article')),20)
                    self.assertEqual(channel_page.select_one('nav.bottom a.active').get_text(),'探索')
                    self.assertEqual(BeautifulSoup((target/'x/index.html').read_text(),'html.parser').select_one('nav.bottom a.active').get_text(),'探索')
                    if mode=='public': self.assertFalse((target/'mail').exists())

    def test_public_rebuild_scrubs_private_tree_and_detects_private_copy(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'assets').mkdir();(root/'media').mkdir()
            (root/'assets'/'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
            (root/'style.css').write_text('');(root/'app.js').write_text('')
            target=root/'site';(target/'mail').mkdir(parents=True);(target/'mail'/'private.html').write_text('private')
            sources=[dict(id=id,type='inbox',name=name,visibility=visibility,icon='all',color='#1f6fd1',nav={'enabled':True}) for id,name,visibility in [('mail','邮件精华','private'),('world','环球要闻','public')]]
            cfg=prepare(dict(categories={},sources=sources))
            secret=dict(schema='shiguang.feed/1',source='mail',date='2026-10-17',blocks=[],sections=[dict(title='section',items=[dict(title='unique private story title for leak check',body='private body')])])
            with patch.object(pages,'ROOT',root),patch.object(pages,'WEB',root),patch.object(sitebuild,'WEB',root),patch.object(pages,'config',return_value=cfg),patch.dict(os.environ,{'SITE_MODE':'public','MAIL_DIGEST':'0','SITE_OUT':str(target)}):
                only_mail=lambda source,local: [(secret,root)] if source['id']=='mail' else []
                with patch.object(pages,'load_issues',side_effect=only_mail),patch.object(sitebuild,'load_issues',side_effect=only_mail):
                    sitebuild.build([],[],datetime.now(timezone.utc))
                self.assertFalse((target/'mail').exists());self.assertFalse((target/'world').exists())
                with patch.object(pages,'load_issues',return_value=[(secret,root)]),patch.object(sitebuild,'load_issues',return_value=[(secret,root)]):
                    with self.assertRaisesRegex(RuntimeError,'private 内容'):
                        sitebuild.build([],[],datetime.now(timezone.utc))

if __name__=='__main__':unittest.main()

"""Focused regression checks for ingestion and privacy boundaries."""
import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import feeds

class FeedTests(unittest.TestCase):
    def test_hot_daily_registration(self):
        cfg=json.loads((Path(__file__).parent/'sources.json').read_text())
        source=next(s for s in cfg['sources'] if s['id']=='hot-daily')
        self.assertEqual(source['type'],'inbox')
        self.assertEqual(source['visibility'],'public')
        self.assertEqual(source['nav'],dict(enabled=True,order=26))
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

class PrivacyBuildTests(unittest.TestCase):
    def test_cross_source_home_daily_and_fixed_tabs(self):
        import sitebuild
        from bs4 import BeautifulSoup
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for directory in ('assets','media'): (root/directory).mkdir()
            for file in ('style.css','app.js'): (root/file).write_text('')
            sources=[]; issues={}
            for order,id in enumerate(('hot-daily','mail','world','x','github','future')):
                sources.append(dict(id=id,type='inbox',name='邮件精华' if id=='mail' else id,visibility='private' if id=='mail' else 'public',icon='all',color='#123456',nav=dict(enabled=True,order=order),daily_order=order,home_cap=2,home_weight=100 if id=='future' else 1))
                issues[id]=[(dict(date='2026-10-17',blocks=[dict(type='oneliner',items=[id+' summary'])],sections=[dict(title='section',items=[dict(title=id+str(n),body='body') for n in range(5)])]),root)]
            # Future sources and dates enter without renderer changes; blocks alone count as data.
            issues['future'].append((dict(date='2026-10-16',sections=[],blocks=[dict(type='oneliner',items=['older future'])]),root))
            sources.append(dict(id='tg',channel='tg',type='telegram',name='TG',visibility='public',icon='all',color='#123456',nav=dict(enabled=False),home_cap=2))
            rows=[dict(ch='tg',title='TG '+str(n),body='body',images=[],ts='2026-10-17 10:00',day='2026-10-17',cat='综合',url='') for n in range(20)]
            cfg=dict(categories={},sources=sources,nav=dict(tabs=dict(public=['favorites','daily','home','news','x'],private=['mail','daily','home','news','x'])))
            with patch.object(sitebuild,'ROOT',root),patch.object(sitebuild,'config',return_value=cfg),patch.object(sitebuild,'load_issues',side_effect=lambda source,local: issues.get(source['id'],[])):
                for mode in ('private','public'):
                    target=root/mode
                    with patch.dict(os.environ,dict(SITE_MODE=mode,MAIL_DIGEST='0',SITE_OUT=str(target))):
                        sitebuild.build(rows,[],datetime(2026,10,17,12,tzinfo=ZoneInfo('Asia/Shanghai')))
                    home=BeautifulSoup((target/'index.html').read_text(),'html.parser')
                    expected=set(issues)|{'tg'}
                    if mode=='public': expected.remove('mail')
                    badges=home.select('article [data-source]')
                    self.assertEqual({b['data-source'] for b in badges},expected)
                    for source in expected: self.assertEqual(sum(b['data-source']==source for b in badges),2)
                    self.assertEqual(home.select_one('article [data-source]')['data-source'],'future')
                    # 「光」: the tab bar holds words only, home in the middle.
                    self.assertEqual([a.get_text() for a in home.select('nav.bottom a')],['邮件' if mode=='private' else '收藏','日报','首页','资讯','推特爆款'])
                    self.assertIsNone(home.select_one('nav.bottom svg'))
                    self.assertTrue(home.select('article button.bookmark[aria-pressed="false"][aria-label="收藏"]'))
                    favorites=BeautifulSoup((target/'favorites.html').read_text(),'html.parser')
                    self.assertFalse(favorites.select('[data-bookmark]'))
                    self.assertFalse(favorites.select('[data-source]'))
                    self.assertEqual(favorites.body['data-bookmark-scope'],mode)
                    self.assertIn('还没有收藏',favorites.get_text())
                    self.assertIsNotNone(home.select_one('#more-nav a[href="all.html"]'))
                    self.assertIsNotNone(home.select_one('.column-row a[href="favorites.html"]'))
                    self.assertEqual(home.select_one('nav.bottom a.home-slot')['aria-current'],'page')
                    day=BeautifulSoup((target/'archive/2026-10-17.html').read_text(),'html.parser')
                    ordered=[s['data-source'] for s in day.select('section.digest-source[data-source]')]
                    self.assertEqual(ordered,[id for id in issues if id in expected])
                    self.assertIn('TG 资讯',day.get_text())
                    self.assertIn('older future',(target/'archive/2026-10-16.html').read_text())
                    self.assertIn('hot-daily summary',(target/'archive/index.html').read_text())
                    if mode=='public': self.assertFalse((target/'mail').exists())

    def test_public_rebuild_scrubs_private_tree_and_detects_private_copy(self):
        import sitebuild
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'assets').mkdir();(root/'media').mkdir()
            (root/'assets'/'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
            (root/'style.css').write_text('');(root/'app.js').write_text('')
            target=root/'site';(target/'mail').mkdir(parents=True);(target/'mail'/'private.html').write_text('private')
            sources=[dict(id=id,type='inbox',name=name,visibility=visibility,icon='all',color='#1f6fd1',nav={'enabled':True}) for id,name,visibility in [('mail','邮件精华','private'),('world','环球要闻','public')]]
            cfg=dict(categories={},sources=sources)
            secret=dict(schema='shiguang.feed/1',source='mail',date='2026-10-17',blocks=[],sections=[dict(title='section',items=[dict(title='unique private story title for leak check',body='private body')])])
            with patch.object(sitebuild,'ROOT',root),patch.object(sitebuild,'config',return_value=cfg),patch.dict(os.environ,{'SITE_MODE':'public','MAIL_DIGEST':'0','SITE_OUT':str(target)}):
                with patch.object(sitebuild,'load_issues',side_effect=lambda source,local: [(secret,root)] if source['id']=='mail' else []):
                    sitebuild.build([],[],datetime.now(timezone.utc))
                self.assertFalse((target/'mail').exists());self.assertFalse((target/'world').exists())
                with patch.object(sitebuild,'load_issues',return_value=[(secret,root)]):
                    with self.assertRaisesRegex(RuntimeError,'private 内容'):
                        sitebuild.build([],[],datetime.now(timezone.utc))

if __name__=='__main__':unittest.main()

"""公众号/博客正文按原文顺序（v13，阿欢 2026-11-15 22:08 第 6 条）：段落、标题、图片、引用、列表；不重复、不漏图、不打乱。不联网。"""
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from rebang.bloggers import media
from rebang.bloggers.common import blocks_text, html_blocks, unwrap_image_url
from rebang.contract import validate_item
from rebang.site import builder

FIX = Path(__file__).parent / 'fixtures' / 'rebang' / 'bloggers' / 'wechat-article.html'


def jpeg(w=40, h=20):
    buf = io.BytesIO()
    Image.new('RGB', (w, h), (200, 100, 50)).save(buf, format='JPEG')
    return buf.getvalue()


class BlocksTests(unittest.TestCase):
    def setUp(self):
        self.blocks = html_blocks(FIX.read_text(encoding='utf-8'), 'https://mp.weixin.qq.com/s/x', wechat=True)

    def test_exact_order_and_types(self):
        got = [(b['type'], b.get('text') or b.get('src') or b.get('items')) for b in self.blocks]
        self.assertEqual(got, [
            ('p', '第一段。'),
            ('img', 'https://mmbiz.qpic.cn/a/640?wx_fmt=jpeg'),
            ('h', '小标题'),
            ('p', '第二段，加粗接着说。'),
            ('quote', '引用第一行\n引用第二行'),
            ('ul', ['要点一', '要点二']),
            ('p', '第三段'),
            ('img', 'https://mmbiz.qpic.cn/b/640'),
            ('p', '第四段'),
        ], '去掉 Wechat2RSS 加的「原创/作者/日期」行和封面图、1px 追踪图；其余严格按原文顺序')

    def test_image_dims_from_wechat_ratio(self):
        self.assertEqual((self.blocks[1]['width'], self.blocks[1]['height']), (1080, 540))

    def test_no_duplicate_images_and_text(self):
        srcs = [b['src'] for b in self.blocks if b['type'] == 'img']
        self.assertEqual(len(srcs), len(set(srcs)))
        self.assertEqual(blocks_text(self.blocks).count('第一段'), 1)

    def test_unwrap_proxy(self):
        self.assertEqual(unwrap_image_url('https://wechat2rss.xlab.app/img-proxy/?k=1&u=https%3A%2F%2Fmmbiz.qpic.cn%2Fz'), 'https://mmbiz.qpic.cn/z')
        self.assertEqual(unwrap_image_url('https://a.com/b.png'), 'https://a.com/b.png')

    def test_schema(self):
        item = {'id': 'wechat-x:1', 'kind': 'post', 'channel': None, 'source_id': 'wechat-x', 'source_name': 'x', 'title': 't',
                'summary': '', 'url': '', 'published_at': '2026-11-15T10:00:00+08:00', 'lang': 'zh',
                'blogger': {'platform': 'wechat', 'handle': 'x', 'display_name': 'x', 'media': [], 'quote': None},
                'blocks': self.blocks}
        self.assertEqual(validate_item(item), [])
        self.assertEqual(len(validate_item(dict(item, blocks=[{'type': 'img', 'src': 'data:x'}, {'type': 'p', 'text': ' '}]))), 2)


class MediaTests(unittest.TestCase):
    def test_localize_downloads_in_order_and_site_copies(self):
        blocks = html_blocks(FIX.read_text(encoding='utf-8'), '', wechat=True)
        item = {'blogger': {'platform': 'wechat'}, 'blocks': blocks, 'image': {'url': 'https://wechat2rss.xlab.app/img-proxy/?u=https%3A%2F%2Fmmbiz.qpic.cn%2Fcover'}}
        fetched = []

        def get(url):
            fetched.append(url)
            if url.endswith('/b/640'):
                raise RuntimeError('404')
            return jpeg()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            stats = media.localize([item], tmp / 'media', get=get)
            self.assertEqual(stats, {'saved': 2, 'reused': 0, 'failed': 1})
            self.assertTrue(all('Referer' not in u for u in fetched))
            self.assertIn('local', blocks[1])
            self.assertNotIn('local', blocks[7])
            self.assertTrue(item['image_local']['rel'].startswith('wechat/'))
            site = tmp / 'site'
            site.mkdir()
            builder.localize_images([item], site)
            self.assertTrue(blocks[1]['src'].startswith('media/wechat/'))
            self.assertTrue((site / blocks[1]['src']).is_file())
            self.assertNotIn('local', blocks[1], '本机路径不进站点数据')
            self.assertTrue(blocks[7].get('missing'), '下载失败的公众号图如实标「没存下来」，不外链（外站引用会变成占位图）')
            self.assertTrue(item['image']['url'].startswith('media/wechat/'))
            self.assertEqual(media.prune([], tmp / 'media'), 2)


class WeiboMediaTests(unittest.TestCase):
    """sinaimg/weibocdn 只认 weibo.com 的 Referer：图、视频封面、头像抓取时下载，站上用本站副本。"""

    def test_localize_weibo_images_cover_avatar_and_site_copies(self):
        item = {'id': 'weibo-1:1', 'blogger': {'platform': 'weibo', 'handle': '1', 'avatar': 'https://tva1.sinaimg.cn/crop.0.0.1.1.1024/av.jpg',
                'media': [{'type': 'image', 'url': 'https://wx1.sinaimg.cn/large/a.jpg', 'width': 3000, 'height': 1500},
                          {'type': 'image', 'url': 'https://wx1.sinaimg.cn/large/broken.jpg'},
                          {'type': 'video', 'url': 'https://f.video.weibocdn.com/o0/v.mp4', 'preview_url': 'https://wx3.sinaimg.cn/orj480/c.jpg'}]},
                'image': {'url': 'https://wx1.sinaimg.cn/large/a.jpg'}}
        fetched = []

        def get(url):
            fetched.append(url)
            if 'broken' in url:
                raise RuntimeError('403')
            return jpeg(80, 40)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            stats = media.localize_weibo([item], tmp / 'media', get=get)
            self.assertEqual(stats, {'saved': 3, 'reused': 0, 'failed': 1})
            self.assertNotIn('https://f.video.weibocdn.com/o0/v.mp4', fetched, '视频本体不下载')
            m = item['blogger']['media']
            self.assertTrue(m[0]['local']['rel'].startswith('weibo/') and 'local' not in m[1] and m[2]['preview_local'])
            self.assertTrue(item['blogger']['avatar_local'] and item['image'] is None and item['image_local'] == m[0]['local'])
            # 第二次：文件都在，直接复用，不再下载
            fetched.clear()
            media.localize_weibo([item], tmp / 'media', get=get)
            self.assertEqual(fetched, ['https://wx1.sinaimg.cn/large/broken.jpg'])
            site = tmp / 'site'
            site.mkdir()
            builder.localize_images([item], site)
            b = item['blogger']
            self.assertTrue(b['media'][0]['url'].startswith('media/weibo/') and (site / b['media'][0]['url']).is_file())
            self.assertEqual(b['media'][0]['orig_url'], 'https://wx1.sinaimg.cn/large/a.jpg')
            self.assertEqual((b['media'][0]['width'], b['media'][0]['height']), (80, 40))
            self.assertEqual(b['media'][1]['url'], 'https://wx1.sinaimg.cn/large/broken.jpg', '没存下的保持原地址，不拿别的图顶替')
            self.assertTrue(b['media'][2]['preview_url'].startswith('media/weibo/') and b['media'][2]['url'].startswith('https://f.video'))
            self.assertTrue(b['avatar'].startswith('media/weibo/') and item['image']['url'].startswith('media/weibo/'))
            self.assertNotIn('"path"', json.dumps(item), '本机路径不进站点数据')
            self.assertEqual(media.prune([], tmp / 'media', platform='weibo'), 3)


if __name__ == '__main__':
    unittest.main()


class WechatTailTests(unittest.TestCase):
    def test_wechat2rss_jump_link_dropped(self):
        html = '<p>原创 作者 2026-11-12 22:29 北京</p><p>正文。</p><p><a href="https://wechat2rss.xlab.app/link-proxy/?u=x">跳转微信打开</a></p>'
        self.assertEqual(html_blocks(html, '', wechat=True), [{'type': 'p', 'text': '正文。'}])
        self.assertEqual(html_blocks('<p>正文。</p><p>阅读原文</p>', '', wechat=False)[-1]['text'], '阅读原文', '只对公众号去尾')

"""兼容入口：本机脚本（如 publish_public.py）仍可 `import feeds`。实现已移到 shiguang/，第 4 步后删除。

config() 在这里返回旧字段（categories、nav、daily_order、home_weight、home_cap、color），
让还按旧格式读取配置的脚本继续工作。
"""
from shiguang.config import ROOT, directory, private_mode
from shiguang.config import config as _config
from shiguang.ingest.feeds import compress_images, image_refs, load_issues, normalize, safe_image, validate

__all__ = ['ROOT', 'config', 'directory', 'private_mode', 'compress_images', 'image_refs', 'load_issues', 'normalize', 'safe_image', 'validate']


def config():
    data = _config()
    data['categories'] = data['topics']
    for s in data['sources']:
        s.setdefault('nav', {'enabled': s['type'] == 'inbox' and s['id'] != data['hot']['source'], 'order': s['order']})
        s.setdefault('daily_order', s['order'])
        s.setdefault('home_weight', s['home']['weight'])
        s.setdefault('home_cap', s['home']['cap'])
        s.setdefault('color', '#4f5b66')
    return data

"""兼容入口：本机脚本（如 publish_public.py）仍可 `import feeds`。实现已移到 shiguang/，第 4 步后删除。"""
from shiguang.config import ROOT, config, directory, private_mode
from shiguang.ingest.feeds import compress_images, image_refs, load_issues, normalize, safe_image, validate

__all__ = ['ROOT', 'config', 'directory', 'private_mode', 'compress_images', 'image_refs', 'load_issues', 'normalize', 'safe_image', 'validate']

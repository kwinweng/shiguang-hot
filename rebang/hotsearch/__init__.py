"""热搜采集：按 hotsearch.json 逐家调用独立适配器，汇总为 rebang.hotsearch/1。"""
from .collect import collect
from .http import ProviderError

__all__ = ['collect', 'ProviderError']

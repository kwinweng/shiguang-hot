"""可插拔翻译接口：translate(texts, src_lang='en') -> list[str] | None。

失败、未配置或缓存缺失时返回 None，调用方据此写 translated=false，绝不编译文。

引擎（环境变量 REBANG_TRANSLATE_ENGINE 选择，默认 cache）：
- ``none``：永远返回 None。
- ``cache``：只查本地译文缓存（默认 var/rebang/translate/cache.json）。缺的原文记进
  pending.json，由 Grok Bot 例程（盒子上现有中文圈早报 / 资讯中译用的就是它，只用 Grok 自身额度）
  读 pending、写译文后用 ``python3 -m rebang.translate fill`` 合并；下次生成即带上译文。
- ``openai-compatible``：可选。调用任意 OpenAI 兼容的 /chat/completions 端点。需要运维提供
  REBANG_TRANSLATE_URL、REBANG_TRANSLATE_MODEL，以及“存放密钥的环境变量名”
  REBANG_TRANSLATE_KEY_ENV（默认 REBANG_TRANSLATE_API_KEY）。密钥只在请求时从环境变量取，
  不落盘、不打印、不写进错误信息。结果同样写入缓存。
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / 'var' / 'rebang' / 'translate' / 'cache.json'
LABEL = '机器翻译'


def text_key(text, src_lang='en'):
    return hashlib.sha256(f'{src_lang}\0{text}'.encode('utf-8')).hexdigest()[:32]


class Cache:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('REBANG_TRANSLATE_CACHE') or DEFAULT_CACHE)
        self.pending_path = self.path.with_name('pending.json')
        self.entries = {}
        self.pending = {}
        if self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text(encoding='utf-8')).get('entries', {})
            except (ValueError, OSError):
                self.entries = {}
        if self.pending_path.exists():
            try:
                self.pending = json.loads(self.pending_path.read_text(encoding='utf-8')).get('pending', {})
            except (ValueError, OSError):
                self.pending = {}

    def get(self, text, src_lang):
        entry = self.entries.get(text_key(text, src_lang))
        if entry and entry.get('src') == text and isinstance(entry.get('zh'), str) and entry['zh'].strip():
            return entry
        return None

    def put(self, text, src_lang, zh, engine):
        self.entries[text_key(text, src_lang)] = {'src': text, 'src_lang': src_lang, 'zh': zh, 'engine': engine}
        self.pending.pop(text_key(text, src_lang), None)

    def want(self, text, src_lang, kind=None):
        key = text_key(text, src_lang)
        rec = self.pending.setdefault(key, {'src': text, 'src_lang': src_lang})
        if kind and not rec.get('kind'):
            rec['kind'] = kind

    def save(self):
        """先并入盘上最新内容再写（ingest 与 bloggers 共用一份缓存，先后或同时跑都不互相覆盖）。"""
        disk = Cache.__new__(Cache)
        disk.path, disk.pending_path = self.path, self.pending_path
        disk.entries, disk.pending = {}, {}
        try:
            disk.entries = json.loads(self.path.read_text(encoding='utf-8')).get('entries', {})
        except (ValueError, OSError):
            pass
        try:
            disk.pending = json.loads(self.pending_path.read_text(encoding='utf-8')).get('pending', {})
        except (ValueError, OSError):
            pass
        self.entries = {**disk.entries, **self.entries}
        self.pending = {k: v for k, v in {**disk.pending, **self.pending}.items() if k not in self.entries}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({'schema': 'rebang.translate-cache/1', 'entries': self.entries},
                                        ensure_ascii=False, indent=1), encoding='utf-8')
        self.pending_path.write_text(json.dumps({'schema': 'rebang.translate-pending/1', 'pending': self.pending},
                                                ensure_ascii=False, indent=1), encoding='utf-8')


class Translator:
    """一次运行共享一个实例；``translate_detailed`` 返回 (译文列表, engine) 或 None。"""

    def __init__(self, engine=None, cache=None, http_post=None):
        self.engine = engine or os.environ.get('REBANG_TRANSLATE_ENGINE', 'cache')
        self.cache = cache if cache is not None else (None if self.engine == 'none' else Cache())
        self.http_post = http_post or _curl_post_json
        self.errors = 0

    def translate_detailed(self, texts, src_lang='en', kinds=None):
        if self.engine == 'none' or not texts:
            return None
        if src_lang.startswith('zh'):
            return None
        hits = [self.cache.get(t, src_lang) for t in texts]
        if all(hits):
            engines = {h['engine'] for h in hits}
            return [h['zh'] for h in hits], '+'.join(sorted(engines))
        if self.engine == 'cache':
            for i, (text, hit) in enumerate(zip(texts, hits)):
                if not hit:
                    kind = kinds[i] if kinds and i < len(kinds) else None
                    self.cache.want(text, src_lang, kind=kind)
            return None
        if self.engine == 'openai-compatible':
            try:
                out = self._openai(texts, src_lang)
            except Exception:  # 网络/格式错误一律当失败，不泄露细节
                self.errors += 1
                out = None
            if out is None:
                for i, text in enumerate(texts):
                    kind = kinds[i] if kinds and i < len(kinds) else None
                    self.cache.want(text, src_lang, kind=kind)
                return None
            model = os.environ.get('REBANG_TRANSLATE_MODEL', 'unknown')
            engine = f'openai-compatible:{model}'
            for text, zh in zip(texts, out):
                self.cache.put(text, src_lang, zh, engine)
            return out, engine
        return None

    def translate(self, texts, src_lang='en'):
        result = self.translate_detailed(texts, src_lang)
        return None if result is None else result[0]

    def save(self):
        if self.cache is not None:
            self.cache.save()

    def _openai(self, texts, src_lang):
        url = os.environ.get('REBANG_TRANSLATE_URL')
        model = os.environ.get('REBANG_TRANSLATE_MODEL')
        key = os.environ.get(os.environ.get('REBANG_TRANSLATE_KEY_ENV', 'REBANG_TRANSLATE_API_KEY'))
        if not (url and model and key):
            return None
        prompt = ('把下面 JSON 数组里每段文字从 %s 忠实翻译成简体中文，保留链接、代码和专有名词，'
                  '不增删内容。只输出同样长度的 JSON 字符串数组。\n' % src_lang) + json.dumps(texts, ensure_ascii=False)
        body = {'model': model, 'temperature': 0, 'messages': [{'role': 'user', 'content': prompt}]}
        reply = self.http_post(url, body, {'Authorization': 'Bearer ' + key})
        content = reply['choices'][0]['message']['content'].strip()
        if content.startswith('```'):
            content = content.strip('`').split('\n', 1)[-1]
        out = json.loads(content)
        if not (isinstance(out, list) and len(out) == len(texts) and all(isinstance(x, str) and x.strip() for x in out)):
            return None
        return out


def _curl_post_json(url, body, headers):
    """POST JSON。请求头（含密钥）写进权限 600 的临时 curl 配置文件，不出现在进程参数里，用完即删。"""
    import tempfile
    with tempfile.NamedTemporaryFile('w', delete=True) as cfg:
        os.chmod(cfg.name, 0o600)
        for name, value in headers.items():
            cfg.write('header = "%s: %s"\n' % (name, value.replace('"', '')))
        cfg.flush()
        args = ['curl', '-q', '-sS', '--max-time', '60', '--proto', '=https,http', '-X', 'POST',
                '-H', 'Content-Type: application/json', '--data-binary', '@-', '-K', cfg.name, url]
        result = subprocess.run(args, input=json.dumps(body).encode('utf-8'), capture_output=True)
    if result.returncode:
        raise RuntimeError('network')
    return json.loads(result.stdout)



PENDING_LIMIT = 150  # 例程单轮建议上限
_KIND_RANK = {'title': 0, 'summary': 1, 'preview': 1, 'comment': 3, 'body': 4, 'block': 4}


def pending_rank(key, rec):
    """标题、摘要优先，长正文和回复靠后。没有 kind 时按长度估计。"""
    src = rec.get('src') or ''
    kind = rec.get('kind')
    if kind in _KIND_RANK:
        return (_KIND_RANK[kind], len(src), key)
    n = len(src)
    # 无 kind 的短词块多半是正文小标题（Gaza、Meta），不要排到列表标题前面
    if n <= 24 and ' ' not in src.strip() and '\n' not in src:
        return (4, n, key)
    if n <= 220:
        return (0, n, key)
    if n <= 520:
        return (1, n, key)
    return (4, -n, key)


def list_pending(cache, limit=None):
    rows = [{'key': k, **v} for k, v in cache.pending.items()]
    rows.sort(key=lambda r: pending_rank(r['key'], r))
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    return rows


_default = None


def translate(texts, src_lang='en'):
    """模块级便捷接口（任务卡约定的签名）。"""
    global _default
    if _default is None:
        _default = Translator()
    return _default.translate(list(texts), src_lang)

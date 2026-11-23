#!/usr/bin/env python3
"""拾光资讯：用 DeepSeek Flash（OpenAI 兼容接口）清 var/rebang/translate/pending.json。

沿用已实测的批量翻译实现。密钥只从环境变量读（默认 REBANG_TRANSLATE_API_KEY），
只放在内存里的请求头，不打印、不写盘。默认使用本仓库，不依赖旧机器目录。

  var/rebang/venv/bin/python tools/translate_deepseek.py [--limit N] [--max-minutes M]

退出码：0 正常（含没有待译）；2 连续失败而停下（保留 pending，下一轮重试）；3 锁被占用；4 配置缺失。
最后一行打印 JSON 摘要：done / failed / remaining / secs / requests / prompt_tokens / completion_tokens 等。
"""
import argparse
import fcntl
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit

REPO = os.environ.get('REBANG_REPO', str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, REPO)
from rebang.translate import Cache, list_pending  # noqa: E402

MODEL = 'deepseek-flash'  # 固定本人批准的模型，不能仅凭名字含 flash 就放行。

SYSTEM = (
    '你是专业的英译中新闻编辑。把用户给的 JSON 对象里每个值从英文（或其他外语）忠实翻译成简体中文，'
    '键保持不变，只输出同样键的 JSON 对象，不要输出任何其他内容。\n'
    '要求：\n'
    '1. 忠实、通顺、自然，不增删内容，不加评论或解释，不总结。\n'
    '2. 地名、国家、机构通称、话题词、普通名词即使很短也要译成中文（例如 Middle East→中东，'
    'Gaza→加沙，Climate→气候，Business→商业，Supreme Court→最高法院）。\n'
    '3. 产品名、公司名、软件/仓库名、代码、命令、URL、@用户名、#话题标签保持原文'
    '（例如 GitHub、OpenAI、Claude Code、Vikunja、owner/repo）。常见人名可用通行中文译名，没把握就保留原文。\n'
    '4. 保留原有换行、Markdown、列表符号和链接。\n'
    '5. 原文已是中文或只有链接/符号时原样返回。'
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """不跟随任何跳转：urllib 跳转时会把 Authorization 头原样带到新地址。"""

    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


class CallError(RuntimeError):
    """一次请求失败；usage 为服务端已返回的用量（没有回包时为空）。"""

    def __init__(self, msg, usage=None):
        super().__init__(msg)
        self.usage = usage or {}


def die(code, msg):
    print(json.dumps({'error': msg}, ensure_ascii=False))
    sys.exit(code)


class DeepSeek:
    def __init__(self, url, model, key, effort, timeout):
        self.url, self.model, self._key, self.effort, self.timeout = url, model, key, effort, timeout

    def call(self, texts):
        """texts: list[str] -> (list[str], usage dict)。失败抛 CallError（信息不含密钥，带已返回的用量）。"""
        payload = {str(i + 1): t for i, t in enumerate(texts)}
        n_chars = sum(len(t) for t in texts)
        body = {
            'model': self.model,
            'messages': [{'role': 'system', 'content': SYSTEM},
                         {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'response_format': {'type': 'json_object'},
            'max_tokens': min(65536, max(2048, n_chars * 2 + 1024)),
            'stream': False,
        }
        if self.effort == 'none':
            body['thinking'] = {'type': 'disabled'}
            body['temperature'] = 0.2
        else:
            body['reasoning_effort'] = self.effort
        req = urllib.request.Request(self.url, data=json.dumps(body).encode('utf-8'), method='POST',
                                     headers={'Content-Type': 'application/json',
                                              'Authorization': 'Bearer ' + self._key})
        try:
            with OPENER.open(req, timeout=self.timeout) as resp:
                reply = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise CallError('http %s' % e.code) from None
        except Exception as e:  # noqa: BLE001
            raise CallError('network %s' % type(e).__name__) from None
        usage = (reply.get('usage') if isinstance(reply, dict) else None) or {}
        try:
            choice = reply['choices'][0]
            if choice.get('finish_reason') not in (None, 'stop'):
                raise CallError('finish %s' % choice.get('finish_reason'), usage)
            content = (choice['message'].get('content') or '').strip()
            if content.startswith('```'):
                content = content.strip('`').split('\n', 1)[-1]
            out = json.loads(content)
        except CallError:
            raise
        except Exception as e:  # noqa: BLE001
            raise CallError('bad reply %s' % type(e).__name__, usage) from None
        res = []
        for i, src in enumerate(texts):
            zh = out.get(str(i + 1)) if isinstance(out, dict) else None
            if not isinstance(zh, str) or not zh.strip():
                raise CallError('missing item', usage)
            res.append(zh.strip())
        return res, usage


def batches(rows, max_items, max_chars):
    cur, size = [], 0
    for r in rows:
        n = len(r['src'])
        if n > max_chars:  # 长正文单独一批
            yield [r]
            continue
        if cur and (len(cur) >= max_items or size + n > max_chars):
            yield cur
            cur, size = [], 0
        cur.append(r)
        size += n
    if cur:
        yield cur


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None, help='本轮最多译多少段（默认全部 pending）')
    ap.add_argument('--max-minutes', type=float, default=40)
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--batch-items', type=int, default=20)
    ap.add_argument('--batch-chars', type=int, default=3500)
    ap.add_argument('--effort', default=os.environ.get('REBANG_TRANSLATE_EFFORT', 'none'),
                    choices=['none', 'low', 'high'], help='none=关闭思考（默认，翻译够用且最省）')
    ap.add_argument('--timeout', type=int, default=180)
    ap.add_argument('--max-consecutive-fail', type=int, default=6)
    ap.add_argument('--usage-log', default=str(Path(REPO) / 'var/rebang/logs/deepseek-usage.jsonl'))
    ap.add_argument('--cache', default=None)
    args = ap.parse_args(argv)

    url = os.environ.get('REBANG_TRANSLATE_URL', 'https://api.deepseek.com/chat/completions')
    model = os.environ.get('REBANG_TRANSLATE_MODEL', 'deepseek-flash')
    key = os.environ.get(os.environ.get('REBANG_TRANSLATE_KEY_ENV', 'REBANG_TRANSLATE_API_KEY'))
    if model != MODEL:
        die(4, 'model must be exactly %s' % MODEL)  # 不回显输入值，以免误填的密钥被打印
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname:
        die(4, 'translate url must be https')
    if not key:
        die(4, 'api key env not set')
    engine = 'openai-compatible:%s' % model

    os.chdir(REPO)
    lock_path = os.path.join(REPO, 'var/rebang/translate/.translate.lock')
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    lock = open(lock_path, 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        die(3, 'another translate run holds %s' % lock_path)

    t0 = time.time()
    deadline = t0 + args.max_minutes * 60
    cache = Cache(args.cache)
    rows = list_pending(cache, args.limit)
    total_pending = len(cache.pending)
    client = DeepSeek(url, model, key, args.effort, args.timeout)
    stats = {'done': 0, 'failed': 0, 'requests': 0, 'prompt_tokens': 0, 'completion_tokens': 0,
             'cache_hit_tokens': 0, 'reasoning_tokens': 0}
    failed_keys = []
    consecutive = 0
    stopped = None

    def add_usage(u):
        stats['requests'] += 1
        stats['prompt_tokens'] += int(u.get('prompt_tokens') or 0)
        stats['completion_tokens'] += int(u.get('completion_tokens') or 0)
        stats['cache_hit_tokens'] += int(u.get('prompt_cache_hit_tokens') or 0)
        stats['reasoning_tokens'] += int((u.get('completion_tokens_details') or {}).get('reasoning_tokens') or 0)

    def work(batch):
        """返回 [(row, zh|None)], usages, err。失败一次则拆成两半各试一次。"""
        usages = []  # 每次请求记一条（失败也记，带服务端已返回的用量）

        def attempt(rows_):
            try:
                out, u = client.call([r['src'] for r in rows_])
            except Exception as e:  # noqa: BLE001
                usages.append(getattr(e, 'usage', None) or {})
                raise
            usages.append(u)
            return out

        try:
            return list(zip(batch, attempt(batch))), usages, None
        except Exception as e:  # noqa: BLE001
            err = str(e)
        if len(batch) == 1:
            try:
                return [(batch[0], attempt(batch)[0])], usages, None
            except Exception as e:  # noqa: BLE001
                return [(batch[0], None)], usages, str(e)
        mid = len(batch) // 2
        res, last_err = [], err
        for half in (batch[:mid], batch[mid:]):
            try:
                res.extend(zip(half, attempt(half)))
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                res.extend((r, None) for r in half)
        ok = any(zh for _, zh in res)
        return res, usages, (None if ok else last_err)

    todo = list(batches(rows, args.batch_items, args.batch_chars))
    errors = {}
    last_save = time.time()
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        it = iter(todo)
        running = set()

        def submit_next():
            if stopped or time.time() > deadline:
                return False
            b = next(it, None)
            if b is None:
                return False
            running.add(pool.submit(work, b))
            return True

        for _ in range(args.threads):
            submit_next()
        while running:
            fut = next(as_completed(running))
            running.discard(fut)
            res, usages, err = fut.result()
            for u in usages:
                add_usage(u)
            for row, zh in res:  # 只在主线程写缓存
                if zh:
                    cache.put(row['src'], row.get('src_lang', 'en'), zh, engine)
                    stats['done'] += 1
                else:
                    stats['failed'] += 1
                    failed_keys.append(row['key'])
            if err:
                errors[err] = errors.get(err, 0) + 1
                consecutive += 1
                if consecutive >= args.max_consecutive_fail:
                    stopped = 'consecutive failures'
            else:
                consecutive = 0
            if time.time() - last_save > 60:
                cache.save()
                last_save = time.time()
            if time.time() > deadline and not stopped:
                stopped = 'max-minutes'
            submit_next()
    cache.save()
    after = Cache(args.cache)
    summary = {
        'model': model, 'effort': args.effort, 'pending_before': total_pending, 'selected': len(rows),
        **stats, 'remaining': len(after.pending), 'secs': round(time.time() - t0, 1),
        'stopped': stopped, 'errors': errors, 'failed_keys': failed_keys[:20],
        'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }
    try:
        Path(args.usage_log).parent.mkdir(parents=True, exist_ok=True)
        with open(args.usage_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(summary, ensure_ascii=False) + '\n')
    except OSError:
        pass
    print(json.dumps(summary, ensure_ascii=False))
    if stopped == 'consecutive failures' or (stats['done'] == 0 and rows):
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

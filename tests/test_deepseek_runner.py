"""Exercise the migrated runner with real pending/cache files and a fake HTTP boundary."""
import io
import json
import urllib.error

import pytest

from rebang.translate import Cache
from tools import translate_deepseek as runner


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'REPO', str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REBANG_TRANSLATE_API_KEY', 'test-key-do-not-log')
    monkeypatch.setenv('REBANG_TRANSLATE_MODEL', 'deepseek-flash')
    monkeypatch.delenv('REBANG_TRANSLATE_KEY_ENV', raising=False)
    monkeypatch.delenv('REBANG_TRANSLATE_URL', raising=False)
    monkeypatch.delenv('REBANG_TRANSLATE_EFFORT', raising=False)
    cache = Cache(tmp_path / 'translate/cache.json')
    return cache


@pytest.mark.parametrize('model', ['deepseek-pro', 'other-flash', 'deepseek-flash-pro'])
def test_refuses_every_model_except_approved_flash(configured, monkeypatch, capsys, model):
    monkeypatch.setenv('REBANG_TRANSLATE_MODEL', model)
    with pytest.raises(SystemExit) as stopped:
        runner.main(['--cache', str(configured.path)])
    assert stopped.value.code == 4
    assert 'test-key-do-not-log' not in capsys.readouterr().out
    assert not configured.path.exists()


def test_model_rejection_does_not_echo_the_value(configured, monkeypatch, capsys):
    monkeypatch.setenv('REBANG_TRANSLATE_MODEL', 'sk-accidentally-pasted-key')
    with pytest.raises(SystemExit):
        runner.main(['--cache', str(configured.path)])
    assert 'sk-accidentally-pasted-key' not in capsys.readouterr().out


def test_refuses_plain_http_endpoint(configured, monkeypatch, capsys):
    monkeypatch.setenv('REBANG_TRANSLATE_URL', 'http://api.deepseek.com/chat/completions')
    with pytest.raises(SystemExit) as stopped:
        runner.main(['--cache', str(configured.path)])
    assert stopped.value.code == 4
    assert not configured.path.exists()


def test_redirects_are_not_followed_so_the_key_stays_put():
    assert runner.NoRedirect().redirect_request(None, None, 302, 'Found', {}, 'https://evil.example/') is None
    assert any(isinstance(h, runner.NoRedirect) for h in runner.OPENER.handlers)


def test_usage_counts_failed_attempts(configured, monkeypatch, capsys):
    configured.want('One', 'en')
    configured.want('Two', 'en')
    configured.save()
    replies = iter([
        {'choices': [{'finish_reason': 'length', 'message': {'content': ''}}],
         'usage': {'prompt_tokens': 10, 'completion_tokens': 10}},
        {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"1":"一"}'}}],
         'usage': {'prompt_tokens': 10, 'completion_tokens': 10}},
        {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"1":"二"}'}}],
         'usage': {'prompt_tokens': 10, 'completion_tokens': 10}},
    ])
    monkeypatch.setattr(runner.OPENER, 'open', lambda request, timeout: io.BytesIO(json.dumps(next(replies)).encode()))
    assert runner.main(['--cache', str(configured.path), '--threads', '1']) == 0
    summary = json.loads(capsys.readouterr().out)
    assert (summary['done'], summary['requests'], summary['prompt_tokens']) == (2, 3, 30)


def test_missing_key_exits_before_creating_cache(configured, monkeypatch, capsys):
    monkeypatch.delenv('REBANG_TRANSLATE_API_KEY')
    with pytest.raises(SystemExit) as stopped:
        runner.main(['--cache', str(configured.path)])
    assert stopped.value.code == 4
    assert json.loads(capsys.readouterr().out)['error'] == 'api key env not set'
    assert not configured.path.exists()


def test_real_pending_is_filled_and_usage_logged(configured, monkeypatch, capsys, tmp_path):
    configured.want('New update', 'en', kind='title')
    configured.save()
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        body = json.loads(request.data)
        assert body['model'] == 'deepseek-flash'
        assert body['thinking'] == {'type': 'disabled'}
        assert json.loads(body['messages'][1]['content']) == {'1': 'New update'}
        assert request.get_header('Authorization') == 'Bearer test-key-do-not-log'
        return io.BytesIO(json.dumps({
            'choices': [{'finish_reason': 'stop', 'message': {'content': '{"1":"最新进展"}'}}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 5},
        }).encode())

    monkeypatch.setattr(runner.OPENER, 'open', urlopen)
    assert runner.main(['--cache', str(configured.path), '--threads', '1']) == 0
    output = capsys.readouterr().out
    assert 'test-key-do-not-log' not in output
    summary = json.loads(output)
    assert (summary['done'], summary['failed'], summary['remaining'], summary['requests']) == (1, 0, 0, 1)
    restored = Cache(configured.path)
    assert restored.get('New update', 'en')['zh'] == '最新进展'
    assert restored.get('New update', 'en')['engine'] == 'openai-compatible:deepseek-flash'
    log = tmp_path / 'var/rebang/logs/deepseek-usage.jsonl'
    assert json.loads(log.read_text()) == summary
    assert len(requests) == 1


def test_network_failure_keeps_pending_and_does_not_log_key(configured, monkeypatch, capsys):
    configured.want('New update', 'en', kind='title')
    configured.save()
    attempts = []

    def fail(*args, **kwargs):
        attempts.append(1)
        raise urllib.error.URLError('test-key-do-not-log')

    monkeypatch.setattr(runner.OPENER, 'open', fail)
    assert runner.main(['--cache', str(configured.path), '--threads', '1']) == 2
    output = capsys.readouterr().out
    assert 'test-key-do-not-log' not in output
    summary = json.loads(output)
    assert (summary['done'], summary['failed'], summary['remaining']) == (0, 1, 1)
    assert len(attempts) == 2
    restored = Cache(configured.path)
    assert restored.get('New update', 'en') is None
    assert len(restored.pending) == 1


def test_cache_save_holds_the_shared_lock(tmp_path):
    import fcntl
    import threading
    import time
    cache = Cache(tmp_path / 'translate/cache.json')
    cache.want('Queued by ingest', 'en')
    cache.path.parent.mkdir(parents=True)
    done = threading.Event()
    with open(cache.path.with_name('.cache.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        worker = threading.Thread(target=lambda: (cache.save(), done.set()))
        worker.start()
        time.sleep(0.2)
        assert not done.is_set()  # 另一写入者持锁时必须等待
    worker.join(5)
    assert done.is_set()
    assert len(Cache(cache.path).pending) == 1


def test_refresh_keeps_site_when_build_cannot_start(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / 'tools').mkdir()
    shutil.copy(repo / 'tools/rebang_refresh.sh', tmp_path / 'tools/')
    (tmp_path / 'site-v11').mkdir()
    (tmp_path / 'site-v11/index.html').write_text('previous')
    path = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'
    if not shutil.which('flock', path=path):
        pytest.skip('flock not installed')
    result = subprocess.run(['sh', 'tools/rebang_refresh.sh', '--no-fetch', '--no-publish'], cwd=tmp_path,
                            env={'PATH': path, 'HOME': str(tmp_path), 'BOX_PYTHON': str(tmp_path / 'missing-python')},
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert (tmp_path / 'site-v11/index.html').read_text() == 'previous'
    assert not (tmp_path / 'site-v11.prev').exists()


def test_unreadable_cache_is_not_overwritten(tmp_path):
    import os
    if os.geteuid() == 0:
        pytest.skip('root can read mode-000 files')
    cache = Cache(tmp_path / 'translate/cache.json')
    cache.put('Old', 'en', '旧', 'x')
    cache.save()
    os.chmod(cache.path, 0)
    try:
        writer = Cache(cache.path)  # 读不了，内存里是空的
        writer.want('New', 'en')
        with pytest.raises(PermissionError):
            writer.save()
    finally:
        os.chmod(cache.path, 0o600)
    assert Cache(cache.path).get('Old', 'en')['zh'] == '旧'
    assert oct(cache.path.stat().st_mode & 0o777) == '0o600'


def test_save_keeps_file_mode_and_only_merges_own_changes(tmp_path):
    import os
    path = tmp_path / 'translate/cache.json'
    first = Cache(path)
    first.want('Title', 'en', kind='title')
    first.save()
    os.chmod(path, 0o600)
    stale = Cache(path)            # 拿到旧快照的另一写入者
    fresh = Cache(path)
    fresh.put('Title', 'en', '标题', 'x')
    fresh.save()
    stale.want('Other', 'en')
    stale.save()                   # 不能把已译的 Title 又排回待译
    final = Cache(path)
    assert final.get('Title', 'en')['zh'] == '标题'
    assert set(r['src'] for r in final.pending.values()) == {'Other'}
    assert oct(path.stat().st_mode & 0o777) == '0o600'


def test_pending_already_translated_is_dropped_on_load(tmp_path):
    import json as _json
    from rebang.translate import text_key
    path = tmp_path / 'cache.json'
    k = text_key('Done', 'en')
    path.write_text(_json.dumps({'entries': {k: {'src': 'Done', 'src_lang': 'en', 'zh': '完', 'engine': 'x'}}}))
    path.with_name('pending.json').write_text(_json.dumps({'pending': {k: {'src': 'Done', 'src_lang': 'en'}}}))
    assert Cache(path).pending == {}


def test_bad_usage_values_do_not_crash_accounting(configured, monkeypatch, capsys):
    configured.want('One', 'en')
    configured.save()
    replies = iter([
        {'choices': [{'finish_reason': 'length', 'message': {'content': ''}}], 'usage': {'prompt_tokens': 'unknown'}},
        {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"1":"一"}'}}], 'usage': {'prompt_tokens': 7}},
    ])
    monkeypatch.setattr(runner.OPENER, 'open', lambda request, timeout: io.BytesIO(json.dumps(next(replies)).encode()))
    assert runner.main(['--cache', str(configured.path), '--threads', '1']) == 0
    summary = json.loads(capsys.readouterr().out)
    assert (summary['done'], summary['requests'], summary['prompt_tokens']) == (1, 2, 7)


def test_refresh_stops_when_old_prev_cannot_be_removed(tmp_path):
    import os
    import shutil
    import subprocess
    from pathlib import Path
    if os.geteuid() == 0:
        pytest.skip('root ignores directory permissions')
    path = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'
    if not shutil.which('flock', path=path):
        pytest.skip('flock not installed')
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / 'tools').mkdir()
    shutil.copy(repo / 'tools/rebang_refresh.sh', tmp_path / 'tools/')
    fake = tmp_path / 'fakepy'
    fake.write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = --out ] && out=$2; shift; done\n'
                    'case "$out" in site-v11.tmp-*) mkdir -p "$out/data"; echo new > "$out/index.html"; echo {} > "$out/data/meta.json";; '
                    '*) mkdir -p "$(dirname "$out")"; echo {} > "$out";; esac\n')
    fake.chmod(0o755)
    (tmp_path / 'site-v11').mkdir()
    (tmp_path / 'site-v11/index.html').write_text('previous')
    prev = tmp_path / 'site-v11.prev'
    (prev / 'locked').mkdir(parents=True)
    (prev / 'locked/f').write_text('x')
    os.chmod(prev / 'locked', 0o555)
    try:
        result = subprocess.run(['sh', 'tools/rebang_refresh.sh', '--no-fetch', '--no-publish'], cwd=tmp_path,
                                env={'PATH': path, 'HOME': str(tmp_path), 'BOX_PYTHON': str(fake)},
                                capture_output=True, text=True)
    finally:
        os.chmod(prev / 'locked', 0o755)
    assert result.returncode != 0
    assert (tmp_path / 'site-v11/index.html').read_text() == 'previous'
    assert not (prev / 'site-v11').exists()

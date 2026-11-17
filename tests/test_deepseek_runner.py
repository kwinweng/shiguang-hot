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

    monkeypatch.setattr(runner.urllib.request, 'urlopen', urlopen)
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

    monkeypatch.setattr(runner.urllib.request, 'urlopen', fail)
    assert runner.main(['--cache', str(configured.path), '--threads', '1']) == 2
    output = capsys.readouterr().out
    assert 'test-key-do-not-log' not in output
    summary = json.loads(output)
    assert (summary['done'], summary['failed'], summary['remaining']) == (0, 1, 1)
    assert len(attempts) == 2
    restored = Cache(configured.path)
    assert restored.get('New update', 'en') is None
    assert len(restored.pending) == 1

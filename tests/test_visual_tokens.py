"""Approved v0.3 values and publication boundary regressions."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generated_tokens_match_approved_design():
    reference = Path('/workspace/proto-bot/rebang-visual/deploy/tokens.css')
    css = (ROOT / 'web/tokens.css').read_text()
    if reference.exists():
        assert css == reference.read_text()
    for token in ['--c-brand:#D7282F', '--c-brand:#F05A5F', '--s-bar-h:70px', '--s-thumb-w:120px', '--s-thumb-h:90px']:
        assert token in css


def test_components_have_no_legacy_variables_or_literal_colors():
    for filename in ['style.css', 'visual.css']:
        css = (ROOT / 'web' / filename).read_text()
        assert not re.search(r'#[0-9a-fA-F]{3,8}\b', css)
        assert '--space-' not in css
        assert '--tab-clearance' not in css
        assert 'brightness(' not in css
        assert not re.search(r'(?:font-size|line-height):\s*\d', css.replace('font-size:11px;line-height:14px', ''))


def test_clearance_has_no_later_mobile_override():
    css = (ROOT / 'web/visual.css').read_text()
    assert 'padding-bottom:calc(var(--s-bar-h) + 16px + env(safe-area-inset-bottom) + 16px)' in css
    assert css.count('.visual-main{') == 2  # mobile rule and desktop-only rule
    assert 'height:calc(var(--s-bar-h) + 16px + env(safe-area-inset-bottom) + 8px);background:var(--c-bg)' in css
    assert 'backdrop-filter:var(--m-blur)' in css


def test_categories_keep_regular_weight_and_brand_underline():
    css = (ROOT / 'web/visual.css').read_text()
    rule = re.search(r'\.chips>button.on\{([^}]+)', css)[1]
    assert 'font-weight:400' in rule
    assert 'border-bottom-color:var(--c-brand)' in rule


def test_acceptance_list_is_exactly_49_unique_screens():
    from tools.qa_v03 import MOBILE, DESKTOP
    assert len(MOBILE) == 42
    assert len(DESKTOP) == 7
    assert len(set(MOBILE + DESKTOP)) == 49
    assert 'news-quick-mid' in MOBILE


def test_presentation_preserves_bookmark_identity_and_scope(tmp_path):
    import json
    from shiguang.site import visual, history
    from tests.test_news_history import context, item
    record = item(7)
    content, site = context([record, record])
    content.now = site.now
    content.heat = {}
    content.trials = []
    visual.write(tmp_path, content)
    data = json.loads((tmp_path / 'visual-data.json').read_text())
    assert data['scope'] == 'public'
    assert len(data['news']) == 1
    assert data['news'][0]['id'] == history.uid(record)
    assert len(data['news'][0]['spark'].split()) == 72
    content.private = True
    visual.write(tmp_path, content)
    assert json.loads((tmp_path / 'visual-data.json').read_text())['scope'] == 'private'

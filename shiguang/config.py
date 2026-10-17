"""sources.json, the build mode and where each source's files live."""
import json, math, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # repository root
WEB = ROOT / 'web'                               # style.css, app.js, assets/


def private_mode():
    return os.getenv('SITE_MODE') == 'private' or os.getenv('MAIL_DIGEST') == '1'


def config():
    data = json.loads(Path(os.getenv('SOURCES_OVERRIDE', ROOT / 'sources.json')).read_text())
    ids = set()
    for s in data['sources']:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', s['id']) or s['id'] in ids or s['id'] in ('archive','media','assets','img','index','hot','all'):
            raise ValueError('来源 id 非法或重复')
        ids.add(s['id'])
        if s['visibility'] not in ('public', 'private') or s['type'] not in ('telegram', 'inbox'):
            raise ValueError('来源类型或 visibility 非法')
        if s['type'] == 'inbox' and s.get('adapter', 'native') not in ('native', 'mail', 'world', 'x'):
            raise ValueError('未知 adapter')
        for field in ('home_weight','daily_order'):
            value=s.get(field,1 if field=='home_weight' else 50 if s['type']=='telegram' else 45)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or (field=='home_weight' and value<0):
                raise ValueError(field+' 必须为有效数值，home_weight 不得为负')
        cap=s.get('home_cap',4 if s['type']=='telegram' else 8)
        if isinstance(cap,bool) or not isinstance(cap,int) or cap<0:
            raise ValueError('home_cap 必须为非负整数')
    return data


def directory(source):
    return Path(os.getenv(source.get('env', source['id'].upper() + '_FEED_DIR'), source.get('directory', '/workspace/feeds-inbox/' + source['id'])))

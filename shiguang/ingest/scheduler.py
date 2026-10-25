"""Natural-hour source quotas in tg.db. This is not a distributed lock/service."""
import fcntl
import hashlib
import json
import re
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from shiguang.model import BEIJING
from shiguang.ingest import http

TABLES = {'source_fetch_meta', 'source_fetch_state', 'source_fetch_batch', 'fetch_resource_state'}
BACKOFF = (1, 2, 4, 8, 12, 24)
BLOCKED_COOLDOWN_SECONDS = 6 * 3600
BLOCKED_ALERT_THRESHOLD = 3


def utc(now):
    if now.tzinfo is None:
        raise ValueError('fetch time must include timezone')
    return now.astimezone(timezone.utc)


def stamp(now):
    return utc(now).isoformat()


def next_hour(now):
    return (now.astimezone(BEIJING).replace(minute=0, second=0, microsecond=0) +
            timedelta(hours=1)).astimezone(timezone.utc)


def endpoint(url):
    parts = urlsplit(url)
    if parts.scheme.lower() not in ('http', 'https') or not parts.netloc or parts.username or parts.password:
        raise ValueError('expected public HTTP endpoint without credentials')
    # Do not discard/reorder query parameters or infer aliases from redirects/titles.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, ''))


def plans(sources):
    grouped = {}
    for source in sorted(sources, key=lambda s: s['id']):
        if source['type'] == 'telegram':
            identity = 'telegram:' + source['channel'].lower()
        elif source['type'] == 'feed':
            identity = 'feed:' + hashlib.sha256(endpoint(source['url']).encode()).hexdigest()
        else:
            continue
        grouped.setdefault(identity, source)
    return list(grouped.items())


def validate_image_ref(task, key):
    try:
        table, owner, item, channel, image_id, index, url, at = task
        valid = (table in ('msg', 'entry') and isinstance(owner, str) and
                 re.fullmatch(r'[A-Za-z0-9_-]+', owner) and channel == owner and
                 type(index) is int and index > 0 and isinstance(url, str) and
                 url.startswith('https://') and key == 'image:' + hashlib.sha256(endpoint(url).encode()).hexdigest())
        if table == 'msg':
            valid = valid and type(item) is int and item > 0 and image_id == item
        else:
            valid = valid and isinstance(item, str) and image_id == hashlib.sha1(item.encode()).hexdigest()[:12]
        utc(datetime.fromisoformat(at))
        if not valid:
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise RuntimeError('damaged image reference state; collection stopped') from None


@contextmanager
def collection_lock(database):
    """Persistent lock inode; removing it on exit would permit racing collectors."""
    with open(str(Path(database).resolve()) + '.fetch.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def ensure_schema(db):
    if db.execute('pragma quick_check').fetchone() != ('ok',):
        raise RuntimeError('fetch database is damaged; collection stopped')
    existing = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    if existing & TABLES:
        if not TABLES <= existing:
            raise RuntimeError('fetch state schema incomplete; collection stopped')
        if db.execute('select version from source_fetch_meta').fetchall() != [(1,)]:
            raise RuntimeError('unsupported fetch state schema')
        # Read every required column before attempting network access; never silently repair it.
        db.execute('select source_id,last_attempt_at,last_success_at,next_eligible_at,consecutive_failures,status,error_code from source_fetch_state limit 0')
        db.execute('select source_id,hour_key,attempt_id,started_at,finished_at,status from source_fetch_batch limit 0')
        db.execute('select source_id,resource_key,last_attempt_at,etag,last_modified,materialized_at,representation_valid,signature,error_code,image_refs from fetch_resource_state limit 0')
        for key, references in db.execute('select resource_key,image_refs from fetch_resource_state'):
            try:
                tasks = json.loads(references)
            except (ValueError, TypeError):
                raise RuntimeError('damaged resource state; collection stopped') from None
            if not isinstance(tasks, list):
                raise RuntimeError('damaged resource state; collection stopped')
            for task in tasks:
                validate_image_ref(task, key)
        return
    db.executescript('''
        create table source_fetch_meta(version integer not null);
        insert into source_fetch_meta values(1);
        create table source_fetch_state(
            source_id text primary key, last_attempt_at text, last_success_at text,
            next_eligible_at text, consecutive_failures integer not null default 0,
            status text not null, error_code text);
        create table source_fetch_batch(
            source_id text not null, hour_key text not null, attempt_id text not null,
            started_at text not null, finished_at text, status text not null,
            primary key(source_id,hour_key));
        create table fetch_resource_state(
            source_id text not null, resource_key text not null, last_attempt_at text,
            etag text, last_modified text, materialized_at text,
            representation_valid integer not null default 0, signature text,
            error_code text, image_refs text not null default '[]',
            primary key(source_id,resource_key));
    ''')


def emit(source, **fields):
    # Called only for sources visible to this build. No URLs, response bodies or exception text.
    print('fetch_status ' + json.dumps(dict(source=source['id'], **fields), sort_keys=True), file=sys.stderr)


def report(source, result):
    if result.pop('blocked_alert', False):
        emit(source, result='alert', alert='blocked', error_code=result['error_code'],
             consecutive_blocks=result.pop('consecutive_blocks'),
             next_eligible_at=result['next_eligible_at'])
    else:
        result.pop('consecutive_blocks', None)
    emit(source, **result)


def claim(db, source_id, now):
    now = utc(now)
    hour = now.astimezone(BEIJING).strftime('%Y-%m-%dT%H')
    db.execute('begin immediate')
    try:
        row = db.execute('select status,next_eligible_at,consecutive_failures from source_fetch_state where source_id=?', (source_id,)).fetchone()
        if row:
            if row[0] not in ('running', 'interrupted', 'ok', 'partial', 'error', 'blocked') or row[2] < 0:
                raise RuntimeError('invalid fetch state; collection stopped')
            if row[1]: utc(datetime.fromisoformat(row[1]))
            if row[0] == 'running':
                db.execute("update source_fetch_batch set status='interrupted',finished_at=? where source_id=? and status='running'", (stamp(now), source_id))
                db.execute("update source_fetch_state set status='interrupted',error_code='interrupted' where source_id=?", (source_id,))
        reason = None
        if row and row[0] == 'blocked' and row[1] and utc(datetime.fromisoformat(row[1])) > now:
            reason = 'blocked'
        elif db.execute('select 1 from source_fetch_batch where source_id=? and hour_key=?', (source_id, hour)).fetchone():
            reason = 'hour_used'
        elif row and row[1] and utc(datetime.fromisoformat(row[1])) > now:
            reason = 'not_due'
        if reason:
            db.commit()
            return None, reason
        attempt = uuid.uuid4().hex
        # Holding the exclusive collection lock means prior running rows belong to a dead run.
        db.execute("update source_fetch_batch set status='interrupted',finished_at=? where source_id=? and status='running'", (stamp(now), source_id))
        db.execute('insert into source_fetch_batch values(?,?,?,?,?,?)', (source_id, hour, attempt, stamp(now), None, 'running'))
        db.execute('''insert into source_fetch_state(source_id,last_attempt_at,next_eligible_at,status)
            values(?,?,?,'running') on conflict(source_id) do update set
            last_attempt_at=excluded.last_attempt_at,next_eligible_at=excluded.next_eligible_at,status='running',error_code=null''',
                   (source_id, stamp(now), stamp(next_hour(now))))
        db.commit()  # Claim is durable BEFORE the first request.
        return Batch(db, source_id, attempt, now, row[2] if row else 0), None
    except BaseException:
        db.rollback()
        raise


class Batch:
    def __init__(self, db, source_id, attempt, now, failures):
        self.db, self.source_id, self.attempt, self.now = db, source_id, attempt, utc(now)
        self.failures = failures
        self.clock = lambda: self.now
        self.responses = {}
        self.image_cache = {}
        self.errors = []
        self.requests = self.cached = self.new = self.progress = 0
        self.halted = False

    def key(self, kind, url):
        return kind + ':' + hashlib.sha256(endpoint(url).encode()).hexdigest()

    def state(self, key):
        return self.db.execute('select etag,last_modified,representation_valid,signature from fetch_resource_state where source_id=? and resource_key=?', (self.source_id, key)).fetchone()

    def note(self, error):
        if not isinstance(error, http.FetchFailure):
            error = http.FetchFailure('invalid_content')
        if not any(e.code == error.code for e in self.errors):
            self.errors.append(error)
        if error.code in ('blocked', 'rate_limited'):
            self.halted = True

    def resource_error(self, kind, url, error):
        if not isinstance(error, http.FetchFailure):
            error = http.FetchFailure('invalid_content')
        self.note(error)
        self.db.execute('update fetch_resource_state set error_code=? where source_id=? and resource_key=?',
                        (error.code, self.source_id, self.key(kind, url)))

    def clear_error(self, kind, url):
        self.db.execute('update fetch_resource_state set error_code=null where source_id=? and resource_key=?',
                        (self.source_id, self.key(kind, url)))

    def release_image_response(self, url, error=None):
        key = self.key('image', url)
        response = self.responses.get(key)
        if isinstance(response, http.Response):
            response.body = b''  # Reuse the converted file, not every original image body in RAM.
        if error is not None and key in self.responses:
            self.responses[key] = error

    def get(self, kind, url, signature=None):
        key = self.key(kind, url)
        if key in self.responses:
            result = self.responses[key]
            if isinstance(result, Exception):
                raise result
            self.cached += 1
            return result
        if self.halted:
            raise self.errors[-1]
        state = self.state(key)
        headers = {}
        if state and state[2] and signature is not None and state[3] == signature:
            if state[0]: headers['If-None-Match'] = state[0]
            if state[1]: headers['If-Modified-Since'] = state[1]
        elif state and signature is not None:
            self.db.execute('update fetch_resource_state set etag=null,last_modified=null,representation_valid=0 where source_id=? and resource_key=?', (self.source_id, key))
        self.db.execute('''insert into fetch_resource_state(source_id,resource_key,last_attempt_at) values(?,?,?)
            on conflict(source_id,resource_key) do update set last_attempt_at=excluded.last_attempt_at''',
                        (self.source_id, key, stamp(self.now)))
        self.db.commit()
        self.requests += 1
        try:
            response = http.request(url, headers)
            http.check(response, utc(self.clock()))
            if response.status == 304 and not headers:
                raise http.FetchFailure('materialization_missing')
            if response.status == 304:
                self.cached += 1
            self.clear_error(kind, url)
            self.responses[key] = response
            return response
        except http.FetchFailure as error:
            self.responses[key] = error
            self.note(error)
            self.db.execute('update fetch_resource_state set error_code=? where source_id=? and resource_key=?', (error.code, self.source_id, key))
            self.db.commit()
            raise

    def materialize(self, kind, url, response, signature):
        self.db.execute('''update fetch_resource_state set etag=?,last_modified=?,
            materialized_at=?,representation_valid=1,signature=?,error_code=null
            where source_id=? and resource_key=?''',
            (response.headers.get('etag'), response.headers.get('last-modified'), stamp(self.now),
             signature, self.source_id, self.key(kind, url)))
        self.db.commit()  # Parsed entries and their validators are committed together.

    def image_task(self, url, task):
        key = self.key('image', url)
        validate_image_ref(task, key)
        row = self.db.execute('select image_refs from fetch_resource_state where source_id=? and resource_key=?', (self.source_id, key)).fetchone()
        tasks = json.loads(row[0]) if row else []
        if not any(t[:-1] == task[:-1] for t in tasks):
            tasks.append(task)
        self.db.execute('''insert into fetch_resource_state(source_id,resource_key,image_refs) values(?,?,?)
            on conflict(source_id,resource_key) do update set image_refs=excluded.image_refs''',
            (self.source_id, key, json.dumps(tasks)))

    def retry_images(self):
        from shiguang.ingest import telegram
        for key, references in self.db.execute('select resource_key,image_refs from fetch_resource_state where source_id=? and image_refs!=?', (self.source_id, '[]')).fetchall():
            remaining = []
            for task in json.loads(references):
                table, owner, item, c, image_id, index, url, at = task
                if self.now - utc(datetime.fromisoformat(at)) > timedelta(days=telegram.MEDIA_DAYS):
                    continue
                if table not in ('msg', 'entry'):
                    raise RuntimeError('invalid image work state')
                column = 'ch' if table == 'msg' else 'source'
                row = self.db.execute(f'select images from {table} where {column}=? and id=?', (owner, item)).fetchone()
                if not row:
                    continue
                # Keep successful references too: a later media-cache loss plus feed 304 must be repairable.
                remaining.append(task)
                rel = f'media/{c}/{image_id}_{index}.webp'
                if key in self.responses and not Path(telegram.D, rel).is_file():
                    continue
                path = telegram.save_image(c, image_id, index, url, self)
                if not path:
                    continue
                images = json.loads(row[0])
                if path not in images:
                    prefix = f'media/{c}/{image_id}_'
                    def position(image):
                        match = re.fullmatch(re.escape(prefix) + r'(\d+)\.webp', image)
                        return int(match[1]) if match else 0
                    images = sorted(images + [path], key=position)
                    self.db.execute(f'update {table} set images=? where {column}=? and id=?', (json.dumps(images), owner, item))
            self.db.execute('update fetch_resource_state set image_refs=? where source_id=? and resource_key=?', (json.dumps(remaining), self.source_id, key))
        self.db.commit()

    def finish(self, finished=None):
        finished = utc(finished or self.now)
        errors = {e.code: e for e in self.errors}
        code = 'blocked' if 'blocked' in errors else 'rate_limited' if 'rate_limited' in errors else next(iter(errors), None)
        status = 'blocked' if code == 'blocked' else ('partial' if self.progress else 'error') if code else 'ok'
        failures = self.failures + 1 if code else 0
        eligible = next_hour(self.now)
        if code == 'blocked':
            eligible = finished + timedelta(seconds=BLOCKED_COOLDOWN_SECONDS)
        elif code == 'rate_limited':
            eligible = max(eligible, errors[code].retry_at)
        elif code:
            eligible = max(eligible, finished + timedelta(hours=BACKOFF[min(failures - 1, len(BACKOFF) - 1)]))
        self.db.execute('''update source_fetch_state set status=?,error_code=?,next_eligible_at=?,
            consecutive_failures=?,last_success_at=case when ?='ok' then ? else last_success_at end where source_id=?''',
            (status, code, stamp(eligible), failures, status, stamp(finished), self.source_id))
        self.db.execute('update source_fetch_batch set status=?,finished_at=? where attempt_id=?', (status, stamp(finished), self.attempt))
        self.db.execute("delete from source_fetch_batch where started_at<? and status in ('ok','partial','error')", (stamp(self.now - timedelta(days=7)),))
        self.db.execute('''delete from fetch_resource_state where image_refs='[]'
            and (resource_key like 'image:%' or resource_key like 'telegram:%')
            and coalesce(last_attempt_at,'') < ?''', (stamp(self.now - timedelta(days=14)),))
        self.db.commit()
        # The batch table has no error_code column; 'blocked' is its only blocked-result status.
        consecutive_blocks = 0
        for (batch_status,) in self.db.execute(
                '''select status from source_fetch_batch where source_id=? and finished_at is not null
                   order by finished_at desc, rowid desc''', (self.source_id,)):
            if batch_status != 'blocked':
                break
            consecutive_blocks += 1
        success = self.db.execute('select last_success_at from source_fetch_state where source_id=?', (self.source_id,)).fetchone()[0]
        return dict(result=status, error_code=code, next_eligible_at=stamp(eligible),
                    attempt_id=self.attempt, hour_key=self.now.astimezone(BEIJING).strftime('%Y-%m-%dT%H'),
                    last_checked=stamp(self.now), last_success=success,
                    requests=self.requests, cache_hits=self.cached, new=self.new,
                    blocked_alert=code == 'blocked' and consecutive_blocks >= BLOCKED_ALERT_THRESHOLD,
                    consecutive_blocks=consecutive_blocks)


def run(db, sources, images_migrated=False, *, clock=None, first_page_only=False):
    """Caller holds collection_lock; adapters remain independently usable in offline tests."""
    from shiguang.ingest import telegram, web
    ensure_schema(db)
    db.commit()
    clock = clock or (lambda: datetime.now(timezone.utc))
    first = True
    for source_id, source in plans(sources):
        # Sample each source's actual claim time; a long build may cross an hour boundary.
        batch, reason = claim(db, source_id, clock())
        if reason:
            state = db.execute('select status,next_eligible_at,last_attempt_at,last_success_at from source_fetch_state where source_id=?', (source_id,)).fetchone()
            emit(source, result='skip', skip_reason=reason, source_status=state[0], next_eligible_at=state[1],
                 last_checked=state[2], last_success=state[3], requests=0, cache_hits=0, new=0)
            continue
        if not first:
            time.sleep(1)  # At least one second between the first visits of successive sources.
        first = False
        batch.clock = clock
        try:
            if source['type'] == 'telegram':
                options = dict(first_page_only=True) if first_page_only else {}
                telegram.fetch(db, [source['channel']], batch.now.astimezone(BEIJING), images_migrated, batch=batch, **options)
            else:
                options = dict(download_media=False) if first_page_only else {}
                web.fetch(db, [source], batch.now.astimezone(BEIJING), batch=batch, **options)
            if not first_page_only:
                batch.retry_images()
        except sqlite3.Error:
            raise  # State corruption/persistence errors must block collection/publication.
        except (http.FetchFailure, ValueError, OSError) as error:
            batch.note(error)
        report(source, batch.finish(clock()))

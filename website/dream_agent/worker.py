"""Persistent per-account scheduling, serialized with SQLite transactions."""
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .store import Store, encode
from .engine import run
from .dreaming import dream
from .tools import validate_case


def load(store):
    row = store.db.execute("SELECT value FROM state WHERE key='worker'").fetchone()
    return json.loads(row[0]) if row else {'status': 'stopped'}


def save(store, config):
    store.db.execute("INSERT OR REPLACE INTO state VALUES ('worker',?)", (encode(config),))


def configure(store, goal, case, interval, dream_interval, actor):
    validate_case(case)
    if not goal.strip() or len(goal) > 8000:
        raise ValueError('Tujuan wajib diisi (maksimal 8000 karakter).')
    interval, dream_interval = int(interval), int(dream_interval)
    if not 30 <= interval <= 31536000 or not 30 <= dream_interval <= 31536000:
        raise ValueError('Interval harus 30 detik hingga satu tahun.')
    with store.transaction():
        config = load(store)
        config.update(goal=goal, dataset=case, interval=interval, dream_interval=dream_interval,
                      next_run=0, next_dream=0, status='running', last_error=None, mode='dataset')
        save(store, config)
        store.log('worker_configured', {'actor': actor, 'interval': interval, 'dream_interval': dream_interval})


def control(store, action, actor):
    with store.transaction():
        config = load(store)
        if 'dataset' not in config and config.get('mode') != 'live':
            raise ValueError('Simpan tujuan dan dataset terlebih dahulu.')
        config['status'] = {'pause': 'paused', 'stop': 'stopped', 'resume': 'running'}[action]
        save(store, config)
        store.log('worker_' + action, {'actor': actor})


def tick(store, timestamp=None):
    current = time.time() if timestamp is None else timestamp
    if load(store).get('mode') == 'live':
        return live_tick(store, current)
    # All built-in tools are bounded and local. Atomic commit covers run, audit,
    # dreaming and checkpoint: a crash rolls back the entire tick for safe retry.
    with store.transaction():
        config = load(store)
        if config['status'] != 'running':
            return config
        config['heartbeat'] = current
        if current >= config.get('next_run', 0):
            try:
                case = dict(config['dataset'])
                case['as_of'] = datetime.fromtimestamp(current, timezone(timedelta(hours=7))).date().isoformat()
                version = store.active()[0]
                fingerprint = hashlib.sha256(encode([config['goal'], case, version]).encode()).hexdigest()
                if fingerprint != config.get('fingerprint'):
                    result = run(store, config['goal'], case)
                    if result['errors']:
                        raise ValueError(str(result['errors']))
                    config.update(fingerprint=fingerprint, last_run=result['id'], last_result='Riset selesai', last_error=None)
                else:
                    config['last_result'] = 'Menunggu data, tanggal riset, atau prosedur baru'
                config['next_run'] = current + config['interval']
            except Exception as exc:
                config['last_error'] = str(exc)[:1000]
                config['next_run'] = current + min(config['interval'], 300)
                store.log('worker_error', {'error': config['last_error']})
        if current >= config.get('next_dream', 0):
            try:
                result = dream(store)
                config['last_dream'] = result['status']
                config['next_dream'] = current + config['dream_interval']
            except Exception as exc:
                config['last_error'] = str(exc)[:1000]
                config['next_dream'] = current + 300
                store.log('worker_dream_error', {'error': config['last_error']})
        save(store, config)
        return config


def serve(root, stop_event, poll=5):
    root = Path(root)
    while not stop_event.is_set():
        for path in root.glob('*.sqlite3'):
            try:
                store = Store(path)
                try:
                    tick(store)
                finally:
                    store.close()
            except Exception:
                logging.getLogger(__name__).exception('Worker failed for %s', path.name)
        stop_event.wait(poll)


def install(app):
    if app.config.get('TESTING') or not app.config.get('DREAM_AGENT_WORKER_ENABLED', True):
        return
    if 'dream_agent_worker' in app.extensions:
        return
    root = app.config.get('DREAM_AGENT_DATA_DIR', Path(app.instance_path) / 'dream_agent')
    event = threading.Event()
    thread = threading.Thread(target=serve, args=(root, event), daemon=True, name='dream-agent-worker')
    app.extensions['dream_agent_worker'] = (thread, event)
    thread.start()


def configure_live(store, ticker, interval, dream_interval, actor):
    from .live import symbol
    import uuid
    ticker = symbol(ticker)
    interval, dream_interval = int(interval), int(dream_interval)
    if not 900 <= interval <= 31536000 or not 60 <= dream_interval <= 31536000:
        raise ValueError('Riset live minimal 900 detik; dreaming minimal 60 detik.')
    with store.transaction():
        config = load(store)
        config.update(mode='live', ticker=ticker, goal='Pantau fundamental, perubahan harga dan risiko ' + ticker,
                      interval=interval, dream_interval=dream_interval, next_run=0, next_dream=0,
                      status='running', revision=uuid.uuid4().hex, lease_until=0, fingerprint=None, last_error=None)
        save(store, config)
        store.log('live_research_configured', {'actor': actor, 'ticker': ticker, 'interval': interval})


def live_tick(store, current):
    from .live import collect, analyze
    import uuid
    token = uuid.uuid4().hex
    with store.transaction():
        config = load(store)
        if config.get('status') != 'running' or config.get('lease_until', 0) > current:
            return config
        config['heartbeat'] = current
        due = current >= config.get('next_run', 0)
        if due:
            config.update(lease=token, lease_until=current + 120, last_result='Mengambil harga dan laporan keuangan')
        save(store, config)
    payload, error = None, None
    if due:
        try:
            payload = collect(config['ticker'])
        except Exception as exc:
            error = str(exc)[:1000]
    with store.transaction():
        latest = load(store)
        if latest.get('revision') != config.get('revision') or latest.get('status') != 'running':
            return latest
        if due and latest.get('lease') != token:
            return latest
        if due:
            latest['lease_until'] = 0
            latest['next_run'] = current + latest['interval']
            if error:
                latest.update(last_error=error, last_result='Pengambilan data gagal; akan dicoba pada jadwal berikutnya')
                store.log('live_fetch_error', {'error': error})
            else:
                store.db.execute('CREATE TABLE IF NOT EXISTS research_reports(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
                row = store.db.execute('SELECT body FROM research_reports ORDER BY id DESC LIMIT 1').fetchone()
                previous = json.loads(row[0])['evidence'] if row else None
                stable = {k:v for k,v in payload.items() if k != 'retrieved_at'}
                fingerprint = hashlib.sha256(encode([stable, store.active()[0]]).encode()).hexdigest()
                if fingerprint != latest.get('fingerprint'):
                    report = analyze(payload, previous if previous and previous.get('ticker') == payload['ticker'] else None)
                    report['version'] = store.active()[0]
                    cursor = store.db.execute('INSERT INTO research_reports(body) VALUES (?)', (encode(report),))
                    latest.update(fingerprint=fingerprint, last_report=cursor.lastrowid, last_result='Laporan riset nyata tersimpan')
                    store.log('live_report_completed', {'report': cursor.lastrowid, 'ticker': payload['ticker']})
                    # Feed quality experience into the existing approval-gated loop when two revenue periods exist.
                    statements = payload['statements']
                    if len(statements) >= 2 and all(x.get('revenue') is not None for x in statements[:2]):
                        case = dict(ticker=payload['ticker'], as_of=datetime.fromtimestamp(current, timezone(timedelta(hours=7))).date().isoformat(),
                                    period=statements[0]['period'], revenue=statements[0]['revenue'], previous_revenue=statements[1]['revenue'],
                                    comparable=False, synthetic=False, source=payload['sources'][1]['url'])
                        result = run(store, latest['goal'], case)
                        latest['last_run'] = result['id']
                else:
                    latest['last_result'] = 'Sumber diperiksa; belum ada perubahan data'
                latest.update(last_error=None, last_fetch=payload['retrieved_at'])
        if current >= latest.get('next_dream', 0):
            result = dream(store)
            latest.update(last_dream=result['status'], next_dream=current + latest['dream_interval'])
        save(store, latest)
        return latest

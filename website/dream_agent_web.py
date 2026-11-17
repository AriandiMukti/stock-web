"""Authenticated UI for the bundled procedural-learning agent."""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import hashlib
import json
import sqlite3
from pathlib import Path
from flask import jsonify, Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from .dream_agent.store import Store
from .dream_agent.engine import run
from .dream_agent.dreaming import dream, review, rollback

from .dream_agent.worker import configure, configure_live, control, load

dream_agent_web = Blueprint('dream_agent_web', __name__, url_prefix='/dream-agent')


def user_store():
    identity = hashlib.sha256(str(current_user.get_id()).encode()).hexdigest()
    root = Path(current_app.config.get('DREAM_AGENT_DATA_DIR',
                                     Path(current_app.instance_path) / 'dream_agent'))
    return Store(root / (identity + '.sqlite3'))


@dream_agent_web.route('/', methods=['GET', 'POST'])
@login_required
def index():
    store = user_store()
    try:
        if request.method == 'POST':
            action = request.form.get('action', '')
            actor = 'user:' + str(current_user.get_id())
            try:
                if action in ('pause', 'stop', 'resume'):
                    control(store, action, actor)
                    flash('Status worker diperbarui.', 'success')
                elif action == 'start_live':
                    configure_live(store, request.form.get('ticker', ''), request.form.get('interval', '3600'),
                                   request.form.get('dream_interval', '86400'), actor)
                    flash('Riset data nyata aktif.', 'success')
                elif action == 'start':
                    raw = request.form.get('dataset', '')
                    if len(raw.encode('utf-8')) > 100000:
                        raise ValueError('Dataset maksimal 100 KB.')
                    configure(store, request.form.get('goal', ''), json.loads(raw),
                              request.form.get('interval', '3600'), request.form.get('dream_interval', '86400'), actor)
                    flash('Worker aktif. Riset dan dreaming berjalan otomatis.', 'success')
                elif action == 'run':
                    raw = request.form.get('dataset', '')
                    if len(raw.encode('utf-8')) > 100000:
                        raise ValueError('Dataset maksimal 100 KB.')
                    case = json.loads(raw)
                    result = run(store, request.form.get('goal', ''), case)
                    if result['errors']:
                        flash('Run tersimpan, tetapi eksekusi gagal. Lihat detail riwayat.', 'error')
                    else:
                        flash('Riset selesai. Skor kualitas %.1f%%.' % (100 * result['evaluation']['score']), 'success')
                elif action == 'dream':
                    result = dream(store)
                    messages = {'pending': 'Proposal baru siap ditinjau.', 'already_pending': 'Proposal yang sama masih menunggu keputusan.',
                                'no_change': 'Belum ada pola kesalahan baru yang dapat ditangani.', 'blocked': 'Kandidat tidak lolos evaluasi.'}
                    flash(messages[result['status']], 'success')
                elif action in ('approve', 'reject'):
                    review(store, int(request.form.get('id', '')), actor,
                           request.form.get('reason', '').strip()[:1000], action == 'approve')
                    flash('Proposal disetujui.' if action == 'approve' else 'Proposal ditolak.', 'success')
                elif action == 'rollback':
                    rollback(store, int(request.form.get('id', '')), actor,
                             request.form.get('reason', '').strip()[:1000])
                    flash('Prosedur dipulihkan sebagai versi baru.', 'success')
                else:
                    raise ValueError('Tindakan tidak dikenal.')
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                flash('Tidak dapat memproses: ' + str(exc)[:300], 'error')
            return redirect(url_for('.index'))
        reports = []
        if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='research_reports'").fetchone():
            reports = [dict(id=r[0], **json.loads(r[1])) for r in store.db.execute('SELECT id,body FROM research_reports ORDER BY id DESC LIMIT 20')]
        version, procedure = store.active()
        runs = store.runs()
        proposals = store.proposals()
        versions = [r[0] for r in store.db.execute('SELECT id FROM versions ORDER BY id DESC')]
        audit = [dict(r) for r in store.db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 50')]
        example = json.loads((Path(__file__).parent / 'dream_agent' / 'examples' / 'adro_synthetic.json').read_text(encoding='utf-8'))
        return render_template('dream_agent.html', user=current_user, version=version,
                               reports=reports, worker=load(store), procedure=procedure, runs=list(reversed(runs))[:30], total_runs=len(runs),
                               proposals=list(reversed(proposals))[:30], versions=versions,
                               pending=sum(p['status'] == 'pending' for p in proposals), audit=audit,
                               audit_valid=store.verify(), example=json.dumps(example, indent=2, ensure_ascii=False))
    except sqlite3.Error:
        current_app.logger.exception('Dream Agent database error')
        return 'Penyimpanan Dream Agent sedang tidak tersedia. Coba lagi.', 503
    finally:
        store.close()


@dream_agent_web.route('/status')
@login_required
def worker_status():
    store = user_store()
    try:
        config = load(store)
        return jsonify({key: config.get(key) for key in ('status', 'heartbeat', 'next_run', 'next_dream', 'last_run', 'last_result', 'last_error', 'last_dream')})
    finally:
        store.close()

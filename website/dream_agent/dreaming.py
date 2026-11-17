import json
import time
from .engine import execute
from .evaluation import regression_cases, RUBRIC
from .store import encode, now
from .tools import CHECKS, LESSONS


def benchmark(procedure):
    return [execute('Uji kualitas riset', c, procedure)['evaluation']['score'] for c in regression_cases()]


def compare(base, candidate):
    before, after = benchmark(base), benchmark(candidate)
    return {"rubric": RUBRIC, "suite": "synthetic-regression-v1", "before": before, "after": after,
            "mean_before": sum(before) / len(before), "mean_after": sum(after) / len(after),
            "passed": all(b >= a for a, b in zip(before, after)) and sum(after) > sum(before)}


def dream(store, interval=None, timestamp=None):
    """One transaction prevents concurrent scheduler ticks creating duplicate proposals."""
    current = time.time() if timestamp is None else timestamp
    if interval is not None and interval <= 0:
        raise ValueError('Interval must be positive')
    with store.transaction():
        if interval is not None:
            last = store.db.execute("SELECT value FROM state WHERE key='last_dream'").fetchone()
            if last and current - float(last[0]) < interval:
                return {"status": "not_due"}
        store.db.execute("INSERT OR REPLACE INTO state VALUES ('last_dream',?)", (str(current),))
        version, base = store.active()
        # Only failures from the current procedure motivate a change.
        experience = [r for r in store.runs() if r['version'] == version]
        failures = {f for r in experience for f in r['evaluation']['failures']}
        added = [c for c in CHECKS if c in failures and c not in base['checks']]
        if not added:
            store.log('dream_no_change', {"base": version, "reason": "No supported new failure pattern"})
            return {"status": "no_change"}
        candidate = {"checks": [c for c in CHECKS if c in base['checks'] or c in added],
                     "lessons": list(dict.fromkeys(base['lessons'] + [LESSONS[c] for c in added]))}
        for proposal in store.proposals():
            if proposal['base'] == version and proposal['status'] == 'pending' and proposal['candidate'] == candidate:
                return {"status": "already_pending", "id": proposal['id']}
        evaluation = compare(base, candidate)
        body = {"candidate": candidate, "added_checks": added,
                "evidence_run_ids": [r['id'] for r in experience if set(r['evaluation']['failures']) & set(added)],
                "evaluation": evaluation, "created_at": now()}
        status = 'pending' if evaluation['passed'] else 'blocked'
        cursor = store.db.execute("INSERT INTO proposals(base,body,status) VALUES (?,?,?)", (version, encode(body), status))
        store.log('dream_proposed', {"proposal": cursor.lastrowid, "base": version, **body, "status": status})
        return {"id": cursor.lastrowid, "base": version, "status": status, **body}


def review(store, proposal_id, actor, reason, approve):
    if not actor.strip() or not reason.strip():
        raise ValueError('Actor and reason are required')
    with store.transaction():
        row = store.db.execute('SELECT * FROM proposals WHERE id=?', (proposal_id,)).fetchone()
        if row is None or row['status'] != 'pending':
            raise ValueError('Proposal does not exist or is not pending')
        proposal = json.loads(row['body'])
        version, base = store.active()
        new_version = None
        if approve:
            if version != row['base']:
                raise ValueError('Stale proposal: active version changed; run dreaming again')
            if not compare(base, proposal['candidate'])['passed']:
                raise ValueError('Evaluation gate failed')
            cursor = store.db.execute('INSERT INTO versions(body) VALUES (?)', (encode(proposal['candidate']),))
            new_version = cursor.lastrowid
            store.db.execute("UPDATE state SET value=? WHERE key='active'", (str(new_version),))
        status = 'approved' if approve else 'rejected'
        store.db.execute('UPDATE proposals SET status=? WHERE id=?', (status, proposal_id))
        store.log('proposal_' + status, {'proposal': proposal_id, 'actor': actor, 'reason': reason,
                                        'from_version': version, 'to_version': new_version})
        return {"status": status, "active_version": new_version if approve else version}


def rollback(store, target, actor, reason):
    if not actor.strip() or not reason.strip():
        raise ValueError('Actor and reason are required')
    with store.transaction():
        previous, _ = store.active()
        body = store.version(target)
        # Create a new version even when restoring old content, invalidating stale proposals.
        cursor = store.db.execute('INSERT INTO versions(body) VALUES (?)', (encode(body),))
        restored = cursor.lastrowid
        store.db.execute("UPDATE state SET value=? WHERE key='active'", (str(restored),))
        store.log('rollback', {'from_version': previous, 'restored_from': target, 'to_version': restored,
                               'actor': actor, 'reason': reason})
        return {"active_version": restored, "restored_from": target}

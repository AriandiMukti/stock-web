import argparse
import json
import sys
import time
from pathlib import Path
from .dreaming import dream, review, rollback
from .engine import run
from .planner import CommandPlanner
from .store import Store


def output(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local agent with auditable procedural learning')
    parser.add_argument('--db', default='data/agent.sqlite3')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    task = commands.add_parser('run')
    task.add_argument('--goal', required=True)
    task.add_argument('--dataset', required=True)
    task.add_argument('--model-command', help='JSON argv of a trusted local model wrapper')
    commands.add_parser('dream')
    commands.add_parser('proposals')
    commands.add_parser('status')
    commands.add_parser('runs')
    commands.add_parser('audit')
    commands.add_parser('verify-audit')
    for name in ('approve', 'reject', 'rollback'):
        command = commands.add_parser(name)
        command.add_argument('id', type=int)
        command.add_argument('--actor', required=True)
        command.add_argument('--reason', required=True)
    schedule = commands.add_parser('schedule')
    schedule.add_argument('--interval-seconds', type=float, default=86400)
    schedule.add_argument('--once', action='store_true', help='One due check, suitable for OS task schedulers')
    args = parser.parse_args(argv)
    store = Store(args.db)
    try:
        if args.command == 'run':
            path = Path(args.dataset)
            if path.stat().st_size > 1_000_000:
                raise ValueError('Dataset exceeds 1 MB budget')
            case = json.loads(path.read_text(encoding='utf-8'))
            planner = CommandPlanner(json.loads(args.model_command)) if args.model_command else None
            result = run(store, args.goal, case, planner)
            output(result)
            return 1 if result['errors'] else 0
        elif args.command == 'dream':
            output(dream(store))
        elif args.command in ('approve', 'reject'):
            output(review(store, args.id, args.actor, args.reason, args.command == 'approve'))
        elif args.command == 'rollback':
            output(rollback(store, args.id, args.actor, args.reason))
        elif args.command == 'proposals':
            output(store.proposals())
        elif args.command == 'runs':
            output(store.runs())
        elif args.command == 'audit':
            output([dict(r) for r in store.db.execute('SELECT * FROM audit ORDER BY id')])
        elif args.command == 'verify-audit':
            valid = store.verify()
            output({'valid': valid})
            return 0 if valid else 1
        elif args.command == 'schedule':
            if not 0 < args.interval_seconds <= 31536000:
                raise ValueError('Interval must be between 0 and 31536000 seconds')
            while True:
                output(dream(store, interval=args.interval_seconds))
                if args.once:
                    break
                time.sleep(min(args.interval_seconds, 30))
        else:
            version, procedure = store.active()
            output({'active_version': version, 'procedure': procedure, 'audit_valid': store.verify()})
        return 0
    except (ValueError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    finally:
        store.close()

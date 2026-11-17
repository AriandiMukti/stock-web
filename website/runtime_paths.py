"""Filesystem configuration shared by Flask, research modules and local tools."""
import os
import json
import re
from datetime import date
from pathlib import Path

WEBSITE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = WEBSITE_DIR.parent


def external_root(variable, default):
    root = Path(os.environ.get(variable) or default).expanduser().resolve()
    if root == PROJECT_DIR or root.is_relative_to(PROJECT_DIR):
        raise ValueError(variable + ' must point outside the source-code directory')
    return root


RUNTIME_DIR = external_root('FLASK_RUNTIME_DIR', PROJECT_DIR.parent / 'var')
MARKET_DIR = external_root('BDM_BASE_PATH', RUNTIME_DIR / 'market-data')


def storage_path(relative):
    """Map a website-relative artifact to private runtime storage, without I/O."""
    relative = str(relative).replace('\\', '/')
    parts = Path(relative).parts
    if relative.startswith('/') or Path(relative).anchor or '..' in parts or ':' in relative:
        raise ValueError('Artifact paths must be relative and contained')
    name = Path(relative).name.lower()
    suffix = Path(relative).suffix.lower()
    if suffix in {'.session', '.key', '.pem', '.keystore', '.pass'} or 'session' in name or name in {'.env', 'kode.txt'}:
        category = 'secrets'
    elif suffix in {'.db', '.sqlite', '.sqlite3'}:
        category = 'databases'
    elif suffix in {'.pt', '.pth', '.keras', '.h5', '.onnx'}:
        category = 'models'
    elif any('cache' in part.lower() for part in parts) or name == 'broker_ledger.pkl':
        category = 'cache'
    elif suffix == '.log' or 'logs' in parts:
        category = 'logs'
    else:
        category = 'data'
    return Path(category) / relative


def runtime_file(module_directory='', *parts):
    relative = Path(module_directory)
    for part in parts:
        relative = relative / str(part).replace('\\', '/')
    return RUNTIME_DIR / storage_path(relative)


def market_file(*parts):
    path = MARKET_DIR
    for part in parts:
        path = path / str(part).replace('\\', '/')
    resolved = path.resolve()
    if not resolved.is_relative_to(MARKET_DIR):
        raise ValueError('Market input path is outside BDM_BASE_PATH')
    return str(resolved)


def prepare_runtime():
    """Create configured storage directories only when starting an application."""
    for name in ['cache', 'data', 'databases', 'models', 'secrets', 'logs']:
        (RUNTIME_DIR / name).mkdir(parents=True, exist_ok=True)
    for name in ['research_cache', 'twin/cache', 'stocklang/.cache']:
        runtime_file('', name).mkdir(parents=True, exist_ok=True)


def research_groups(required=False):
    """Private Telegram archive metadata is configured outside published source."""
    path = external_root('TELEGRAM_RESEARCH_CONFIG', RUNTIME_DIR/'data/riset_sentimen_obrolan/groups.json')
    if not path.is_file():
        if required:
            raise ValueError('Configure TELEGRAM_RESEARCH_CONFIG with authorized research groups first')
        return []
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list):
        raise ValueError('Research group configuration must be a list')
    aliases = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str) or not row['name'].strip() or len(row['name'])>256:
            raise ValueError('Invalid research group configuration')
        if not isinstance(row.get('archive'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', row['archive']) or row['archive'] in aliases:
            raise ValueError('Archive aliases must be unique safe filenames')
        aliases.add(row['archive'])
        try:
            start, split = date.fromisoformat(row['start']), date.fromisoformat(row['split'])
        except (ValueError, TypeError, KeyError):
            raise ValueError('Research dates must use ISO calendar dates') from None
        if start > split:
            raise ValueError('Research split cannot precede the collection start')
    return rows

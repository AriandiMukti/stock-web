"""Read-only APK inspection; writes evidence locally, never contacts a service."""
try:
    from ...runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = _runtime_file('', 'reports', 'apk-local-audit-26645675')


def dex_inventory(data):
    def u32(offset):
        return struct.unpack_from('<I', data, offset)[0]

    strings = []
    for i in range(u32(56)):
        offset = u32(u32(60) + 4 * i)
        while data[offset] & 128:
            offset += 1
        offset += 1
        end = data.index(b'\0', offset)
        strings.append(data[offset:end].decode('utf-8', errors='replace'))
    types = [strings[u32(u32(68) + 4 * i)] for i in range(u32(64))]
    classes = [types[u32(u32(100) + 32 * i)] for i in range(u32(96))]
    methods = []
    for i in range(u32(88)):
        cls, proto, name = struct.unpack_from('<HHI', data, u32(92) + 8 * i)
        methods.append(types[cls] + '->' + strings[name])
    categories = {
        'shell_execution': r'Ljava/lang/(Runtime;->exec|ProcessBuilder;)',
        'dynamic_dex_loading': r'Ldalvik/system/.*(DexClassLoader|InMemoryDexClassLoader|DexFile)',
        'native_library_loading': r'Ljava/lang/(System|Runtime);->load',
        'sms_contacts_location_microphone': r'Landroid/(telephony/Sms|location/|media/MediaRecorder|provider/Contacts)',
        'accessibility': r'Landroid/accessibilityservice/',
    }
    return {
        'defined_classes': classes,
        'method_references': sorted(set(methods)),
        'url_literals': sorted(s for s in strings if re.match(r'https?://', s)),
        'selected_risky_api_references': {
            k: sorted(m for m in methods if re.search(v, m)) for k, v in categories.items()
        },
        'limitation': 'Reference inventory is not a complete malware detector or runtime analysis.',
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = {
        'old': Path(str(_RUNTIME_DIR / "artifacts" / 'BDM-Saku.apk')),
        'first_flagged': _runtime_file('', 'hp/BDM-Saku-play-protect-26645635.apk'),
        'native_hardened': _runtime_file('', 'hp/BDM-Saku-play-protect-26645648.apk'),
        'current': _runtime_file('', 'hp/BDM-Saku.apk'),
    }
    report = {}
    for label, path in paths.items():
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            dex = z.read('classes.dex')
            entries = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
            report[label] = {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'entries_sha256': entries,
                'dex': dex_inventory(dex),
            }
            # Exact, fixed entry name: no bulk ZIP extraction.
            (_runtime_file('reports/apk-local-audit-26645675', label + '-app.js')).write_bytes(z.read('assets/app.js'))
            if label == 'current':
                (_runtime_file('reports/apk-local-audit-26645675', 'current.dex')).write_bytes(dex)
                report[label]['assets_match_source'] = all(
                    z.read(n) == (_runtime_file('', 'hp/android', n)).read_bytes()
                    for n in z.namelist() if n.startswith('assets/')
                )
    (_runtime_file('reports/apk-local-audit-26645675', 'apk-inventory.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    for label, row in report.items():
        print(label, row['sha256'])
        print(' classes:', ', '.join(row['dex']['defined_classes']))
        print(' selected risky APIs:', row['dex']['selected_risky_api_references'])
    print('Current assets match source:', report['current']['assets_match_source'])
    print('Evidence:', OUT)


if __name__ == '__main__':
    main()

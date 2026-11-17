"""
Pratinjau UI BDM Saku di browser laptop, tanpa build APK: melayani folder
assets/ dan data.json (= hp/data/bdm_hp.json.gz yang dibuka), persis seperti
yang dilakukan MainActivity di HP.

    python pratinjau.py [port]
"""
try:
    from ...runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import gzip
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

SINI = os.path.dirname(os.path.abspath(__file__))
DATA = str(_runtime_file('hp', 'data', 'bdm_hp.json.gz'))


class Penjawab(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(_runtime_file('hp/android', 'assets')), **kw)

    def do_GET(self):
        if self.path.split('?')[0] == '/data.json':
            if not os.path.exists(DATA):
                self.send_error(404)
                return
            b = gzip.open(DATA).read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5072
    ThreadingHTTPServer(('127.0.0.1', port), Penjawab).serve_forever()

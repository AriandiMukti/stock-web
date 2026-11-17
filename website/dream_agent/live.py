"""Bounded Yahoo Finance collection and deterministic evidence-based research."""
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def symbol(value):
    value = value.upper().strip().removesuffix('.JK')
    if not re.fullmatch('[A-Z]{4}', value):
        raise ValueError('Gunakan kode emiten BEI empat huruf, misalnya ADRO.')
    return value + '.JK'


def collect(ticker):
    result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), symbol(ticker)],
                            capture_output=True, text=True, timeout=90, check=True)
    payload = json.loads(result.stdout)
    if payload.get('error'):
        raise ValueError(payload['error'])
    return payload


def download(ticker):
    import yfinance as yf
    stock = yf.Ticker(ticker)
    history = stock.history(period='3mo', auto_adjust=False, timeout=20)
    if history.empty:
        raise ValueError('Harga tidak tersedia dari Yahoo Finance; coba lagi nanti.')
    frame = stock.income_stmt
    statements = []
    if frame is not None and not frame.empty:
        for column in sorted(frame.columns, reverse=True)[:2]:
            def number(key):
                if key not in frame.index:
                    return None
                n = float(frame.loc[key, column])
                return n if math.isfinite(n) else None
            statements.append({'period': column.date().isoformat(), 'revenue': number('Total Revenue'),
                               'net_income': number('Net Income')})
    closes = history['Close'].dropna()
    if closes.empty:
        raise ValueError('Harga penutupan kosong.')
    first, last = float(closes.iloc[0]), float(closes.iloc[-1])
    return {'ticker': ticker, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'price_date': closes.index[-1].date().isoformat(), 'close': last,
            'window_start': closes.index[0].date().isoformat(),
            'price_change_pct': round((last / first - 1) * 100, 2) if first else None,
            'statements': statements, 'currency': 'Tidak diverifikasi; angka laporan mengikuti satuan penyedia',
            'sources': [{'title': 'Yahoo Finance: harga', 'url': f'https://finance.yahoo.com/quote/{ticker}/history/'},
                        {'title': 'Yahoo Finance: laporan tahunan', 'url': f'https://finance.yahoo.com/quote/{ticker}/financials/'},
                        {'title': 'BEI: verifikasi dokumen resmi (belum diunduh agent)',
                         'url': 'https://www.idx.co.id/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan/'}]}


def analyze(payload, previous=None):
    findings = [f"Harga penutupan {payload['close']:,.2f} pada {payload['price_date']} (Yahoo Finance).",
                f"Perubahan harga sejak {payload['window_start']}: {payload['price_change_pct']}%; tanpa penyesuaian dividen/aksi korporasi."]
    risks = ['Data pihak ketiga perlu dicocokkan dengan dokumen resmi; keterbandingan cakupan bisnis dan mata uang belum diverifikasi.',
             'Perubahan harga historis tidak menentukan arah harga berikutnya.']
    statements = payload['statements']
    if statements:
        latest = statements[0]
        findings.append(f"Periode tahunan terbaru yang tersedia: {latest['period']}; pendapatan {latest['revenue']}, laba bersih {latest['net_income']} (satuan penyedia).")
        if latest['net_income'] is not None and latest['net_income'] < 0:
            risks.append('Laba bersih pada periode terbaru bernilai negatif.')
        if (datetime.now(timezone.utc).date() - datetime.fromisoformat(latest['period']).date()).days > 550:
            risks.append('Periode laporan yang tersedia sudah lebih dari 550 hari; belum memadai untuk kesimpulan terkini.')
        if len(statements) > 1:
            findings.append(f"Pembanding {statements[1]['period']}: pendapatan {statements[1]['revenue']}, laba bersih {statements[1]['net_income']}. Pertumbuhan ditahan sampai keterbandingan diverifikasi.")
    else:
        risks.append('Laporan keuangan tidak tersedia dari penyedia. Analisis fundamental belum dapat diselesaikan.')
    changes = []
    if previous:
        for key in ('close', 'price_date', 'statements'):
            if previous.get(key) != payload.get(key):
                changes.append(key)
    return {'findings': findings, 'risks': risks, 'changed_fields': changes,
            'conclusion': 'Bukti ini cukup untuk pemantauan awal. Kesimpulan prospek dan valuasi memerlukan verifikasi laporan resmi, cakupan bisnis, utang dan arus kas; belum ada rekomendasi transaksi.',
            'evidence': payload}


if __name__ == '__main__':
    try:
        print(json.dumps(download(symbol(sys.argv[1])), allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error': str(exc)[:500]}))

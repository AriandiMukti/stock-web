"""Peringkat konsistensi net broker, membaca hanya lima arsip harian saham."""
import math
import os
import re
from datetime import date

from .broker_ledger import ALL_DIR, ringkasan_broker, _angka


def rank_days(days, daily):
    """daily: tanggal -> {broker: net lot}; None berarti sumber tidak tersedia."""
    brokers = sorted({b for rows in daily.values() if rows is not None for b in rows})
    result = {'buy': [], 'sell': []}
    for broker in brokers:
        values = [daily[d].get(broker) if daily.get(d) is not None else None for d in days]
        total = sum(v for v in values if v is not None)
        for side, sign in (('buy', 1), ('sell', -1)):
            count = sum(v is not None and v * sign > 0 for v in values)
            if not count:
                continue
            streak = 0
            for value in reversed(values):
                if value is None or value * sign <= 0:
                    break
                streak += 1
            result[side].append(dict(broker=broker, values=values, days=count,
                                     streak=streak, net_lot=total))
    for side, sign in (('buy', 1), ('sell', -1)):
        result[side].sort(key=lambda r: (-r['days'], -r['streak'], -sign * r['net_lot'], r['broker']))
        result[side] = result[side][:5]
    return result


def session_dates(directory):
    folders = []
    if os.path.isdir(directory):
        for item in os.scandir(directory):
            if not item.is_dir() or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', item.name):
                continue
            try:
                day = date.fromisoformat(item.name)
            except ValueError:
                continue
            if day <= date.today() and day.weekday() < 5:
                folders.append(item.name)
    return sorted(folders)


def read_days(stock, days, directory):
    daily, missing = {}, []
    for day in days:
        folder = os.path.join(directory, day)
        # Sama dengan ledger: dahulukan JSON ALL; jangan campur data FOREIGN.
        paths = [os.path.join(folder, '%s_ALL_%s.json' % (stock, day)),
                 os.path.join(folder, '%s_ALL_%s.json' % (stock, day.replace('-', ''))),
                 os.path.join(folder, stock + '.xls')]
        path = next((p for p in paths if os.path.isfile(p)), None)
        summary = ringkasan_broker(path) if path else None
        if not summary or not (summary.get('brokers_buy') or summary.get('brokers_sell')):
            daily[day] = None
            missing.append(day)
            continue
        source_dates = {str(r.get('netbs_date')).replace('-', '')
                        for field in ('brokers_buy', 'brokers_sell')
                        for r in summary.get(field) or [] if r.get('netbs_date')}
        if source_dates and source_dates != {day.replace('-', '')}:
            daily[day] = None
            missing.append(day)
            continue
        rows = {}
        for field, lot_key, sign in (('brokers_buy', 'blot', 1), ('brokers_sell', 'slot', -1)):
            for row in summary.get(field) or []:
                code = str(row.get('netbs_broker_code') or '').strip().upper()
                lot = abs(_angka(row.get(lot_key) or 0))
                if code and math.isfinite(lot):
                    rows[code] = rows.get(code, 0) + sign * lot
        daily[day] = rows or None
        if not rows:
            missing.append(day)
    return daily, missing


def build(stock, directory=None):
    stock = stock.strip().upper()
    if not re.fullmatch(r'[A-Z]{4}', stock):
        raise ValueError('Masukkan kode saham 4 huruf, misalnya ADRO.')
    directory = directory or ALL_DIR
    days = session_dates(directory)[-5:]
    daily, missing = read_days(stock, days, directory)
    return dict(stock=stock, dates=days, missing=missing, available_days=len(days) - len(missing),
                **rank_days(days, daily))

(() => {
    'use strict';
    const el = id => document.getElementById(id);
    const number = value => new Intl.NumberFormat('id-ID', {maximumFractionDigits: 2}).format(value);
    let latest = null;
    let timer;
    function render(payload) {
        latest = payload;
        el('emaRefresh').disabled = payload.running;
        el('emaError').hidden = !payload.error;
        el('emaError').textContent = payload.error || '';
        const report = payload.report;
        el('emaRows').replaceChildren();
        if (!report) {
            el('emaStatus').textContent = payload.running
                ? `Mengunduh data Yahoo Finance: ${payload.processed} / ${payload.total || '…'} saham. Halaman dapat tetap dibuka selama pemindaian.`
                : 'Hasil belum tersedia. Tekan Perbarui dari Yahoo untuk mencoba lagi.';
            return;
        }
        const weeks = Number(el('emaWeeks').value);
        const query = el('emaSearch').value.trim().toUpperCase();
        // Even an old saved report must never display signals older than two
        // weeks relative to the latest closed week returned by the server.
        const rows = report.rows.filter(row => row.weeks_ago < weeks && row.ticker.includes(query));
        el('emaStatus').textContent = payload.running
            ? `Memperbarui: ${payload.processed} / ${payload.total || '…'} saham. Menampilkan hasil tersimpan (${rows.length} saham).`
            : `${rows.length} saham ditemukan · ${report.counts.ok} dari ${report.total} saham berhasil dianalisis.`;
        el('emaMeta').textContent = `Minggu terakhir: ${report.week_ending} · Diperbarui: ${new Date(report.updated_at).toLocaleString('id-ID', {timeZone: 'Asia/Jakarta'})} WIB${payload.stale ? ' · Hasil tersimpan belum diperbarui.' : ''}`;
        rows.forEach(row => {
            const tr = document.createElement('tr');
            const ticker = document.createElement('td');
            const link = document.createElement('a');
            link.href = `/saham/${encodeURIComponent(row.ticker)}`;
            link.textContent = row.ticker;
            ticker.append(link);
            tr.append(ticker);
            [row.signal_week, number(row.close), number(row.ema10), number(row.ema20),
                row.still_above ? 'EMA10 > EMA20' : 'EMA10 ≤ EMA20'].forEach(value => {
                const td = document.createElement('td');
                td.textContent = value;
                tr.append(td);
            });
            el('emaRows').append(tr);
        });
        if (!rows.length) {
            const td = document.createElement('td');
            td.colSpan = 6;
            td.style.textAlign = 'center';
            td.textContent = query ? 'Tidak ada saham yang cocok dengan pencarian.' : 'Tidak ada golden cross pada periode yang dipilih.';
            const tr = document.createElement('tr');
            tr.append(td);
            el('emaRows').append(tr);
        }
        const reasons = {unavailable: 'data Yahoo tidak tersedia', short_history: 'riwayat kurang dari 21 minggu', stale: 'data belum mencapai minggu terakhir'};
        el('emaSkipped').hidden = !report.skipped.length;
        el('emaSkippedText').textContent = report.skipped.map(row => `${row.ticker}: ${reasons[row.reason] || row.reason}`).join(' · ');
    }
    async function load(refresh = false) {
        clearTimeout(timer);
        el('emaRefresh').disabled = true;
        try {
            const response = await fetch(refresh ? '/ema-weekly/refresh' : '/ema-weekly/data', {
                method: refresh ? 'POST' : 'GET',
                headers: refresh ? {'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content} : {},
            });
            if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
                throw new Error('Data tidak dapat dimuat. Pastikan sesi login masih aktif, lalu coba lagi.');
            }
            const payload = await response.json();
            render(payload);
            if (payload.running) timer = setTimeout(load, 2500);
        } catch (error) {
            el('emaError').hidden = false;
            el('emaError').textContent = error.message;
            el('emaStatus').textContent = 'Pemindaian belum dapat diperiksa. Tekan Perbarui dari Yahoo untuk mencoba lagi.';
            el('emaRefresh').disabled = false;
        }
    }
    el('emaRefresh').addEventListener('click', () => load(true));
    ['emaWeeks', 'emaSearch'].forEach(id => el(id).addEventListener('input', () => { if (latest) render(latest); }));
    load();
})();

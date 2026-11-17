/* Tampilan arsip emiten, digunakan oleh web dan HP. */
function historiEsc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
        return {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c];
    });
}

function historiNum(value, digits) {
    return value == null ? '—' : Number(value).toLocaleString('id-ID', {maximumFractionDigits: digits});
}

function historiDelta(value, digits, unit) {
    if (value == null) return '—';
    var color = value > 0 ? 'var(--accum, var(--up))' : value < 0 ? 'var(--distrib, var(--down))' : 'inherit';
    return '<span style="color:' + color + '">' + (value > 0 ? '+' : '') + historiNum(value, digits) + unit + '</span>';
}

function historiTable(headers, rows) {
    if (!rows.length) return '<p>Tidak ada baris yang cocok.</p>';
    return '<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;text-align:left">' +
        '<thead><tr>' + headers.map(function (x) { return '<th style="padding:8px">' + historiEsc(x) + '</th>'; }).join('') +
        '</tr></thead><tbody>' + rows.map(function (row) {
            return '<tr>' + row.map(function (x) {
                return '<td style="padding:8px;border-top:1px solid var(--line);white-space:nowrap">' + x + '</td>';
            }).join('') + '</tr>';
        }).join('') + '</tbody></table></div>';
}

function historiRender(root, kind, data) {
    var esc = historiEsc;
    if (!data || !data.available) {
        root.innerHTML = '<p>' + esc(data && data.message || 'Data belum tersedia. Perbarui data dari laptop.') + '</p>';
        return;
    }
    if (kind === 'musiman_saham') {
        var stocks = Object.keys(data.saham).sort();
        var months = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
        root.innerHTML = '<p>Arsip hingga ' + esc(data.as_of) + ' · ' + stocks.length + ' saham</p>' +
            '<label>Kode saham <select class="form-control" aria-label="Kode saham">' + stocks.map(function (ticker) {
                return '<option>' + esc(ticker) + '</option>';
            }).join('') + '</select></label><div data-histori-tabel></div><p>' + esc(data.message) + '</p>';
        var select = root.querySelector('select');
        if (data.saham.BBCA) select.value = 'BBCA';
        function showStock() {
            var rows = (data.saham[select.value] || []).map(function (r) {
                return [months[r.bulan - 1], historiDelta(r.median, 2, '%'), historiDelta(r.rata, 2, '%'),
                        historiNum(100 * r.naik / r.sampel, 0) + '%', esc(r.sampel)];
            });
            root.querySelector('[data-histori-tabel]').innerHTML =
                historiTable(['Bulan','Median','Rata-rata','Porsi naik','Sampel'], rows);
        }
        select.addEventListener('change', showStock);
        showStock();
        return;
    }
    root.innerHTML = '<label>Sumber <select class="form-control"><option value="ksei">KSEI · asing dan individu lokal</option>' +
        '<option value="registri">IDX · pemegang saham bernama</option></select></label> ' +
        '<label>Cari <input class="form-control" type="search" placeholder="Kode saham atau nama pemegang"></label>' +
        '<div data-histori-tabel></div><p>' + esc(data.message) + '</p>';
    var source = root.querySelector('select');
    var search = root.querySelector('input');
    if (!data.ksei.length) source.value = 'registri';
    function showChanges() {
        var query = search.value.trim().toLowerCase();
        var filtered = data[source.value].filter(function (row) {
            return (row.ticker + ' ' + (row.nama || '') + ' ' + (row.kategori || '') +
                    (row.pengendali ? ' pengendali' : '')).toLowerCase().includes(query);
        });
        var rows = filtered.slice(0, 100);
        var subtitle = '<p>' + rows.length + ' dari ' + filtered.length + ' hasil. Gunakan pencarian untuk mempersempit hasil.</p>';
        var table;
        if (source.value === 'ksei') {
            subtitle += '<p>Periode KSEI ' + esc(data.periode_ksei.join(' → ')) + '</p>';
            table = historiTable(['Saham','Asing awal → akhir','Δ asing (pp)','Δ asing (lembar)','Individu lokal awal → akhir','Δ individu (pp)'],
                rows.map(function (r) {
                    return [esc(r.ticker) + (r.modal_berubah ? ' · modal tercatat berubah' : ''),
                        historiNum(r.asing_awal,2) + '% → ' + historiNum(r.asing,2) + '%',
                        historiDelta(r.asing_delta,2,''), historiDelta(r.asing_lembar_delta,0,''),
                        historiNum(r.individu_awal,2) + '% → ' + historiNum(r.individu,2) + '%',
                        historiDelta(r.individu_delta,2,'')];
                }));
        } else {
            subtitle += '<p>' + esc(data.n_registri) + ' emiten memiliki dua snapshot pembanding.</p>';
            table = historiTable(['Saham','Pemegang saham','Kategori','Snapshot','Lembar sebelum','Lembar sesudah','Δ lembar','Porsi sebelum → sesudah'],
                rows.map(function (r) {
                    return [esc(r.ticker), esc(r.nama), esc(r.kategori) + (r.pengendali ? ' · Pengendali' : ''),
                        esc(r.awal + ' → ' + r.akhir),
                        r.sebelum ? historiNum(r.sebelum.lembar,0) : 'Belum terlihat',
                        r.sesudah ? historiNum(r.sesudah.lembar,0) : 'Tidak terlihat',
                        historiDelta(r.delta,0,''),
                        (r.sebelum && r.sebelum.persen != null ? historiNum(r.sebelum.persen,3) + '%' : '—') + ' → ' +
                        (r.sesudah && r.sesudah.persen != null ? historiNum(r.sesudah.persen,3) + '%' : '—')];
                }));
        }
        root.querySelector('[data-histori-tabel]').innerHTML = subtitle + table;
    }
    search.addEventListener('input', showChanges);
    source.addEventListener('change', showChanges);
    showChanges();
}

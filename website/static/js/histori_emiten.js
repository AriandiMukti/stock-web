/* Tampilan arsip emiten, digunakan oleh web dan HP. */
function historiEsc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
        return {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c];
    });
}

function historiStockLink(ticker) {
    return '<a href="/search?searched=' + historiEsc(encodeURIComponent(ticker)) + '">' +
        historiEsc(ticker) + '</a>';
}

function historiNum(value, digits) {
    return value == null ? '—' : Number(value).toLocaleString('id-ID', {maximumFractionDigits: digits});
}

function historiDelta(value, digits, unit) {
    if (value == null) return '—';
    var color = value > 0 ? 'var(--accum, var(--up))' : value < 0 ? 'var(--distrib, var(--down))' : 'inherit';
    return '<span style="color:' + color + '">' + (value > 0 ? '+' : '') + historiNum(value, digits) + unit + '</span>';
}

function historiTable(headers, rows, sort) {
    if (!rows.length) return '<p>Tidak ada baris yang cocok.</p>';
    return '<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;text-align:left">' +
        '<thead><tr>' + headers.map(function (x, index) {
            var key = sort && sort.columns[index];
            if (!key) return '<th style="padding:8px">' + historiEsc(x) + '</th>';
            var active = sort.key === key;
            var direction = active ? (sort.desc ? 'descending' : 'ascending') : 'none';
            var arrow = active ? (sort.desc ? ' \u25bc' : ' \u25b2') : ' \u2195';
            return '<th style="padding:8px" aria-sort="' + direction + '">' +
                '<button type="button" data-histori-sort="' + key + '" ' +
                'style="background:none;border:0;padding:0;color:inherit;font:inherit;font-weight:inherit;cursor:pointer;white-space:nowrap" ' +
                'title="Klik untuk mengurutkan ' + historiEsc(x) + '">' + historiEsc(x) +
                '<span aria-hidden="true">' + arrow + '</span></button></th>';
        }).join('') +
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
    var sort = {
        columns: {2: 'asing_delta', 3: 'asing_lembar_delta', 5: 'individu_delta', 6: 'value_rata5'},
        key: 'individu_delta',
        desc: false
    };
    var tableRoot = root.querySelector('[data-histori-tabel]');
    tableRoot.addEventListener('click', function (event) {
        var button = event.target.closest('[data-histori-sort]');
        if (!button) return;
        var key = button.getAttribute('data-histori-sort');
        sort.desc = sort.key === key ? !sort.desc : true;
        sort.key = key;
        showChanges();
        tableRoot.querySelector('[data-histori-sort="' + key + '"]').focus();
    });
    function showChanges() {
        var query = search.value.trim().toLowerCase();
        var filtered = data[source.value].filter(function (row) {
            return (row.ticker + ' ' + (row.nama || '') + ' ' + (row.kategori || '') +
                    (row.pengendali ? ' pengendali' : '')).toLowerCase().includes(query);
        });
        if (source.value === 'ksei' && sort.key) {
            filtered.sort(function (a, b) {
                var av = a[sort.key];
                var bv = b[sort.key];
                // Missing values stay last in either direction; compare raw numbers.
                var aMissing = av == null || !Number.isFinite(Number(av));
                var bMissing = bv == null || !Number.isFinite(Number(bv));
                if (aMissing || bMissing) return Number(aMissing) - Number(bMissing);
                return (Number(av) - Number(bv)) * (sort.desc ? -1 : 1);
            });
        }
        var rows = filtered.slice(0, 100);
        var subtitle = '<p>' + rows.length + ' dari ' + filtered.length + ' hasil. Gunakan pencarian untuk mempersempit hasil.</p>';
        var table;
        if (source.value === 'ksei') {
            subtitle += '<p>Periode KSEI ' + esc(data.periode_ksei.join(' → ')) + '</p>';
            table = historiTable(['Saham','Asing awal → akhir','Δ asing (pp)','Δ asing (lembar)','Individu lokal awal → akhir','Δ individu (pp)','Value rata-rata 5 hari (Rp miliar)'],
                rows.map(function (r) {
                    return [historiStockLink(r.ticker) + (r.modal_berubah ? ' · modal tercatat berubah' : ''),
                        historiNum(r.asing_awal,2) + '% → ' + historiNum(r.asing,2) + '%',
                        historiDelta(r.asing_delta,2,''), historiDelta(r.asing_lembar_delta,0,''),
                        historiNum(r.individu_awal,2) + '% → ' + historiNum(r.individu,2) + '%',
                        historiDelta(r.individu_delta,2,''), historiNum(r.value_rata5,2)];
                }), sort);
        } else {
            subtitle += '<p>' + esc(data.n_registri) + ' emiten memiliki dua snapshot pembanding.</p>';
            table = historiTable(['Saham','Pemegang saham','Kategori','Snapshot','Lembar sebelum','Lembar sesudah','Δ lembar','Porsi sebelum → sesudah','Value rata-rata 5 hari (Rp miliar)'],
                rows.map(function (r) {
                    return [historiStockLink(r.ticker), esc(r.nama), esc(r.kategori) + (r.pengendali ? ' · Pengendali' : ''),
                        esc(r.awal + ' → ' + r.akhir),
                        r.sebelum ? historiNum(r.sebelum.lembar,0) : 'Belum terlihat',
                        r.sesudah ? historiNum(r.sesudah.lembar,0) : 'Tidak terlihat',
                        historiDelta(r.delta,0,''),
                        (r.sebelum && r.sebelum.persen != null ? historiNum(r.sebelum.persen,3) + '%' : '—') + ' → ' +
                        (r.sesudah && r.sesudah.persen != null ? historiNum(r.sesudah.persen,3) + '%' : '—'), historiNum(r.value_rata5,2)];
                }));
        }
        root.querySelector('[data-histori-tabel]').innerHTML = subtitle + table;
    }
    search.addEventListener('input', showChanges);
    source.addEventListener('change', showChanges);
    showChanges();
}

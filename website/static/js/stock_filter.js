/*
 * Bar filter bersama -- satu komponen, dipakai ulang di semua halaman daftar.
 *
 * PRINSIP YANG TIDAK BOLEH DILANGGAR (lihat stock_filter.py untuk alasannya):
 *
 *  1. MEMBUANG, BUKAN MEMILIH. Filter di sini tidak berpura-pura memilih
 *     pemenang -- tidak ada aturan beli di app ini yang bertahan di luar
 *     sampel. Ia hanya membuang yang tidak layak dinilai.
 *
 *  2. TIDAK ADA YANG DISEMBUNYIKAN DIAM-DIAM. Setiap emiten yang tersaring
 *     tetap bisa ditampilkan lengkap dengan alasannya. Tombol "tampilkan yang
 *     tersaring" selalu tersedia, dan jumlahnya selalu terlihat.
 *
 *  3. SISI B DITANDAI, BUKAN DIBUANG. Bawaannya cuma ditandai. Membuang harus
 *     dipilih sendiri -- selisihnya kecil dan sempat berbalik di 2020-2022,
 *     jadi memperlakukannya sebagai aturan keras berarti mengulang kesalahan
 *     yang sudah berkali-kali dikoreksi di modul lain.
 *
 * PEMAKAIAN
 *     StockFilter.init({
 *         mount:    '#idKontainer',
 *         tickers:  ['BBCA', 'ADRO', ...],
 *         onChange: function (hasil) { ... }      // {lolos, tersaring, alasan}
 *     });
 *
 * `hasil.lolos`     -> array kode yang lolos, urutan asli dipertahankan
 * `hasil.tersaring` -> array kode yang dibuang
 * `hasil.alasan`    -> {kode: 'kalimat alasan'} untuk yang dibuang
 * `hasil.fakta`     -> {kode: fakta} supaya pemanggil bisa menandai barisnya
 */
var StockFilter = (function () {
    'use strict';

    var KUNCI_SIMPAN = 'bdm_filter_preset_v1';
    var BAWAAN = {
        buangBasi: true,
        buangSepi: true,
        buangSisiB: false,          // ditandai saja, sesuai prinsip 3
        lapis: { 'Lapis 1': true, 'Lapis 2': true, 'Lapis 3': true, 'terlalu sepi': true },
        tampilkanTersaring: false
    };

    var data = null;        // payload dari /filter-facts
    var state = null;
    var cfg = null;

    function bacaSimpanan() {
        try {
            var raw = localStorage.getItem(KUNCI_SIMPAN);
            if (!raw) { return null; }
            var p = JSON.parse(raw);
            // gabungkan supaya kunci baru tetap punya nilai bawaan
            return $.extend(true, {}, BAWAAN, p);
        } catch (e) { return null; }
    }

    function simpan() {
        try { localStorage.setItem(KUNCI_SIMPAN, JSON.stringify(state)); } catch (e) { /* abaikan */ }
    }

    function esc(t) { return $('<div>').text(t === null || t === undefined ? '' : t).html(); }

    function alasanUntuk(kode, f) {
        if (!f) { return null; }
        // Alasan ditulis seperti orang bicara, dan SELALU memuat angkanya --
        // pembaca harus bisa menilai sendiri apakah penyaringannya masuk akal
        // untuk emiten itu, bukan cuma diberi tahu bahwa ia disaring.
        if (state.buangBasi && f.basi > data.ambang.basi) {
            return 'Data terakhirnya ' + f.basi + ' hari lalu, jadi semua hitungan di app ini sudah basi.';
        }
        if (state.buangSepi && f.lapis === 'terlalu sepi') {
            return 'Cuma Rp' + f.nilai_label + ' sehari — terlalu sepi, order Anda sendiri yang akan menggerakkan harga.';
        }
        if (!state.lapis[f.lapis]) {
            return f.lapis + ' sedang tidak ditampilkan.';
        }
        if (state.buangSisiB && f.sisi === 'B') {
            return 'Harganya sudah naik ' + (f.harga20 || 0).toFixed(1)
                 + '% dalam 20 hari. Kalau masuk sekarang, Anda masuk setelah harganya lari.';
        }
        return null;
    }

    function hitung() {
        var lolos = [], tersaring = [], alasan = {};
        (cfg.tickers || []).forEach(function (kode) {
            var f = data && data.facts ? data.facts[kode] : null;
            var a = alasanUntuk(kode, f);
            if (a) { tersaring.push(kode); alasan[kode] = a; }
            else { lolos.push(kode); }
        });
        return { lolos: lolos, tersaring: tersaring, alasan: alasan,
                 fakta: (data && data.facts) || {} };
    }

    function chipSisi(kode) {
        var f = data && data.facts ? data.facts[kode] : null;
        if (!f) { return ''; }
        if (f.sisi === 'A') {
            return '<span class="sf-chip sf-chip-a" title="Harga 20 hari terakhir '
                 + (f.harga20 || 0).toFixed(1) + '%. Saham yang sedang turun lebih sering berbalik naik, '
                 + 'tapi untungnya kecil — jangan dijadikan alasan beli sendirian.">lagi turun</span>';
        }
        if (f.sisi === 'B') {
            return '<span class="sf-chip sf-chip-b" title="Harga sudah naik '
                 + (f.harga20 || 0).toFixed(1) + '% dalam 20 hari dan pembeli besar masih memborong. '
                 + 'Kalau masuk sekarang, Anda masuk setelah harganya lari.">sudah naik banyak</span>';
        }
        return '';
    }

    function render() {
        var h = hitung();
        var lc = data.lapis_counts || {};

        var ARTI_LAPIS = {
            'Lapis 1': 'Ramai: transaksinya Rp100 miliar sehari ke atas.',
            'Lapis 2': 'Sedang: transaksinya Rp10 sampai 100 miliar sehari.',
            'Lapis 3': 'Kecil: transaksinya Rp200 juta sampai 10 miliar sehari.'
        };
        var kotakLapis = ['Lapis 1', 'Lapis 2', 'Lapis 3'].map(function (L) {
            return '<label class="sf-check" title="' + ARTI_LAPIS[L] + '">'
                 + '<input type="checkbox" data-lapis="' + L + '"'
                 + (state.lapis[L] ? ' checked' : '') + '> ' + L
                 + ' <span class="sf-dim">' + (lc[L] || 0) + '</span></label>';
        }).join('');

        // Teks yang terlihat pakai bahasa sehari-hari dan pendek; penjelasan
        // panjangnya pindah ke tooltip tiap kotak. Istilah bikinan seperti
        // "sisi A/B" sengaja tidak dipakai di layar -- hanya orang yang sudah
        // membaca halaman Audit Screener yang paham artinya.
        function kotak(id, aktif, teks, jumlah, judul) {
            return '<label class="sf-check" title="' + judul + '">'
                 + '<input type="checkbox" id="' + id + '"' + (aktif ? ' checked' : '') + '> '
                 + teks + ' <span class="sf-dim">' + jumlah + '</span></label>';
        }

        $(cfg.mount).html(
            '<div class="sf-bar">'
          + '  <div class="sf-row">'
          + '    <span class="sf-label">Buang</span>'
          + kotak('sfBasi', state.buangBasi, 'datanya tidak update', data.n_basi,
                  'Datanya berhenti lebih dari ' + data.ambang.basi + ' hari lalu. Semua hitungan 20 dan 60 '
                + 'hari di app ini jadi memakai tanggal yang sudah lewat, jadi angkanya bukan cuma kasar — '
                + 'tapi tentang waktu yang salah.')
          + kotak('sfSepi', state.buangSepi, 'terlalu sepi', (lc['terlalu sepi'] || 0),
                  'Transaksinya kurang dari Rp200 juta sehari. Saham sesepi ini tidak pernah ikut diuji '
                + 'waktu app ini dibuat, dan order Anda sendiri yang akan menggerakkan harganya.')
          + kotak('sfSisiB', state.buangSisiB, 'harganya sudah naik banyak', ((data.sisi_counts || {}).B || 0),
                  'Harga sudah naik lebih dari 5% dalam 20 hari, tapi pembeli besar masih memborong. '
                + 'Kelompok ini hasilnya paling jelek di semua pengujian — walau bedanya tipis, jadi '
                + 'bawaannya cuma ditandai, tidak dibuang.')
          + '  </div>'
          + '  <div class="sf-row">'
          + '    <span class="sf-label">Lapis</span>' + kotakLapis
          + '  </div>'
          + '  <div class="sf-row sf-row-end">'
          + '    <span class="sf-count" id="sfCount"></span>'
          + '    <button type="button" class="sf-link" id="sfToggleTersaring"></button>'
          + '    <button type="button" class="sf-link" id="sfReset" title="Kembali ke setelan awal: buang '
          + 'yang datanya tidak update dan yang terlalu sepi, tandai yang harganya sudah naik banyak, '
          + 'tampilkan semua lapis.">Setel ulang</button>'
          + '  </div>'
          + '  <div class="sf-tersaring" id="sfTersaring" style="display:none;"></div>'
          + '</div>');

        $('#sfCount').html('<strong>' + h.lolos.length + '</strong> dari '
            + (cfg.tickers || []).length + ' tampil');

        $('#sfToggleTersaring')
            .toggle(h.tersaring.length > 0)
            .text(h.tersaring.length + ' dibuang ' + (state.tampilkanTersaring ? '\u25B4' : '\u25BE'));

        if (state.tampilkanTersaring && h.tersaring.length) {
            $('#sfTersaring').show().html(h.tersaring.map(function (k) {
                return '<div class="sf-alasan"><span class="sf-kode">' + esc(k) + '</span>'
                     + '<span>' + esc(h.alasan[k]) + '</span></div>';
            }).join(''));
        } else {
            $('#sfTersaring').hide().empty();
        }

        if (typeof cfg.onChange === 'function') { cfg.onChange(h); }
    }

    function ubah() { simpan(); render(); }

    function pasangPeristiwa() {
        var m = $(cfg.mount);
        m.on('change', '#sfBasi', function () { state.buangBasi = this.checked; ubah(); });
        m.on('change', '#sfSepi', function () { state.buangSepi = this.checked; ubah(); });
        m.on('change', '#sfSisiB', function () { state.buangSisiB = this.checked; ubah(); });
        m.on('change', '[data-lapis]', function () {
            state.lapis[$(this).data('lapis')] = this.checked; ubah();
        });
        m.on('click', '#sfToggleTersaring', function () {
            state.tampilkanTersaring = !state.tampilkanTersaring; ubah();
        });
        m.on('click', '#sfReset', function () {
            state = $.extend(true, {}, BAWAAN); ubah();
        });
    }

    function init(options) {
        cfg = options || {};
        if (!cfg.mount || !cfg.tickers || !cfg.tickers.length) { return; }
        state = bacaSimpanan() || $.extend(true, {}, BAWAAN);

        function mulai() {
            pasangPeristiwa();
            render();
        }

        if (data) { mulai(); return; }
        // Header CSRF dipasang sendiri, tidak menumpang $.ajaxSetup di
        // base.html: setup itu berjalan di dalam $(function(){...}), jadi
        // komponen yang di-init dari tingkat atas skrip halaman akan
        // menembak lebih dulu dan balasannya 400. Bug ini sudah pernah
        // terjadi pada tiga menu lain; dengan header eksplisit di sini,
        // urutan muat tidak lagi jadi soal untuk halaman mana pun.
        $.ajax({
            url: '/filter-facts', type: 'POST', data: {},
            beforeSend: function (xhr) {
                var tok = $('meta[name="csrf-token"]').attr('content');
                if (tok) { xhr.setRequestHeader('X-CSRFToken', tok); }
            }
        }).done(function (d) {
            if (!d || !d.available) { $(cfg.mount).hide(); return; }
            data = d;
            mulai();
        }).fail(function () { $(cfg.mount).hide(); });
    }

    /* Perbarui daftar kode tanpa mengambil ulang fakta. */
    function setTickers(list) {
        if (!cfg) { return; }
        cfg.tickers = list || [];
        if (data) { render(); }
    }

    return { init: init, setTickers: setTickers, chipSisi: chipSisi };
})();

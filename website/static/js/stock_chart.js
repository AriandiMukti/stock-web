/*
 * Chart saham bersama: candlestick + arus Net Lot + volume, plus
 * autoscale saat zoom dan alat ukur box-select.
 *
 * Sebelumnya kode ini tinggal di dalam templates/stocks_image.html. Saat
 * Scanner Lab butuh chart yang sama untuk pratinjau sinyal, menyalinnya
 * berarti menduplikasi ~360 baris logika Plotly yang rumit -- jadi
 * dipindah ke sini dan dipakai berdua.
 *
 * Datanya dari GET /stock-chart-data/<kode>, dan endpoint itu menerima
 * ?focus=YYYY-MM-DD untuk menggambar penanda "Signal" pada tanggal
 * tertentu -- itu yang dipakai Scanner Lab untuk menandai hari sinyal.
 *
 * Butuh Plotly.js sudah dimuat lebih dulu.
 */
    // Palet warna chart. Didefinisikan DI SINI, bukan di template, karena
    // dipakai bersama: renderChart() di file ini dan renderWeeklyChart()
    // yang masih tinggal di stocks_image.html. Template memuat file ini
    // lebih dulu, jadi THEME sudah tersedia saat skrip inline-nya jalan.
    var THEME = {
        grid: '#38455A', text: '#93A2B6', textStrong: '#F4F7FB',
        up: '#16E0AE', down: '#FF6076', accent: '#16E0AE', level: '#93A2B6', flag: '#FFC352', srInfo: '#B892FF',
        absorb: '#4C7DF0', lepas: '#FF8A3D'
    };

    function bantalan(min, max, frac) {
        var range = max - min;
        if (range === 0) { range = Math.abs(max) || 1; }
        return [min - range * frac, max + range * frac];
    }

    // Skala vertikal keempat panel untuk rentang bar i0..i1. Dipakai dua
    // kali: saat chart pertama dibuka (dikunci ke 100 hari terakhir) dan
    // setiap kali di-zoom/geser. Sejak seluruh riwayat dari Januari ikut
    // dikirim, ini wajib -- tanpa penyesuaian, 100 hari terakhir akan
    // terjepit oleh rentang harga sembilan bulan.
    function rentangTerlihat(data, i0, i1, pad) {
        pad = pad || bantalan;
        var visHigh = data.high.slice(i0, i1 + 1);
        var visLow = data.low.slice(i0, i1 + 1);
        var visNetLot = data.netTop3Lot.slice(i0, i1 + 1);
        var visVol = data.volume.slice(i0, i1 + 1);
        var visFlow = data.cumulativeNorm.slice(i0, i1 + 1)
                        .concat(data.retailCumulativeNorm.slice(i0, i1 + 1));
        return {
            'yaxis.range': pad(Math.min.apply(null, visLow), Math.max.apply(null, visHigh), 0.08),
            'yaxis.autorange': false,
            // Garis arus ikut diskalakan. Dulu sumbunya dikunci [0,1] karena
            // seluruh data yang dikirim memang cuma 100 bar, jadi 0-1 selalu
            // pas. Sekarang datanya sembilan bulan, jadi kalau dibiarkan
            // dikunci, bagian yang sedang dilihat bisa jadi garis rata.
            'yaxis2.range': pad(Math.min.apply(null, visFlow), Math.max.apply(null, visFlow), 0.08),
            'yaxis2.autorange': false,
            'yaxis3.range': pad(Math.min(0, Math.min.apply(null, visNetLot)), Math.max(0, Math.max.apply(null, visNetLot)), 0.15),
            'yaxis3.autorange': false,
            'yaxis5.range': pad(0, Math.max.apply(null, visVol), 0.1),
            'yaxis5.autorange': false
        };
    }

    function attachAutoscale(div, data) {
        var n = data.dates.length;
        var pad = bantalan;

        // Posisi tiap batang mingguan di sumbu HARIAN. Dipakai untuk
        // menerjemahkan rentang zoom lilin ke rentang panel mingguan.
        //
        // Kenapa perlu diterjemahkan: panel mingguan punya sumbu kategori
        // sendiri supaya jarak antar batang seragam (baris di berkas
        // mingguan tidak berjarak tetap -- ada pekan 3 hari, ada yang 14).
        // Konsekuensinya dia tidak ikut bergerak saat lilin di-zoom. Alih-
        // alih menyerah dan mengembalikannya ke sumbu harian, rentangnya
        // disetel ulang di sini: zoom tetap terasa, jarak tetap rata.
        var mWeek = (data.weeklyNetTop3 || []).length;

        // Pemetaan PROPORSIONAL, bukan "cari batang mana yang masuk".
        //
        // Versi pertama mencari indeks batang pertama & terakhir yang
        // jatuh di dalam rentang zoom, lalu memakai itu sebagai rentang
        // panel. Zoom in terasa, zoom out tidak: begitu rentangnya
        // menyentuh batang pertama dan terakhir, hasilnya berhenti
        // berubah -- padahal lilinnya masih terus melebar. Hasilnya
        // "mentok" tanpa ada yang kelihatan bergerak.
        //
        // Pemetaan lurus dari posisi relatif menghilangkan mentok itu:
        // berapa pun rentang harian, panel mingguan bergerak sebanding,
        // termasuk saat di-zoom melebihi batas data (rentangnya ikut
        // melebihi batas, persis seperti panel harian).
        function weeklyRange(x0, x1) {
            if (mWeek < 2 || n < 2) { return null; }
            var skala = (mWeek - 1) / (n - 1);
            return [x0 * skala - 0.5, x1 * skala + 0.5];
        }

        div.on('plotly_relayout', function (ev) {
            if (ev['xaxis.autorange']) {
                Plotly.relayout(div, { 'yaxis.autorange': true, 'yaxis3.autorange': true,
                                       'yaxis5.autorange': true,
                                       'xaxis4.range': null, 'xaxis4.autorange': true,
                                       'yaxis4.range': null, 'yaxis4.autorange': true });
                return;
            }
            // Plotly mengirim rentang dalam DUA bentuk: 'xaxis.range[0]' /
            // 'xaxis.range[1]' saat digeser atau di-zoom dengan tetikus, tapi
            // 'xaxis.range' sebagai larik saat disetel lewat relayout().
            // Dulu cuma bentuk pertama yang dikenali, jadi setiap perubahan
            // rentang bentuk larik lolos tanpa menyesuaikan skala vertikal --
            // zoom out sampai Januari tetap memakai skala 100 hari terakhir
            // dan dasar harga Januari terpotong di luar layar.
            var x0 = ev['xaxis.range[0]'], x1 = ev['xaxis.range[1]'];
            if (x0 === undefined && Array.isArray(ev['xaxis.range'])) {
                x0 = ev['xaxis.range'][0];
                x1 = ev['xaxis.range'][1];
            }
            if (x0 === undefined || x1 === undefined) { return; }

            var i0 = Math.max(0, Math.floor(x0));
            var i1 = Math.min(n - 1, Math.ceil(x1));
            if (i1 <= i0) { return; }

            var ubah = rentangTerlihat(data, i0, i1, pad);

            var wr = weeklyRange(x0, x1);
            if (wr) {
                ubah['xaxis4.range'] = wr;
                ubah['xaxis4.autorange'] = false;
                // Skala vertikalnya ikut menyesuaikan batang yang terlihat,
                // sama seperti tiga panel lain.
                var a = Math.max(0, Math.round(wr[0] + 0.5));
                var b = Math.min(mWeek - 1, Math.round(wr[1] - 0.5));
                var vis = b >= a ? data.weeklyNetTop3.slice(a, b + 1) : [];
                if (vis.length) {
                    ubah['yaxis4.range'] = pad(Math.min(0, Math.min.apply(null, vis)),
                                               Math.max(0, Math.max.apply(null, vis)), 0.15);
                    ubah['yaxis4.autorange'] = false;
                }
            }

            Plotly.relayout(div, ubah);
        });
    }

    // Indices where series[i] is more than `z` standard deviations above
    // the mean of the trailing `window` bars — a plain rolling z-score,
    // not a real anomaly-detection model, but enough to flag "this day
    // doesn't look like the recent normal."
    function findAnomalies(series, window, z) {
        var idx = [];
        for (var i = window; i < series.length; i++) {
            var slice = series.slice(i - window, i);
            var mean = slice.reduce(function (a, b) { return a + b; }, 0) / slice.length;
            var variance = slice.reduce(function (a, b) { return a + Math.pow(b - mean, 2); }, 0) / slice.length;
            var std = Math.sqrt(variance);
            if (std > 0 && series[i] > mean + z * std) { idx.push(i); }
        }
        return idx;
    }

    // Same idea but flags either direction — a lot value can spike very
    // negative (a distribution burst) just as meaningfully as very
    // positive, unlike volume which only really spikes one way.
    function findAnomaliesAbs(series, window, z) {
        var idx = [];
        for (var i = window; i < series.length; i++) {
            var slice = series.slice(i - window, i);
            var mean = slice.reduce(function (a, b) { return a + b; }, 0) / slice.length;
            var variance = slice.reduce(function (a, b) { return a + Math.pow(b - mean, 2); }, 0) / slice.length;
            var std = Math.sqrt(variance);
            if (std > 0 && Math.abs(series[i] - mean) > z * std) { idx.push(i); }
        }
        return idx;
    }

    // Fase siklus harga (data.phases dari utilities.py stockChartData),
    // dilukis sebagai blok warna sepanjang rentang tanggalnya.
    //
    // Versi pertama fitur ini memakai tanda arus Net Top5 vs Retail 20
    // hari; diganti setelah diukur. Sumbu arus itu ternyata tidak punya
    // daya pisah sama sekali (865 emiten, H+10: akumulasi +0,67pp,
    // distribusi +0,69pp, netral +0,69pp -- ketiganya sama), dan label
    // gabungannya terbalik dari namanya. Sekarang fase dihitung dari
    // kemiringan MA20, jadi blok di chart SELALU sejalan dengan lilin
    // yang dilihat mata. Lihat catatan panjang di utilities.py.
    //
    // Warnanya MENJELASKAN arah harga, bukan menilai bagus/buruk: rekam
    // jejak tiap fase berbalik arah antar rezim (MARKUP -2,51pp di 2026
    // tapi +1,09pp di 2016-2025), jadi hijau di sini berarti "harga naik",
    // bukan "layak beli".
    // Tujuh fase. Arahnya ditentukan harga, NAMANYA ikut arus bandar,
    // mengikuti kerangka siklus bandar (lihat catatan di utilities.py):
    //   Markup        harga naik, Top5 TIDAK ikut beli -- bandar sudah
    //                 pegang barang, tinggal menggiring dan mulai melepas
    //   Naik Diborong harga naik DAN Top5 ikut beli >=2% volume -- bandar
    //                 memang sedang memborong, bukan sekadar menggiring
    //   Markdown      harga turun, Top5 TIDAK ikut jual -- barangnya sudah
    //                 habis dilepas, tinggal menekan sambil menyerap
    //   Turun Dilepas harga turun DAN Top5 ikut jual -- bandar benar-benar
    //                 sedang keluar
    //
    // WARNANYA IKUT APA YANG BANDAR LAKUKAN, BUKAN ARAH HARGA.
    //
    // Ini sengaja bukan konvensi chart biasa (hijau=naik, merah=turun).
    // Dari sisi orang yang mau masuk, yang menentukan bukan harganya lagi
    // ke mana, tapi dia sedang jadi lawan transaksi siapa:
    //
    //   merah  = bandar sedang MELEPAS ke pasar. Markup masuk sini: harga
    //            naik justru karena digiring sementara bandarnya jualan --
    //            yang beli di situ sedang menampung barangnya.
    //   hijau  = bandar sedang MENYERAP. Markdown masuk sini: harga turun
    //            tapi yang jual justru ditadah.
    //
    // Jadi Markup merah dan Markdown hijau, kebalikan dari warna lilinnya.
    //
    // Tetap DESKRIPSI, bukan ramalan: sumbu arus sudah diuji dan tidak
    // punya daya pisah terhadap return ke depan (akumulasi +0,67pp vs
    // distribusi +0,69pp di H+10). Merah berarti "lo lawan transaksi
    // bandar di sini", bukan "harga pasti turun".
    var PHASE_COLOR = {
        // bandar menyerap
        AKUMULASI:     THEME.srInfo,
        MARKDOWN:      THEME.up,
        NAIK_DIBORONG: THEME.absorb,
        // bandar melepas
        MARKUP:        THEME.down,
        DISTRIBUSI:    THEME.flag,
        TURUN_DILEPAS: THEME.lepas,
        RANGE:         THEME.level
    };

    // Pemicu: hari harga berbalik 10% dari ekstrem 20 harinya. Ini bagian
    // yang bisa dipakai SAAT ITU JUGA -- beda dari warna fase, yang batas
    // kirinya baru bisa diketahui setelah pembalikan terjadi.
    //
    // Dua-duanya lolos uji di dua sampel terpisah (21 emiten 2016-2025 dan
    // semesta penuh 2026), di ketiga horizon, dan di seluruh rentang
    // ambang 5-15% -- lihat PHASE_REVERSAL_PCT di utilities.py. Angkanya
    // ada di hover tiap penanda supaya bisa dinilai sendiri, bukan cuma
    // dipercaya.
    var TRIGGER_STYLE = {
        turun_dari_puncak: { color: THEME.down, symbol: 'triangle-down', size: 13, atas: true },
        naik_dari_dasar:   { color: THEME.up, symbol: 'triangle-up', size: 13, atas: false }
    };

    function hexToRgba(hex, alpha) {
        var r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    function buildPhaseVisuals(data) {
        var phases = data.phases || [];
        var dates = data.dates;
        var shapes = [], annotations = [];
        var lastLabeledTag = null;
        // Baris label diselang-seling supaya dua label yang titik
        // tengahnya berdekatan tidak bertumpuk -- Plotly tidak
        // menghindari tumpang tindih antar anotasi sendiri.
        var labelRows = [1, 0.92];
        var rowIdx = 0;
        phases.forEach(function (seg, idx) {
            var color = PHASE_COLOR[seg.key];
            if (!color) { return; }
            // Batas kanan blok ini = awal blok berikutnya, supaya
            // rentang-rentang bersambung tanpa celah maupun tumpang tindih
            // (bukan berhenti di tengah lilin terakhir milik fase ini).
            var next = phases[idx + 1];
            var x1 = next ? dates[next.startIdx] : dates[dates.length - 1];
            shapes.push({
                type: 'rect', xref: 'x', x0: dates[seg.startIdx], x1: x1,
                yref: 'y domain', y0: 0, y1: 1,
                fillcolor: hexToRgba(color, 0.10), line: { width: 0 }, layer: 'below'
            });
            // Garis batas di kedua ujung blok -- tanpa ini dua isian yang
            // mepet (keduanya cuma alpha 0,10) berbaur jadi satu gradasi,
            // bukan dua masa yang jelas beda.
            if (seg.startIdx > 0) {
                shapes.push({
                    type: 'line', xref: 'x', x0: dates[seg.startIdx], x1: dates[seg.startIdx],
                    yref: 'y domain', y0: 0, y1: 1,
                    line: { color: hexToRgba(color, 0.55), width: 1, dash: 'dot' }, layer: 'below'
                });
            }
            if (next) {
                shapes.push({
                    type: 'line', xref: 'x', x0: x1, x1: x1, yref: 'y domain', y0: 0, y1: 1,
                    line: { color: hexToRgba(color, 0.55), width: 1, dash: 'dot' }, layer: 'below'
                });
            }
            if (seg.endIdx - seg.startIdx >= 3 && seg.label !== lastLabeledTag) {
                var midIdx = Math.floor((seg.startIdx + seg.endIdx) / 2);
                // Besaran arusnya ditempel di label -- sejak penamaan cuma
                // memakai TANDA arus, angkanya yang memberi tahu seberapa
                // kuat, supaya "secara berarti" tetap bisa dinilai sendiri.
                var arus = seg.bandarPct;
                var teks = seg.label;
                if (arus !== null && arus !== undefined) {
                    teks += '  ' + (arus > 0 ? '+' : '') + arus.toFixed(1) + '%';
                }
                annotations.push({
                    xref: 'x', x: dates[midIdx], yref: 'y domain', y: labelRows[rowIdx % labelRows.length],
                    yanchor: 'top', text: teks, showarrow: false,
                    font: { color: color, size: 10, family: 'JetBrains Mono' }, opacity: 0.9
                });
                lastLabeledTag = seg.label;
                rowIdx++;
            }
        });
        return { shapes: shapes, annotations: annotations };
    }

    // Penanda pemicu digambar sebagai TRACE (bukan anotasi) supaya
    // angka hasil pengujiannya bisa muncul di hover -- itu yang membuat
    // penanda ini bisa dinilai sendiri, bukan cuma dipercaya.
    function buildTriggerTraces(data) {
        var trig = data.phaseTriggers || [];
        var dates = data.dates, high = data.high, low = data.low;
        var out = [];
        Object.keys(TRIGGER_STYLE).forEach(function (kind) {
            var sel = trig.filter(function (t) { return t.kind === kind; });
            if (!sel.length) { return; }
            var st = TRIGGER_STYLE[kind];
            // Penanda turun ditaruh DI ATAS lilinnya, penanda naik di
            // bawah -- supaya tidak menutupi badan lilin di hari yang
            // justru paling ingin dilihat.
            out.push({
                type: 'scatter', mode: 'markers',
                x: sel.map(function (t) { return dates[t.idx]; }),
                y: sel.map(function (t) {
                    return st.atas ? high[t.idx] * 1.02 : low[t.idx] * 0.98;
                }),
                marker: { symbol: st.symbol, size: st.size, color: st.color,
                          line: { color: '#04060A', width: 1.5 } },
                xaxis: 'x', yaxis: 'y', showlegend: false,
                customdata: sel.map(function (t) { return [t.label, t.note]; }),
                hovertemplate: '<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>'
            });
        });
        return out;
    }

    function renderChart(data, targetId) {
        // Default ke chartDiv supaya pemanggilan lama tetap jalan;
        // Scanner Lab mengoper id div modal-nya sendiri.
        targetId = targetId || 'chartDiv';
        // Empat panel, tiga sela. Sejak plot_bgcolor dicat, tiap panel
        // punya kotak sendiri yang kelihatan -- dan selanya dulu 0,03 /
        // 0,05 / 0,11, tidak rata, yang baru ketahuan begitu kotaknya
        // tidak lagi transparan. Sekarang tiga sela sama besar (0,04) dan
        // ketiga panel bawah sama tinggi (0,14); panel harga mengambil
        // sisanya. Jumlahnya tepat 1,0.
        var candleDomain = [0.54, 1.00];
        var volumeDomain = [0.36, 0.50];
        var netLotDomain = [0.18, 0.32];
        var retailDomain = [0.00, 0.14];

        // Per-day % change from the previous close, for the hover box --
        // `data.change` is only the latest day's change, but every candle
        // needs its own value here.
        var dailyChangePct = data.close.map(function (c, i) {
            if (i === 0 || !data.close[i - 1]) { return null; }
            return (c - data.close[i - 1]) / data.close[i - 1] * 100;
        });
        // Plotly's candlestick trace doesn't fully honor a custom
        // hovertemplate -- it keeps showing its own High/Low lines
        // alongside it regardless. hoverinfo:'text' + a fully pre-built
        // text string is the version that actually suppresses them.
        var candleHoverText = data.open.map(function (o, i) {
            var c = dailyChangePct[i];
            var chgStr = c === null ? '—' : (c >= 0 ? '+' : '') + c.toFixed(2) + '%';
            return 'Open: ' + o + '<br>Close: ' + data.close[i] + '<br>Change: ' + chgStr;
        });
        var candlestick = {
            type: 'candlestick',
            x: data.dates, open: data.open, high: data.high, low: data.low, close: data.close,
            increasing: { line: { color: THEME.up, width: 1 }, fillcolor: THEME.up },
            decreasing: { line: { color: THEME.down, width: 1 }, fillcolor: THEME.down },
            xaxis: 'x', yaxis: 'y', name: '',
            text: candleHoverText,
            hoverinfo: 'text'
        };

        function glowLine(y, color) {
            return [4, 2].map(function (w) {
                return {
                    type: 'scatter', mode: 'lines', x: data.dates, y: y,
                    line: { color: color, width: w, shape: 'spline', smoothing: 0.65 },
                    opacity: 0.12, xaxis: 'x', yaxis: 'y2', hoverinfo: 'skip', showlegend: false
                };
            });
        }
        // Net Top5/Retail Lot are in lots (1 lot = 100 shares) -- convert
        // to Rupiah value in billions using that day's own Avg Price
        // (same convention the confidence-score value fields already
        // use), so the hover shows an actual money figure instead of the
        // 0-1 normalized value the line itself is plotted with.
        var bigLotFlowValueB = data.netTop5Lot.map(function (v, i) {
            return v * 100 * (data.avgPriceSeries[i] || 0) / 1e9;
        });
        var retailFlowValueB = data.retail.map(function (v, i) {
            return v * 100 * (data.avgPriceSeries[i] || 0) / 1e9;
        });

        var bigMoneyGlow = glowLine(data.cumulativeNorm, THEME.up);
        var bigMoneyLine = {
            type: 'scatter', mode: 'lines', x: data.dates, y: data.cumulativeNorm,
            line: { color: THEME.up, width: 1.75, shape: 'spline', smoothing: 0.65 },
            xaxis: 'x', yaxis: 'y2', name: 'Big Lot Flow',
            customdata: bigLotFlowValueB,
            hovertemplate: 'Big Lot Flow: %{customdata:.2f}B<extra></extra>'
        };
        var retailGlow = glowLine(data.retailCumulativeNorm, THEME.down);
        var retailLine = {
            type: 'scatter', mode: 'lines', x: data.dates, y: data.retailCumulativeNorm,
            line: { color: THEME.down, width: 1.75, shape: 'spline', smoothing: 0.65 },
            xaxis: 'x', yaxis: 'y2', name: 'Retail Flow',
            customdata: retailFlowValueB,
            hovertemplate: 'Retail Flow: %{customdata:.2f}B<extra></extra>'
        };
        // Accumulation start = the backend's combined signal (Net Top5
        // rolling sum flips up the same day Retail's rolling sum flips
        // down) — validated by backtesting as the strongest version of
        // this signal, stronger than either flip happening on its own.
        var crossingsUp = data.combinedCrossingDays || [];

        function crossingHalo(idxList) {
            return {
                type: 'scatter', mode: 'markers',
                x: idxList.map(function (i) { return data.dates[i]; }),
                y: idxList.map(function (i) { return data.cumulativeNorm[i]; }),
                marker: { symbol: 'circle', size: 20, color: 'rgba(4,6,10,0.85)' },
                xaxis: 'x', yaxis: 'y2', hoverinfo: 'skip', showlegend: false
            };
        }
        var crossingUpHalo = crossingHalo(crossingsUp);
        var crossingMarkers = {
            type: 'scatter', mode: 'markers',
            x: crossingsUp.map(function (i) { return data.dates[i]; }),
            y: crossingsUp.map(function (i) { return data.cumulativeNorm[i]; }),
            marker: { symbol: 'triangle-up', size: 14, color: THEME.flag, line: { color: '#04211D', width: 2 } },
            xaxis: 'x', yaxis: 'y2', name: 'Accumulation start',
            hovertemplate: 'Big Lot Flow turns positive<extra></extra>', showlegend: false
        };
        var netLotColors = data.retail.map(function (r) { return r < 0 ? THEME.up : THEME.down; });
        var netLotBars = {
            type: 'bar', x: data.dates, y: data.netTop3Lot,
            marker: { color: netLotColors, opacity: 0.85, line: { width: 0 } },
            xaxis: 'x', yaxis: 'y3', name: 'Net Top3 Lot'
        };
        var netLotAnomalyIdx = findAnomaliesAbs(data.netTop3Lot, 20, 2);
        var netLotAnomalyMarkers = {
            type: 'scatter', mode: 'markers',
            x: netLotAnomalyIdx.map(function (i) { return data.dates[i]; }),
            y: netLotAnomalyIdx.map(function (i) { return data.netTop3Lot[i]; }),
            marker: { symbol: 'star', size: 10, color: THEME.flag, line: { color: '#04211D', width: 1.5 } },
            xaxis: 'x', yaxis: 'y3', name: 'Unusual net lot',
            hovertemplate: 'Net lot spike (2σ from 20D avg)<extra></extra>', showlegend: false
        };
        // Arah maknanya kebalikan dari retail: Net Top3 POSITIF berarti
        // tiga broker teratas net beli -- akumulasi, jadi warna naik.
        var weeklyColors = data.weeklyNetTop3.map(function (v) { return v > 0 ? THEME.up : THEME.down; });
        // SUMBU SENDIRI, tidak lagi matches:'x'.
        //
        // Sebelumnya panel ini memakai sumbu kategori harian yang sama
        // dengan lilin, supaya tiap batang jatuh tepat di bawah
        // tanggalnya. Masalahnya baris di berkas mingguan TIDAK berjarak
        // tetap: sebarannya 7 hari untuk 22 baris, tapi ada juga yang 3,
        // 4, 5, 6, 8, 9, 10, dan 14 hari -- pekan pendek karena libur
        // bursa, plus hari yang memang hilang di berkas harian. Di sumbu
        // harian itu terlihat sebagai batang yang menggerombol lalu
        // menganga, dan lebar per-batang yang dulu dipakai untuk
        // menghindari tumpang-tindih membuat sebagiannya jadi kurus
        // sendiri.
        //
        // Tiap baris tetap MEWAKILI satu pekan perdagangan walau tanggal
        // penutupnya bergeser, jadi jaraknya memang seharusnya seragam.
        // Yang ditukar: batang tidak lagi sebaris vertikal dengan lilin
        // di atasnya, dan panel ini tidak ikut bergeser saat chart harga
        // digeser -- karena itu sumbunya dikunci (fixedrange) supaya
        // tidak bisa digeser sendiri dan jadi menyesatkan.
        var retailBars = {
            type: 'bar', x: data.weeklyDates, y: data.weeklyNetTop3,
            marker: { color: weeklyColors, opacity: 0.85, line: { width: 0 } },
            xaxis: 'x4', yaxis: 'y4', name: 'Weekly Net Top3 All Lot',
            hovertemplate: 'Pekan %{x}<br>Net Top3 %{y:,.0f} lot<extra></extra>'
        };
        var volColors = data.volUp.map(function (u) { return u ? THEME.up : THEME.down; });
        var volBars = {
            type: 'bar', x: data.dates, y: data.volume,
            marker: { color: volColors, opacity: 0.55, line: { width: 0 } },
            xaxis: 'x', yaxis: 'y5', name: 'Volume'
        };

        // Flags days where volume is a statistical outlier against its own
        // trailing 20-day average — a sudden, unusual spike is often more
        // telling than the slow accumulation trend the flow lines track.
        var volAnomalyIdx = findAnomalies(data.volume, 20, 2);
        var volAnomalyMarkers = {
            type: 'scatter', mode: 'markers',
            x: volAnomalyIdx.map(function (i) { return data.dates[i]; }),
            y: volAnomalyIdx.map(function (i) { return data.volume[i]; }),
            marker: { symbol: 'star', size: 11, color: THEME.flag, line: { color: '#04211D', width: 1.5 } },
            xaxis: 'x', yaxis: 'y5', name: 'Unusual volume',
            hovertemplate: 'Volume spike (2σ above 20D avg)<extra></extra>', showlegend: false
        };
        var shapes = data.levels.map(function (lvl) {
            return { type: 'line', xref: 'x domain', x0: 0, x1: 1, yref: 'y', y0: lvl, y1: lvl, line: { color: THEME.level, width: 1, dash: 'dot' } };
        });
        // Nearest support (highest level below last close) and resistance
        // (lowest level above it) -- used below to tag their % distance
        // from the last close near the last candle, instead of appended
        // to the level label at the domain edge (that got clipped by the
        // chart's right margin once the text got longer).
        var lastCloseForLevels = data.close[data.close.length - 1];
        var nearestSupport = null, nearestResistance = null;
        data.levels.forEach(function (lvl) {
            if (lvl <= lastCloseForLevels && (nearestSupport === null || lvl > nearestSupport)) { nearestSupport = lvl; }
            if (lvl >= lastCloseForLevels && (nearestResistance === null || lvl < nearestResistance)) { nearestResistance = lvl; }
        });
        // Support/resistance TERDEKAT dikecualikan dari sini -- harganya
        // sudah ikut ditulis di label ±% dekat lilin terakhir (di bawah).
        // Dulu dua-duanya digambar terpisah: tag harga polos di sini
        // (tanpa bgcolor, di tepi domain) DAN label ±% di dekat lilin
        // (dengan bgcolor opaque). Saat level itu harganya dekat dengan
        // penutupan terakhir, dua tag itu jatuh di lokasi yang nyaris
        // sama -- dan karena tag di sini digambar duluan (jadi lapisan
        // paling bawah) serta tidak punya bgcolor, ia ketimpa kotak
        // opaque milik label ±% dan jadi tidak kelihatan sama sekali.
        var annotations = data.levels.filter(function (lvl) {
            return lvl !== nearestSupport && lvl !== nearestResistance;
        }).map(function (lvl) {
            return { xref: 'x domain', x: 1.0, xanchor: 'left', yref: 'y', y: lvl, text: lvl.toFixed(0), showarrow: false, font: { color: THEME.level, size: 10, family: 'JetBrains Mono' } };
        });

        // Last-day change %, tagged right at the last candle instead of
        // only in the title above -- easier to read at a glance where the
        // candle actually is, especially once you've zoomed/panned away
        // from the title.
        var lastIdx = data.dates.length - 1;
        if (lastIdx >= 0 && data.change !== null && data.change !== undefined) {
            var lastChangeColor = data.change >= 0 ? THEME.up : THEME.down;
            annotations.push({
                xref: 'x', x: data.dates[lastIdx], xanchor: 'left', xshift: 14,
                yref: 'y', y: data.close[lastIdx], yanchor: 'middle',
                text: (data.change >= 0 ? '+' : '') + data.change + '%',
                showarrow: false, font: { color: lastChangeColor, size: 11, family: 'JetBrains Mono' },
                bgcolor: 'rgba(4,6,10,0.85)', borderpad: 3
            });
        }

        // % distance from the last close to the nearest support/
        // resistance, tagged near the last candle (same spot as the
        // change % above) instead of appended to the level label at the
        // domain edge, which got clipped once that text got longer.
        // Pinned to the last close's y position (not the level's own y)
        // with a fixed vertical pixel offset, not the level's actual
        // price -- when a level sits close in price to the last close
        // (e.g. CDIA: close 680, support 650, only ~4% apart), anchoring
        // at the level's own y put this right on top of the Change label
        // above. A fixed yshift away from the close keeps them apart
        // regardless of how close the level's price is.
        if (lastIdx >= 0 && nearestSupport !== null) {
            annotations.push({
                xref: 'x', x: data.dates[lastIdx], xanchor: 'left', xshift: 14,
                yref: 'y', y: lastCloseForLevels, yanchor: 'middle', yshift: -18,
                text: nearestSupport.toFixed(0) + '  -' + ((lastCloseForLevels - nearestSupport) / lastCloseForLevels * 100).toFixed(1) + '%',
                showarrow: false, font: { color: THEME.srInfo, size: 10, family: 'JetBrains Mono' },
                bgcolor: 'rgba(4,6,10,0.85)', borderpad: 3
            });
        }
        if (lastIdx >= 0 && nearestResistance !== null) {
            annotations.push({
                xref: 'x', x: data.dates[lastIdx], xanchor: 'left', xshift: 14,
                yref: 'y', y: lastCloseForLevels, yanchor: 'middle', yshift: 18,
                text: nearestResistance.toFixed(0) + '  +' + ((nearestResistance - lastCloseForLevels) / lastCloseForLevels * 100).toFixed(1) + '%',
                showarrow: false, font: { color: THEME.srInfo, size: 10, family: 'JetBrains Mono' },
                bgcolor: 'rgba(4,6,10,0.85)', borderpad: 3
            });
        }

        // Marks the signal date when this chart was opened from the
        // Breakout Signals list (data.focusIndex), so the setup that
        // triggered the signal is easy to find instead of hunting for it
        // in the candles.
        if (data.focusIndex !== null && data.focusIndex !== undefined && data.dates[data.focusIndex]) {
            var focusX = data.dates[data.focusIndex];
            shapes.push({
                type: 'line', xref: 'x', x0: focusX, x1: focusX, yref: 'paper', y0: 0, y1: 1,
                line: { color: THEME.flag, width: 1.5, dash: 'dash' }
            });
            annotations.push({
                xref: 'x', x: focusX, yref: 'paper', y: 1, yanchor: 'bottom',
                text: 'Signal', showarrow: false,
                font: { color: THEME.flag, size: 10, family: 'JetBrains Mono' }
            });
        }

        // Blok fase digambar PALING BAWAH (layer 'below' di atas sudah
        // menaruhnya di belakang lilin) dan label-nya digabung sebelum
        // anotasi lain, supaya tidak menutupi anotasi PRICE/VOLUME dkk.
        var phaseVisuals = buildPhaseVisuals(data);
        shapes = phaseVisuals.shapes.concat(shapes);
        annotations = phaseVisuals.annotations.concat(annotations);

        annotations = annotations.concat([
            { text: 'PRICE', y: candleDomain[1] },
            { text: 'VOLUME', y: volumeDomain[1] },
            { text: 'NET LOT · D', y: netLotDomain[1] },
            { text: 'NET TOP3 · W', y: retailDomain[1] }
        ].map(function (p) {
            return {
                xref: 'paper', x: 0, xanchor: 'left', yref: 'paper', y: p.y, yanchor: 'top',
                text: p.text, showarrow: false,
                font: { color: THEME.text, size: 9.5, family: 'JetBrains Mono' }, opacity: 0.55
            };
        }));

        var axisCommon = {
            gridcolor: 'rgba(255,255,255,0.045)', color: THEME.text,
            zeroline: false, showline: false, ticks: '',
            tickfont: { size: 10, family: 'JetBrains Mono' }
        };

        var layout = {
            // Bidang plot dicat --void, bukan transparan: kartu di
            // belakangnya bergradien terang (#1B2330), dan lilin tipis di
            // atasnya jadi kurang kontras. Kertasnya tetap transparan
            // supaya bingkai kartunya masih terlihat.
            paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: '#04060A', font: { color: THEME.text, family: 'JetBrains Mono' },
            title: { text: 'Value ' + data.value + 'B   ·   Change ' + data.change + '%', font: { color: THEME.textStrong, size: 13, family: "'Plus Jakarta Sans', sans-serif" }, x: 0.01, xanchor: 'left' },
            showlegend: false, hovermode: 'x unified',
            hoverlabel: { bgcolor: '#26313F', bordercolor: '#38455A', font: { family: 'JetBrains Mono', size: 11, color: '#F4F7FB' } },
            // Kanan dilebarkan dari 46 -- label ±% support/resistance dekat
            // lilin terakhir sekarang ikut memuat harga levelnya (mis.
            // "650  -4.2%", bukan cuma "-4.2%"), dan margin lama cuma
            // cukup untuk versi pendeknya. Teks yang lebih panjang jatuh
            // di luar area yang digambar Plotly dan jadi tidak kelihatan
            // sama sekali, bukan sekadar terpotong.
            margin: { t: 40, l: 46, r: 100, b: 28 },
            bargap: 0.3,
            dragmode: 'pan',
            xaxis: Object.assign({ domain: [0, 1], anchor: 'y', type: 'category',
                categoryorder: 'array', categoryarray: data.dates, rangeslider: { visible: false }, matches: 'x',
                showspikes: true, spikemode: 'across', spikesnap: 'cursor', spikecolor: THEME.accent, spikethickness: 1, spikedash: 'dot' }, axisCommon),
            // Label tanggal DIMATIKAN. Tiga panel lain menumpang sumbu
            // harian dan labelnya cuma muncul sekali di bawah lilin; kalau
            // panel ini punya baris tanggalnya sendiri, dia jadi satu-satunya
            // yang punya dan langsung kebaca sebagai chart terpisah yang
            // ditempel di bawah, bukan bagian dari tumpukan yang sama.
            // Tanggal per batang tetap ada di hover ('Pekan 05 Sep').
            xaxis4: Object.assign({
                domain: [0, 1], anchor: 'y4', type: 'category',
                categoryorder: 'array', categoryarray: data.weeklyDates,
                // fixedrange SENGAJA tidak dipakai: di Plotly ia memblokir
                // perubahan rentang lewat relayout() juga, bukan cuma drag
                // manual -- jadi panel ini tidak akan pernah ikut ter-zoom.
                // Konsekuensinya panel mingguan bisa digeser sendiri; kalau
                // itu terjadi, klik-ganda (autorange) mengembalikannya.
                showticklabels: false, autorange: true
            }, axisCommon),
            yaxis: Object.assign({ domain: candleDomain }, axisCommon),
            yaxis2: { domain: candleDomain, overlaying: 'y', side: 'right', showgrid: false, range: [0, 1], visible: false },
            yaxis3: Object.assign({ domain: netLotDomain }, axisCommon),
            yaxis4: Object.assign({ domain: retailDomain }, axisCommon),
            yaxis5: Object.assign({ domain: volumeDomain }, axisCommon),
            shapes: shapes, annotations: annotations
        };

        // Tampilan awal dikunci ke 100 hari terakhir walau datanya dari
        // Januari -- zoom out baru memunculkan sisanya. Skala vertikal
        // keempat panel ikut disetel ke jendela itu; kalau tidak, 100 hari
        // terakhir akan terjepit oleh rentang harga sembilan bulan.
        var awal = data.focusStart;
        if (awal !== null && awal !== undefined && awal > 0 && awal < data.dates.length - 1) {
            var akhir = data.dates.length - 1;
            // WAJIB indeks ANGKA, bukan string tanggal. Sumbu ini bertipe
            // 'category' (tanggal lengkap dengan tahun tetap kategori, bukan
            // sumbu tanggal), dan range pada sumbu kategori
            // memakai posisi 0..n-1. Versi pertama mengoper ["14 Apr","11 Sep"]
            // -- Plotly gagal mengurainya dan jatuh ke [-1, 6], yang membuat
            // chart terbuka ter-zoom di tujuh bar pertama alias awal Januari.
            layout.xaxis.range = [awal - 0.5, akhir + 0.5];
            layout.xaxis.autorange = false;
            var rv = rentangTerlihat(data, awal, akhir);
            layout.yaxis.range = rv['yaxis.range'];
            layout.yaxis.autorange = false;
            layout.yaxis2.range = rv['yaxis2.range'];
            layout.yaxis3.range = rv['yaxis3.range'];
            layout.yaxis3.autorange = false;
            layout.yaxis5.range = rv['yaxis5.range'];
            layout.yaxis5.autorange = false;
        }

        var traces = [candlestick].concat(bigMoneyGlow, [bigMoneyLine], retailGlow, [retailLine],
            [crossingUpHalo, crossingMarkers],
            [netLotBars, netLotAnomalyMarkers, retailBars, volBars, volAnomalyMarkers],
            buildTriggerTraces(data));

        // Dikembalikan (bukan dibuang) supaya pemanggil yang perlu tahu
        // KAPAN chart-nya benar-benar selesai dilukis bisa menunggu --
        // dipakai captureAllForShare() di stocks_image.html supaya tidak
        // menangkap screenshot chart yang belum sempat digambar.
        var plotted = Plotly.newPlot(targetId, traces, layout, {
            responsive: true, displaylogo: false, scrollZoom: true,
            modeBarButtonsToRemove: ['lasso2d']
        });

        attachAutoscale(document.getElementById(targetId), data);
        attachMeasureTool(document.getElementById(targetId), data);
        return plotted;
    }

    // Box-select (the modebar's select tool, left enabled above) between
    // two candles draws a line connecting their close prices and labels
    // the % / Rp change and trading-day count between them -- click the
    // select-box icon in the chart's modebar, drag across a range, done.
    function attachMeasureTool(div, data) {
        div.removeAllListeners('plotly_selected');
        div.removeAllListeners('plotly_deselect');

        function clearMeasure() {
            Plotly.relayout(div, {
                shapes: (div.layout.shapes || []).filter(function (s) { return s.name !== 'measureLine'; }),
                annotations: (div.layout.annotations || []).filter(function (a) { return a.name !== 'measureLabel'; })
            });
        }

        div.on('plotly_selected', function (eventData) {
            if (!eventData || !eventData.range || !eventData.range.x) { return; }
            var x0 = eventData.range.x[0], x1 = eventData.range.x[1];
            var n = data.dates.length;
            var i0 = Math.max(0, Math.min(n - 1, Math.round(Math.min(x0, x1))));
            var i1 = Math.max(0, Math.min(n - 1, Math.round(Math.max(x0, x1))));
            if (i0 === i1) { clearMeasure(); return; }

            var p0 = data.close[i0], p1 = data.close[i1];
            var chg = p1 - p0;
            var pct = p0 ? (chg / p0) * 100 : 0;
            var color = chg >= 0 ? THEME.up : THEME.down;
            var label = (chg >= 0 ? '+' : '') + pct.toFixed(2) + '%  (' + (chg >= 0 ? '+' : '') + chg.toFixed(0) + ')  ·  ' + (i1 - i0) + 'D';

            Plotly.relayout(div, {
                shapes: (div.layout.shapes || []).filter(function (s) { return s.name !== 'measureLine'; }).concat([{
                    name: 'measureLine', type: 'line', xref: 'x', yref: 'y',
                    x0: data.dates[i0], x1: data.dates[i1], y0: p0, y1: p1,
                    line: { color: color, width: 2, dash: 'dot' }
                }]),
                annotations: (div.layout.annotations || []).filter(function (a) { return a.name !== 'measureLabel'; }).concat([{
                    name: 'measureLabel', xref: 'x', yref: 'y',
                    x: data.dates[i1], y: p1, xanchor: 'left', yanchor: 'middle',
                    yshift: chg >= 0 ? -18 : 18,
                    text: label, showarrow: false,
                    font: { color: color, size: 11, family: 'JetBrains Mono' },
                    bgcolor: 'rgba(4,6,10,0.9)', borderpad: 4
                }])
            });
        });

        div.on('plotly_deselect', clearMeasure);
    }

/*
 * Kartu keputusan: ringkasan sumber sinyal yang sudah dihitung di tempat
 * lain (scanner.py score_signal, flow_health FLOW_COLOR), TANPA
 * menggabungkannya jadi satu skor -- tiap kartu berdiri sendiri, warnanya
 * cuma menandai arah bukti masing-masing.
 *
 * "Screen otomatis" dan "Aktivitas insider" sengaja TIDAK dimasukkan:
 * screen otomatis nyaris selalu merah/netral (cuma Consol Low yang
 * historisnya positif, screen_eval.py), dan cluster insider tidak pernah
 * divalidasi sebagai sinyal hijau (insider_activity.buy_cluster_count())
 * -- dimensi yang strukturnya tidak pernah bisa hijau cuma menambah
 * bising, jadi dibuang dari kartu ini.
 *
 * Awalnya tinggal di templates/stock_hub.html; dipindah ke sini supaya
 * halaman Watchlist/Screens (stocks_image.html) bisa memakainya juga
 * tanpa menyalin ~140 baris logika verdict.
 *
 * Pemanggil menyediakan id lima elemen DOM (lihat render()) dan payload
 * dari POST /saham-data/<kode> (build_hub() -- lihat stock_hub.py).
 */
var DecisionCard = (function () {
    function esc(t) { return $('<div>').text(t === null || t === undefined ? '' : t).html(); }
    function idNum(v, d) {
        if (v === null || v === undefined || isNaN(v)) { return '—'; }
        return Number(v).toLocaleString('id-ID', {
            minimumFractionDigits: d || 0, maximumFractionDigits: d === undefined ? 0 : d });
    }
    function pct(v, d) {
        if (v === null || v === undefined || isNaN(v)) { return '—'; }
        return idNum(v, d === undefined ? 2 : d) + '%';
    }

    var VERDICT_COLOR = { hijau: '#16E0AE', kuning: '#FFC352', merah: '#FF6076', netral: '#586479' };
    var FLOW_COLOR = { akumulasi: 'hijau', netral: 'kuning', distribusi: 'merah' };
    var chartInstances = {};

    function bestFlowCheckpoint(flow) {
        var available = (flow || []).filter(function (f) { return f.available; });
        if (!available.length) { return null; }
        return available.reduce(function (best, f) { return f.horizon > best.horizon ? f : best; });
    }

    // Ambang volume disalin persis dari scanner.py score_signal() -- itu
    // satu-satunya faktor yang terbukti besar & monoton di backtest
    // Scanner Lab (selisih 7,9pp antar kelompok volume).
    function volumeVerdict(vol) {
        if (vol === null || vol === undefined || isNaN(vol)) {
            return { v: 'netral', text: 'Data volume tidak tersedia.' };
        }
        if (vol < 1) { return { v: 'hijau', text: 'Volume sepi (' + vol.toFixed(1) + 'x) — historis terbaik.' }; }
        if (vol < 2) { return { v: 'netral', text: 'Volume normal (' + vol.toFixed(1) + 'x).' }; }
        if (vol < 5) { return { v: 'kuning', text: 'Volume ramai (' + vol.toFixed(1) + 'x) — historis buruk.' }; }
        return { v: 'merah', text: 'Volume melonjak (' + vol.toFixed(1) + 'x) — historis terburuk.' };
    }

    // Selalu tampilkan tanggal kalender-nya -- "X hari lalu" cuma
    // tambahan kalau asOfDate ada, BUKAN pengganti tanggalnya. Regresi
    // yang sempat terjadi: versi sebelumnya cuma menampilkan "(X hari
    // lalu)" dan itu jadi string kosong kalau asOfDate tidak dikirim
    // (mis. dari Jurnal Keputusan), membuat tanggal sinyalnya hilang
    // total dari teks.
    function _signalAgeText(sig, asOfDate) {
        var days = asOfDate ? daysBetween(sig.signal_date, asOfDate) : null;
        return ' (' + esc(sig.signal_date) + (days === null ? '' : ', ' + days + ' hari lalu') + ')';
    }

    // Ambang skor disalin persis dari scoreColor() yang sudah dipakai di
    // Scanner Lab / Kering Screener supaya artinya konsisten.
    //
    // sig.pending (dari FORWARD_NEEDED di scanner.py) menandai apakah
    // sinyal ini masih dalam masa evaluasinya (20-60 hari tergantung
    // scanner). Kalau sudah lewat (pending === false), skornya jadi
    // NETRAL apa pun nilainya -- sinyal yang sudah "matang" itu
    // mengukur pola SAAT MUNCUL, bukan kondisi sekarang, dan hasilnya
    // (kalau ada) sudah tercermin di harga. Menampilkan skornya seolah
    // masih berlaku ke depan menyesatkan -- lihat riwayat percakapan
    // saat fitur ini pertama kali dipertanyakan.
    function scoreVerdict(sig, asOfDate) {
        if (!sig) { return { v: 'netral', text: 'Tidak ada sinyal scanner yang sedang berjalan.' }; }
        var base = 'Skor pola ' + sig.score + '/100 dari sinyal ' + esc(sig.scanner_label) + _signalAgeText(sig, asOfDate) + '.';
        if (sig.pending === false) {
            return { v: 'netral', text: base + ' Sinyal historis, sudah lewat masa evaluasi ('
                + (sig.forward_needed || '?') + ' hari) — bukan indikasi kondisi sekarang.' };
        }
        var s = sig.score;
        if (s >= 65) { return { v: 'hijau', text: base + ' Tergolong pola kuat secara historis.' }; }
        if (s < 40) { return { v: 'merah', text: base + ' Tergolong pola lemah secara historis.' }; }
        return { v: 'netral', text: base + ' Netral, bukan pola kuat.' };
    }

    function flowVerdict(sig, asOfDate) {
        if (!sig) { return { v: 'netral', text: 'Tidak ada sinyal untuk dihitung kesehatan arusnya.' }; }
        if (sig.pending === false) {
            return { v: 'netral', text: 'Sinyal historis' + _signalAgeText(sig, asOfDate)
                + ', sudah lewat masa evaluasi (' + (sig.forward_needed || '?') + ' hari) — bukan indikasi kondisi sekarang.' };
        }
        var best = bestFlowCheckpoint(sig.flow);
        if (!best) {
            return { v: 'netral', text: 'Belum ada checkpoint kesehatan arus yang tersedia (terlalu baru sejak sinyal'
                + _signalAgeText(sig, asOfDate) + ').' };
        }
        return {
            v: FLOW_COLOR[best.arah_arus] || 'netral',
            text: 'H+' + best.horizon + ' sejak sinyal' + _signalAgeText(sig, asOfDate) + ': ' + esc(best.label)
                + ' — harga ' + (best.price_pct >= 0 ? '+' : '') + best.price_pct.toFixed(2) + '%'
                + (best.low_sample ? ' (sampel kecil)' : '') + '.'
        };
    }

    // Persentase KSEI dihitung dari saham SCRIPLESS, bukan dari seluruh
    // saham perusahaan (KSEI cuma "melihat" yang discripless-kan). Untuk
    // emiten dengan scripless_pct_of_listed rendah (mis. LAJU 32,56%),
    // "Retail 99,54%" bisa terbaca seolah 99,54% PERUSAHAAN dimiliki
    // ritel, padahal dari total saham cuma ~32%. Baris kedua ("dari
    // total X%") cuma muncul saat perbedaannya berarti (<95% scripless)
    // supaya mayoritas saham (yang sudah ~100% scripless, dua angkanya
    // sama) tidak menampilkan baris yang tidak perlu.
    function ownershipVerdict(o) {
        if (!o) { return { v: 'netral', text: 'Data kepemilikan belum ditarik.' }; }
        var sp = o.scripless_pct_of_listed;
        var text = 'Retail ' + pct(o.pct_retail, 1) + ', lokal non-ritel ' + pct(o.pct_local_non_retail, 1) + '.';
        // Selalu ditampilkan (bukan cuma saat rendah) -- kalau disembunyikan
        // waktu tinggi, halaman terlihat seperti datanya hilang padahal
        // cuma tidak ada apa-apa yang perlu dikoreksi (banyak saham
        // scripless-nya persis 100%, mis. RLCO).
        // Ritel sesungguhnya = %ritel (dari saham scripless) x %scripless.
        // Angka KSEI hanya mencakup saham yang sudah scripless, jadi "retail
        // 21%" pada emiten yang baru 43% scripless sebenarnya cuma 9% dari
        // seluruh saham tercatat.
        var ritelAsli = null;
        if (sp !== null && sp !== undefined && !isNaN(sp)
            && o.pct_retail !== null && o.pct_retail !== undefined && !isNaN(o.pct_retail)) {
            ritelAsli = o.pct_retail * sp / 100;
            if (sp < 95) {
                text += ' Cuma ' + pct(sp, 0) + ' saham scripless — dari total: retail '
                      + ritelAsli.toFixed(0) + '%.';
            } else {
                text += ' Scripless ' + pct(sp, 0) + ' (data KSEI mencakup hampir semua saham tercatat).';
            }
        }
        if (ritelAsli === null) { return { v: 'netral', text: text }; }
        // Ambang ditetapkan pengguna: basis ritel tipis dianggap baik,
        // tebal dianggap berisiko. Belum diuji terhadap return -- kalau
        // nanti diuji dan gagal, angkanya yang berubah, bukan strukturnya.
        if (ritelAsli <= 30) {
            return { v: 'hijau', text: text + ' Ritel ' + ritelAsli.toFixed(0)
                   + '% dari total saham — tipis (batas hijau 30%).' };
        }
        if (ritelAsli >= 50) {
            return { v: 'merah', text: text + ' Ritel ' + ritelAsli.toFixed(0)
                   + '% dari total saham — tebal (batas merah 50%).' };
        }
        return { v: 'netral', text: text + ' Ritel ' + ritelAsli.toFixed(0) + '% dari total saham.' };
    }

    // Selalu netral, sengaja -- ini KONTEKS untuk menafsirkan dimensi
    // lain (dibaca bersama Kondisi Pasar di Ringkasan Watchlist), bukan
    // sinyal arah yang berdiri sendiri. Belum ada backtest yang
    // membuktikan "korelasi rendah ke IHSG = return lebih baik" --
    // memberi warna hijau/merah di sini akan berpura-pura tahu lebih
    // dari yang datanya tunjukkan, sama seperti Komposisi Kepemilikan.
    function independenceVerdict(ind) {
        if (!ind || !ind.available) { return { v: 'netral', text: 'Data korelasi IHSG tidak tersedia.' }; }
        return { v: 'netral', text: 'Korelasi ' + ind.correlation.toFixed(2) + ' ke IHSG — ' + esc(ind.label) + '.' };
    }

    // Bukan angka yang sudah dibacktest sendiri -- ini penerapan langsung
    // dari kerangka akumulasi/distribusi yang sama dengan flow_health.py
    // (Top5 & Retail berlawanan arah) ke arus 5 hari terakhir, supaya ada
    // pembacaan arus yang SELALU tersedia walau tidak ada sinyal scanner
    // aktif (beda dengan Skor Pola yang sering netral untuk saham diam).
    function shortFlowVerdict(p) {
        var top5 = p && p.net_top5_5d, retail = p && p.retail_5d;
        if (top5 === null || top5 === undefined || retail === null || retail === undefined) {
            return { v: 'netral', text: 'Data arus 5 hari tidak tersedia.' };
        }
        var lot = function (v) { return (v >= 0 ? '+' : '') + idNum(v / 1000, 1) + 'rb'; };
        var text = 'Top5 ' + lot(top5) + ', Retail ' + lot(retail);
        if (top5 > 0 && retail < 0) { return { v: 'hijau', text: text + ' — akumulasi.' }; }
        if (top5 < 0 && retail > 0) { return { v: 'merah', text: text + ' — distribusi.' }; }
        return { v: 'netral', text: text + '.' };
    }

    function daysBetween(a, b) {
        var da = new Date(a + 'T00:00:00'), db = new Date(b + 'T00:00:00');
        if (isNaN(da) || isNaN(db)) { return null; }
        return Math.round((db - da) / 86400000);
    }

    // Hijau = sinyalnya BARU (<=7 hari), bukan "kemungkinan naik" --
    // backtest Kering Screener sendiri NEGATIF di semua horizon (H=5:
    // -9,44% mean, win 21,9%, -9,79pp vs pasar; docstring
    // kering_screener.py) baik untuk kandidat baru maupun lama. Warna di
    // sini cuma menandai KEBARUAN sinyal, peringatannya tetap disertakan
    // di teks supaya tidak disalahartikan sebagai ajakan beli.
    function keringVerdict(k, asOfDate) {
        if (!k) { return { v: 'netral', text: 'Bukan kandidat Kering Screener.' }; }
        var days = asOfDate ? daysBetween(k.date, asOfDate) : null;
        var freshTxt = days === null ? '' : (' (' + days + 'h lalu)');
        var text = 'Kandidat' + freshTxt + ', skor ' + k.skor + ' — riwayat negatif, bukan ajakan beli.';
        return { v: (days !== null && days <= 7) ? 'hijau' : 'merah', text: text };
    }

    // Skor pola dari H-5 s.d. sekarang -- BUKAN dari tanggal sinyal
    // scanner historis (beda dengan scoreVerdict di atas, yang tetap
    // dipakai Ringkasan Watchlist/Jurnal Keputusan untuk menilai sinyal
    // DISKRET yang pernah muncul). Selalu tersedia, tidak pernah basi,
    // karena jendelanya ikut bergerak bersama "sekarang". stock_hub.py:
    // _current_score() membangun barisnya dari data hari ini lalu
    // memanggil score_signal() yang sama persis dipakai Scanner Lab.
    function currentScoreVerdict(cs) {
        if (!cs) { return { v: 'netral', text: 'Data skor pola tidak tersedia.' }; }
        if (cs.score >= 65) { return { v: 'hijau', text: 'Skor ' + cs.score + '/100 — kuat.' }; }
        if (cs.score < 40) { return { v: 'merah', text: 'Skor ' + cs.score + '/100 — lemah.' }; }
        return { v: 'netral', text: 'Skor ' + cs.score + '/100 — netral.' };
    }

    // Sama seperti di atas -- flow_health.check_current() memakai
    // metode identik dengan check() (korelasi kumulatif Top5/Retail
    // terhadap waktu), cuma jendelanya H-5 s.d. hari terakhir yang ada
    // datanya, bukan signal_date+1 s.d. checkpoint.
    function currentFlowVerdict(cf) {
        if (!cf || !cf.available) { return { v: 'netral', text: (cf && cf.message) || 'Data kesehatan arus tidak tersedia.' }; }
        return {
            v: FLOW_COLOR[cf.arah_arus] || 'netral',
            text: esc(cf.label) + ' (' + (cf.price_pct >= 0 ? '+' : '') + cf.price_pct.toFixed(1) + '%)'
                + (cf.low_sample ? ' · sampel kecil' : '') + '.'
        };
    }

    // Modal bandar: rata-rata harga lot yang MASIH DIPEGANG seluruh broker
    // (FIFO, jadi yang tersisa adalah pembelian terbaru), dibanding harga
    // sekarang. Sengaja SELALU netral, tidak pernah hijau/merah: arah dari
    // posisi modal gagal direplikasi di luar sampel (21 emiten, 2016-2025 --
    // sisi peringatan malah berbalik tanda, dan hanya negatif di 5 dari 10
    // tahun). Yang ditampilkan cuma fakta posisinya, bukan penilaian.
    function modalBandarVerdict(mb) {
        if (!mb || mb.harga_modal === null || mb.harga_modal === undefined) {
            return { v: 'netral', text: 'Modal bandar tidak bisa dihitung (data broker belum ada).' };
        }
        var arah = mb.rasio >= 0 ? 'di atas' : 'di bawah';
        var t = 'Modal ' + idNum(mb.harga_modal, 0) + ' vs harga ' + idNum(mb.harga_sekarang, 0)
              + ' — harga ' + pct(Math.abs(mb.rasio), 1) + ' ' + arah + ' modal (' + esc(mb.posisi) + ')';
        if (mb.gerak10 !== null && mb.gerak10 !== undefined) {
            t += ', harga bergerak ' + (mb.gerak10 >= 0 ? '+' : '') + mb.gerak10.toFixed(1)
               + '% dalam ' + mb.hari_gerak + ' hari';
        }

        // Aturan warna ditetapkan pengguna. "Harga bergerak" dibaca sebagai
        // BESARAN geraknya (naik atau turun sama saja) supaya kata yang sama
        // berarti sama di kedua sisi: <=5% berarti harga masih diam, >=10%
        // berarti sudah bergerak jauh.
        //
        //   hijau : bandar rugi >=5%  DAN harga masih diam (<=5% dalam 10h)
        //           -- bandar tersangkut sementara harganya belum ke mana-mana
        //   merah : bandar untung >=5% DAN harga sudah bergerak >=10%
        //           -- bandar punya untung DAN momentum untuk melepas
        //
        // CATATAN: arah dari posisi modal saja tidak lolos uji luar sampel
        // (21 emiten, 2016-2025). Aturan di sini BEDA -- ia menambahkan
        // syarat gerak harga, dan syarat itu belum diuji terpisah.
        var g = (mb.gerak10 === null || mb.gerak10 === undefined) ? null : Math.abs(mb.gerak10);
        if (g !== null) {
            if (mb.rasio <= -5 && g <= 5) {
                return { v: 'hijau', text: t + '. Bandar tersangkut sementara harga masih diam.' };
            }
            if (mb.rasio >= 5 && g >= 10) {
                return { v: 'merah', text: t + '. Bandar sudah untung dan harga sudah bergerak jauh — '
                       + 'mereka punya alasan sekaligus kesempatan melepas.' };
            }
        }
        return { v: 'netral', text: t + '.' };
    }

    // ids: { ring, headline, sub, legend, flags } -- id elemen DOM tujuan.
    // d: payload dari POST /saham-data/<kode> (build_hub()).
    function render(ids, d) {
        var asOfDate = d.price && d.price.date;
        var flags = [
            { name: 'Lonjakan hari ini', r: volumeVerdict(d.price && d.price.vol_mult) },
            { name: 'Kesehatan arus terbaru', r: currentFlowVerdict(d.current_flow) },
            { name: 'Arus Top5/Retail 5 hari', r: shortFlowVerdict(d.price) },
            { name: 'Skor pola sinyal', r: currentScoreVerdict(d.current_score) },
            { name: 'Kandidat Kering Screener', r: keringVerdict(d.kering, asOfDate) },
            { name: 'Komposisi kepemilikan', r: ownershipVerdict(d.ownership) },
            { name: 'Independensi dari IHSG', r: independenceVerdict(d.independence) },
            { name: 'Modal bandar', r: modalBandarVerdict(d.modal_bandar) }
        ];

        var counts = { hijau: 0, kuning: 0, merah: 0, netral: 0 };
        flags.forEach(function (f) { counts[f.r.v]++; });

        $('#' + ids.flags).html(flags.map(function (f) {
            return '<div class="hb-flag hb-flag-' + f.r.v + '">'
                 + '<div class="hb-flag-name">' + esc(f.name) + '</div>'
                 + '<div class="hb-flag-detail">' + f.r.text + '</div>'
                 + '</div>';
        }).join(''));

        $('#' + ids.legend).html(
            '<span><span class="hb-decision-dot" style="background:' + VERDICT_COLOR.merah + ';"></span>' + counts.merah + ' merah</span>'
          + '<span><span class="hb-decision-dot" style="background:' + VERDICT_COLOR.kuning + ';"></span>' + counts.kuning + ' kuning</span>'
          + '<span><span class="hb-decision-dot" style="background:' + VERDICT_COLOR.netral + ';"></span>' + counts.netral + ' netral</span>'
          + '<span><span class="hb-decision-dot" style="background:' + VERDICT_COLOR.hijau + ';"></span>' + counts.hijau + ' hijau</span>');

        var total = flags.length;
        var headline, headColor;
        if (counts.merah > 0) { headline = counts.merah + '/' + total; headColor = VERDICT_COLOR.merah; }
        else if (counts.hijau > 0) { headline = counts.hijau + '/' + total; headColor = VERDICT_COLOR.hijau; }
        else { headline = '0/' + total; headColor = VERDICT_COLOR.netral; }
        $('#' + ids.headline).text(headline).css('color', headColor);
        $('#' + ids.sub).text(counts.merah > 0 ? 'merah' : (counts.hijau > 0 ? 'hijau' : 'bendera'));

        if (chartInstances[ids.ring]) { chartInstances[ids.ring].destroy(); }
        chartInstances[ids.ring] = new Chart(document.getElementById(ids.ring), {
            type: 'doughnut',
            data: {
                labels: flags.map(function (f) { return f.name; }),
                datasets: [{ data: flags.map(function () { return 1; }),
                            backgroundColor: flags.map(function (f) { return VERDICT_COLOR[f.r.v]; }),
                            borderColor: '#1B2330', borderWidth: 3 }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: '68%',
                plugins: { legend: { display: false } },
                // Tanpa ini, cincinnya baru selesai dianimasikan ~1 detik
                // setelah dibuat -- kalau ditangkap layar (mis. Kirim PDF
                // ke WhatsApp) sebelum itu, hasilnya cincin yang baru
                // separuh terisi, seperti belum selesai dibentuk.
                animation: false
            }
        });
    }

    // Cincin kecil tanpa legenda/headline -- dipakai Ringkasan Watchlist
    // untuk menampilkan ringkasan per baris tanpa memanggil /saham-data
    // sendiri-sendiri per ticker (Digest sudah punya datanya dari
    // build_digest(), verdicts dihitung dari situ lewat scoreVerdict/
    // flowVerdict/keringVerdict yang diekspos di bawah).
    function renderMiniRing(canvasId, verdicts) {
        if (chartInstances[canvasId]) { chartInstances[canvasId].destroy(); }
        chartInstances[canvasId] = new Chart(document.getElementById(canvasId), {
            type: 'doughnut',
            data: {
                datasets: [{ data: verdicts.map(function () { return 1; }),
                            backgroundColor: verdicts.map(function (v) { return VERDICT_COLOR[v]; }),
                            borderColor: '#1B2330', borderWidth: 2 }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: '55%',
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                animation: false
            }
        });
    }

    return {
        render: render,
        renderMiniRing: renderMiniRing,
        scoreVerdict: scoreVerdict,
        flowVerdict: flowVerdict,
        currentScoreVerdict: currentScoreVerdict,
        currentFlowVerdict: currentFlowVerdict,
        keringVerdict: keringVerdict,
        VERDICT_COLOR: VERDICT_COLOR
    };
})();

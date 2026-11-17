(() => {
    const byId = suffix => document.getElementById(`hbCandle${suffix}`);
    const {results, trades} = JSON.parse(byId('Data').textContent);
    const labels = {
        strong_bull: 'Candle bullish besar', engulfing: 'Bullish engulfing',
        morning_like: 'Morning-star-like', hammer: 'Hammer',
        breakout20: 'Breakout high 20 sesi', pullback20: 'Pullback ke MA20',
    };
    const reasons = {stop: 'Stop', gap_stop: 'Gap di bawah stop', target: 'Target', time: 'Batas pegang'};
    const number = (value, digits = 0) => Number(value).toLocaleString('id-ID', {
        minimumFractionDigits: digits, maximumFractionDigits: digits,
    });
    const pct = (value, digits = 2) => value === '' ? '—' : `${value > 0 ? '+' : ''}${number(value, digits)}%`;

    function addRow(table, values) {
        const row = table.insertRow();
        values.forEach((value, index) => {
            const cell = row.insertCell();
            if (index === 0) cell.className = 'hb-left';
            cell.append(value);
        });
        return row;
    }

    function render() {
        const period = byId('Period').value;
        const hold = byId('Hold').value;
        const filter = byId('Filter').value;
        const table = byId('Results');
        const audit = byId('Audit');
        table.replaceChildren();
        audit.hidden = true;

        for (const [pattern, label] of Object.entries(labels)) {
            const result = results.find(row => row.period === period && row.hold === hold && row.pattern === pattern + filter);
            if (!result) continue;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-sm btn-outline-secondary';
            button.textContent = label;
            button.setAttribute('aria-expanded', 'false');
            button.setAttribute('aria-controls', audit.id);
            addRow(table, [button, result.trades, result.win_pct === '' ? '—' : `${number(result.win_pct, 1)}%`,
                pct(result.avg_pct), pct(result.return_pct), pct(result.max_dd_pct)]);

            button.addEventListener('click', () => {
                const expanded = button.getAttribute('aria-expanded') === 'true';
                table.querySelectorAll('button').forEach(other => other.setAttribute('aria-expanded', 'false'));
                audit.hidden = expanded;
                if (expanded) return;
                button.setAttribute('aria-expanded', 'true');
                const entries = trades.filter(trade => trade.period === period && trade.hold === hold && trade.pattern === result.pattern);
                const tradeTable = byId('Trades');
                tradeTable.replaceChildren();
                byId('AuditTitle').textContent = `${label} · ${entries.length} transaksi`;
                for (const trade of entries) {
                    addRow(tradeTable, [trade.signal, trade.entry_date, number(trade.entry, 2), trade.exit_date,
                        number(trade.exit, 2), number(trade.stop, 2), number(trade.target, 2),
                        reasons[trade.reason] || trade.reason, pct(100 * trade.net_return)]);
                }
            });
        }
        const benchmark = results.find(row => row.period === period && row.pattern === 'buy_hold');
        byId('Benchmark').textContent = benchmark
            ? `Beli dan tahan pada periode yang sama ${pct(benchmark.return_pct)} setelah biaya, tanpa dividen. Drawdown ${pct(benchmark.max_dd_pct)}.`
            : '';
    }

    ['Period', 'Hold', 'Filter'].forEach(id => byId(id).addEventListener('change', render));
    render();
})();

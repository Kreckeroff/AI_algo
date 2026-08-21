from ai_algo.domain.trade_analysis import analyze_trades, infer_script_regime


def test_infer_trend_regime():
    nodes = [{"id": "1", "type": "indicator_supertrend"}, {"id": "2", "type": "indicator_adx"}]
    assert infer_script_regime(nodes) == "trend"


def test_sawtooth_trend_suggests_filter():
    # Alternating short holds — chop for a trend script
    trades = []
    t0 = 1_700_000_000
    for i in range(12):
        trades.append(
            {
                "entryTime": t0 + i * 60,
                "exitTime": t0 + i * 60 + 120,
                "side": "buy",
                "qty": 1,
                "entryPrice": 100,
                "exitPrice": 101 if i % 2 == 0 else 99,
                "pnl": 1.0 if i % 2 == 0 else -1.0,
                "barsHeld": 2,
            }
        )
    report = analyze_trades(
        trades,
        graph_nodes=[{"type": "indicator_ema"}, {"type": "indicator_adx"}],
    )
    assert report["regime"] == "trend"
    assert "пила_короткие_сделки" in report["findings"] or "тренд_без_фильтра_флэта" in report["findings"]
    assert any("фильтр" in s.lower() or "ADX" in s or "флэт" in s for s in report["suggestions"])


def test_few_trades_warning():
    report = analyze_trades(
        [{"entryTime": 1, "exitTime": 2, "pnl": 1, "barsHeld": 5, "side": "buy"}],
    )
    assert report["trade_count"] == 1
    assert "мало_закрытых_сделок" in report["findings"]

"""Heuristic analysis of historical backtest trades for advice."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def _closed(trades: Sequence[dict]) -> List[dict]:
    out = []
    for t in trades:
        if not isinstance(t, dict):
            continue
        if t.get("exitTime") is None and t.get("exit_time") is None:
            continue
        pnl = t.get("pnl")
        if pnl is None:
            continue
        out.append(t)
    return out


def _pnl(t: dict) -> float:
    try:
        return float(t.get("pnl") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _bars_held(t: dict) -> Optional[float]:
    v = t.get("barsHeld")
    if v is None:
        v = t.get("bars_held")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _side(t: dict) -> str:
    s = str(t.get("side") or "").lower()
    if s in ("sell", "short", "s"):
        return "short"
    return "long"


def infer_script_regime(graph_nodes: Optional[Sequence[Any]]) -> str:
    """Rough regime from block types: trend | mean_reversion | breakout | unknown."""
    if not graph_nodes:
        return "unknown"
    types = []
    for n in graph_nodes:
        if isinstance(n, dict):
            types.append(str(n.get("type") or "").lower())
        else:
            types.append(str(n).lower())
    blob = " ".join(types)
    score = {"trend": 0, "mean_reversion": 0, "breakout": 0}
    for key in (
        "supertrend",
        "adx",
        "plus_di",
        "minus_di",
        "ema",
        "sma",
        "macd",
        "sar",
    ):
        if key in blob:
            score["trend"] += 1
    for key in ("bb_lower", "bb_upper", "bb", "rsi", "stoch", "cci"):
        if key in blob:
            score["mean_reversion"] += 1
    for key in ("highest", "lowest", "volume", "breakout"):
        if key in blob:
            score["breakout"] += 1
    # RSI alone in trend stack still counts MR a bit; prefer max
    best = max(score, key=lambda k: score[k])
    if score[best] == 0:
        return "unknown"
    return best


def analyze_trades(
    trades: Optional[Sequence[dict]],
    *,
    graph_nodes: Optional[Sequence[Any]] = None,
    regime: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return findings + Russian suggestions grounded in trade list.

    Examples of issues we try to catch:
    - sawtooth / chop: many short alternating wins/losses (bad for trend scripts)
    - overtrading / tiny holds
    - long losing streaks
    - side imbalance (one side destroys PnL)
    - MR script with very long holds (holding through trend)
    """
    closed = _closed(trades or [])
    findings: List[str] = []
    suggestions: List[str] = []
    regime = regime or infer_script_regime(graph_nodes)

    n = len(closed)
    if n < 5:
        findings.append("мало_закрытых_сделок")
        suggestions.append(
            "Мало закрытых сделок для разбора — расширьте окно бэктеста или ослабьте фильтры входа."
        )
        return {
            "regime": regime,
            "trade_count": n,
            "findings": findings,
            "suggestions": suggestions[:5],
        }

    pnls = [_pnl(t) for t in closed]
    holds = [h for h in (_bars_held(t) for t in closed) if h is not None]
    median_hold = sorted(holds)[len(holds) // 2] if holds else None
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    winrate = wins / n if n else 0.0

    # Alternating W/L = sawtooth / chop
    signs = [1 if p > 0 else (-1 if p < 0 else 0) for p in pnls]
    flips = sum(1 for i in range(1, len(signs)) if signs[i] and signs[i - 1] and signs[i] != signs[i - 1])
    flip_rate = flips / max(1, n - 1)

    if flip_rate >= 0.55 and median_hold is not None and median_hold <= 8:
        findings.append("пила_короткие_сделки")
        if regime == "trend":
            suggestions.append(
                "Похоже на «пилу»: частые короткие сделки с чередованием плюс/минус. "
                "Для трендового скрипта добавьте фильтр режима (ADX / направление DI / выше EMA) "
                "или запрет входа во флэте, увеличьте минимальное время в позиции / hold."
            )
        elif regime == "mean_reversion":
            suggestions.append(
                "Много коротких разворотных сделок подряд. "
                "Для mean-reversion сузьте зону входа (ближе к крайним BB/RSI) "
                "или добавьте фильтр «не торговать в сильном тренде» (ADX высокий → пауза)."
            )
        else:
            suggestions.append(
                "Частая «пила» коротких сделок. Добавьте фильтр режима рынка "
                "(тренд vs флэт) и ограничьте число входов в день."
            )

    if median_hold is not None and median_hold <= 3 and n >= 15:
        findings.append("сверхкороткие_удержания")
        suggestions.append(
            "Медиана удержания очень мала — похоже на шум/overtrading. "
            "Увеличьте период сигналов, добавьте подтверждение на старшем ТФ или logic_hold."
        )

    # Losing streak
    max_lose = 0
    cur = 0
    for p in pnls:
        if p < 0:
            cur += 1
            max_lose = max(max_lose, cur)
        else:
            cur = 0
    if max_lose >= 5:
        findings.append("серия_убытков")
        suggestions.append(
            "Длинная серия убытков подряд. Добавьте паузу после N убытков "
            "(блок «2 убытка подряд» / cooldown) или уменьшите размер после просадки."
        )

    # Side imbalance
    long_pnl = sum(_pnl(t) for t in closed if _side(t) == "long")
    short_pnl = sum(_pnl(t) for t in closed if _side(t) == "short")
    long_n = sum(1 for t in closed if _side(t) == "long")
    short_n = sum(1 for t in closed if _side(t) == "short")
    if long_n >= 3 and short_n >= 3:
        if long_pnl > 0 and short_pnl < 0 and abs(short_pnl) > 0.5 * abs(long_pnl):
            findings.append("шорты_портят_результат")
            suggestions.append(
                "Long в плюсе, short сильно тянет вниз — отключите шорты или ужесточите условия short "
                "(только при подтверждённом нисходящем режиме)."
            )
        elif short_pnl > 0 and long_pnl < 0 and abs(long_pnl) > 0.5 * abs(short_pnl):
            findings.append("лонги_портят_результат")
            suggestions.append(
                "Short в плюсе, long тянет вниз — отключите лонги или усильте фильтр бычьего тренда."
            )

    if regime == "mean_reversion" and median_hold is not None and median_hold >= 40:
        findings.append("mr_слишком_долго_держит")
        suggestions.append(
            "Mean-reversion удерживает позицию слишком долго. "
            "Добавьте быстрый выход к середине канала / противоположный RSI и жёсткий SL."
        )

    if regime == "trend" and winrate < 0.4 and n >= 12 and flip_rate >= 0.45:
        findings.append("тренд_без_фильтра_флэта")
        suggestions.append(
            "Трендовая логика при низкой винрейте и частых разворотах — типичный флэт. "
            "Фильтр: торговать только при ADX выше порога или при согласии цены и EMA/SuperTrend."
        )

    if not suggestions:
        suggestions.append(
            "Явных паттернов «пилы»/серий не видно по сделкам — смотрите diff метрик и блоков; "
            "проверьте out-of-sample окно."
        )

    return {
        "regime": regime,
        "trade_count": n,
        "winrate": round(winrate, 4),
        "median_bars_held": median_hold,
        "flip_rate": round(flip_rate, 4),
        "max_losing_streak": max_lose,
        "long_pnl": long_pnl,
        "short_pnl": short_pnl,
        "findings": findings,
        "suggestions": suggestions[:5],
    }

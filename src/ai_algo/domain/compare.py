from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def metrics_diff(before: dict, after: dict) -> Dict[str, float]:
    keys = ("pnl", "max_dd", "winrate", "trades")
    out: Dict[str, float] = {}
    for k in keys:
        out[k] = float(after[k]) - float(before[k])
    for k in ("sharpe", "sortino"):
        if k in before and k in after:
            out[k] = float(after[k]) - float(before[k])
    return out


def _metrics_unchanged(diff: Dict[str, float], eps: float = 1e-12) -> bool:
    return all(abs(diff.get(k, 0.0)) <= eps for k in ("pnl", "max_dd", "winrate", "trades"))


def verdict_from_diff(
    before: dict,
    after: dict,
    align_before: Optional[dict] = None,
    align_after: Optional[dict] = None,
) -> Tuple[str, Dict[str, float], List[str], List[str]]:
    """Return verdict, diff, warnings, suggestions."""
    warnings: List[str] = []
    suggestions: List[str] = []

    if align_before is not None and align_after is not None:
        for key in ("symbol", "timeframe", "commission", "from", "to"):
            if align_before.get(key) != align_after.get(key):
                raise ValueError("align_mismatch")

    diff = metrics_diff(before, after)

    if before.get("trades", 0) < 5 or after.get("trades", 0) < 5:
        warnings.append("low_sample")

    if _metrics_unchanged(diff):
        verdict = "unchanged"
        suggestions.append(
            "Метрики бэктеста не изменились на этом окне — либо тот же прогон, либо смена блоков/period не затронула результат."
        )
        suggestions.append("Убедитесь: Запомнить → изменить граф → новый бэктест → Спросить ИИ.")
        return verdict, diff, warnings, suggestions[:3]

    pnl_better = after["pnl"] > before["pnl"]
    dd_better = after["max_dd"] < before["max_dd"]
    pnl_worse = after["pnl"] < before["pnl"]
    dd_worse = after["max_dd"] > before["max_dd"]

    if pnl_better and dd_better:
        verdict = "better"
    elif pnl_worse and dd_worse:
        verdict = "worse"
    else:
        verdict = "mixed"

    if dd_worse:
        suggestions.append("Просадка выросла — проверьте стопы / размер / фильтры.")
    if pnl_worse:
        suggestions.append("Прибыль хуже — проверьте входы/выходы и комиссии.")
    if verdict == "mixed":
        suggestions.append("Прибыль и просадка разошлись — выберите главный критерий (доход или риск).")
    if not suggestions:
        suggestions.append("Оставьте изменение и проверьте на другом out-of-sample окне.")

    return verdict, diff, warnings, suggestions[:3]


_VERDICT_RU = {
    "better": "лучше",
    "worse": "хуже",
    "mixed": "смешанно",
    "unchanged": "без изменений",
}


def commentary(verdict: str, diff: Dict[str, float], graph_notes: Optional[List[str]] = None) -> str:
    label = _VERDICT_RU.get(verdict, verdict)
    parts = [
        "Вердикт: {v}.".format(v=label),
        "Δприбыль={pnl:.4f}, Δпросадка={dd:.4f}, Δвинрейт={wr:.4f}, Δсделки={tr:.0f}.".format(
            pnl=diff.get("pnl", 0.0),
            dd=diff.get("max_dd", 0.0),
            wr=diff.get("winrate", 0.0),
            tr=diff.get("trades", 0.0),
        ),
    ]
    if verdict == "unchanged":
        parts.append("Метрики до/после совпали.")
    if graph_notes:
        parts.append("Изменения блоков: " + "; ".join(graph_notes) + ".")
    elif verdict == "unchanged":
        parts.append("Снимка отличий графа нет — снова нажмите «Запомнить» на старой версии, затем меняйте блоки.")
    return " ".join(parts)


def graph_change_notes(before_graph, after_graph):
    """Human notes about block/param changes (MVP structural diff)."""
    if before_graph is None:
        before_graph = []
    if after_graph is None:
        after_graph = []
    if not isinstance(before_graph, list) or not isinstance(after_graph, list):
        return []
    if not before_graph and not after_graph:
        return []
    before_by_id = {
        str(n.get("id")): n for n in before_graph if isinstance(n, dict) and n.get("id") is not None
    }
    after_by_id = {
        str(n.get("id")): n for n in after_graph if isinstance(n, dict) and n.get("id") is not None
    }
    notes = []
    if not before_graph and after_graph:
        notes.append("в базе не было снимка графа (снова нажмите «Запомнить результат»)")
        return notes
    added = [i for i in after_by_id if i not in before_by_id]
    removed = [i for i in before_by_id if i not in after_by_id]
    if added:
        notes.append("добавлены блоки: {ids}".format(ids=", ".join(added[:8])))
    if removed:
        notes.append("удалены блоки: {ids}".format(ids=", ".join(removed[:8])))
    for i in after_by_id:
        if i not in before_by_id:
            continue
        b, a = before_by_id[i], after_by_id[i]
        if b.get("type") != a.get("type"):
            notes.append(
                "блок {i} тип {bt} → {at}".format(i=i, bt=b.get("type"), at=a.get("type"))
            )
            continue
        bd = b.get("data") if isinstance(b.get("data"), dict) else {}
        ad = a.get("data") if isinstance(a.get("data"), dict) else {}
        keys = sorted(set(bd) | set(ad))
        changed = []
        for k in keys:
            if bd.get(k) != ad.get(k):
                changed.append("{k}: {bv} → {av}".format(k=k, bv=bd.get(k), av=ad.get(k)))
        if changed:
            label = a.get("type") or i
            notes.append("блок {label} ({i}): {c}".format(label=label, i=i, c="; ".join(changed[:6])))
    return notes[:12]

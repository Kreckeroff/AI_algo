#!/usr/bin/env python3
"""Build BUSINESS_ANALYTICS.html — plain-language + full training analytics through C19."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESS = ROOT / "artifacts/agent_loop/sessions"
OUT = ROOT / "artifacts/agent_loop" / "BUSINESS_ANALYTICS.html"

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def main() -> None:
    c17 = load_json(SESS / "2026-08-21-c17-walkforward-div/results/variant_summary.json", {}) or {}
    c17m = load_json(SESS / "2026-08-21-c17-walkforward-div/models/feature_names.json", {}) or {}
    b0 = load_json(SESS / "2026-08-21-b0-regime-annotate/results/summary.json", {}) or {}
    b0b = load_json(SESS / "2026-08-21-b0b-regime-thresholds/results/summary.json", {}) or {}
    c18 = load_json(SESS / "2026-08-21-c18-regime-dual/results/variant_summary.json", {}) or {}
    c18b = load_json(SESS / "2026-08-21-c18b-mr-overlay/results/variant_summary.json", {}) or {}
    c19 = load_json(SESS / "2026-08-21-c19-selective-apply/results/summary.json", {}) or {}
    promoted = load_json(SESS / "2026-08-21-c19-selective-apply/results/promoted.json", []) or []

    c17_cv = (c17.get("full_cv") or c17m.get("metrics") or {}).get("cv_accuracy") or c17.get("model", {}).get("cv_accuracy")
    c17_auc = (c17.get("full_cv") or c17m.get("metrics") or {}).get("cv_auc") or c17.get("model", {}).get("cv_auc")

    waves = [
        ("C14", "Фьючерсы + акции", "21614 пар", "~0.72 / 0.79", "34p-*"),
        ("C15", "Бить buy&hold", "21614", "~0.77 / 0.84", "35p-*"),
        ("C16", "ATR стоп/тейк + снять фильтр", "25452", "~0.77 / 0.84", "36p-*"),
        ("C17", "Дивиденды + walk-forward", "25452", "~0.80 / 0.85", "37p-*"),
        ("B0", "Разметка тренд/пила", "6552 enriched", "—", "—"),
        ("C18", "Правка «не входить в пилу» всегда", str(c18.get("n_pairs", "—")),
         f"{(c18.get('model') or {}).get('cv_accuracy', float('nan')):.2f} / {(c18.get('model') or {}).get('cv_auc', float('nan')):.2f}"
         if c18.get("model") else "—", "0"),
        ("C18b", "Правка «отскок в пиле» всегда", str(c18b.get("n_pairs", "—")),
         f"{(c18b.get('model') or {}).get('cv_accuracy', float('nan')):.2f} / {(c18b.get('model') or {}).get('cv_auc', float('nan')):.2f}"
         if c18b.get("model") else "—", "0"),
        ("B0b", "Тюнинг детектора пилы", "26 окон",
         f"chop {(b0b.get('windows_b0b') or {}).get('mean_chop', 0):.2f}", "—"),
        ("C19", "Выборочные правки", str(c19.get("n_pairs", "—")),
         f"{(c19.get('model') or {}).get('cv_accuracy', float('nan')):.2f} / {(c19.get('model') or {}).get('cv_auc', float('nan')):.2f}"
         if c19.get("model") else "—", str(c19.get("n_promoted", 0))),
    ]

    policies = (c19.get("policies") or {})
    sel = policies.get("sel chop&model") or {}
    always = policies.get("always") or {}
    oracle = policies.get("oracle high_chop&better") or {}

    prom_rows = "".join(
        f"<tr><td class='l'>{p['to']}</td><td>{p['kind'].replace('add_','')}</td>"
        f"<td>{p['wins']}</td><td>{p['mean_delta']:.0f}</td><td>{p['mean_delta_pnl_in_chop']:.0f}</td>"
        f"<td class='l'>{', '.join(p.get('slots') or [])}</td></tr>"
        for p in promoted
    ) or "<tr><td colspan=6>нет</td></tr>"

    wave_rows = "".join(
        f"<tr><td>{a}</td><td class='l'>{b}</td><td>{c}</td><td>{d}</td><td>{e}</td></tr>"
        for a, b, c, d, e in waves
    )

    w_v1 = b0b.get("windows_v1") or {}
    w_v2 = b0b.get("windows_b0b") or {}

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<title>AI_algo — бизнес-аналитика</title>
<style>
:root {{
  --bg:#0e141b; --card:#18222d; --line:#2a3744; --text:#e8eef4; --muted:#8b9aab;
  --good:#6dcea4; --bad:#e07a7a; --accent:#7eb6ff;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"IBM Plex Sans",system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.45}}
.wrap{{max-width:1100px;margin:0 auto;padding:32px 20px 64px}}
h1{{font-size:1.75rem;margin:0 0 6px}}
h2{{font-size:1.15rem;margin:28px 0 12px;color:var(--accent)}}
.sub{{color:var(--muted);margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr 1fr}}}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
.k{{font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
.v{{font-size:1.35rem;font-weight:650;margin-top:6px}}
.v.sm{{font-size:1.05rem}}
.good{{color:var(--good)}} .bad{{color:var(--bad)}}
p.lead{{font-size:1.05rem;max-width:62ch}}
table{{width:100%;border-collapse:collapse;background:var(--card);font-size:.82rem;margin-top:8px}}
th,td{{border:1px solid var(--line);padding:8px 10px;text-align:right}}
th,td.l{{text-align:left;color:var(--muted)}}
th{{font-weight:600;color:var(--muted);font-size:.72rem;text-transform:uppercase}}
.note{{color:var(--muted);font-size:.85rem;margin-top:10px}}
.bar{{height:10px;background:#243040;border-radius:6px;overflow:hidden;margin-top:8px}}
.bar>i{{display:block;height:100%;background:linear-gradient(90deg,#3d7ea6,#6dcea4)}}
ul.plain{{margin:8px 0 0;padding-left:1.1rem;color:var(--muted)}}
ul.plain li{{margin:4px 0}}
a{{color:var(--accent)}}
</style>
</head>
<body>
<div class="wrap">
<h1>AI_algo — полная аналитика для бизнеса</h1>
<p class="sub">Обновлено {NOW} · волны до C19 · см. также <code>docs/work/BUSINESS_STATUS.md</code></p>

<p class="lead">
Мы учим не «торговать вместо вас», а <b>правильно советовать правки</b> алго-скриптов:
когда изменение графа помогает, а когда вредит. Главный вывод дня —
правки нужно применять <b>выборочно</b>, а не всегда.
</p>

<div class="grid">
  <div class="card"><div class="k">Качество модели (C19)</div><div class="v">{(c19.get('model') or {}).get('cv_accuracy',0)*100:.0f}% / {(c19.get('model') or {}).get('cv_auc',0):.2f}</div></div>
  <div class="card"><div class="k">Всегда править</div><div class="v bad">{always.get('lift_vs_base',0):+.0f}</div></div>
  <div class="card"><div class="k">Выборочно править</div><div class="v good">{sel.get('lift_vs_base',0):+.0f}</div></div>
  <div class="card"><div class="k">Отобрано в корпус</div><div class="v">{c19.get('n_promoted',0)} × 38p_sel</div></div>
</div>

<h2>1. Вердикт для продукта</h2>
<div class="card">
<ul class="plain">
<li><b>Стало лучше</b> умение выбирать момент для правки (selective lift +{sel.get('lift_vs_base',0):.0f} ≈ oracle +{oracle.get('lift_vs_base',0):.0f}).</li>
<li><b>Не стало</b> доказанным «алго стабильно зарабатывает» — это советчик по изменениям, не готовый робот.</li>
<li><b>В прод Desktop пока не вшиваем</b> (правило §7G) — сначала качество и честные метрики.</li>
<li>Применение правил: только если доля «пилы» на окне ≥ {c19.get('chop_thr',0.38)} и уверенность модели ≥ {c19.get('proba_thr',0.55)} (сейчас срабатывает ~{100*(sel.get('apply_rate') or 0):.0f}% случаев).</li>
</ul>
</div>

<h2>2. Эволюция волн обучения</h2>
<table>
<thead><tr><th>Волна</th><th class="l">Смысл</th><th>Объём</th><th>Качество (acc/auc)</th><th>Промоут</th></tr></thead>
<tbody>{wave_rows}</tbody>
</table>
<p class="note">C17 — лучший «общий» рангер правок на большой выборке. C19 — лучший режим «когда чинить пилу».</p>

<h2>3. Режим рынка (пила vs тренд)</h2>
<div class="grid">
  <div class="card">
    <div class="k">Доля пилы (было → стало)</div>
    <div class="v sm">{w_v1.get('mean_chop',0):.0%} → {w_v2.get('mean_chop',0):.0%}</div>
    <div class="bar"><i style="width:{100*(w_v2.get('mean_chop') or 0):.0f}%"></i></div>
  </div>
  <div class="card">
    <div class="k">Доля тренда</div>
    <div class="v sm">{w_v1.get('mean_trend',0):.0%} → {w_v2.get('mean_trend',0):.0%}</div>
    <div class="bar"><i style="width:{100*(w_v2.get('mean_trend') or 0):.0f}%"></i></div>
  </div>
  <div class="card">
    <div class="k">Переходная зона</div>
    <div class="v sm">{w_v2.get('mean_transition',0):.0%}</div>
    <div class="bar"><i style="width:{100*(w_v2.get('mean_transition') or 0):.0f}%"></i></div>
  </div>
  <div class="card">
    <div class="k">C18 «всегда gate» mean Δ</div>
    <div class="v sm bad">{c18.get('mean_delta',0):+.0f}</div>
  </div>
</div>
<p class="note">Раньше детектор почти всё называл «пилой» (~76%). После настройки — баланс ~37% пила / ~34% тренд / ~27% переход.</p>

<h2>4. Политики применения правок (C19)</h2>
<table>
<thead><tr><th class="l">Политика</th><th>Lift к базе</th><th>% применений</th><th>Средний эффект, когда применили</th></tr></thead>
<tbody>
{''.join(
  f"<tr><td class='l'>{name}</td><td class='{'good' if (s.get('lift_vs_base') or 0)>0 else 'bad'}'>{s.get('lift_vs_base',0):+.1f}</td>"
  f"<td>{100*(s.get('apply_rate') or 0):.1f}%</td><td>{s.get('mean_delta_when_applied',0):+.1f}</td></tr>"
  for name,s in policies.items()
)}
</tbody>
</table>

<h2>5. Отобранные скрипты (38p selective)</h2>
<table>
<thead><tr><th class="l">Файл</th><th>Тип правки</th><th>Побед</th><th>Средний Δ</th><th>Δ в пиле</th><th class="l">Где сработало</th></tr></thead>
<tbody>{prom_rows}</tbody>
</table>

<h2>6. Что смотреть дальше</h2>
<div class="card">
<ul class="plain">
<li>Полная техническая карта волн: <code>artifacts/agent_loop/TRAINING_UNIVERSE_MAP.html</code></li>
<li>Бизнес-текст: <code>docs/work/BUSINESS_STATUS.md</code></li>
<li>Бэклог: <code>docs/work/BACKLOG.md</code> (снимок статусов вверху)</li>
<li>Следующие крупные куски: history-window sweep · combo-правки · Advisor в UI (позже)</li>
</ul>
</div>

</div>
</body>
</html>
"""
    OUT.write_text(html)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

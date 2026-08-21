#!/usr/bin/env python3
"""Fetch MOEX equity dividend calendars (Smart-Lab) into a local cache.

Source: https://smart-lab.ru/q/{SECID}/dividend/
Columns parsed: last_buy_date, registry_close_date, dividend_rub, yield_pct.

Official MOEX ISS /dividends is currently empty — we cache HTML-derived rows
and treat them as provisional until a stable API is back (§7H / P3.7).
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "dividends" / "moex_equities.json"
DEFAULT_SYMBOLS = [
    "SBER",
    "GAZP",
    "LKOH",
    "ROSN",
    "GMKN",
    "NVTK",
    "TATN",
    "PLZL",
    "MGNT",
    "MTSS",
]

UA = {"User-Agent": "AI_algo/1.0 (research; dividend ingest; contact: local)"}


def _parse_date(s: str) -> Optional[str]:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{y}-{mo}-{d}"


def _parse_money(s: str) -> Optional[float]:
    if not s:
        return None
    t = s.replace("\xa0", " ").replace("₽", "").replace("%", "").strip()
    t = t.replace(" ", "").replace(",", ".")
    t = re.sub(r"[^0-9.\-]", "", t)
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def fetch_html(url: str, timeout: float = 25.0) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_smartlab_dividend_page(html: str, secid: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", td)).strip()
            for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        ]
        tds = [t for t in tds if t and t != "&nbsp;"]
        if len(tds) < 5:
            continue
        if tds[0].upper() != secid.upper():
            continue
        last_buy = _parse_date(tds[1])
        registry = _parse_date(tds[2])
        if not last_buy or not registry:
            continue
        div = _parse_money(tds[4])
        yld = _parse_money(tds[6]) if len(tds) > 6 else None
        period = tds[3] if len(tds) > 3 else None
        rows.append(
            {
                "secid": secid.upper(),
                "last_buy_date": last_buy,
                "registry_close_date": registry,
                # Gap / cash charge typically hits after last day to buy.
                "ex_effect_date": last_buy,
                "dividend_rub": div,
                "yield_pct": yld,
                "period_label": period,
                "source": "smart-lab",
            }
        )
    # unique by last_buy + amount
    seen = set()
    uniq = []
    for r in rows:
        k = (r["last_buy_date"], r["dividend_rub"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    uniq.sort(key=lambda x: x["last_buy_date"])
    return uniq


def fetch_symbol(secid: str, sleep_s: float = 0.5) -> List[Dict[str, Any]]:
    url = f"https://smart-lab.ru/q/{secid}/dividend/"
    html = fetch_html(url)
    time.sleep(sleep_s)
    return parse_smartlab_dividend_page(html, secid)


def filter_window(
    events: List[Dict[str, Any]], from_date: Optional[str], to_date: Optional[str]
) -> List[Dict[str, Any]]:
    out = []
    for e in events:
        d = e["ex_effect_date"]
        if from_date and d < from_date:
            continue
        if to_date and d > to_date:
            continue
        out.append(e)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--from", dest="from_date", default=None, help="YYYY-MM-DD inclusive")
    ap.add_argument("--to", dest="to_date", default=None, help="YYYY-MM-DD inclusive")
    args = ap.parse_args()

    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    errors: Dict[str, str] = {}
    for sym in args.symbols:
        try:
            ev = fetch_symbol(sym)
            by_symbol[sym] = filter_window(ev, args.from_date, args.to_date) if (args.from_date or args.to_date) else ev
            print(f"{sym}: {len(by_symbol[sym])} events (raw {len(ev)})", flush=True)
        except Exception as e:  # noqa: BLE001
            errors[sym] = f"{type(e).__name__}: {e}"
            print(f"{sym}: FAIL {errors[sym]}", flush=True)

    payload = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "smart-lab.ru/q/{SECID}/dividend/",
        "note": (
            "Provisional calendar for §7H. ex_effect_date=last_buy_date (cash charge if short "
            "is open through that session). MOEX ISS /dividends empty as of fetch date."
        ),
        "symbols": by_symbol,
        "errors": errors,
        "counts": {k: len(v) for k, v in by_symbol.items()},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print("wrote", args.out, "total", sum(payload["counts"].values()), flush=True)


if __name__ == "__main__":
    main()

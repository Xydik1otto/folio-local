# Tax report rendering: CSV export + printable HTML, from realized-gains data.
from __future__ import annotations

import csv
import io


def tax_csv(report: dict) -> str:
    """Realized gains report as CSV: one row per sale + a total row."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "ticker", "quantity", "proceeds", "cost_basis",
                "gain", "currency"])
    for s in report["sales"]:
        w.writerow([s["date"], s["ticker"], s["quantity"], s["proceeds"],
                    s["cost_basis"], s["gain"], report["currency"]])
    w.writerow(["", f"TOTAL {report['method'].upper()} {report['year']}", "", "", "",
                report["total_gain"], report["currency"]])
    return buf.getvalue()


def tax_html(report: dict) -> str:
    """Printable HTML version of the tax report (UA labels, print CSS)."""
    rows = "".join(
        f"<tr><td>{s['date']}</td><td>{s['ticker']}</td><td>{s['quantity']}</td>"
        f"<td class='num'>{s['proceeds']:.2f}</td>"
        f"<td class='num'>{s['cost_basis']:.2f}</td>"
        f"<td class='num {'gain-pos' if s['gain'] >= 0 else 'gain-neg'}'>"
        f"{s['gain']:.2f}</td></tr>"
        for s in report["sales"])
    if not rows:
        rows = "<tr><td colspan='6' class='empty'>Продажів за рік немає</td></tr>"
    total_cls = "gain-pos" if report["total_gain"] >= 0 else "gain-neg"
    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<title>Податковий звіт {report['year']} ({report['method'].upper()})</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; margin: 2.5cm; color: #111; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 .2rem; }}
  .meta {{ color: #444; font-size: .9rem; margin-bottom: 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #333; padding: .3rem .5rem; font-size: .9rem; }}
  th {{ background: #eee; text-align: left; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .gain-pos {{ color: #0a6b2d; }} .gain-neg {{ color: #a5231b; }}
  .empty {{ text-align: center; color: #555; }}
  tfoot th {{ background: #eee; }}
  @media print {{
    body {{ margin: 1.5cm; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
<h1>Податковий звіт — реалізовані прибутки {report['year']}</h1>
<p class="meta">Метод: {report['method'].upper()} &middot; Валюта: {report['currency']}
 &middot; folio-local</p>
<table>
<thead><tr><th>Дата</th><th>Тікер</th><th>К-ть</th>
<th class="num">Виторг</th><th class="num">Собівартість</th><th class="num">Прибуток</th></tr></thead>
<tbody>{rows}</tbody>
<tfoot><tr><th colspan="5">Разом за {report['year']} ({report['method'].upper()})</th>
<th class="num {total_cls}">{report['total_gain']:.2f} {report['currency']}</th></tr></tfoot>
</table>
<p class="meta no-print">Згенеровано folio-local — дані лише з вашої локальної SQLite.
Друк: Ctrl+P.</p>
</body>
</html>"""

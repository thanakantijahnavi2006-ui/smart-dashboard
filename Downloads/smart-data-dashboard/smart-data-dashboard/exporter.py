"""Excel and HTML downloads."""
import html
import io

import pandas as pd


def to_excel_bytes(df: pd.DataFrame, summary: pd.DataFrame, steps: list, title="Cleaned data") -> bytes:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl", datetime_format="yyyy-mm-dd", date_format="yyyy-mm-dd") as xw:
        df.to_excel(xw, sheet_name=title[:31], index=False)
        summary.to_excel(xw, sheet_name="Column summary", index=False)
        pd.DataFrame({"What was done": steps or ["Nothing to report"]}).to_excel(xw, sheet_name="Cleaning report", index=False)
        for ws in xw.book.worksheets:
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="3F3D9E")
                cell.alignment = Alignment(vertical="center")
            ws.freeze_panes = "A2"
            if ws.dimensions and ws.max_row > 1:
                ws.auto_filter.ref = ws.dimensions
            for i, col in enumerate(ws.columns, start=1):
                width = max((len(str(c.value)) for c in list(col)[:300] if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)
    return buf.getvalue()


def dashboard_html(title: str, kpi_cards: list, insights: list, figs: list) -> str:
    """One self-contained page (charts load Plotly from the internet) that can be e-mailed or opened anywhere."""
    e = html.escape
    cards = "".join(
        f"<div class='card'><div class='lab'>{e(l)}</div><div class='val'>{e(v)}</div>"
        f"<div class='dl'>{e(d or '')}</div></div>" for l, v, d in kpi_cards)
    ins = "".join(f"<li>{e(t).replace('**', '')}</li>" for t in insights)
    charts = []
    for i, f in enumerate(figs):
        charts.append("<div class='chart'>" + f.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False) + "</div>")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f5f6fa;margin:0;padding:24px;color:#1f2937}}
h1{{margin:0 0 16px}} .cards{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px}}
.card{{background:#fff;border-radius:10px;padding:14px 18px;min-width:170px;box-shadow:0 1px 3px #0002}}
.lab{{color:#6b7280;font-size:13px}} .val{{font-size:26px;font-weight:700}} .dl{{font-size:12px;color:#059669}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:14px}}
.chart{{background:#fff;border-radius:10px;padding:8px;box-shadow:0 1px 3px #0002}}
ul{{background:#fff;border-radius:10px;padding:14px 14px 14px 34px;box-shadow:0 1px 3px #0002}}</style></head>
<body><h1>{e(title)}</h1><div class="cards">{cards}</div><ul>{ins}</ul><div class="grid">{''.join(charts)}</div></body></html>"""

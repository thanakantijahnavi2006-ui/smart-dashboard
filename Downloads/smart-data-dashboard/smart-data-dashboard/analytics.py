"""Column roles, aggregation, KPIs and plain-English insights. No Streamlit here."""
import numpy as np
import pandas as pd

from cleaner import is_id_name

AGGS = {"Sum": "sum", "Average": "mean", "Median": "median", "Min": "min", "Max": "max",
        "Count rows": "size", "Count unique": "nunique"}
FREQS = {"Day": "D", "Week": "W", "Month": "M", "Quarter": "Q", "Year": "Y"}
KEY_WORDS = ("sales", "revenue", "amount", "profit", "total", "income", "cost", "value", "qty", "quantity", "units")
NON_ADDITIVE = ("price", "rate", "discount", "margin", "percent", "pct", "age", "rating", "score", "ratio", "average", "avg")


def default_agg(col: str) -> str:
    """Prices, rates, discounts... should be averaged, not summed."""
    return "Average" if any(w in str(col) for w in NON_ADDITIVE) else "Sum"


def _measure_rank(col: str, position: int):
    kw = next((i for i, w in enumerate(KEY_WORDS) if w in col), 99)
    return (default_agg(col) == "Average", kw, position)


def pretty(name) -> str:
    return str(name).replace("_", " ").strip().title()


def profile_columns(df: pd.DataFrame) -> dict:
    """Decide which columns are dates, measures (numbers to add up), dimensions (categories) and ids."""
    n = max(len(df), 1)
    dates, measures, dims, ids, texts = [], [], [], [], []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            dates.append(c)
        elif pd.api.types.is_bool_dtype(s):
            dims.append(c)
        elif pd.api.types.is_numeric_dtype(s):
            if is_id_name(c):
                ids.append(c)
            else:
                measures.append(c)
                if s.nunique() <= 12:
                    dims.append(c)
        else:
            u = s.nunique(dropna=True)
            if is_id_name(c) and u / n > 0.9:
                ids.append(c)
            elif 1 < u <= 200 and u <= 0.6 * n:
                dims.append(c)
            else:
                texts.append(c)
    cols = list(df.columns)
    measures.sort(key=lambda c: _measure_rank(c, cols.index(c)))
    dates.sort(key=lambda c: -df[c].notna().sum())
    return {"dates": dates, "measures": measures, "dims": dims, "ids": ids, "texts": texts}


def column_summary(df: pd.DataFrame) -> pd.DataFrame:
    p = profile_columns(df)
    rows = []
    for c in df.columns:
        role = ("Date" if c in p["dates"] else "Number" if c in p["measures"] else
                "ID" if c in p["ids"] else "Category" if c in p["dims"] else "Text")
        ex = df[c].dropna()
        rows.append({"Column": c, "Detected as": role, "Filled": f"{int(df[c].notna().sum()):,}",
                     "Missing %": round(100 * df[c].isna().mean(), 1), "Unique": int(df[c].nunique()),
                     "Example": "" if ex.empty else str(ex.iloc[0])[:40]})
    return pd.DataFrame(rows)


def dim_options(p: dict) -> dict:
    """label -> (column, frequency or None). Dates can be grouped by day/week/month/quarter/year."""
    opts = {}
    for d in p["dates"]:
        for lab in FREQS:
            opts[f"{pretty(d)} (by {lab})"] = (d, lab)
    for c in p["dims"]:
        opts[pretty(c)] = (c, None)
    return opts


def aggregate(df, x, freq, measure, agg, color=None, top_n=0, sort="High to low"):
    """Group df by x (optionally split by color) and aggregate measure. Returns columns: x, [color], value."""
    cols = {c for c in (x, measure, color) if c is not None and c in df.columns}
    d = df[list(cols)].copy()
    if freq:
        d = d[d[x].notna()]
        d["_x"] = d[x].dt.to_period(FREQS[freq]).dt.to_timestamp()
    elif pd.api.types.is_numeric_dtype(d[x]):
        d = d[d[x].notna()]
        d["_x"] = d[x]
    else:
        d["_x"] = d[x].astype(object).where(d[x].notna(), "(blank)")
    keys = ["_x"]
    if color:
        d["_c"] = d[color].astype(object).where(d[color].notna(), "(blank)").astype(str)
        keys.append("_c")
    if agg == "Count rows" or measure is None:
        g = d.groupby(keys, sort=False).size().rename("value").reset_index()
    else:
        g = d.groupby(keys, sort=False)[measure].agg(AGGS[agg]).rename("value").reset_index()

    additive = agg in ("Sum", "Count rows", "Count unique")
    tot = g.groupby("_x")["value"].sum() if additive else g.groupby("_x")["value"].mean()
    if freq:
        g = g.sort_values("_x")
    else:
        ascending = sort == "Low to high"
        order = tot.sort_values(ascending=ascending)
        if top_n and top_n > 0:
            order = order.head(int(top_n))
        if sort == "A to Z":
            keep = tot.sort_values(ascending=False).head(int(top_n)) if top_n else tot
            order = keep.sort_index()
        rank = {k: i for i, k in enumerate(order.index)}
        g = g[g["_x"].isin(rank)].copy()
        g["_r"] = g["_x"].map(rank)
        g = g.sort_values("_r").drop(columns="_r")
    g["_x"] = g["_x"].astype(str) if (not freq and pd.api.types.is_numeric_dtype(g["_x"])) else g["_x"]
    g = g.rename(columns={"_x": "x", "_c": "color"})
    return g.reset_index(drop=True)


def fmt_number(x, style="International") -> str:
    if x is None or (not isinstance(x, str) and pd.isna(x)):
        return "–"
    ax, sign = abs(float(x)), "-" if float(x) < 0 else ""
    if style.startswith("Indian"):
        if ax >= 1e7:
            return f"{sign}{ax / 1e7:.2f} Cr"
        if ax >= 1e5:
            return f"{sign}{ax / 1e5:.2f} L"
    else:
        if ax >= 1e9:
            return f"{sign}{ax / 1e9:.2f}B"
        if ax >= 1e6:
            return f"{sign}{ax / 1e6:.2f}M"
    if ax >= 1e4:
        return f"{sign}{ax / 1e3:.1f}K"
    return f"{sign}{ax:,.0f}" if ax >= 100 or ax == int(ax) else f"{sign}{ax:,.2f}"


def period_change(df, date_col, measure, agg="Sum"):
    """Latest month vs the month before. Returns (label, value, pct_change or None)."""
    g = aggregate(df, date_col, "Month", measure, agg)
    if len(g) < 2:
        return None
    last, prev = g.iloc[-1], g.iloc[-2]
    pct = None if prev["value"] == 0 else 100 * (last["value"] - prev["value"]) / abs(prev["value"])
    return last["x"].strftime("%b %Y"), float(last["value"]), pct


def kpis(df, p, style="International", max_measures=3):
    """List of (label, value_text, delta_text or None)."""
    cards = [("Rows", f"{len(df):,}", None)]
    date = p["dates"][0] if p["dates"] else None
    for m in p["measures"][:max_measures]:
        agg = default_agg(m)
        value = df[m].sum() if agg == "Sum" else df[m].mean()
        delta = None
        if date:
            ch = period_change(df, date, m, agg)
            if ch and ch[2] is not None:
                delta = f"{ch[2]:+.1f}% vs previous month"
        cards.append((f"{'Total' if agg == 'Sum' else 'Average'} {pretty(m)}", fmt_number(value, style), delta))
    if p["measures"] and default_agg(p["measures"][0]) == "Sum":
        m = p["measures"][0]
        cards.append((f"Average {pretty(m)} per row", fmt_number(df[m].mean(), style), None))
    return cards


def best_dim(p: dict, df: pd.DataFrame, skip=None):
    cands = [c for c in p["dims"] if c != skip and c not in p["measures"] and 3 <= df[c].nunique() <= 25]
    if not cands:
        cands = [c for c in p["dims"] if c != skip and c not in p["measures"]]
    return cands[0] if cands else None


def auto_specs(df, p) -> list:
    """A sensible starter dashboard: dicts the chart builder understands."""
    specs = []
    m = p["measures"][0] if p["measures"] else None
    m2 = p["measures"][1] if len(p["measures"]) > 1 else None
    d = p["dates"][0] if p["dates"] else None
    c1 = best_dim(p, df)
    c2 = best_dim(p, df, skip=c1)
    freq = "Month"
    if d is not None:
        span = (df[d].max() - df[d].min()).days if df[d].notna().any() else 0
        freq = "Day" if span <= 60 else "Week" if span <= 180 else "Month"
    agg = default_agg(m) if m else "Count rows"
    if d is not None:
        specs.append({"type": "Line", "x": f"{pretty(d)} (by {freq})", "measure": m, "agg": agg, "color": None, "top_n": 0, "sort": "High to low"})
    if c1:
        specs.append({"type": "Bar", "x": pretty(c1), "measure": m, "agg": agg, "color": None, "top_n": 10, "sort": "High to low"})
    if c2:
        specs.append({"type": "Donut", "x": pretty(c2), "measure": m, "agg": agg, "color": None, "top_n": 8, "sort": "High to low"})
    if m2 and c1:
        specs.append({"type": "Horizontal bar", "x": pretty(c1), "measure": m2, "agg": default_agg(m2), "color": None, "top_n": 10, "sort": "High to low"})
    elif m2 and d is not None:
        specs.append({"type": "Area", "x": f"{pretty(d)} (by {freq})", "measure": m2, "agg": default_agg(m2), "color": None, "top_n": 0, "sort": "High to low"})
    if m:
        specs.append({"type": "Histogram", "x": None, "measure": m, "agg": "Sum", "color": None, "top_n": 0, "sort": "High to low"})
    return specs[:6]


def auto_insights(df, p, style="International") -> list:
    out = []
    if not p["measures"]:
        return [f"The table has {len(df):,} rows. Add a numeric column to unlock totals and trends."]
    m = p["measures"][0]
    agg = default_agg(m)
    nm = pretty(m)
    if agg == "Sum":
        out.append(f"Total {nm} is **{fmt_number(df[m].sum(), style)}** across {len(df):,} rows "
                   f"(average {fmt_number(df[m].mean(), style)} per row).")
    else:
        out.append(f"Average {nm} is **{fmt_number(df[m].mean(), style)}** across {len(df):,} rows.")
    c1 = best_dim(p, df)
    if c1 and agg == "Sum":
        g = aggregate(df, c1, None, m, "Sum")
        tot = g["value"].sum()
        if len(g) >= 2 and tot:
            top, low = g.iloc[0], g.iloc[-1]
            out.append(f"**{top['x']}** leads {pretty(c1)} with {fmt_number(top['value'], style)} "
                       f"({100 * top['value'] / tot:.0f}% of {nm}); **{low['x']}** is lowest at {fmt_number(low['value'], style)}.")
    if p["dates"] and agg == "Sum":
        d = p["dates"][0]
        g = aggregate(df, d, "Month", m, "Sum")
        if len(g) >= 3:
            best = g.loc[g["value"].idxmax()]
            out.append(f"Best month for {nm} was **{best['x'].strftime('%b %Y')}** ({fmt_number(best['value'], style)}).")
            ch = period_change(df, d, m)
            if ch and ch[2] is not None:
                word = "up" if ch[2] >= 0 else "down"
                out.append(f"The latest month ({ch[0]}) is {word} **{abs(ch[2]):.1f}%** compared with the month before.")
    return out


def default_filter_cols(df, p, limit=3):
    """Sensible starting filters: short category columns such as Region or Category."""
    cands = [c for c in p["dims"] if c not in p["measures"] and c != "source_sheet" and 2 <= df[c].nunique() <= 12]
    return cands[:limit]

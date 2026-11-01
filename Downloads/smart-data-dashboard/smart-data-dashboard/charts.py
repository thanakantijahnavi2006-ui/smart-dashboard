"""Turns a chart 'spec' (what the user picked) into a Plotly figure + the numbers behind it."""
import pandas as pd
import plotly.express as px

import analytics
from analytics import pretty

CHART_TYPES = ["Bar", "Horizontal bar", "Line", "Area", "Pie", "Donut", "Scatter", "Histogram", "Box", "Table"]
PALETTE = ["#4F46E5", "#06B6D4", "#F59E0B", "#10B981", "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6", "#84CC16", "#F97316"]


def y_label(spec) -> str:
    if spec.get("agg") == "Count rows" or not spec.get("measure"):
        return "Number of rows"
    return f"{spec['agg']} of {pretty(spec['measure'])}"


def default_title(spec) -> str:
    t = spec["type"]
    if t == "Scatter":
        return f"{pretty(spec['y_measure'])} vs {pretty(spec['x_measure'])}"
    if t == "Histogram":
        return f"Distribution of {pretty(spec['measure'])}"
    if t == "Box":
        return f"{pretty(spec['measure'])} by {spec['x']}"
    return f"{y_label(spec)} by {spec['x']}"


def _style(fig, title, height=380):
    fig.update_layout(template="plotly_white", title=dict(text=title, font=dict(size=16)), height=height,
                      margin=dict(l=10, r=10, t=55, b=10), legend_title_text="", colorway=PALETTE, font=dict(size=12))
    return fig


def build_figure(df: pd.DataFrame, spec: dict, dims: dict):
    """Return (figure or None, table). Table-type charts return (None, table)."""
    t = spec["type"]
    title = spec.get("title") or default_title(spec)

    if t == "Histogram":
        m = spec["measure"]
        d = df[[m]].dropna()
        fig = px.histogram(d, x=m, nbins=int(spec.get("bins", 30)), labels={m: pretty(m)}, color_discrete_sequence=PALETTE)
        fig.update_layout(yaxis_title="Number of rows", bargap=0.05)
        table = d[m].describe().round(2).reset_index()
        table.columns = ["statistic", pretty(m)]
        return _style(fig, title), table

    if t == "Scatter":
        xm, ym, color = spec["x_measure"], spec["y_measure"], spec.get("color")
        cols = [xm, ym] + ([color] if color and color not in (xm, ym) else [])
        d = df[cols].dropna(subset=[xm, ym]).copy()
        if len(d) > 5000:
            d = d.sample(5000, random_state=1)
        if color and color in d.columns:
            d[color] = d[color].astype(str)
        labels = {xm: pretty(xm), ym: pretty(ym)}
        if color and color in d.columns:
            labels[color] = pretty(color)
        fig = px.scatter(d, x=xm, y=ym, color=color if color in d.columns else None, opacity=0.7,
                         labels=labels, color_discrete_sequence=PALETTE)
        return _style(fig, title), d.head(200)

    xcol, freq = dims[spec["x"]]

    if t == "Box":
        m = spec["measure"]
        d = df[[xcol, m]].dropna(subset=[m]).copy()
        d[xcol] = d[xcol].astype(object).where(d[xcol].notna(), "(blank)").astype(str)
        keep = d[xcol].value_counts().head(20).index
        d = d[d[xcol].isin(keep)]
        fig = px.box(d, x=xcol, y=m, labels={xcol: pretty(xcol), m: pretty(m)}, color_discrete_sequence=PALETTE)
        fig.update_xaxes(type="category")
        table = d.groupby(xcol)[m].describe().round(2).reset_index()
        return _style(fig, title), table

    color = spec.get("color")
    if color and color == xcol and not freq:
        color = None
    g = analytics.aggregate(df, xcol, freq, spec.get("measure"), spec["agg"], color=color,
                            top_n=int(spec.get("top_n") or 0), sort=spec.get("sort", "High to low"))
    xl, yl = spec["x"], y_label(spec)
    cl = pretty(color) if color else None
    if cl in (xl, yl):
        cl = f"{cl} (split)"
    g = g.rename(columns={"x": xl, "value": yl, **({"color": cl} if color else {})})

    if t == "Table":
        table = g.pivot_table(index=xl, columns=cl, values=yl, aggfunc="sum").reset_index() if color else g
        return None, table
    if t in ("Pie", "Donut"):
        fig = px.pie(g, names=xl, values=yl, hole=0.5 if t == "Donut" else 0, color_discrete_sequence=PALETTE)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        return _style(fig, title), g
    if t == "Bar":
        fig = px.bar(g, x=xl, y=yl, color=cl, barmode="stack", text_auto=".2s", color_discrete_sequence=PALETTE)
        if not freq:
            fig.update_xaxes(type="category")
    elif t == "Horizontal bar":
        fig = px.bar(g, x=yl, y=xl, color=cl, orientation="h", text_auto=".2s", color_discrete_sequence=PALETTE)
        if not freq:
            fig.update_yaxes(type="category", autorange="reversed")
    elif t == "Line":
        fig = px.line(g, x=xl, y=yl, color=cl, markers=True, color_discrete_sequence=PALETTE)
        if not freq:
            fig.update_xaxes(type="category")
    elif t == "Area":
        fig = px.area(g, x=xl, y=yl, color=cl, color_discrete_sequence=PALETTE)
        if not freq:
            fig.update_xaxes(type="category")
    else:
        raise ValueError(f"Unknown chart type: {t}")
    return _style(fig, title), g


def auto_chart(df: pd.DataFrame):
    """Quick chart for a free-form query result (first column = labels, other numeric columns = values)."""
    if df.shape[0] < 2 or df.shape[1] < 2:
        return None
    x = df.columns[0]
    y = [c for c in df.columns[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not y:
        return None
    d = df.head(40)
    if any(k in str(x).lower() for k in ("date", "month", "year", "quarter", "week", "day")):
        fig = px.line(d, x=x, y=y, markers=True, color_discrete_sequence=PALETTE)
    else:
        fig = px.bar(d, x=x, y=y, barmode="group", color_discrete_sequence=PALETTE)
    fig.update_xaxes(type="category")
    return _style(fig, "", 340)

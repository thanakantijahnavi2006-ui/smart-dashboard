"""
Smart Data Dashboard
Upload raw Excel/CSV  ->  auto-clean  ->  sort & filter  ->  dashboard you control  ->  download / ask questions.
Run:  streamlit run app.py   (or double-click run.bat)
"""
import os

import pandas as pd
import streamlit as st

import ai_sql
import analytics
import charts
import cleaner
import exporter
from analytics import AGGS, pretty

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(APP_DIR, "sample_data", "messy_sales_sample.xlsx")

st.set_page_config(page_title="Smart Data Dashboard", page_icon="📊", layout="wide")


# ---------------------------------------------------------------- cached loaders
@st.cache_data(show_spinner="Reading file...")
def load_raw(file_bytes: bytes, filename: str):
    return cleaner.read_raw(file_bytes, filename)


@st.cache_data(show_spinner="Cleaning data...")
def clean_cached(file_bytes: bytes, filename: str, sheet: str, opts: dict):
    return cleaner.clean_sheet(load_raw(file_bytes, filename)[sheet], opts)


@st.cache_data(show_spinner=False)
def make_xlsx(out: pd.DataFrame, steps: list):
    return exporter.to_excel_bytes(out, analytics.column_summary(out), steps)


def label_of(c):
    return c if c == "(none)" else pretty(c)


# ---------------------------------------------------------------- sidebar: upload + cleaning options
with st.sidebar:
    st.title("📊 Smart Data Dashboard")
    st.subheader("1 · Upload your data")
    uploaded = st.file_uploader("Raw Excel or CSV files", type=["xlsx", "xlsm", "xls", "csv"],
                                accept_multiple_files=True,
                                help="Upload one or many files. Files/sheets with the same columns are stacked together.")
    if st.button("Try the sample messy Excel"):
        st.session_state["use_sample"] = True
    with st.expander("⚙️ Cleaning options"):
        dayfirst = st.checkbox("Dates are day-first (DD/MM/YYYY)", True)
        drop_dups = st.checkbox("Remove duplicate rows", True)
        drop_totals = st.checkbox("Remove Total / Subtotal rows", True)
        title_case = st.checkbox("Tidy capitalisation (north → North)", True)
        fill_down = st.checkbox("Fill blank cells downward (merged cells)", False)
        miss_num = st.selectbox("Missing numbers", ["Leave blank", "Fill with 0", "Fill with median", "Fill with mean", "Drop rows"])
        miss_txt = st.selectbox("Missing text", ["Leave blank", "Fill with 'Unknown'", "Drop rows"])
        rm_out = st.checkbox("Remove extreme outliers", False)
        header_row = st.number_input("Header row number (0 = detect automatically)", 0, 200, 0)
    style = st.selectbox("Number style", ["International (K, M, B)", "Indian (Lakh, Crore)"])

opts = {"dayfirst": dayfirst, "drop_duplicates": drop_dups, "drop_total_rows": drop_totals, "title_case": title_case,
        "fill_down": fill_down, "missing_numbers": miss_num, "missing_text": miss_txt,
        "remove_outliers": rm_out, "header_row": int(header_row)}

inputs = []
if uploaded:
    inputs = [(f.name, f.getvalue()) for f in uploaded]
elif st.session_state.get("use_sample") and os.path.exists(SAMPLE_PATH):
    with open(SAMPLE_PATH, "rb") as fh:
        inputs = [("messy_sales_sample.xlsx", fh.read())]

tab_clean, tab_data, tab_dash, tab_ai, tab_export = st.tabs(
    ["1 · Upload & Clean", "2 · Sort & Explore", "3 · Dashboard", "4 · Ask questions (AI)", "5 · Download"])

df = None
all_steps = []
dashboard_html = None
view = None

# ================================================================ TAB 1: upload & clean
with tab_clean:
    if not inputs:
        st.header("Turn raw Excel sheets into a clean dashboard")
        st.markdown("""
**How it works**
1. **Upload** your raw Excel or CSV file(s) in the sidebar. They can be messy.
2. The app **cleans and arranges** the data: finds the real header, fixes numbers, dates and spelling, removes duplicates and total rows.
3. **Sort, search and filter** the table.
4. Pick the numbers and charts you need, or use the **auto dashboard**.
5. **Download** the clean Excel or the dashboard as a web page.

No file handy? Click **Try the sample messy Excel** in the sidebar.
""")
        if os.path.exists(SAMPLE_PATH):
            with open(SAMPLE_PATH, "rb") as fh:
                st.download_button("Download the sample raw file (to see what 'messy' looks like)", fh.read(),
                                   file_name="messy_sales_sample.xlsx")
    else:
        catalog = {}
        for fname, fbytes in inputs:
            try:
                sheets = load_raw(fbytes, fname)
            except Exception as e:
                st.error(f"{fname}: {e}")
                continue
            for sname, raw in sheets.items():
                if raw.dropna(how="all").shape[0] >= 2:
                    catalog[f"{fname} › {sname}"] = (fname, fbytes, sname)
        if not catalog:
            st.error("No sheet with data was found in the uploaded file(s).")
        else:
            chosen = st.multiselect("Sheets to include (sheets with the same columns are stacked into one table)",
                                    list(catalog), default=list(catalog))
            frames, reports = {}, {}
            for lab in chosen:
                fname, fbytes, sname = catalog[lab]
                try:
                    frames[lab], reports[lab] = clean_cached(fbytes, fname, sname, opts)
                except Exception as e:
                    st.warning(f"Could not clean '{lab}': {e}")
            if frames:
                df, notes = cleaner.combine_frames(frames, drop_dups)
                raw_rows = sum(r["rows_raw"] for r in reports.values())
                completeness = sum(r["completeness"] * r["rows_clean"] for r in reports.values()) / max(sum(r["rows_clean"] for r in reports.values()), 1)
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Rows in raw file", f"{raw_rows:,}")
                k2.metric("Rows after cleaning", f"{len(df):,}")
                k3.metric("Columns", f"{df.shape[1]}")
                k4.metric("Data completeness", f"{completeness:.1f}%")
                for n in notes:
                    st.info(n)
                for lab, r in reports.items():
                    all_steps += [f"[{lab}] {s}" for s in r["steps"]]
                with st.expander("✅ What the cleaner did", expanded=True):
                    for lab, r in reports.items():
                        if len(reports) > 1:
                            st.markdown(f"**{lab}**")
                        for s in r["steps"]:
                            st.markdown(f"- {s}")
                first = catalog[chosen[0]]
                left, right = st.columns(2)
                with left:
                    st.markdown("**Before: the raw sheet (first rows)**")
                    st.dataframe(load_raw(first[1], first[0])[first[2]].head(12).fillna("").astype(str))
                with right:
                    st.markdown("**After: clean, analysis-ready table**")
                    st.dataframe(df.head(12))
                with st.expander("Column types the app detected"):
                    st.dataframe(analytics.column_summary(df))
                st.success("Your data is ready. Open the Sort & Explore and Dashboard tabs.")

if df is None:
    for t in (tab_data, tab_dash, tab_ai, tab_export):
        with t:
            st.info("Upload a file in the sidebar first, or click 'Try the sample messy Excel'.")
    st.stop()

# ---------------------------------------------------------------- sidebar: filters
p = analytics.profile_columns(df)
dims_map = analytics.dim_options(p)
df_f = df
with st.sidebar:
    st.subheader("2 · Filter the data")
    if p["dates"]:
        dcol = st.selectbox("Date column", p["dates"], format_func=pretty)
        dvals = df[dcol].dropna()
        if not dvals.empty:
            lo, hi = dvals.min().date(), dvals.max().date()
            rng = st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
            if isinstance(rng, (list, tuple)) and len(rng) == 2 and (rng[0], rng[1]) != (lo, hi):
                df_f = df_f[(df_f[dcol] >= pd.Timestamp(rng[0])) & (df_f[dcol] < pd.Timestamp(rng[1]) + pd.Timedelta(days=1))]
    cat_cols = [c for c in p["dims"] if c not in p["measures"]]
    pick = st.multiselect("Filter by", cat_cols, default=analytics.default_filter_cols(df, p), format_func=pretty)
    for c in pick:
        options = sorted(df[c].dropna().unique().tolist(), key=str)
        sel = st.multiselect(pretty(c), options, help="Leave empty to include everything")
        if sel:
            df_f = df_f[df_f[c].isin(sel)]
    if p["measures"]:
        mcol = st.selectbox("Number range filter (optional)", ["(none)"] + p["measures"], format_func=label_of)
        if mcol != "(none)":
            lo_n, hi_n = float(df[mcol].min()), float(df[mcol].max())
            if lo_n < hi_n:
                a, b = st.slider(pretty(mcol), lo_n, hi_n, (lo_n, hi_n))
                if (a, b) != (lo_n, hi_n):
                    df_f = df_f[df_f[mcol].between(a, b)]
    st.caption(f"Showing {len(df_f):,} of {len(df):,} rows")

if df_f.empty:
    for t in (tab_data, tab_dash, tab_ai, tab_export):
        with t:
            st.warning("No rows match your filters. Widen the filters in the sidebar.")
    st.stop()

# ================================================================ TAB 2: sort & explore
with tab_data:
    st.subheader("Your clean data: sort, search, rearrange")
    cols_all = list(df_f.columns)
    s1, s2, s3, s4 = st.columns([2, 1.3, 2, 1.3])
    with s1:
        sort1 = st.selectbox("Sort by", ["(original order)"] + cols_all, format_func=label_of)
    with s2:
        order1 = st.radio("Order", ["Ascending", "Descending"], horizontal=True, key="order1")
    with s3:
        sort2 = st.selectbox("Then by (optional)", ["(none)"] + cols_all, format_func=label_of)
    with s4:
        order2 = st.radio("Order ", ["Ascending", "Descending"], horizontal=True, key="order2")
    shown = st.multiselect("Columns to show (the order you pick is the order shown)", cols_all, default=cols_all, format_func=pretty)
    query = st.text_input("Search any text in the table", placeholder="e.g. laptop")

    view = df_f
    if query.strip():
        mask = pd.Series(False, index=view.index)
        for c in view.columns:
            mask |= view[c].astype(str).str.contains(query.strip(), case=False, na=False, regex=False)
        view = view[mask]
    sort_cols, asc = [], []
    if sort1 != "(original order)":
        sort_cols.append(sort1)
        asc.append(order1 == "Ascending")
    if sort2 != "(none)" and sort2 != sort1:
        sort_cols.append(sort2)
        asc.append(order2 == "Ascending")
    if sort_cols:
        view = view.sort_values(sort_cols, ascending=asc, kind="mergesort", na_position="last")
    view = view[shown or cols_all]
    st.caption(f"{len(view):,} rows × {view.shape[1]} columns")
    st.dataframe(view, height=480)

# ================================================================ TAB 3: dashboard
def chart_controls(i, d, p, dims_map):
    """The settings for chart number i. Returns a spec dict."""
    k = lambda name: f"ch{i}_{name}"
    measures = p["measures"]
    dim_labels = list(dims_map)
    cat_map = {pretty(c): c for c in p["dims"]}
    plain_dims = [lab for lab, (_, f) in dims_map.items() if f is None]

    def idx(options, value):
        return options.index(value) if value in options else 0

    c1, c2, c3 = st.columns([1.2, 2, 2])
    with c1:
        t = st.selectbox("Chart type", charts.CHART_TYPES, index=idx(charts.CHART_TYPES, d.get("type", "Bar")), key=k("type"))
    spec = {"type": t}
    with c3:
        spec["title"] = st.text_input("Title (optional)", key=k("title"))

    if t == "Scatter":
        if len(measures) < 2:
            spec["invalid"] = "A scatter chart needs at least two number columns."
            return spec
        with c2:
            spec["x_measure"] = st.selectbox("X axis (number)", measures, format_func=pretty, key=k("xm"))
        r1, r2 = st.columns(2)
        with r1:
            spec["y_measure"] = st.selectbox("Y axis (number)", measures, index=1, format_func=pretty, key=k("ym"))
        with r2:
            col = st.selectbox("Colour by (optional)", ["(none)"] + list(cat_map), key=k("color"))
            spec["color"] = cat_map.get(col)
        return spec

    if t == "Histogram":
        if not measures:
            spec["invalid"] = "A histogram needs a number column."
            return spec
        with c2:
            spec["measure"] = st.selectbox("Number to analyse", measures, index=idx(measures, d.get("measure")), format_func=pretty, key=k("m"))
        spec["bins"] = st.slider("Number of bars", 5, 100, 30, key=k("bins"))
        return spec

    if t == "Box":
        if not measures or not plain_dims:
            spec["invalid"] = "A box plot needs a number column and a category column."
            return spec
        with c2:
            spec["x"] = st.selectbox("Group by", plain_dims, key=k("x"))
        spec["measure"] = st.selectbox("Number to analyse", measures, format_func=pretty, key=k("m"))
        return spec

    if not dim_labels:
        spec["invalid"] = "No category or date columns were found to group by."
        return spec
    with c2:
        spec["x"] = st.selectbox("Group by (X axis)", dim_labels, index=idx(dim_labels, d.get("x")), key=k("x"))
    r1, r2, r3 = st.columns(3)
    agg_options = list(AGGS) if measures else ["Count rows"]
    with r2:
        spec["agg"] = st.selectbox("Calculate", agg_options, index=idx(agg_options, d.get("agg", "Sum")), key=k("agg"))
    with r1:
        if spec["agg"] == "Count rows":
            spec["measure"] = None
            st.caption("Counting rows")
        else:
            m_opts = list(df.columns) if spec["agg"] == "Count unique" else measures
            spec["measure"] = st.selectbox("Number column", m_opts, index=idx(m_opts, d.get("measure")), format_func=pretty, key=k("m") + spec["agg"])
    with r3:
        xcol = dims_map[spec["x"]][0]
        color_opts = ["(none)"] + [lab for lab, c in cat_map.items() if c != xcol]
        col = st.selectbox("Split by (optional)", color_opts, key=k("color"))
        spec["color"] = cat_map.get(col)
    if t in ("Bar", "Horizontal bar", "Pie", "Donut", "Table") and not dims_map[spec["x"]][1]:
        q1, q2 = st.columns(2)
        with q1:
            spec["top_n"] = st.number_input("Show top N (0 = all)", 0, 500, int(d.get("top_n", 10)), key=k("topn"))
        with q2:
            sorts = ["High to low", "Low to high", "A to Z"]
            spec["sort"] = st.selectbox("Sort", sorts, index=idx(sorts, d.get("sort")), key=k("sort"))
    return spec


with tab_dash:
    st.subheader("Key numbers")
    cards = analytics.kpis(df_f, p, style)
    for col, (lab, val, delta) in zip(st.columns(len(cards)), cards):
        with col:
            with st.container(border=True):
                st.metric(lab, val, delta)

    insights = analytics.auto_insights(df_f, p, style)
    with st.container(border=True):
        st.markdown("**💡 What the data says**")
        for line in insights:
            st.markdown(f"- {line}")

    mode = st.radio("Dashboard type", ["Auto dashboard", "Build my own dashboard"], horizontal=True)
    auto = analytics.auto_specs(df, p)
    if mode == "Auto dashboard":
        specs = auto
    else:
        n = int(st.number_input("How many charts?", 1, 8, max(len(auto), 2)))
        specs = []
        with st.expander("⚙️ Chart settings: choose exactly what you want to see", expanded=True):
            for i in range(n):
                st.markdown(f"**Chart {i + 1}**")
                default = auto[i] if i < len(auto) else {}
                specs.append(chart_controls(i, default, p, dims_map))
                st.divider()

    figs = []
    if not specs:
        st.info("Nothing to chart yet. Switch to 'Build my own dashboard'.")
    grid = st.columns(2)
    for i, spec in enumerate(specs):
        with grid[i % 2]:
            with st.container(border=True):
                if spec.get("invalid"):
                    st.info(spec["invalid"])
                    continue
                try:
                    fig, table = charts.build_figure(df_f, spec, dims_map)
                    if fig is None:
                        st.markdown(f"**{spec.get('title') or charts.default_title(spec)}**")
                        st.dataframe(table)
                    else:
                        st.plotly_chart(fig, key=f"fig_{i}")
                        figs.append(fig)
                        with st.expander("Show the numbers behind this chart"):
                            st.dataframe(table)
                except Exception as e:
                    st.warning(f"Chart {i + 1} could not be drawn: {e}")

    with st.expander("🧮 Pivot table (rows × columns)"):
        if p["measures"]:
            mm = st.selectbox("Values", p["measures"], format_func=pretty, key="pv_val")
            cats = [c for c in p["dims"] if c not in p["measures"]] or p["dims"]
            dim_cols = [c for c in cats if c != mm]
        else:
            mm, dim_cols = None, []
        if mm and dim_cols:
            r = st.multiselect("Rows", dim_cols, default=dim_cols[:1], format_func=pretty, key="pv_rows")
            cc = st.selectbox("Columns (optional)", ["(none)"] + [c for c in dim_cols if c not in r], format_func=label_of, key="pv_cols")
            ag = st.selectbox("Summarise as", ["Sum", "Average", "Median", "Min", "Max", "Count rows"], key="pv_agg")
            if r:
                try:
                    func = {"Sum": "sum", "Average": "mean", "Median": "median", "Min": "min", "Max": "max", "Count rows": "count"}[ag]
                    pv = pd.pivot_table(df_f, index=r, columns=None if cc == "(none)" else cc, values=mm,
                                        aggfunc=func, margins=True, margins_name="Total", fill_value=0)
                    st.dataframe(pv.round(2))
                except Exception as e:
                    st.warning(f"Pivot could not be built: {e}")
        else:
            st.info("A pivot table needs at least one category column and one number column.")

    if figs:
        dashboard_html = exporter.dashboard_html("Dashboard", cards, insights, figs)

# ================================================================ TAB 4: AI questions
with tab_ai:
    st.subheader("Ask questions about your data in plain English")
    st.caption("The AI writes a safe, read-only SQL query on the rows currently shown (after your sidebar filters), "
               "runs it and explains the result. Needs an Anthropic API key. Every other tab works without one.")
    api_key = st.text_input("Anthropic API key", type="password", value=os.getenv("ANTHROPIC_API_KEY", ""))
    st.session_state.setdefault("ai_history", [])
    with st.form("ask_form"):
        q = st.text_input("Your question", placeholder="e.g. Which product category made the most profit in March?")
        go = st.form_submit_button("Ask")
    if go and q.strip():
        if not api_key:
            st.warning("Paste your API key above first.")
        else:
            with st.spinner("Thinking..."):
                try:
                    sql, res, insight = ai_sql.answer(q.strip(), df_f, api_key)
                    st.session_state["ai_history"].insert(0, {"q": q.strip(), "sql": sql, "df": res, "insight": insight})
                except Exception as e:
                    st.error(str(e))
    for j, h in enumerate(st.session_state["ai_history"]):
        with st.container(border=True):
            st.markdown(f"**🧑 {h['q']}**")
            st.markdown(h["insight"])
            fig = charts.auto_chart(h["df"])
            if fig is not None:
                st.plotly_chart(fig, key=f"ai_{j}")
            with st.expander("Show SQL and data"):
                st.code(h["sql"], language="sql")
                st.dataframe(h["df"])

# ================================================================ TAB 5: download
with tab_export:
    st.subheader("Download your results")
    scope = st.radio("What to download", ["Everything (cleaned)", "Only what I see now (filters, sort, columns)"], horizontal=True)
    out = df if scope.startswith("Everything") else view
    st.caption(f"{len(out):,} rows × {out.shape[1]} columns")
    st.download_button("⬇️ Excel (.xlsx): data + column summary + cleaning report", make_xlsx(out, all_steps),
                       file_name="cleaned_data.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("⬇️ CSV", out.to_csv(index=False).encode("utf-8-sig"), file_name="cleaned_data.csv", mime="text/csv")
    if dashboard_html:
        st.download_button("⬇️ Dashboard as a web page (.html)", dashboard_html.encode("utf-8"),
                           file_name="dashboard.html", mime="text/html")
        st.caption("Open it in any browser or e-mail it. The charts need an internet connection to draw.")
    else:
        st.caption("Open the Dashboard tab first to enable the dashboard download.")

"""
Raw Excel/CSV  ->  clean, analysis-ready table.
Pure pandas (no Streamlit), so it can be tested on its own.

What it fixes automatically:
  * title rows / blank rows above the real header      * messy column names
  * empty rows and columns                              * stray spaces, N/A / null / "-" placeholders
  * numbers stored as text ("₹12,500", "(300)", "10%")  * dates in mixed formats
  * inconsistent text ("north", "NORTH ", "North")      * duplicate rows
  * "Total" / "Subtotal" rows pasted into the data      * missing values (your choice)
"""
import datetime as dt
import io
import re
import warnings
from collections import Counter

import numpy as np
import pandas as pd

DEFAULTS = {
    "dayfirst": True,                  # 05/03/2025 = 5 March (India/UK style)
    "drop_duplicates": True,
    "drop_total_rows": True,
    "title_case": True,
    "fill_down": False,                # for merged cells
    "missing_numbers": "Leave blank",  # Leave blank | Fill with 0 | Fill with median | Fill with mean | Drop rows
    "missing_text": "Leave blank",     # Leave blank | Fill with 'Unknown' | Drop rows
    "remove_outliers": False,
    "header_row": 0,                   # 0 = detect automatically, else the row number (counting non-blank rows)
}

NA_TOKENS = {"", "nan", "none", "null", "n/a", "na", "#n/a", "#na", "-", "--", "?", "nil", "missing", "#value!", "#div/0!"}
ID_TOKENS = {"id", "code", "phone", "mobile", "contact", "zip", "pin", "pincode", "sku", "ref", "uuid", "no", "num", "number", "gstin"}
TOTAL_RE = re.compile(r"^(grand\s*)?(sub\s*)?totals?$", re.I)
DATE_RE = re.compile(
    r"^\s*(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}"
    r"|\d{1,2}[-/ .]?[A-Za-z]{3,9}[-/ ,.]*\d{2,4}"
    r"|[A-Za-z]{3,9}[ -]\d{1,2}[, -]+\d{2,4})"
    r"(\s+\d{1,2}:\d{2}(:\d{2})?(\s*[APap][Mm])?)?\s*$"
)


def is_id_name(name: str) -> bool:
    return str(name).split("_")[-1] in ID_TOKENS


# ----------------------------------------------------------------------------- reading
def read_raw(file_bytes: bytes, filename: str) -> dict:
    """Return {sheet_name: DataFrame} with NO header applied (we find the header ourselves)."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, header=None)
        return {str(k): v for k, v in sheets.items()}
    if not file_bytes.strip():
        raise ValueError("The file is empty.")
    last_err = None
    for enc in ("utf-8-sig", "latin-1"):
        for sep in (None, ","):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), header=None, encoding=enc, sep=sep,
                                 engine="python", on_bad_lines="skip", dtype=str)
                return {"Sheet1": df}
            except Exception as e:  # try the next delimiter / encoding
                last_err = e
    raise ValueError(f"This does not look like a valid CSV/Excel file ({last_err}).")


# ----------------------------------------------------------------------------- helpers
def _to_number(v):
    """Turn '₹12,500', '(300)', '10%', 'Rs. 99' into a float. Returns None if it is not a number."""
    if isinstance(v, (bool, np.bool_)):
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        return None if pd.isna(v) else float(v)
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = re.sub(r"^(rs\.?|inr|usd|eur|gbp)\s*", "", s, flags=re.I)
    s = re.sub(r"[₹$€£¥%,\s]", "", s)
    if not re.fullmatch(r"[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?", s, flags=re.I):
        return None
    x = float(s)
    return -x if neg else x


def _is_number_like(v) -> bool:
    return _to_number(v) is not None


def _clean_cell(v):
    if isinstance(v, str):
        v = re.sub(r"\s+", " ", v.replace("\u00a0", " ")).strip()
        if v.lower() in NA_TOKENS:
            return np.nan
    return v


def clean_names(values) -> list:
    names, seen = [], {}
    for i, v in enumerate(values):
        s = "" if (not isinstance(v, str) and pd.isna(v)) else str(v)
        s = re.sub(r"[\W_]+", "_", s.strip().lower()).strip("_")
        if not s:
            s = f"column_{i + 1}"
        if s[0].isdigit():
            s = "col_" + s
        base = s
        if base in seen:
            seen[base] += 1
            s = f"{base}_{seen[base]}"
        else:
            seen[base] = 1
        names.append(s)
    return names


def detect_header_row(raw: pd.DataFrame, max_scan: int = 30) -> int:
    """Find the row that looks like column titles: mostly text, all different, nearly full width."""
    width = int(raw.notna().any(axis=0).sum()) or 1
    best_i, best_score = 0, -1.0
    for i in range(min(max_scan, len(raw) - 1)):
        vals = [v for v in raw.iloc[i].tolist() if not (not isinstance(v, str) and pd.isna(v)) and str(v).strip() != ""]
        if len(vals) < max(2, int(0.5 * width)):
            continue
        text_ratio = sum(isinstance(v, str) and not _is_number_like(v) for v in vals) / len(vals)
        unique_ratio = len({str(v).strip().lower() for v in vals}) / len(vals)
        score = 0.6 * text_ratio + 0.2 * unique_ratio + 0.2 * min(len(vals) / width, 1.0)
        if score >= 0.95:
            return i
        if score > best_score:
            best_i, best_score = i, score
    return best_i


ISO_RE = re.compile(r"^\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


def _parse_dates(s: pd.Series, dayfirst: bool) -> pd.Series:
    """Year-first text (2025-03-12) is always year-month-day; the day-first switch only affects 05/03/2025 style."""
    iso = s.map(lambda v: isinstance(v, str) and bool(ISO_RE.match(v)))
    parts = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if iso.any():
            parts.append(pd.to_datetime(s[iso], errors="coerce", format="mixed", dayfirst=False))
        if (~iso).any():
            parts.append(pd.to_datetime(s[~iso], errors="coerce", format="mixed", dayfirst=dayfirst))
    return parts[0].reindex(s.index) if len(parts) == 1 else pd.concat(parts).reindex(s.index)


def _infer_series(name, s: pd.Series, dayfirst: bool, stats: dict) -> pd.Series:
    if pd.api.types.is_bool_dtype(s) or pd.api.types.is_datetime64_any_dtype(s) or pd.api.types.is_numeric_dtype(s):
        return s
    non_null = s.dropna()
    n = len(non_null)
    if n == 0:
        return s

    # 1) real date objects from Excel (mixed with text dates)
    n_dt = sum(isinstance(v, (pd.Timestamp, dt.datetime, dt.date)) for v in non_null)
    n_str_dates = sum(isinstance(v, str) and bool(DATE_RE.match(v)) for v in non_null)
    if (n_dt + n_str_dates) / n >= 0.8:
        parsed = _parse_dates(s, dayfirst)
        ok = int(parsed.notna().sum())
        if ok / n >= 0.8:
            stats["date_cols"].append(name)
            stats["unparsed_dates"] += n - ok
            if parsed.dropna().dt.time.eq(dt.time(0, 0)).all():
                parsed = parsed.dt.normalize()
            return parsed

    # 2) numbers stored as text
    if not is_id_name(name):
        nums = pd.to_numeric(non_null.map(_to_number), errors="coerce")
        ok = int(nums.notna().sum())
        if ok / n >= 0.9:
            stats["numeric_cols"].append(name)
            stats["invalid_numeric"] += n - ok
            return pd.to_numeric(s.map(_to_number), errors="coerce")

    # 3) ids stored as numbers-with-decimals: 1001.0 -> "1001"
    def _fix_id(v):
        if isinstance(v, (int, np.integer)):
            return str(v)
        if isinstance(v, (float, np.floating)) and not pd.isna(v) and float(v).is_integer():
            return str(int(v))
        return v
    return s.map(_fix_id)


def _merge_case(s: pd.Series, title_case: bool):
    """North / north / NORTH  ->  North. Variants of the same text are always unified;
    Title Case is only applied to category-like columns (not free-text notes)."""
    vals = s.dropna()
    if vals.empty:
        return s, 0
    strs = vals[vals.map(lambda v: isinstance(v, str))]
    if len(strs) < 0.9 * len(vals):
        return s, 0
    counts = Counter(strs.tolist())
    if len(counts) > 20000:
        return s, 0
    best = {}
    for v, n in counts.items():
        k = v.lower()
        if k not in best or n > best[k][1]:
            best[k] = (v, n)
    mapping = {v: best[v.lower()][0] for v in counts}
    category_like = len(counts) <= 50 or len(counts) <= 0.5 * len(strs)
    if title_case and category_like:
        def tc(v):
            return v.title() if (v.islower() or (v.isupper() and len(v) > 3)) else v
        mapping = {k: tc(v) for k, v in mapping.items()}
    out = s.map(lambda v: mapping.get(v, v) if isinstance(v, str) else v)
    changed = int(((out != s) & s.notna()).sum())
    return out, changed


# ----------------------------------------------------------------------------- main
def clean_sheet(raw: pd.DataFrame, opts: dict | None = None):
    """Clean one raw sheet. Returns (clean_df, report)."""
    o = {**DEFAULTS, **(opts or {})}
    steps = []
    raw = raw.copy()
    rows_raw = len(raw)

    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    raw.columns = range(raw.shape[1])
    if len(raw) < 2:
        raise ValueError("This sheet has no data rows.")

    auto = int(o["header_row"] or 0) == 0
    h = detect_header_row(raw) if auto else min(int(o["header_row"]) - 1, len(raw) - 2)
    if h > 0:
        steps.append(f"Skipped {h} title/blank row(s) above the table and used row {h + 1} as the header"
                     + (" (auto-detected)" if auto else " (your choice)"))
    else:
        steps.append("Header found in the first row")

    body = raw.iloc[h + 1:].copy()
    body.columns = clean_names(raw.iloc[h].tolist())
    n_cols_before = body.shape[1]
    body = body.dropna(axis=1, how="all")
    if body.shape[1] < n_cols_before:
        steps.append(f"Removed {n_cols_before - body.shape[1]} empty column(s)")
    steps.append("Standardised column names (lowercase, underscores, no symbols)")

    # tidy cells: trim spaces, turn N/A, null, '-' into real blanks
    body = body.apply(lambda c: c.map(_clean_cell))
    body = body.dropna(how="all").reset_index(drop=True)

    # total / subtotal rows
    if o["drop_total_rows"]:
        mask = pd.Series(False, index=body.index)
        for c in body.columns:
            mask |= body[c].map(lambda v: isinstance(v, str) and bool(TOTAL_RE.match(v.strip())))
        if mask.any():
            steps.append(f"Removed {int(mask.sum())} 'Total/Subtotal' row(s) that would double-count your numbers")
            body = body[~mask].reset_index(drop=True)

    # merged cells
    if o["fill_down"]:
        filled = []
        for c in body.columns:
            col = body[c]
            txt = col.dropna().map(lambda v: isinstance(v, str) and not _is_number_like(v))
            blank_ratio = col.isna().mean()
            if len(txt) and txt.mean() > 0.8 and 0.01 < blank_ratio < 0.85:
                body[c] = col.ffill()
                filled.append(c)
        if filled:
            steps.append("Filled blank cells downward (merged cells) in: " + ", ".join(filled))

    # data types
    stats = {"numeric_cols": [], "date_cols": [], "invalid_numeric": 0, "unparsed_dates": 0}
    for c in list(body.columns):
        body[c] = _infer_series(c, body[c], bool(o["dayfirst"]), stats)
    if stats["numeric_cols"]:
        steps.append("Converted text to numbers in: " + ", ".join(stats["numeric_cols"]))
    if stats["date_cols"]:
        steps.append("Converted mixed date formats to real dates in: " + ", ".join(stats["date_cols"])
                     + (" (day-first)" if o["dayfirst"] else " (month-first)"))
    if stats["invalid_numeric"]:
        steps.append(f"Blanked {stats['invalid_numeric']} value(s) that were not valid numbers")
    if stats["unparsed_dates"]:
        steps.append(f"Blanked {stats['unparsed_dates']} value(s) that were not valid dates")

    # consistent text
    merged_total = 0
    for c in body.columns:
        if not (pd.api.types.is_numeric_dtype(body[c]) or pd.api.types.is_datetime64_any_dtype(body[c])
                or pd.api.types.is_bool_dtype(body[c])):
            body[c], ch = _merge_case(body[c], bool(o["title_case"]))
            merged_total += ch
    if merged_total:
        steps.append(f"Made {merged_total} text value(s) consistent (e.g. 'north', 'NORTH ' -> 'North')")

    # duplicates
    if o["drop_duplicates"]:
        before = len(body)
        body = body.drop_duplicates().reset_index(drop=True)
        if before - len(body):
            steps.append(f"Removed {before - len(body)} duplicate row(s)")

    # missing values
    missing_before = int(body.isna().sum().sum())
    num_cols = [c for c in body.columns if pd.api.types.is_numeric_dtype(body[c]) and not pd.api.types.is_bool_dtype(body[c])]
    txt_cols = [c for c in body.columns if c not in num_cols and not pd.api.types.is_datetime64_any_dtype(body[c])]
    mn, mt = o["missing_numbers"], o["missing_text"]
    if num_cols and mn != "Leave blank":
        if mn == "Drop rows":
            before = len(body)
            body = body.dropna(subset=num_cols).reset_index(drop=True)
            steps.append(f"Dropped {before - len(body)} row(s) with missing numbers")
        else:
            for c in num_cols:
                if body[c].isna().any():
                    fill = 0 if mn == "Fill with 0" else (body[c].median() if mn == "Fill with median" else body[c].mean())
                    body[c] = body[c].fillna(fill)
            steps.append(f"Filled missing numbers ({mn.lower()})")
    if txt_cols and mt != "Leave blank":
        if mt == "Drop rows":
            before = len(body)
            body = body.dropna(subset=txt_cols).reset_index(drop=True)
            steps.append(f"Dropped {before - len(body)} row(s) with missing text")
        else:
            for c in txt_cols:
                body[c] = body[c].fillna("Unknown")
            steps.append("Filled missing text with 'Unknown'")

    # outliers
    outliers = {}
    for c in num_cols:
        if is_id_name(c) or c not in body.columns:
            continue
        x = body[c].dropna()
        if len(x) < 20:
            continue
        q1, q3 = x.quantile(0.25), x.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
        k = int(((body[c] < lo) | (body[c] > hi)).sum())
        if k:
            outliers[c] = (k, float(lo), float(hi))
    if outliers:
        if o["remove_outliers"]:
            keep = pd.Series(True, index=body.index)
            for c, (k, lo, hi) in outliers.items():
                keep &= ~((body[c] < lo) | (body[c] > hi))
            steps.append(f"Removed {int((~keep).sum())} row(s) with extreme outliers")
            body = body[keep].reset_index(drop=True)
        else:
            steps.append("Extreme values flagged (not removed): "
                         + ", ".join(f"{c} ({k})" for c, (k, _, _) in outliers.items()))

    # tidy ints
    for c in body.columns:
        s = body[c]
        if pd.api.types.is_float_dtype(s) and s.notna().all() and len(s) and (s % 1 == 0).all():
            body[c] = s.astype("int64")

    body = body.reset_index(drop=True)
    cells = body.shape[0] * max(body.shape[1], 1)
    missing_after = int(body.isna().sum().sum())
    report = {
        "rows_raw": rows_raw, "rows_clean": len(body), "cols_clean": body.shape[1],
        "header_row": h + 1, "steps": steps, "missing_before": missing_before,
        "missing_after": missing_after,
        "completeness": round(100 * (1 - missing_after / cells), 1) if cells else 100.0,
        "outliers": {k: v[0] for k, v in outliers.items()},
    }
    return body, report


def combine_frames(frames: dict, drop_duplicates: bool = True):
    """Stack sheets/files that have the same columns. Returns (df, notes)."""
    labels = list(frames)
    if len(labels) == 1:
        return frames[labels[0]], []
    base = list(frames[labels[0]].columns)
    parts, notes = [], []
    for lab in labels:
        f = frames[lab]
        if set(f.columns) == set(base):
            f = f[base].copy()
            f.insert(0, "source_sheet", lab)
            parts.append(f)
        else:
            notes.append(f"Skipped '{lab}': its columns differ from '{labels[0]}'. Upload it on its own to analyse it.")
    out = pd.concat(parts, ignore_index=True)
    if drop_duplicates:
        before = len(out)
        out = out.drop_duplicates(subset=base).reset_index(drop=True)
        if before - len(out):
            notes.append(f"Removed {before - len(out)} duplicate row(s) that appeared in more than one sheet")
    notes.insert(0, f"Combined {len(parts)} sheets with matching columns into one table")
    return out, notes

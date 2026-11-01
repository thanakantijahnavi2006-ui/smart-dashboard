"""Ask questions about the uploaded data in plain English (needs an Anthropic API key)."""
import os
import re
import sqlite3

import pandas as pd

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_RETRIES = 2
ROW_LIMIT = 1000
TABLE = "data"

SQL_SYSTEM = """You are an expert SQLite analyst. Convert the user's question into ONE SQLite query on the table `data`.
Rules:
- Return ONLY the SQL. No explanation, no markdown fences.
- Only SELECT (or WITH ... SELECT). Never modify data.
- Use only the columns in the schema. Text values must match the listed distinct values exactly.
- Dates are stored as ISO text ('YYYY-MM-DD'); use strftime() for month/year grouping.
- For "last month/quarter/year", use the latest date in the data as 'today', not the system date.
- Give result columns clear aliases (e.g. total_sales)."""

FORBIDDEN = r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum|truncate)\b"


def make_conn(df: pd.DataFrame) -> sqlite3.Connection:
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            midnight = d[c].dropna().dt.time.astype(str).eq("00:00:00").all()
            d[c] = d[c].dt.strftime("%Y-%m-%d" if midnight else "%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(":memory:")
    d.to_sql(TABLE, conn, index=False)
    conn.execute("PRAGMA query_only = ON")
    return conn


def schema_text(df: pd.DataFrame) -> str:
    lines = [f"TABLE {TABLE} ({len(df)} rows)"]
    for c in df.columns:
        s = df[c]
        kind = "DATE (text)" if pd.api.types.is_datetime64_any_dtype(s) else "NUMBER" if pd.api.types.is_numeric_dtype(s) else "TEXT"
        extra = ""
        if kind == "TEXT" and 0 < s.nunique() <= 15:
            extra = " distinct values: " + ", ".join(repr(str(v)) for v in s.dropna().unique())
        if kind == "DATE (text)" and s.notna().any():
            extra = f" range: {s.min().date()} to {s.max().date()}"
        lines.append(f"  {c} {kind}{extra}")
    return "\n".join(lines)


def clean_sql(text: str) -> str:
    text = re.sub(r"^```(?:sql)?", "", text.strip(), flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    return text.rstrip(";").strip()


def validate_sql(sql: str):
    low = sql.lower().strip()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("Only SELECT queries are allowed.")
    if ";" in sql:
        raise ValueError("Multiple statements are not allowed.")
    if re.search(FORBIDDEN, low):
        raise ValueError("Query contains a forbidden keyword.")


def run_sql(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    validate_sql(sql)
    return pd.read_sql_query(f"SELECT * FROM ({sql}) LIMIT {ROW_LIMIT}", conn)


def ask_llm(api_key: str, system: str, user: str, max_tokens: int = 1000) -> str:
    from anthropic import Anthropic
    resp = Anthropic(api_key=api_key).messages.create(
        model=MODEL, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def answer(question: str, df: pd.DataFrame, api_key: str):
    """question -> (sql, result_df, insight). Retries with the error message if the SQL fails."""
    conn = make_conn(df)
    schema = schema_text(df)
    sql = clean_sql(ask_llm(api_key, SQL_SYSTEM, f"SCHEMA:\n{schema}\n\nQUESTION: {question}"))
    err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            res = run_sql(conn, sql)
            break
        except Exception as e:
            err = str(e)
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Could not produce a working query. Last error: {err}")
            sql = clean_sql(ask_llm(api_key, SQL_SYSTEM,
                                    f"SCHEMA:\n{schema}\n\nQUESTION: {question}\n\nThis SQL failed:\n{sql}\n\nError: {err}\n\nReturn the corrected SQL only."))
    if res.empty:
        return sql, res, "The query returned no rows."
    insight = ask_llm(api_key,
                      "You are a business analyst. In 2-3 short sentences tell a non-technical manager the key finding with numbers and one suggested action. Use only the data given.",
                      f"QUESTION: {question}\n\nRESULT:\n{res.head(30).to_string(index=False)}", max_tokens=300)
    return sql, res, insight

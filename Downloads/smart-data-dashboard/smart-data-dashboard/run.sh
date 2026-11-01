#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d venv ] || python3 -m venv venv
[ -f venv/installed.flag ] || { venv/bin/pip install -r requirements.txt && touch venv/installed.flag; }
[ -f sample_data/messy_sales_sample.xlsx ] || venv/bin/python make_sample.py
venv/bin/python -m streamlit run app.py

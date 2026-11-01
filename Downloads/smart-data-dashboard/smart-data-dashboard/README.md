# Smart Data Dashboard

Upload raw Excel or CSV files. The app cleans and arranges the data, lets you sort and filter it,
and shows a dashboard of the numbers and charts you choose.

## Run it (Windows)
1. Right-click the zip, choose **Extract All** (do not run it from inside the zip).
2. Open the folder and double-click **run.bat**.
3. Wait 1-3 minutes the first time. Your browser opens the app.
Mac/Linux: `bash run.sh`

## Use it
1. **Upload & Clean**: upload your files in the sidebar (or click *Try the sample messy Excel*).
   The app shows what it fixed, with a before/after view.
2. **Sort & Explore**: sort by one or two columns, search, choose and reorder columns.
3. **Dashboard**: key numbers, plain-English insights, and either an *Auto dashboard* or
   *Build my own dashboard* (pick chart type, what to group by, what to calculate, top N, split by).
   Includes a pivot table. Use the sidebar to filter by date, category and number range.
4. **Ask questions (AI)**: optional, needs an Anthropic API key. Type a question in plain English.
5. **Download**: cleaned Excel (with column summary and cleaning report), CSV, or the dashboard as a web page.

## What the cleaner fixes automatically
- Title rows and blank rows above the table (finds the real header)
- Messy column names, empty rows and columns
- Spaces, N/A, null, "-" placeholders
- Numbers stored as text (₹12,500, Rs. 2,000, (300), 10%)
- Dates in mixed formats (15/03/2025, 2025-03-15, 15-Mar-2025)
- Inconsistent text (north, NORTH, "North ")
- Duplicate rows and Total/Subtotal rows
- Missing values (leave, fill, or drop: your choice in Cleaning options)
- Several sheets or files with the same columns are stacked into one table

## Files
- run.bat / run.sh: one-click launchers
- app.py: the screens
- cleaner.py: raw file to clean table
- analytics.py: column detection, totals, trends, insights
- charts.py: chart builder
- exporter.py: Excel and HTML downloads
- ai_sql.py: plain-English questions (safe, read-only SQL)
- make_sample.py and sample_data/: a deliberately messy example file

## Resume line
Built an end-to-end analytics app that ingests raw, messy Excel/CSV files, automatically cleans and
standardises them (header detection, type repair, de-duplication), and generates interactive
dashboards with custom chart builder, pivoting, exports, and an optional LLM text-to-SQL assistant.

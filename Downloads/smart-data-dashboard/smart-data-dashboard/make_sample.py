"""Creates sample_data/messy_sales_sample.xlsx - a deliberately messy 'raw' Excel file for testing."""
import datetime as dt
import os
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
regions = ["North", "South", "East", "West"]
cats = {"Electronics": [("Laptop", 52000), ("Smartphone", 24000), ("Headphones", 2800)],
        "Furniture": [("Office Chair", 7500), ("Desk", 14000)],
        "Stationery": [("Notebook", 120), ("Pen Set", 240), ("Printer Paper", 430)]}
people = ["Asha Rao", "Vikram Shah", "Neha Iyer", "Rohan Das", "Meera Nair"]
pay = ["UPI", "Card", "Cash", "Net Banking"]


def make_sheet(start, end, n, first_id):
    days = (end - start).days
    rows = []
    for i in range(n):
        cat = rng.choice(list(cats))
        prod, price = cats[cat][rng.integers(len(cats[cat]))]
        qty = int(rng.integers(1, 8))
        disc = int(rng.choice([0, 0, 5, 10, 15]))
        amount = round(price * qty * (1 - disc / 100))
        d = start + dt.timedelta(days=int(rng.integers(0, days)))
        style = rng.integers(0, 4)
        date = (d if style == 0 else d.strftime("%d/%m/%Y") if style == 1 else d.strftime("%Y-%m-%d") if style == 2 else d.strftime("%d-%b-%Y"))
        region = rng.choice(regions)
        region = [region, region.lower(), region.upper(), region + " "][int(rng.integers(0, 4))]
        rows.append({
            "Order ID": f"ORD-{first_id + i}", "Order Date": date,
            "Customer Name": f"Customer {int(rng.integers(1, 90))}", "Region": region,
            "Product Category": cat if rng.random() > 0.1 else cat.upper(), "Product": prod,
            "Quantity": qty, "Unit Price": f"₹{price:,}", "Discount %": f"{disc}%",
            "Sales Amount": f"₹{amount:,}" if rng.random() > 0.5 else amount,
            "Salesperson": rng.choice(people), "Payment Mode": rng.choice(pay),
        })
    df = pd.DataFrame(rows)
    df = df.astype(object)
    for col, frac in (("Salesperson", 0.04), ("Payment Mode", 0.05), ("Quantity", 0.02)):
        for idx in df.sample(frac=frac, random_state=1).index:
            df.at[idx, col] = ["N/A", "-", None][int(rng.integers(0, 3))]
    for idx in df.sample(frac=0.03, random_state=2).index:
        df.at[idx, "Sales Amount"] = "n/a"
    dup = df.sample(6, random_state=3)
    df = pd.concat([df, dup], ignore_index=True)
    return df


os.makedirs("sample_data", exist_ok=True)
path = "sample_data/messy_sales_sample.xlsx"
with pd.ExcelWriter(path, engine="openpyxl") as xw:
    for name, (s, e, first) in {"Jan-Mar": (dt.date(2025, 1, 1), dt.date(2025, 3, 31), 1000),
                                "Apr-Jun": (dt.date(2025, 4, 1), dt.date(2025, 6, 30), 2000)}.items():
        df = make_sheet(s, e, 220, first)
        df.insert(8, "", np.nan)  # an empty column
        df.to_excel(xw, sheet_name=name, index=False, startrow=4)
        ws = xw.sheets[name]
        ws["A1"] = "ACME Traders - Sales Register"
        ws["A2"] = f"Period: {name} 2025   |   Prepared by: Accounts   |   Confidential"
        total_row = ws.max_row + 2
        ws.cell(row=total_row, column=1, value="Total")
        ws.cell(row=total_row, column=7, value=int(pd.to_numeric(df["Quantity"], errors="coerce").sum()))
print("created", path)

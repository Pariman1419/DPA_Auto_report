import pandas as pd
import re

file = "D:\Script\R20251217-002,003,004_Feb10.26.xlsx"

df = pd.read_excel(file, sheet_name="Reliability report", header=None)

start_row = df[df[0].astype(str).str.contains("4.DPA report", case=False, na=False)].index[0]

dpa_data = []

for i in range(start_row + 1, len(df)):
    value = str(df.iloc[i, 0]).strip()

    # stop when new section
    if re.match(r'^\d+\.', value):
        break

    # stop when note
    if value.lower().startswith("note"):
        break

    if value and value != "nan":
        dpa_data.append(value)

print(dpa_data)
import pandas as pd

file = "D:\Script\R20251217-002,003,004_Feb10.26.xlsx"

df = pd.read_excel(file, sheet_name="Reliability report", header=None)
df = df.fillna("")

# หา row ที่มี Background information
start = df[df.apply(lambda r: r.astype(str).str.contains("Background information").any(), axis=1)].index[0]

bg = {}
rel_requests = []

for i in range(start+1, start+15):

    row = df.iloc[i]

    # stop ถ้าเจอ section ถัดไป
    if "Bill Of Material" in " ".join(row.astype(str)):
        break

    key1 = str(row[0]).strip()
    val1 = str(row[1]).strip()

    key2 = str(row[3]).strip()
    val2 = str(row[4]).strip()

    # ฝั่งซ้าย
    if key1:
        bg[key1] = val1

    # ฝั่งขวา
    if key2 == "Rel Request Number":
        rel_requests.append(val2)

    elif key2 == "" and "REQ-" in val2:
        rel_requests.append(val2)

    elif key2:
        bg[key2] = val2

bg["Rel Request Number"] = rel_requests

print(bg)


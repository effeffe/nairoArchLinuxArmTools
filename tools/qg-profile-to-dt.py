#!/usr/bin/env python3
"""Convert a downstream QG battery profile (from a decompiled live DT) into
mainline simple-battery ocv-capacity tables.

Usage: qg-profile-to-dt.py DTS PROFILE_NODE [TABLE]
Default TABLE is qcom,pc-temp-v2-lut, the discharge table downstream uses for
rest-OCV lookups (lookup_soc_ocv(..., charging=false)). Data is in 100 uV
units, rows are state of charge in 0.01 %, columns are degrees C.
"""
import re
import sys


def cells(s):
    return [int(x, 16) if x.startswith("0x") else int(x) for x in s.split()]


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def main():
    dts, profile = sys.argv[1], sys.argv[2]
    table = sys.argv[3] if len(sys.argv) > 3 else "qcom,pc-temp-v2-lut"
    text = open(dts).read()
    start = text.index(profile + " {")
    sub = text[start:]
    t = sub.index(table + " {")
    body = sub[t:sub.index("};", t)]
    col = [s32(v) for v in cells(re.search(r"lut-col-legend = <([^>]*)>", body).group(1))]
    row = cells(re.search(r"lut-row-legend = <([^>]*)>", body).group(1))
    data = cells(re.search(r"lut-data = <([^>]*)>", body).group(1))
    assert len(data) == len(row) * len(col), (len(data), len(row), len(col))

    temps = ", ".join(f"({c})" for c in col)
    print(f"\t\t/* {profile} {table}, converted by tools/qg-profile-to-dt.py */")
    print(f"\t\tocv-capacity-celsius = <{' '.join(f'({c})' for c in col)}>;")
    for ci, c in enumerate(col):
        pairs = []
        last = None
        for ri, r in enumerate(row):
            pct = round(r / 100)
            if pct == last:
                continue  # mainline wants integer percent, keep the first
            last = pct
            pairs.append(f"{data[ri * len(col) + ci] * 100} {pct}")
        print(f"\t\t/* {c} degrees C */")
        print(f"\t\tocv-capacity-table-{ci} =")
        for i in range(0, len(pairs), 4):
            sep = ";" if i + 4 >= len(pairs) else ","
            print("\t\t\t" + ", ".join(f"<{p}>" for p in pairs[i:i + 4]) + sep)


main()

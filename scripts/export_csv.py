"""把 shops.json 导出为 CSV，方便用 Excel 手工补全/校对。

默认只导出探店条目；--all 包含非探店。
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_JSON = os.path.join(ROOT, "data", "shops.json")
OUT_CSV = os.path.join(ROOT, "data", "shops.csv")

FIELDS = [
    ("is_tandian", "是否探店"),
    ("shop_name", "店铺名称"),
    ("location", "城市/地区"),
    ("province", "省份"),
    ("title", "视频标题"),
    ("pubdate", "发布日期"),
    ("play", "播放量"),
    ("confidence", "置信度"),
    ("note", "备注(待人工补全)"),
    ("url", "视频链接"),
    ("bvid", "BV号"),
    ("tags", "标签"),
]


def main():
    include_all = "--all" in sys.argv
    with open(IN_JSON, encoding="utf-8") as f:
        rows = json.load(f)
    rows = [r for r in rows if include_all or r["is_tandian"]]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([label for _, label in FIELDS])
        for r in rows:
            w.writerow([
                ("是" if r.get(k) else ("否" if k == "is_tandian" else ""))
                if k in ("is_tandian",)
                else (r.get(k) if r.get(k) is not None else "")
                for k, _ in FIELDS
            ])
    print(f"已导出 {len(rows)} 条 -> {OUT_CSV}")


if __name__ == "__main__":
    main()

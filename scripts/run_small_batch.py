"""小范围验证：抓取一页（约 12 个）视频 -> 缓存原始数据 -> 解析为 JSON。

为避免重复请求风控，把原始数据缓存到 data/ 下，可反复离线解析。
"""
import json
import os
import sys
import time

from bilibili_api import (
    new_session, WbiSigner, get_arc_page, get_view_info, get_tags,
)
from extract import parse_video

MID = 3546888255048212
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
RAW_CACHE = os.path.join(DATA_DIR, "raw_small.json")
OUT_JSON = os.path.join(DATA_DIR, "shops_small.json")


def fetch_and_cache(count: int):
    os.makedirs(DATA_DIR, exist_ok=True)
    s = new_session()
    signer = WbiSigner(s)
    arc = get_arc_page(s, signer, MID, pn=1, ps=count)
    vlist = arc["data"]["list"]["vlist"]
    rows = []
    for i, v in enumerate(vlist):
        bvid = v["bvid"]
        detail = get_view_info(s, bvid)
        d = detail.get("data") or {}
        try:
            tags_resp = get_tags(s, bvid)
            tags = [t["tag_name"] for t in tags_resp.get("data") or []]
        except Exception as e:
            tags = []
            print(f"  [warn] tags {bvid}: {e}")
        rows.append({
            "raw": v,
            "detail": d,
            "tags": tags,
        })
        print(f"[{i+1}/{len(vlist)}] {v['title'][:30]}")
        time.sleep(1.5)  # 礼貌延时
    with open(RAW_CACHE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("已缓存原始数据 ->", RAW_CACHE)
    return rows


def parse_cached(rows):
    out = [parse_video(r["raw"], r["detail"], r["tags"]) for r in rows]
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("已写出解析结果 ->", OUT_JSON)
    return out


def main():
    refresh = "--refresh" in sys.argv
    if refresh or not os.path.exists(RAW_CACHE):
        rows = fetch_and_cache(12)
    else:
        with open(RAW_CACHE, encoding="utf-8") as f:
            rows = json.load(f)
        print(f"从缓存读取 {len(rows)} 条原始数据")
    out = parse_cached(rows)
    # 打印人可读摘要
    print("\n========== 摘要 ==========")
    for o in out:
        flag = "探店" if o["is_tandian"] else "非探店"
        shop = o["shop_name"] or "—"
        loc = o["location"] or "—"
        print(f"[{o['confidence']:6}] {flag} | {shop:<10} | {loc:<8} | {o['title'][:34]}")


if __name__ == "__main__":
    main()

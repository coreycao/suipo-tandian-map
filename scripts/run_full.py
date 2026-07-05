"""全量抓取：拉取该 UP 主所有视频 -> 缓存(断点续抓) -> 解析为 shops.json。

设计要点：
  - 列表分页拉满（每页 30）
  - 详情/标签逐条抓，每条间隔 ~1.3s，礼貌避风控
  - 缓存按 bvid 落盘，每隔几条保存一次；中断后重跑可跳过已抓项
  - 风控(-412/412)由 bilibili_api 内部退避重试处理
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
RAW_CACHE = os.path.join(DATA_DIR, "raw_full.json")
OUT_JSON = os.path.join(ROOT, "data", "shops.json")

PAGE_SIZE = 30
SLEEP = 1.3  # 每条详情间隔


def save_cache(cache):
    tmp = RAW_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, RAW_CACHE)


def load_cache():
    if os.path.exists(RAW_CACHE):
        with open(RAW_CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def fetch_page_with_retry(session, signer, pn, tries=5):
    """拉取一页列表，带整页重试。"""
    for k in range(tries):
        try:
            arc = get_arc_page(session, signer, MID, pn=pn, ps=PAGE_SIZE)
            if arc.get("code") == 0 and (arc.get("data") or {}).get("list"):
                return arc
            print(f"    [retry {k+1}] 列表 code={arc.get('code')} {arc.get('message')}")
        except Exception as e:
            print(f"    [retry {k+1}] 列表异常: {e}")
        time.sleep(5 + k * 6)
    raise RuntimeError(f"列表第 {pn} 页多次重试仍失败")


def fetch_all_list(session, signer):
    """分页拉取全部视频列表（便宜，只发 4 次左右请求）。"""
    all_v = []
    pn = 1
    while True:
        arc = fetch_page_with_retry(session, signer, pn)
        page = arc["data"]["page"]
        vlist = arc["data"]["list"]["vlist"]
        all_v.extend(vlist)
        total = page.get("count", 0)
        print(f"  列表第 {pn} 页: +{len(vlist)}，累计 {len(all_v)}/{total}")
        if len(all_v) >= total or not vlist or pn > 20:
            break
        pn += 1
        time.sleep(1.2)
    return all_v


def fetch_detail_with_retry(session, bvid, tries=4):
    """拉取单条详情+标签，带重试。失败返回 ({}, [])。"""
    for k in range(tries):
        try:
            detail = get_view_info(session, bvid)
            d = detail.get("data") or {}
            if detail.get("code") == 0 or d:
                try:
                    tags_resp = get_tags(session, bvid)
                    tags = [t["tag_name"] for t in tags_resp.get("data") or []]
                except Exception:
                    tags = []
                return d, tags
            print(f"    [retry {k+1}] {bvid} code={detail.get('code')}")
        except Exception as e:
            print(f"    [retry {k+1}] {bvid} 异常: {e}")
        time.sleep(4 + k * 5)
    return {}, []


def main():
    refresh = "--refresh" in sys.argv
    cache = {} if refresh else load_cache()
    print(f"缓存已有 {len(cache)} 条")

    s = new_session()
    signer = WbiSigner(s)

    print("拉取视频列表…")
    vlist = fetch_all_list(s, signer)
    print(f"列表共 {len(vlist)} 个视频\n")

    rows = []
    new_count = 0
    failed = []
    for i, v in enumerate(vlist):
        bvid = v["bvid"]
        if bvid in cache:
            rows.append(cache[bvid])
            continue
        d, tags = fetch_detail_with_retry(s, bvid)
        if not d and not tags:
            failed.append(bvid)
        entry = {"raw": v, "detail": d, "tags": tags}
        cache[bvid] = entry
        rows.append(entry)
        new_count += 1
        # 增量保存（每 4 条）
        if new_count % 4 == 0:
            save_cache(cache)
        td = "探" if ("探店" in v.get("title", "") or "美食探店" in tags) else "·"
        flag = "!" if failed and bvid == failed[-1] else " "
        print(f"[{i+1:3}/{len(vlist)}]{flag}{td} {v['title'][:34]}")
        time.sleep(SLEEP)

    save_cache(cache)
    print(f"\n抓取完成：新增 {new_count}，缓存共 {len(cache)}，失败 {len(failed)}: {failed}")

    save_cache(cache)
    print(f"\n抓取完成：新增 {new_count}，缓存共 {len(cache)}")

    # 解析
    out = [parse_video(r["raw"], r["detail"], r["tags"]) for r in rows]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已写出 -> {OUT_JSON}（{len(out)} 条）\n")

    # 摘要
    td = [o for o in out if o["is_tandian"]]
    review = [o for o in td if not o["shop_name"] or not o["location"]
              or o["confidence"] != "high"]
    locs = {}
    for o in td:
        if o["location"]:
            locs[o["location"]] = locs.get(o["location"], 0) + 1
    print("========== 全量摘要 ==========")
    print(f"视频总数: {len(out)}")
    print(f"探店数:   {len(td)}")
    print(f"待人工补全: {len(review)}")
    print(f"覆盖城市: {len(locs)} 个")
    top = sorted(locs.items(), key=lambda x: -x[1])[:10]
    print("城市 Top10:", "  ".join(f"{c}({n})" for c, n in top))


if __name__ == "__main__":
    main()

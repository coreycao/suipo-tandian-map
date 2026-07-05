"""探测 view / tags 接口返回了哪些可用于店名/位置解析的字段。"""
import json
import time

from bilibili_api import (
    new_session, WbiSigner, get_arc_page, get_view_info, get_tags,
)

MID = 3546888255048212


s = new_session()
signer = WbiSigner(s)
arc = get_arc_page(s, signer, MID, pn=1, ps=12)
vlist = arc["data"]["list"]["vlist"]

for v in vlist:
    bvid = v["bvid"]
    print("=" * 70)
    print(f"标题: {v['title']}")
    print(f"bvid: {bvid}  play: {v.get('play')}  created: {v.get('created')}  description: {v.get('description')}")
    # 详情
    view = get_view_info(s, bvid)
    if view.get("code") == 0:
        d = view["data"]
        print(f"  [view] desc: {d.get('desc')}")
        print(f"  [view] pub_location: {d.get('pub_location')}")
        print(f"  [view] pubdate: {d.get('pubdate')}  cid: {d.get('cid')}")
    else:
        print(f"  [view] ERROR {view}")
    # 标签
    tg = get_tags(s, bvid)
    if tg.get("code") == 0:
        tags = [t["tag_name"] for t in tg["data"]]
        print(f"  [tags]: {tags}")
    else:
        print(f"  [tags] ERROR {tg}")
    time.sleep(1.2)  # 礼貌延时

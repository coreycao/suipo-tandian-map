"""
Bilibili API helpers with WBI signature support.

WBI 参考: https://github.com/SocialSisterYi/bilibili-API-collect
"""
import hashlib
import random
import time
import urllib.parse

import requests

# 伪装成普通浏览器，避免被识别为爬虫
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# WBI mixin key 打乱顺序表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

NAV_API = "https://api.bilibili.com/x/web-interface/nav"
ARC_SEARCH_API = "https://api.bilibili.com/x/space/wbi/arc/search"
VIEW_API = "https://api.bilibili.com/x/web-interface/view"


class WbiSigner:
    """缓存 WBI img/sub key，避免每次请求都去取一次。"""

    def __init__(self, session: requests.Session):
        self.session = session
        self._img_key = None
        self._sub_key = None

    def _fetch_keys(self):
        j = _get_json(self.session, NAV_API, {})
        data = j["data"]["wbi_img"]
        img_url = data["img_url"]
        sub_url = data["sub_url"]
        self._img_key = img_url.rsplit("/", 1)[1].split(".")[0]
        self._sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]

    @staticmethod
    def _mixin_key(orig: str) -> str:
        return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]

    def sign(self, params: dict) -> dict:
        if self._img_key is None:
            self._fetch_keys()
        mixin = self._mixin_key(self._img_key + self._sub_key)
        params = dict(params)
        params["wts"] = int(time.time())
        params = dict(sorted(params.items()))
        # 过滤掉 key 含特殊字符的项
        params = {
            k: v
            for k, v in params.items()
            if all(ch not in "!'()*" for ch in str(k))
        }
        query = urllib.parse.urlencode(params)
        w_rid = hashlib.md5((query + mixin).encode("utf-8")).hexdigest()
        params["w_rid"] = w_rid
        return params


FINGER_SPI_API = "https://api.bilibili.com/x/frontend/finger/spi"


def _gen_b_lsid() -> str:
    return (
        "".join(random.choices("0123456789ABCDEF", k=8))
        + "_"
        + "".join(random.choices("0123456789", k=8))
    )


def _gen_uuid() -> str:
    def h4():
        return "".join(random.choices("0123456789abcdef", k=4))

    return (
        f"{h4()}{h4()}-{h4()}-4{h4()[1:]}-{random.choice('89ab')}{h4()[1:]}-"
        f"{h4()}{h4()}{h4()}{h4()}INF"
    )


def new_session() -> requests.Session:
    """新建一个带反爬指纹 cookie 的 session。

    B 站现在对 arc/search 等接口要求 buvid3 / buvid4，否则返回 412。
    同时补齐 b_lsid / _uuid 让指纹更完整。
    """
    s = requests.Session()
    # 先访问一下首页拿基础 cookie
    try:
        s.get("https://www.bilibili.com/", headers=HEADERS, timeout=15)
    except requests.RequestException:
        pass
    # 通过 spi 接口换取 buvid3 / buvid4 指纹
    try:
        resp = s.get(FINGER_SPI_API, headers=HEADERS, timeout=15)
        spi = resp.json()["data"]
        s.cookies.set("buvid3", spi["b_3"], domain=".bilibili.com")
        s.cookies.set("buvid4", spi["b_4"], domain=".bilibili.com")
    except (requests.RequestException, KeyError, ValueError):
        pass
    # 补充客户端生成的指纹 cookie
    s.cookies.set("b_lsid", _gen_b_lsid(), domain=".bilibili.com")
    s.cookies.set("_uuid", _gen_uuid(), domain=".bilibili.com")
    s.cookies.set("b_nut", str(int(time.time())), domain=".bilibili.com")
    s.cookies.set(
        "DedeUserID", "0", domain=".bilibili.com"
    )  # 未登录标记
    return s


# B 站风控/限流相关错误码，命中则退避重试（而非直接返回）
RISK_CODES = {-412, -352, -509, -799, -765, -701}


def _get_json(session, url, params, max_retries=7):
    """带风控退避重试的 GET JSON。

    会重试的情况：
      - HTTP 412 (Precondition Failed)
      - HTTP 200 但 body code 命中风控码集合（-412/-352/-509/-799 等）
    重试时刷新 buvid 指纹并退避。
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = session.get(url, params=params, headers=HEADERS, timeout=20)
            if resp.status_code == 412:
                wait = 4 + attempt * 5
                time.sleep(wait)
                _refresh_fingerprint(session)
                continue
            resp.raise_for_status()
            j = resp.json()
            if j.get("code") in RISK_CODES:
                wait = 4 + attempt * 5
                time.sleep(wait)
                _refresh_fingerprint(session)
                continue
            return j
        except requests.RequestException as e:
            last_exc = e
            time.sleep(4 + attempt * 5)
    raise last_exc


def _refresh_fingerprint(session: requests.Session):
    """重新获取 buvid3/buvid4，对抗风控。"""
    try:
        resp = session.get(FINGER_SPI_API, headers=HEADERS, timeout=15)
        spi = resp.json()["data"]
        session.cookies.set("buvid3", spi["b_3"], domain=".bilibili.com")
        session.cookies.set("buvid4", spi["b_4"], domain=".bilibili.com")
        session.cookies.set("b_lsid", _gen_b_lsid(), domain=".bilibili.com")
        session.cookies.set("_uuid", _gen_uuid(), domain=".bilibili.com")
    except requests.RequestException:
        pass


def get_arc_page(
    session: requests.Session,
    signer: WbiSigner,
    mid: int,
    pn: int = 1,
    ps: int = 30,
) -> dict:
    """拉取用户投稿列表的某一页。返回原始 JSON。"""
    params = {
        "mid": mid,
        "pn": pn,
        "ps": ps,
        "order": "pubdate",  # 按发布时间倒序
        "platform": "web",
        "web_location": 1550101,
        "order_avoided": "true",
    }
    signed = signer.sign(params)
    return _get_json(session, ARC_SEARCH_API, signed)


def get_view_info(session: requests.Session, bvid: str) -> dict:
    """拉取单个视频详情（简介、标签、发布地等）。"""
    return _get_json(session, VIEW_API, {"bvid": bvid})


def get_tags(session: requests.Session, bvid: str) -> dict:
    """拉取单个视频的标签列表。"""
    return _get_json(
        session, "https://api.bilibili.com/x/tag/archive/tags", {"bvid": bvid}
    )


if __name__ == "__main__":
    # 自测：拉第一页前几个视频
    MID = 3546888255048212
    s = new_session()
    signer = WbiSigner(s)
    result = get_arc_page(s, signer, MID, pn=1, ps=5)
    print("code:", result.get("code"), "message:", result.get("message"))
    vlist = result.get("data", {}).get("list", {}).get("vlist", [])
    page_info = result.get("data", {}).get("page", {})
    print("总视频数:", page_info.get("count"))
    print("本页视频数:", len(vlist))
    for v in vlist:
        print(" -", v.get("bvid"), "|", v.get("title"), "| play:", v.get("play"))

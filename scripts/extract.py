"""
从 B 站视频数据中解析：是否探店、店铺名称、店铺位置。

数据信号优先级：
  店名  -> 标题中 "—" 之后的部分（隋坡的固定排版）
  位置  -> 标签中的地理名（白名单匹配）-> 回退到标题扫描
  探店  -> 标题含 "探店" / 有可提取店名 + 美食探店标签；
           排除做饭/教学类视频
"""
import datetime as dt

from geo_data import build_geo_set, build_city_to_province

GEO_SET = build_geo_set()
CITY_TO_PROVINCE = build_city_to_province()

# 固定的非地理标签（频道/题材标记），解析位置时直接忽略
NON_GEO_TAGS = {
    "美食", "隋坡", "舌尖真探事务所", "美食探店", "大众点评",
    "记录我的美食日常", "做饭", "吃播", "探店", "vlog", "VLOG",
}

# 表示"做饭/教学"而非探店的负面信号
COOKING_NEGATIVE = {"做饭", "记录我的美食日常", "做菜", "美食教程"}
TITLE_NEGATIVE = ["教你", "怎么做", "做法", "做菜", "做饭", "教程"]

# 可能用作分隔的破折号
DASHES = ["—", "–", "−", "－", "-"]

# 这些词出现在"店名"里，说明破折号后其实是整句而非干净店名
SHOP_NAME_SUSPICIOUS = [
    "怎么", "到底", "是什么", "怎么样", "真的", "超级", "好吃",
    "难吃", "真是", "这家", "那家", "一个", "居然", "竟然", "还是",
]

# 强做饭/教学信号（出现且标题无正面"探店" -> 非探店，破折号后多为菜名）
COOKING_STRONG = {"做饭", "做菜", "美食教程", "食谱", "家常菜教程"}

# 否定词：标题里出现这些，说明是在说"不探店"
TANDIAN_NEGATIONS = ["不探店", "没探店", "非探店", "不是探店"]


def _clean(text: str) -> str:
    """去除首尾的标点、空白、感叹问号等。"""
    text = text.strip()
    while text and text[0] in "？！。，,、~～·:： ":
        text = text[1:]
    while text and text[-1] in "？！。，,、~～·:： ":
        text = text[:-1]
    return text.strip()


def extract_shop_name(title: str):
    """从标题提取店铺名。

    返回 (店名或None, 是否"干净")。
    若破折号后含"到底/怎么样"等整句词，会截到最早出现处，得到更干净的店名。
    "干净"为 False 表示店名仍可能不准确，需人工核对。
    """
    # 取最后一个破折号之后的部分
    idx = -1
    for d in DASHES:
        i = title.rfind(d)
        if i > idx:
            idx = i
    if idx >= 0:
        tail = title[idx + 1:]
        cleaned = _clean(tail)
        if not cleaned:
            return None, False
        # 含整句词则截到最早出现处（如"水仙头私房菜到底怎么样"->"水仙头私房菜"）
        cut = len(cleaned)
        for w in SHOP_NAME_SUSPICIOUS:
            p = cleaned.find(w)
            if p != -1 and p < cut:
                cut = p
        if cut < len(cleaned):
            cleaned = _clean(cleaned[:cut])
        if not cleaned:
            return None, False
        suspicious = (
            len(cleaned) > 14
            or any(w in cleaned for w in SHOP_NAME_SUSPICIOUS)
        )
        return cleaned, (not suspicious)
    return None, False


def title_has_positive_tandian(title: str) -> bool:
    """标题是否正面表达探店（排除"不探店/没探店"等否定）。"""
    t = title
    for neg in TANDIAN_NEGATIONS:
        t = t.replace(neg, "")
    return "探店" in t


GEO_SUFFIXES = ["美食", "攻略", "旅游", "游记", "探店", "打卡", "吃喝", "逛吃", "游记"]


def _match_geo(tag: str):
    """标签是否指向某地名。支持 '北京美食'->'北京' 这类带后缀的标签。"""
    if tag in GEO_SET:
        return tag
    for suf in GEO_SUFFIXES:
        if tag.endswith(suf) and len(tag) > len(suf):
            base = tag[: -len(suf)]
            if base in GEO_SET:
                return base
        if tag.startswith(suf) and len(tag) > len(suf):
            base = tag[len(suf):]
            if base in GEO_SET:
                return base
    return None


def extract_location(tags, title=""):
    """返回 (位置或None, 来源 'tag'|'title'|None, 省份或None)。"""
    # 1) 标签优先（含后缀剥离匹配）
    for t in tags:
        if t in NON_GEO_TAGS:
            continue
        g = _match_geo(t)
        if g:
            return g, "tag", CITY_TO_PROVINCE.get(g)
    # 2) 标题扫描（更具体但需谨慎，避免误命中）
    #    用最长匹配：从 GEO_SET 里找出现在标题里的名字
    hits = [g for g in GEO_SET if g in title]
    if hits:
        # 取最长的一个（更具体，如"乌鲁木齐"优于"新疆"）
        best = max(hits, key=len)
        return best, "title", CITY_TO_PROVINCE.get(best)
    return None, None, None


def classify_tandian(title: str, tags, shop_name, shop_clean, location):
    """返回 (是否探店, 置信度 high|medium|low, 备注)。"""
    title_tandian = title_has_positive_tandian(title)
    has_shop = shop_name is not None
    has_meishi_tag = "美食探店" in tags or "探店" in tags
    cooking_strong = bool(set(tags) & COOKING_STRONG)
    cooking = bool(set(tags) & COOKING_NEGATIVE)
    title_neg = any(k in title for k in TITLE_NEGATIVE)

    def shop_note():
        if has_shop and not shop_clean:
            return "；店名可能非干净店名，建议核对"
        return ""

    # 强做饭/教学视频（即便破折号后有词，多为菜名而非店名）
    if cooking_strong and not title_tandian:
        return False, "high", "标签含做饭/教程类且标题无正面探店 -> 判为非探店"
    if title_neg and not title_tandian and not has_shop:
        return False, "high", "标题为教学/做法类，无探店与店名 -> 判为非探店"
    # 标题明确说"不探店"
    if not title_tandian and any(n in title for n in TANDIAN_NEGATIONS):
        return False, "high", "标题明确表示『不探店』 -> 判为非探店"

    # 强探店信号：标题正面含『探店』
    if title_tandian:
        notes = []
        if not has_shop:
            notes.append("标题含『探店』但未提取到店名，店名待人工补全")
        if not location:
            notes.append("标签与标题均无城市信息，地点未知")
        notes.append(shop_note().lstrip("；"))
        conf = "high" if (has_shop and shop_clean) else "medium"
        return True, conf, "；".join(n for n in notes if n)

    # 无『探店』字样但有店名 + 美食探店标签
    if has_shop and has_meishi_tag:
        notes = ["标题无『探店』字样，但有店名+美食探店标签 -> 推断探店"]
        if not location:
            notes.append("地点未知")
        notes.append(shop_note().lstrip("；"))
        conf = "medium" if shop_clean else "low"
        return True, conf, "；".join(n for n in notes if n)

    # 有店名但无美食探店标签
    if has_shop:
        notes = ["有可提取店名，但标签无探店标记，建议人工确认是否探店"]
        if not location:
            notes.append("地点未知")
        notes.append(shop_note().lstrip("；"))
        return True, "low", "；".join(n for n in notes if n)

    # 关键补充：无店名，但有探店标签 + 地点 + 非教学（如"在重庆的肥肠鸡"这类）
    if has_meishi_tag and location and not cooking_strong and not title_neg:
        return (
            True,
            "medium",
            "标题无店名，但有美食探店标签+地点 -> 推断探店，店名待人工补全",
        )

    # 既无探店字样也无店名，也无地点
    if has_meishi_tag:
        return (
            False,
            "medium",
            "有美食探店标签但无店名/无地点/疑似非探店，建议人工复核",
        )
    return False, "high", "无任何探店/店名信号 -> 判为非探店"


def parse_video(raw: dict, detail: dict, tags: list) -> dict:
    """把原始数据组装成一条结构化记录。

    raw: arc/search 的 vlist 项
    detail: view 接口的 data
    tags: tag 名列表
    """
    title = raw.get("title", "")
    bvid = raw.get("bvid", "")
    shop_name, shop_clean = extract_shop_name(title)
    location, loc_src, province = extract_location(tags, title)
    is_tandian, confidence, note = classify_tandian(
        title, tags, shop_name, shop_clean, location
    )

    pubdate = detail.get("pubdate") or raw.get("created")
    pubdate_iso = None
    if pubdate:
        pubdate_iso = dt.datetime.fromtimestamp(
            int(pubdate), tz=dt.timezone.utc
        ).astimezone().strftime("%Y-%m-%d")

    return {
        "bvid": bvid,
        "title": title,
        "url": f"https://www.bilibili.com/video/{bvid}",
        "cover": raw.get("pic") or (detail.get("pic")),
        "is_tandian": is_tandian,
        "confidence": confidence,
        "shop_name": shop_name if is_tandian else None,
        "location": location if is_tandian else None,
        "province": province if is_tandian else None,
        "location_source": loc_src if is_tandian else None,
        "tags": tags,
        "play": raw.get("play"),
        "pubdate": pubdate_iso,
        "note": note,
    }

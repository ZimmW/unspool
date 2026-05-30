"""B站 API:WBI 签名 + 视频搜索 + AI 字幕提取。

- 搜索(wbi/search/type)需要 WBI 签名,否则 -412 风控
- AI 字幕(player/wbi/v2 → subtitle_url)需要登录 cookie(SESSDATA)
- 字幕是 B站自动生成,质量 ≈ ASR,价值在"免 ASR 省钱省时"
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request

from .transcript import Segment, Transcript

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")

# WBI mixin key 重排表(B站固定置换)
_MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def _headers(cookie_header: str = "") -> dict:
    h = {"User-Agent": _UA, "Referer": "https://www.bilibili.com/"}
    if cookie_header:
        h["Cookie"] = cookie_header
    return h


def _get(url: str, cookie_header: str = "", timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers=_headers(cookie_header))
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in _MIXIN_TAB)[:32]


def get_wbi_keys(cookie_header: str = "") -> tuple[str, str]:
    data = _get("https://api.bilibili.com/x/web-interface/nav", cookie_header)["data"]
    img = data["wbi_img"]["img_url"]
    sub = data["wbi_img"]["sub_url"]
    img_key = img.rsplit("/", 1)[1].split(".")[0]
    sub_key = sub.rsplit("/", 1)[1].split(".")[0]
    return img_key, sub_key


def wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    mixin = _mixin_key(img_key + sub_key)
    p = dict(params)
    p["wts"] = int(time.time())
    p = {k: p[k] for k in sorted(p)}
    # 过滤特殊字符
    p = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in p.items()}
    query = urllib.parse.urlencode(p)
    p["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return p


# ─────────────────────────────────────────────────────────────────
# 视频搜索
# ─────────────────────────────────────────────────────────────────

def _strip_em(s: str) -> str:
    return re.sub(r"</?em[^>]*>", "", s or "")


def _dur_to_sec(s: str) -> int:
    if not s:
        return 0
    parts = [int(x) for x in s.split(":") if x.isdigit()]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def search_video(keyword: str, cookie_header: str = "",
                 limit: int = 8) -> list[dict]:
    """搜 B站 视频,返回 [{bvid,title,uploader,duration,url}]。"""
    try:
        img_key, sub_key = get_wbi_keys(cookie_header)
        params = wbi_sign(
            {"search_type": "video", "keyword": keyword, "page": 1},
            img_key, sub_key)
        url = ("https://api.bilibili.com/x/web-interface/wbi/search/type?"
               + urllib.parse.urlencode(params))
        data = _get(url, cookie_header)
    except Exception:
        return []
    if data.get("code") != 0:
        return []
    out = []
    for r in (data.get("data", {}).get("result") or [])[:limit]:
        bvid = r.get("bvid")
        if not bvid:
            continue
        out.append({
            "bvid": bvid,
            "title": _strip_em(r.get("title")),
            "uploader": r.get("author") or "",
            "duration": _dur_to_sec(r.get("duration")),
            "url": f"https://www.bilibili.com/video/{bvid}/",
        })
    return out


# ─────────────────────────────────────────────────────────────────
# AI 字幕提取
# ─────────────────────────────────────────────────────────────────

def extract_bvid(url: str) -> str | None:
    m = re.search(r"(BV[0-9A-Za-z]{10})", url)
    return m.group(1) if m else None


def has_subtitle(bvid: str, cookie_header: str) -> bool:
    """轻量检查是否有字幕轨道(不下载字幕正文)。"""
    try:
        view = _get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
                    cookie_header)
        cid, aid = view["data"]["cid"], view["data"]["aid"]
        player = _get(
            f"https://api.bilibili.com/x/player/wbi/v2?aid={aid}&cid={cid}&bvid={bvid}",
            cookie_header)
        return bool(player.get("data", {}).get("subtitle", {}).get("subtitles"))
    except Exception:
        return False


def get_subtitle(bvid: str, cookie_header: str) -> Transcript | None:
    """取 B站 AI/CC 字幕 → Transcript。无字幕或未登录返回 None。"""
    try:
        view = _get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
                    cookie_header)
        cid = view["data"]["cid"]
        aid = view["data"]["aid"]
        player = _get(
            f"https://api.bilibili.com/x/player/wbi/v2?aid={aid}&cid={cid}&bvid={bvid}",
            cookie_header)
        subs = player.get("data", {}).get("subtitle", {}).get("subtitles") or []
        if not subs:
            return None
        sub_url = subs[0].get("subtitle_url") or ""
        if not sub_url:
            return None
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url
        body = _get(sub_url, cookie_header).get("body") or []
        if not body:
            return None
        segs = [Segment(start=float(s["from"]), end=float(s["to"]),
                        text=(s.get("content") or "").strip())
                for s in body if s.get("content")]
        if not segs:
            return None
        return Transcript(segments=segs, has_speakers=False)
    except Exception:
        return None

"""跨平台同款搜索:给定标题/作者/时长,去 YouTube + Apple Podcasts 找同款。

用途:源平台是痛点(小红书下整片 / 抖音要 cookie)且 ≥30 分钟时,
找更好的替代源(尤其 YouTube 可能有字幕 → 免 ASR)。

只负责"搜出候选 + 标时长",是否同款由用户最终判断(见 SKILL.md)。
"""
from __future__ import annotations

import json
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


@dataclass
class Candidate:
    platform: str
    title: str
    uploader: str
    duration: int          # 秒
    url: str
    has_subtitle: bool | None = None   # None=未检测
    delta: int = 0                      # 与源时长差(秒)


def _clean_query(title: str) -> str:
    """从标题提取搜索关键词:去掉【】#标签 等噪音,取前若干字。"""
    t = re.sub(r"[【】\[\]()()#]", " ", title)
    # 去掉常见前后缀
    t = re.sub(r"(完整版|完整|全集|上集|下集|EP\d+|第\d+期)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:40]


def search_youtube(query: str, max_results: int = 8) -> list[Candidate]:
    try:
        r = subprocess.run(
            ["yt-dlp", f"ytsearch{max_results}:{query}",
             "--flat-playlist", "-J", "--no-warnings"],
            capture_output=True, text=True, timeout=90,
        )
        if r.returncode != 0 or not r.stdout:
            return []
        data = json.loads(r.stdout)
    except Exception:
        return []
    out: list[Candidate] = []
    for e in data.get("entries", []):
        dur = e.get("duration")
        if not dur or not e.get("id"):
            continue
        out.append(Candidate(
            platform="YouTube",
            title=e.get("title") or "",
            uploader=e.get("uploader") or e.get("channel") or "",
            duration=int(dur),
            url=f"https://www.youtube.com/watch?v={e['id']}",
        ))
    return out


def search_apple(query: str, max_results: int = 8) -> list[Candidate]:
    """iTunes Search API(公开免认证)。"""
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode({
        "term": query, "entity": "podcastEpisode", "limit": max_results,
    })
    try:
        raw = urllib.request.urlopen(url, timeout=20).read()
        data = json.loads(raw)
    except Exception:
        return []
    out: list[Candidate] = []
    for r in data.get("results", []):
        ms = r.get("trackTimeMillis") or 0
        u = r.get("trackViewUrl") or ""
        if not u or not ms:
            continue
        out.append(Candidate(
            platform="Apple Podcasts",
            title=r.get("trackName") or "",
            uploader=r.get("collectionName") or "",
            duration=int(ms / 1000),
            url=u,
        ))
    return out


def _check_youtube_subtitle(url: str) -> bool:
    """探查 YouTube 候选是否有字幕(决定能否免 ASR)。"""
    try:
        from .downloader import probe
        info = probe(url)
        return info.has_subtitles
    except Exception:
        return False


def search_bilibili(query: str, cookie_header: str = "",
                    max_results: int = 8) -> list[Candidate]:
    """B站 搜索(WBI 签名)。"""
    try:
        from . import bilibili
        rows = bilibili.search_video(query, cookie_header, limit=max_results)
    except Exception:
        return []
    return [Candidate(platform="Bilibili", title=r["title"], uploader=r["uploader"],
                      duration=r["duration"], url=r["url"]) for r in rows]


def find_alternatives(title: str, uploader: str, src_duration: int,
                      *, max_results: int = 5,
                      check_subtitle: bool = True,
                      bili_cookie_header: str = "") -> list[Candidate]:
    """搜 YouTube + Apple + B站,按与源时长接近度排序,返回候选。

    对时长接近(Δ<60s)的 YouTube 候选额外探查字幕(免 ASR 的关键)。
    """
    query = _clean_query(title)
    if uploader and uploader not in query:
        query = f"{query} {uploader}"[:50]

    cands = (search_youtube(query) + search_apple(query)
             + search_bilibili(query, bili_cookie_header))
    for c in cands:
        c.delta = abs(c.duration - src_duration) if src_duration else 10 ** 9
    cands.sort(key=lambda c: c.delta)
    cands = cands[:max_results]

    if check_subtitle:
        for c in cands:
            if c.platform == "YouTube" and c.delta < 60:
                c.has_subtitle = _check_youtube_subtitle(c.url)

    return cands

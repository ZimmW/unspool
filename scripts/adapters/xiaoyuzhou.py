"""小宇宙 adapter。

小宇宙单集页面内嵌完整结构化数据(__NEXT_DATA__ 里的 props.pageProps.episode),
含 title / duration / podcast 名 / 音频直链(enclosure.url)。无 anti-bot,纯 HTTP 抓取即可。
yt-dlp 没有小宇宙 extractor,所以走这个 adapter。
"""
from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")

_PATTERNS = [
    re.compile(r"https?://(?:www\.)?xiaoyuzhoufm\.com/episode/[a-f0-9]+"),
]


def is_supported(url: str) -> bool:
    return any(p.search(url) for p in _PATTERNS)


@dataclass
class XyzEpisode:
    eid: str
    title: str
    uploader: str          # 节目名
    duration: int          # 秒
    audio_url: str
    platform: str = "小宇宙"
    raw: dict[str, Any] = field(default_factory=dict)


def probe(url: str) -> XyzEpisode:
    """抓单集页面,解析 __NEXT_DATA__ 拿到结构化信息。"""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="ignore")

    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.S)
    if not m:
        raise RuntimeError("小宇宙页面解析失败:未找到 __NEXT_DATA__")
    data = json.loads(m.group(1))
    ep = (data.get("props", {}).get("pageProps", {}).get("episode")) or {}
    if not ep:
        raise RuntimeError("小宇宙页面解析失败:未找到 episode 数据")

    enc = ep.get("enclosure") or {}
    audio_url = enc.get("url") or ""
    if not audio_url:
        # 兜底:og:audio
        mm = re.search(r'<meta property="og:audio" content="([^"]+)"', html)
        audio_url = (mm.group(1).replace("&amp;", "&") if mm else "")
    if not audio_url:
        raise RuntimeError("小宇宙单集未找到音频直链")

    pod = ep.get("podcast") or {}
    return XyzEpisode(
        eid=ep.get("eid") or "",
        title=ep.get("title") or "未命名单集",
        uploader=pod.get("title") or "",
        duration=int(ep.get("duration") or 0),
        audio_url=audio_url,
        raw=ep,
    )


def download_audio(ep: XyzEpisode, workdir: Path) -> Path:
    """下载 m4a 音频,ffmpeg 转 mp3。"""
    raw_path = workdir / f"{ep.eid or 'xyz'}.m4a"
    mp3_path = workdir / f"{ep.eid or 'xyz'}.mp3"

    req = urllib.request.Request(ep.audio_url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(raw_path, "wb") as f:
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)

    cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-vn",
           "-acodec", "libmp3lame", "-q:a", "5", str(mp3_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0 or not mp3_path.exists():
        raise RuntimeError(f"ffmpeg 转码失败: {res.stderr[-300:]}")

    raw_path.unlink(missing_ok=True)
    return mp3_path

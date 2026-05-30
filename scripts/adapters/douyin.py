"""抖音/TikTok adapter,基于 Evil0ctal/Douyin_TikTok_Download_API 主分支。

集成方式:
- 用户一次性 git clone Evil0ctal 主分支到固定目录(默认 ~/.总裁速览/vendor/...)
- 我们运行时 sys.path.insert,直接 import 它的 DouyinWebCrawler
- Cookie 自动从用户浏览器(Chrome)抽取并注入 vendor 的 config.yaml
- 解析后返回视频直链 + 元数据,接入主下载流程
"""
from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..cookies import cookies_dict_to_header, export_cookies_for


# ──────────────────────────────────────────────────────────────────
# URL 路由
# ──────────────────────────────────────────────────────────────────

DOUYIN_PATTERNS = [
    re.compile(r"https?://(?:[\w-]+\.)?douyin\.com/"),
    re.compile(r"https?://(?:[\w-]+\.)?iesdouyin\.com/"),
    re.compile(r"https?://v\.douyin\.com/"),
]

TIKTOK_PATTERNS = [
    re.compile(r"https?://(?:[\w-]+\.)?tiktok\.com/"),
    re.compile(r"https?://vm\.tiktok\.com/"),
]


def is_douyin(url: str) -> bool:
    return any(p.search(url) for p in DOUYIN_PATTERNS)


def is_tiktok(url: str) -> bool:
    return any(p.search(url) for p in TIKTOK_PATTERNS)


def is_supported(url: str) -> bool:
    return is_douyin(url) or is_tiktok(url)


# ──────────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────────

@dataclass
class DouyinVideo:
    aweme_id: str
    title: str
    uploader: str
    duration: int                # 秒
    video_url: str               # 视频直链(可能是 mp4 或 m3u8)
    platform: str                # "Douyin" / "TikTok"
    raw: dict[str, Any]


# ──────────────────────────────────────────────────────────────────
# Evil0ctal 路径管理 + cookie 注入
# ──────────────────────────────────────────────────────────────────

DEFAULT_VENDOR_PATH = Path.home() / ".总裁速览" / "vendor" / "Douyin_TikTok_Download_API"


def _ensure_vendor_or_raise(vendor_path: Path) -> None:
    if not (vendor_path / "crawlers" / "douyin" / "web" / "web_crawler.py").exists():
        raise RuntimeError(
            f"抖音解析器(Evil0ctal/Douyin_TikTok_Download_API)未找到。\n"
            f"请运行:\n"
            f"  mkdir -p {vendor_path.parent}\n"
            f"  git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git \\\n"
            f"      {vendor_path}\n"
            f"  cd {vendor_path}\n"
            f"  pip install -r requirements.txt"
        )


def _inject_cookies(vendor_path: Path, cookie_header: str) -> None:
    """把 cookie 字符串写入 vendor 的 config.yaml(替换 Cookie: 那一行)。"""
    cfg = vendor_path / "crawlers" / "douyin" / "web" / "config.yaml"
    txt = cfg.read_text(encoding="utf-8")
    new, n = re.subn(
        r"(\n\s{6}Cookie:\s*)[^\n]+",
        lambda m: m.group(1) + cookie_header,
        txt, count=1,
    )
    if n == 0:
        # 真没匹配到(结构变了),告警但不阻断
        print("⚠️  注入 cookie 失败:vendor config.yaml 结构变更", file=sys.stderr)
        return
    if new != txt:
        cfg.write_text(new, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────
# 主入口:解析 URL → DouyinVideo
# ──────────────────────────────────────────────────────────────────

def probe(url: str, *, vendor_path: Path | None = None,
          browser: str = "chrome", browser_profile: str = "",
          backend: str = "evil0ctal") -> DouyinVideo:
    """同步入口:给 URL 返回元信息(含视频直链)。

    backend: evil0ctal(默认)| joeanamier(备选)
    """
    aweme_id = _extract_aweme_id(url) or _resolve_short_link(url)
    if not aweme_id:
        raise RuntimeError(f"无法从 URL 提取抖音视频 ID: {url}")

    if backend == "joeanamier":
        return _probe_joeanamier(aweme_id, browser, browser_profile)

    # ─── 默认 backend:Evil0ctal ───
    if vendor_path is None:
        vendor_path = DEFAULT_VENDOR_PATH
    _ensure_vendor_or_raise(vendor_path)

    # 先用缓存 cookie 试;失败再 force_refresh 重试一次
    detail = _fetch_detail(aweme_id, vendor_path, browser, browser_profile,
                           force_refresh=False)
    if not detail:
        print("      cookie 可能过期,重新从浏览器提取...", file=sys.stderr)
        detail = _fetch_detail(aweme_id, vendor_path, browser, browser_profile,
                               force_refresh=True)
    if not detail:
        raise RuntimeError("抖音 API 返回为空(cookie 失效或视频不可访问)")

    # 抽字段
    video = detail.get("video") or {}
    play_addr = video.get("play_addr") or {}
    url_list = play_addr.get("url_list") or []
    direct_url = url_list[0] if url_list else ""
    if not direct_url:
        raise RuntimeError("抖音返回数据中没有视频直链")

    return DouyinVideo(
        aweme_id=str(detail.get("aweme_id") or aweme_id),
        title=detail.get("desc") or "未命名抖音视频",
        uploader=((detail.get("author") or {}).get("nickname") or ""),
        duration=int((detail.get("duration") or video.get("duration") or 0) // 1000),
        video_url=direct_url,
        platform="Douyin",
        raw=detail,
    )


def _probe_joeanamier(aweme_id: str, browser: str, profile: str) -> DouyinVideo:
    """用 JoeanAmier 后端解析,失败时 force_refresh cookie 重试一次。"""
    from . import douyin_joeanamier as jtt

    def _run(force_refresh: bool):
        cookies = export_cookies_for("douyin", browser=browser, profile=profile,
                                     force_refresh=force_refresh)
        if not cookies:
            raise RuntimeError(f"未从 {browser} 抽到 douyin cookie")
        return jtt.fetch_detail(aweme_id, cookies)

    try:
        info = _run(force_refresh=False)
    except Exception as e:
        print(f"      JoeanAmier 首次失败({e}),刷新 cookie 重试...", file=sys.stderr)
        info = _run(force_refresh=True)

    return DouyinVideo(
        aweme_id=aweme_id,
        title=info["title"],
        uploader=info["uploader"],
        duration=info["duration_sec"],
        video_url=info["video_url"],
        platform="Douyin",
        raw=info,
    )


def _fetch_detail(aweme_id: str, vendor_path: Path, browser: str,
                  profile: str, *, force_refresh: bool) -> dict:
    """抽 cookie → 注入 → 调 Evil0ctal,返回 aweme_detail dict(失败返回 {})。"""
    cookies = export_cookies_for("douyin", browser=browser, profile=profile,
                                 force_refresh=force_refresh)
    if not cookies:
        raise RuntimeError(
            f"未从 {browser} 抽到任何 douyin cookie。"
            f"请先在浏览器里访问一次 douyin.com(不必登录)。"
        )
    _inject_cookies(vendor_path, cookies_dict_to_header(cookies))

    if str(vendor_path) not in sys.path:
        sys.path.insert(0, str(vendor_path))
    from crawlers.douyin.web.web_crawler import DouyinWebCrawler  # type: ignore

    async def _run() -> dict:
        dc = DouyinWebCrawler()
        return await dc.fetch_one_video(aweme_id=aweme_id)

    try:
        data = asyncio.run(_run())
    except Exception:
        return {}
    return (data or {}).get("aweme_detail") or {}


_AWEME_ID_RE = re.compile(r"/video/(\d+)|aweme_id=(\d+)|/note/(\d+)")


def _extract_aweme_id(url: str) -> str | None:
    m = _AWEME_ID_RE.search(url)
    if not m:
        return None
    for g in m.groups():
        if g:
            return g
    return None


def _resolve_short_link(url: str) -> str | None:
    """v.douyin.com 短链 follow 重定向后提取 aweme_id。"""
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
    })
    try:
        # follow redirect
        with urllib.request.urlopen(req, timeout=15) as r:
            final_url = r.geturl()
        return _extract_aweme_id(final_url)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────
# 下载(把视频流落地为本地音频文件,供 ASR 使用)
# ──────────────────────────────────────────────────────────────────

def download_audio(video: DouyinVideo, workdir: Path) -> Path:
    """下载视频直链并用 ffmpeg 抽 mp3。"""
    import subprocess
    import urllib.request

    raw_path = workdir / f"{video.aweme_id}.raw"
    mp3_path = workdir / f"{video.aweme_id}.mp3"

    # 抖音视频直链需要带 Referer 才能访问
    req = urllib.request.Request(video.video_url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
    })
    with urllib.request.urlopen(req, timeout=120) as r, open(raw_path, "wb") as f:
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)

    # ffmpeg 抽 mp3
    cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-vn",
           "-acodec", "libmp3lame", "-q:a", "5", str(mp3_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not mp3_path.exists():
        raise RuntimeError(f"ffmpeg 抽音频失败: {r.stderr[-300:]}")

    raw_path.unlink(missing_ok=True)
    return mp3_path

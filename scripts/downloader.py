"""yt-dlp 封装:探查元信息、下载字幕或音频。"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MediaInfo:
    url: str
    title: str
    uploader: str
    duration: int                 # 秒
    extractor: str                # yt-dlp 的平台标识
    chapters: list[dict[str, Any]] = field(default_factory=list)
    has_subtitles: bool = False
    manual_sub_langs: list[str] = field(default_factory=list)   # 用户上传
    auto_sub_langs: list[str] = field(default_factory=list)     # 自动生成
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def subtitle_langs(self) -> list[str]:
        return self.manual_sub_langs + [l for l in self.auto_sub_langs
                                        if l not in self.manual_sub_langs]


# 手工字幕优先级:中文 > 英文(用户上传的可信)
MANUAL_LANG_PRIORITY = ["zh-Hans", "zh-CN", "zh", "zh-Hant", "en"]
# 自动字幕只选"原始"语言。YouTube 把同一份原始 auto-caption 翻译成几百种;
# 翻译版会触发限流且质量差。优先 en(最常见原始语种),其次 zh。
AUTO_LANG_PRIORITY = ["en", "zh", "zh-Hans", "zh-CN"]


def _cookies_args(cookies_cfg: dict | str | None) -> list[str]:
    """返回 yt-dlp 的 cookie 参数(仅在确实需要 cookie 时调用)。

    策略:默认不带 cookie(公开内容不需要),只有第一次尝试失败后才回退到这里。
    用缓存的 cookies.txt 文件,避免 `--cookies-from-browser` 每次弹 Keychain 密码。

    优先级:
      1. 用户手动指定 cookies_file
      2. from_browser → 缓存的 cookies.txt(首次导出会弹一次密码)
    """
    if not cookies_cfg:
        return []
    if isinstance(cookies_cfg, str):
        return ["--cookies", cookies_cfg] if Path(cookies_cfg).exists() else []
    cf = cookies_cfg.get("cookies_file")
    if cf and Path(cf).exists():
        return ["--cookies", str(cf)]
    fb = cookies_cfg.get("from_browser")
    if fb:
        from .cookies import ensure_cookies_file
        profile = cookies_cfg.get("browser_profile") or ""
        cookie_file = ensure_cookies_file(browser=fb, profile=profile)
        if cookie_file and cookie_file.exists():
            return ["--cookies", str(cookie_file)]
    return []


def probe(url: str, cookies_cfg: dict | str | None = None) -> MediaInfo:
    """调用 yt-dlp --dump-json 拉元信息。

    cookies_cfg 可以是:
      - dict(cookies 配置块,完整)
      - str(单纯的 cookies.txt 路径,向后兼容)
      - None
    """
    # 向后兼容:旧调用方式传 str(cookies_file 路径)
    if isinstance(cookies_cfg, str):
        cookies_cfg = {"cookies_file": cookies_cfg}

    def _try(cookie_args: list[str]) -> subprocess.CompletedProcess:
        cmd = ["yt-dlp", "-J", "--no-warnings", "--skip-download"]
        cmd += cookie_args
        cmd.append(url)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # 先不带 cookie(公开内容);失败再带 cookie 重试一次
    result = _try([])
    if result.returncode != 0:
        cargs = _cookies_args(cookies_cfg)
        if cargs:
            result = _try(cargs)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp probe failed: {result.stderr.strip()[:500]}")

    data = json.loads(result.stdout)

    subs = data.get("subtitles") or {}
    auto_subs = data.get("automatic_captions") or {}
    manual = list(subs.keys())
    auto = list(auto_subs.keys())

    return MediaInfo(
        url=url,
        title=data.get("title") or "未命名",
        # 注意:不要用 uploader_id —— 小红书等平台它是无意义的哈希 ID
        uploader=(data.get("uploader") or data.get("channel")
                  or data.get("creator") or data.get("artist") or ""),
        duration=int(data.get("duration") or 0),
        extractor=data.get("extractor_key") or data.get("extractor") or "",
        chapters=data.get("chapters") or [],
        has_subtitles=bool(manual or auto),
        manual_sub_langs=manual,
        auto_sub_langs=auto,
        description=data.get("description") or "",
        raw=data,
    )


def download_subtitle(url: str, workdir: Path, info: MediaInfo,
                      cookies_cfg: dict | str | None = None) -> Path | None:
    """下载最优字幕,转 vtt 后返回文件路径。无可用字幕返回 None。"""
    if isinstance(cookies_cfg, str):
        cookies_cfg = {"cookies_file": cookies_cfg}
    # 1) 先尝试手工上传字幕(write-subs)
    for lang in MANUAL_LANG_PRIORITY:
        if lang in info.manual_sub_langs:
            vtt = _try_download(url, workdir, lang, auto=False,
                                cookies_cfg=cookies_cfg)
            if vtt:
                return vtt
    # 兜底:任何手工字幕
    for lang in info.manual_sub_langs:
        vtt = _try_download(url, workdir, lang, auto=False,
                            cookies_cfg=cookies_cfg)
        if vtt:
            return vtt

    # 2) 退而求其次,用自动字幕的"原始"语言
    for lang in AUTO_LANG_PRIORITY:
        if lang in info.auto_sub_langs:
            vtt = _try_download(url, workdir, lang, auto=True,
                                cookies_cfg=cookies_cfg)
            if vtt:
                return vtt

    return None


def _try_download(url: str, workdir: Path, lang: str, auto: bool,
                  cookies_cfg: dict | None) -> Path | None:
    out_tpl = str(workdir / "%(id)s.%(ext)s")
    flag = "--write-auto-subs" if auto else "--write-subs"
    cmd = [
        "yt-dlp", "--skip-download", flag,
        "--sub-langs", lang, "--sub-format", "vtt",
        "-o", out_tpl, "--no-warnings",
    ]
    # 字幕是公开资源,不带 cookie(避免 Keychain 弹窗)
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return None
    vtts = list(workdir.glob("*.vtt"))
    return vtts[0] if vtts else None


def download_audio(url: str, workdir: Path,
                   cookies_cfg: dict | str | None = None) -> Path:
    """下载音频并转 mp3。失败抛异常。

    先不带 cookie(公开内容,避免 Keychain 弹窗);失败再带 cookie 重试。
    """
    if isinstance(cookies_cfg, str):
        cookies_cfg = {"cookies_file": cookies_cfg}
    out_tpl = str(workdir / "%(id)s.%(ext)s")

    def _try(cookie_args: list[str]) -> subprocess.CompletedProcess:
        cmd = [
            "yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
            "-o", out_tpl, "--no-warnings",
        ]
        cmd += cookie_args
        cmd.append(url)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    result = _try([])
    if result.returncode != 0:
        cargs = _cookies_args(cookies_cfg)
        if cargs:
            result = _try(cargs)
    if result.returncode != 0:
        raise RuntimeError(f"音频下载失败: {result.stderr.strip()[:500]}")

    mp3s = list(workdir.glob("*.mp3"))
    if not mp3s:
        raise RuntimeError("音频下载完成但找不到 mp3 文件")
    return mp3s[0]

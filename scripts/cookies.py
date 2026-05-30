"""跨浏览器 cookie 提取工具。

yt-dlp 的 `--cookies-from-browser` 能解密 Mac Chrome 的 Keychain 加密 cookies,
我们就借它一次,导出标准 Netscape cookies.txt,再 parse 出我们要的部分。

支持指定 profile(默认让 yt-dlp 自己选最新一个)。
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path


# cookie 缓存目录。缓存能避免每次跑都触发 macOS Keychain 密码弹窗。
CACHE_DIR = Path.home() / ".总裁速览" / "cache"
# 缓存有效期(小时)。设得很长(30 天):cookie 实际能用很久,
# 不靠时间过期,而是靠"用缓存失败 → force_refresh 重新提取"来更新。
# 这样平时几乎不会触发 Keychain 密码弹窗。
CACHE_MAX_AGE_HOURS = 24 * 30


def _cache_path(domain_keyword: str, browser: str) -> Path:
    return CACHE_DIR / f"cookies_{domain_keyword}_{browser}.json"


def _load_cache(domain_keyword: str, browser: str,
                max_age_hours: float) -> dict[str, str] | None:
    p = _cache_path(domain_keyword, browser)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - obj.get("ts", 0) > max_age_hours * 3600:
            return None
        cookies = obj.get("cookies") or {}
        return cookies or None
    except Exception:
        return None


def _save_cache(domain_keyword: str, browser: str,
                cookies: dict[str, str]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(domain_keyword, browser).write_text(
            json.dumps({"ts": time.time(), "cookies": cookies},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def export_cookies_for(domain_keyword: str, *,
                       browser: str = "chrome",
                       profile: str = "",
                       force_refresh: bool = False,
                       max_age_hours: float = CACHE_MAX_AGE_HOURS) -> dict[str, str]:
    """从浏览器导出某域名相关的 cookie dict(name → value)。

    带本地缓存:命中缓存就不触发浏览器解密(避免 macOS Keychain 密码弹窗)。

    Args:
        domain_keyword: 域名关键字,如 "douyin"、"bilibili"
        browser: chrome / safari / firefox / edge / brave
        profile: Chrome profile 名,如 "Profile 3"。空则用 yt-dlp 默认选择
        force_refresh: 跳过缓存强制重新提取(cookie 失效时用)
        max_age_hours: 缓存有效期

    Returns:
        {name: value} dict。空 dict 表示没找到任何 cookie 或导出失败。
    """
    if not force_refresh:
        cached = _load_cache(domain_keyword, browser, max_age_hours)
        if cached:
            return cached

    spec = f"{browser}:{profile}" if profile else browser
    tmpdir = Path(tempfile.mkdtemp(prefix="cookies_"))
    cookies_path = tmpdir / "cookies.txt"

    # yt-dlp 需要一个"目标 URL"配合 export,这里随便给一个 generic URL
    # --cookies <path> 会同时把内部 cookie jar 写到该文件
    seed_url = f"https://www.{domain_keyword}.com/"
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", spec,
        "--cookies", str(cookies_path),
        "--skip-download",
        "--no-warnings",
        "--simulate",
        seed_url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception:
        return {}

    if not cookies_path.exists():
        return {}

    result: dict[str, str] = {}
    for line in cookies_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        host, _, _, _, _, name, value = parts[:7]
        if domain_keyword in host and value:
            result[name] = value

    try:
        cookies_path.unlink()
        tmpdir.rmdir()
    except Exception:
        pass

    if result:
        _save_cache(domain_keyword, browser, result)

    return result


def cookies_dict_to_header(cookies: dict[str, str]) -> str:
    """dict → "k1=v1; k2=v2; ..." 形式的 Cookie header 字符串。"""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def ensure_cookies_file(*, browser: str = "chrome", profile: str = "",
                        force_refresh: bool = False,
                        max_age_hours: float = CACHE_MAX_AGE_HOURS) -> Path | None:
    """导出全量浏览器 cookies 到缓存的 Netscape cookies.txt,返回路径。

    给 yt-dlp 主路径用(`--cookies <file>`),避免每次 `--cookies-from-browser`
    触发 macOS Keychain 密码弹窗(尤其后台运行时会卡死)。

    首次导出会弹一次密码;之后 max_age_hours 内复用缓存文件,零弹窗。
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"cookies_all_{browser}.txt"

    if (not force_refresh and cache_file.exists()
            and time.time() - cache_file.stat().st_mtime < max_age_hours * 3600):
        return cache_file

    spec = f"{browser}:{profile}" if profile else browser
    # yt-dlp 需要一个种子 URL 才会导出 cookie jar;给个轻量的
    cmd = [
        "yt-dlp", "--cookies-from-browser", spec,
        "--cookies", str(cache_file),
        "--skip-download", "--no-warnings", "--simulate",
        "https://www.youtube.com/",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception:
        return cache_file if cache_file.exists() else None

    return cache_file if cache_file.exists() else None

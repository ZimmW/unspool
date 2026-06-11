"""预检:agent 收到链接后先跑这个,决定直接处理还是先找替代源。

规则(与产品 owner 敲定):
- 时长 < 30 分钟 → DIRECT,直接 scripts.run
- 有字幕(YouTube)→ DIRECT(能免 ASR)
- ≥30 分钟 且 无字幕:
    - 源是痛点平台(小红书/抖音)→ 搜 YouTube+Apple 同款 → 列候选给用户选
    - 源是快平台(B站/小宇宙/Apple/YouTube音频)→ 也搜(长内容找到字幕版能省 ASR)
    - 只把"确实更好"的候选(有字幕 / 帮小红书逃下载)摆出来

输出:人类可读 + 机器可解析(DECISION: 行)。
用法:python -m scripts.preflight "<url>"
"""
from __future__ import annotations

import sys

from . import downloader, search
from .adapters import douyin as douyin_adapter
from .adapters import xiaoyuzhou as xiaoyuzhou_adapter
from .config import load_config

THIRTY_MIN = 30 * 60


def _probe_meta(url: str, cfg: dict) -> dict:
    """统一探查源元信息:platform / title / uploader / duration / has_subtitle。"""
    cookies_cfg = cfg.get("cookies") or {}
    if douyin_adapter.is_supported(url):
        browser = cookies_cfg.get("from_browser") or "chrome"
        profile = cookies_cfg.get("browser_profile") or ""
        backend = (cfg.get("douyin") or {}).get("backend", "evil0ctal")
        v = douyin_adapter.probe(url, browser=browser, browser_profile=profile,
                                 backend=backend)
        return {"platform": v.platform, "title": v.title, "uploader": v.uploader,
                "duration": v.duration, "has_subtitle": False}
    if xiaoyuzhou_adapter.is_supported(url):
        ep = xiaoyuzhou_adapter.probe(url)
        return {"platform": ep.platform, "title": ep.title, "uploader": ep.uploader,
                "duration": ep.duration, "has_subtitle": False}
    info = downloader.probe(url, cookies_cfg=cookies_cfg)
    from .run import _platform_name
    has_sub = info.has_subtitles
    # B站:登录后检测 AI 字幕(能免 ASR)
    if not has_sub and info.extractor.lower() == "bilibili":
        has_sub = _bili_has_subtitle(url, cookies_cfg)
    return {"platform": _platform_name(info.extractor), "title": info.title,
            "uploader": info.uploader, "duration": info.duration,
            "has_subtitle": has_sub}


def _bili_cookie_header(cookies_cfg: dict) -> str:
    from .cookies import cookies_dict_to_header, export_cookies_for
    browser = cookies_cfg.get("from_browser") or "chrome"
    profile = cookies_cfg.get("browser_profile") or ""
    try:
        return cookies_dict_to_header(
            export_cookies_for("bilibili", browser=browser, profile=profile))
    except Exception:
        return ""


def _bili_has_subtitle(url: str, cookies_cfg: dict) -> bool:
    from . import bilibili
    bvid = bilibili.extract_bvid(url)
    if not bvid:
        return False
    ck = _bili_cookie_header(cookies_cfg)
    return "SESSDATA" in ck and bilibili.has_subtitle(bvid, ck)


def _fmt_min(sec: int) -> str:
    return f"{sec // 60}min"


def preflight(url: str, config_path: str | None = None) -> None:
    cfg = load_config(config_path)
    meta = _probe_meta(url, cfg)
    plat, title, uploader = meta["platform"], meta["title"], meta["uploader"]
    dur, has_sub = meta["duration"], meta["has_subtitle"]

    print(f"SOURCE: {plat} · {uploader or '—'} · {_fmt_min(dur)} · "
          f"{'有字幕' if has_sub else '无字幕'}")
    if not has_sub:
        # 事前成本可见:无字幕 → 要 ASR(按音频时长计费),agent 把这行转述给用户
        print(f"ASR_NEEDED: ~{_fmt_min(dur)} 音频需语音转写(按音频时长计费)")

    # 规则 1:短内容直接干
    if dur < THIRTY_MIN:
        print("DECISION: DIRECT(<30 分钟,直接处理)")
        return
    # 规则 2:有字幕直接干(免 ASR)
    if has_sub:
        print("DECISION: DIRECT(有字幕,直接处理免 ASR)")
        return

    # 规则 3:≥30 分钟且无字幕 → 找替代
    print(f"SEARCHING: ≥30 分钟无字幕,搜 YouTube + Apple + B站 同款...",
          file=sys.stderr)
    cookies_cfg = cfg.get("cookies") or {}
    cands = search.find_alternatives(
        title, uploader, dur,
        bili_cookie_header=_bili_cookie_header(cookies_cfg))

    # 痛点源:小红书(下整片)/ 抖音(cookie+脆),替代到快平台都划算
    source_painful = any(x in plat for x in ["小红书", "抖音"]) or \
        any(x in plat.lower() for x in ["xiaohongshu", "douyin", "tiktok"])
    # 时长接近度上限 20 分钟:超出的基本是同作者的"别的内容",滤掉避免误选
    MAX_DELTA = 20 * 60
    better = []
    for c in cands:
        if c.delta > MAX_DELTA:
            continue
        if c.has_subtitle or source_painful:
            better.append(c)

    if not better:
        print("DECISION: DIRECT(未找到更好替代,用原链接处理)")
        return

    print("DECISION: CHOOSE(找到可能更好的替代源,请用户选择)")
    print("ALTERNATIVES:")
    for i, c in enumerate(better, 1):
        sub = "有字幕" if c.has_subtitle else ("未知" if c.has_subtitle is None else "无字幕")
        longer = " ⚠可能是更长全集" if c.duration > dur + 120 else ""
        print(f"  {i}. [{c.platform}] {_fmt_min(c.duration)}"
              f"(Δ{c.delta}s,{sub}){longer}  {c.title[:45]}")
        print(f"     {c.url}")
    print(f"  0. 用原链接 {plat} 处理")


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="preflight")
    p.add_argument("url")
    p.add_argument("--config")
    args = p.parse_args(argv)
    try:
        preflight(args.url, args.config)
    except Exception as e:
        print(f"PREFLIGHT_ERROR: {e}", file=sys.stderr)
        # 预检失败不阻断:让 agent 直接处理
        print("DECISION: DIRECT(预检失败,回退直接处理)")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

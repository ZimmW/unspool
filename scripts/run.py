"""总裁速览 主入口。

用法:
    python -m scripts.run <URL> [--config /path/to/config.yaml]
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
import traceback
from pathlib import Path

from . import (asr, bilibili, chapters, downloader, output_feishu, output_local,
               output_notion, summarizer)
from .adapters import douyin as douyin_adapter
from .adapters import xiaoyuzhou as xiaoyuzhou_adapter
from .config import load_config
from .cookies import cookies_dict_to_header, export_cookies_for
from .transcript import parse_vtt


def _try_bilibili_subtitle(url: str, cookies_cfg: dict):
    """尝试取 B站 AI 字幕(需登录)。失败返回 None,流程回退 ASR。"""
    bvid = bilibili.extract_bvid(url)
    if not bvid:
        return None
    browser = cookies_cfg.get("from_browser") or "chrome"
    profile = cookies_cfg.get("browser_profile") or ""
    try:
        cookies = export_cookies_for("bilibili", browser=browser, profile=profile)
        if "SESSDATA" not in cookies:
            return None  # 未登录,取不到 AI 字幕
        return bilibili.get_subtitle(bvid, cookies_dict_to_header(cookies))
    except Exception:
        return None


# yt-dlp extractor key → 中文平台名(小写匹配,容忍大小写差异)
PLATFORM_NAMES = {
    "youtube": "YouTube",
    "bilibili": "Bilibili",
    "tiktok": "TikTok",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "xiaohongshuvideo": "小红书",
    "xiaoyuzhou": "小宇宙",
    "applepodcasts": "Apple Podcasts",
    "ximalaya": "喜马拉雅",
    "kuaishou": "快手",
    "weibo": "微博",
}


def _platform_name(extractor: str) -> str:
    if not extractor:
        return "未知平台"
    return PLATFORM_NAMES.get(extractor.lower(), extractor)


def process(url: str, config_path: str | None = None) -> dict:
    start_time = time.time()
    cfg = load_config(config_path)
    cookies_cfg = cfg.get("cookies") or {}

    # ──── 路由分支:特殊平台走专用 adapter,其他走 yt-dlp ────
    if douyin_adapter.is_supported(url):
        return _process_via_douyin_adapter(url, cfg, cookies_cfg, start_time)
    if xiaoyuzhou_adapter.is_supported(url):
        return _process_via_xiaoyuzhou_adapter(url, cfg, start_time)

    print(f"[1/6] 探查链接: {url}", file=sys.stderr)
    info = downloader.probe(url, cookies_cfg=cookies_cfg)
    platform = _platform_name(info.extractor)
    print(f"      平台={platform} 时长={info.duration}s 字幕={info.has_subtitles}",
          file=sys.stderr)

    if info.duration > 4 * 3600:
        print("⚠️  内容时长超过 4 小时,处理可能不稳定。", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="zongcai_") as tmp:
        workdir = Path(tmp)

        print("[2/6] 获取 transcript", file=sys.stderr)
        transcript = None
        if info.has_subtitles:
            vtt = downloader.download_subtitle(url, workdir, info, cookies_cfg)
            if vtt:
                transcript = parse_vtt(vtt)
                print(f"      ✓ 字幕路径 ({len(transcript.segments)} 段)",
                      file=sys.stderr)

        # B站 AI 字幕(登录后可取,免 ASR)
        if transcript is None and info.extractor.lower() == "bilibili":
            t = _try_bilibili_subtitle(url, cookies_cfg)
            if t:
                transcript = t
                print(f"      ✓ B站 AI 字幕路径 ({len(t.segments)} 段,免 ASR)",
                      file=sys.stderr)

        if transcript is None:
            print("      字幕不可用,走 ASR", file=sys.stderr)
            audio = downloader.download_audio(url, workdir, cookies_cfg)
            transcript = asr.transcribe(audio, cfg["asr"])
            print(f"      ✓ ASR 完成 ({len(transcript.segments)} 段,"
                  f"多说话人={transcript.has_speakers})", file=sys.stderr)

        if not transcript.segments or not transcript.full_text.strip():
            raise RuntimeError("无法获取字幕或音频,请检查链接或换一个视频试试。")

        print("[3/6] 章节切分", file=sys.stderr)
        # 一律走自动生成:LLM 在每个时间段内自己切章节,保持密章节风格一致。
        # 平台原生 / shownotes 时间戳作为可选信息(目前不强制采用,后续可加"借鉴标题"逻辑)。
        chs = None
        n_native = len(chapters.from_native(info.chapters, info.duration) or [])
        n_shownotes = len(chapters.from_shownotes(info.description, info.duration) or [])
        if n_native or n_shownotes:
            print(f"      原生章节={n_native},shownotes={n_shownotes}(忽略,走自动生成)",
                  file=sys.stderr)
        print("      走 inline 自动生成(LLM 在每段内自己切章节)",
              file=sys.stderr)

        print("[4/6] 生成文档(调用 Claude)", file=sys.stderr)
        threshold = cfg.get("long_content", {}).get(
            "per_chapter_threshold_minutes", 60)
        markdown = summarizer.build_doc(
            transcript=transcript,
            title=info.title,
            platform=platform,
            uploader=info.uploader,
            url=url,
            duration=info.duration,
            chapters=chs,
            llm_cfg=cfg["llm"],
            per_chapter_threshold_minutes=threshold,
            start_time=start_time,
        )

    return _do_outputs(cfg, markdown, info.title, platform, info.duration)


def _process_via_douyin_adapter(url: str, cfg: dict, cookies_cfg: dict,
                                start_time: float) -> dict:
    """抖音/TikTok 专用流程,绕过 yt-dlp。"""
    browser = cookies_cfg.get("from_browser") or "chrome"
    profile = cookies_cfg.get("browser_profile") or ""
    backend = (cfg.get("douyin") or {}).get("backend", "evil0ctal")

    print(f"[1/6] 探查链接(抖音/TikTok adapter,backend={backend}): {url}",
          file=sys.stderr)
    try:
        video = douyin_adapter.probe(url, browser=browser, browser_profile=profile,
                                     backend=backend)
    except Exception as e:
        raise RuntimeError(f"抖音解析失败: {e}") from e
    platform = video.platform
    print(f"      平台={platform} 时长={video.duration}s 标题={video.title[:40]}",
          file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="zongcai_") as tmp:
        workdir = Path(tmp)

        print("[2/6] 下载音频(经视频流抽 mp3)", file=sys.stderr)
        audio = douyin_adapter.download_audio(video, workdir)
        print(f"      ✓ 音频文件 {audio.stat().st_size // 1024} KB", file=sys.stderr)

        print("      走 ASR", file=sys.stderr)
        transcript = asr.transcribe(audio, cfg["asr"])
        print(f"      ✓ ASR 完成 ({len(transcript.segments)} 段,"
              f"多说话人={transcript.has_speakers})", file=sys.stderr)

        if not transcript.segments or not transcript.full_text.strip():
            raise RuntimeError("ASR 返回为空")

        print("[3/6] 章节切分:走 inline 自动生成(LLM 在每段内自己切章节)",
              file=sys.stderr)

        print("[4/6] 生成文档(调用 Claude)", file=sys.stderr)
        threshold = cfg.get("long_content", {}).get(
            "per_chapter_threshold_minutes", 60)
        markdown = summarizer.build_doc(
            transcript=transcript,
            title=video.title,
            platform=platform,
            uploader=video.uploader,
            url=url,
            duration=video.duration,
            chapters=None,
            llm_cfg=cfg["llm"],
            per_chapter_threshold_minutes=threshold,
            start_time=start_time,
        )

    return _do_outputs(cfg, markdown, video.title, platform, video.duration)


def _process_via_xiaoyuzhou_adapter(url: str, cfg: dict, start_time: float) -> dict:
    """小宇宙专用流程(yt-dlp 不支持,自抓单集音频)。"""
    print(f"[1/6] 探查链接(小宇宙 adapter): {url}", file=sys.stderr)
    try:
        ep = xiaoyuzhou_adapter.probe(url)
    except Exception as e:
        raise RuntimeError(f"小宇宙解析失败: {e}") from e
    print(f"      平台={ep.platform} · {ep.uploader} 时长={ep.duration}s "
          f"标题={ep.title[:40]}", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="zongcai_") as tmp:
        workdir = Path(tmp)
        print("[2/6] 下载音频", file=sys.stderr)
        audio = xiaoyuzhou_adapter.download_audio(ep, workdir)
        print(f"      ✓ 音频 {audio.stat().st_size // 1024} KB,走 ASR",
              file=sys.stderr)
        transcript = asr.transcribe(audio, cfg["asr"])
        print(f"      ✓ ASR 完成 ({len(transcript.segments)} 段,"
              f"多说话人={transcript.has_speakers})", file=sys.stderr)
        if not transcript.segments or not transcript.full_text.strip():
            raise RuntimeError("ASR 返回为空")

        print("[3/6] 章节切分:走 inline 自动生成", file=sys.stderr)
        print("[4/6] 生成文档(调用 Claude)", file=sys.stderr)
        threshold = cfg.get("long_content", {}).get(
            "per_chapter_threshold_minutes", 60)
        markdown = summarizer.build_doc(
            transcript=transcript, title=ep.title, platform=ep.platform,
            uploader=ep.uploader, url=url, duration=ep.duration,
            chapters=None, llm_cfg=cfg["llm"],
            per_chapter_threshold_minutes=threshold, start_time=start_time,
        )

    return _do_outputs(cfg, markdown, ep.title, ep.platform, ep.duration)


def _do_outputs(cfg: dict, markdown: str, title: str, platform: str,
                duration: int) -> dict:
    """共用的输出步骤(本地 md + 飞书),给所有分支用。"""
    result: dict = {"title": title, "duration": duration, "platform": platform}
    out_cfg = cfg.get("output", {})

    if out_cfg.get("local", {}).get("enabled"):
        print("[5/6] 写本地 Markdown", file=sys.stderr)
        local_path = output_local.save(
            markdown=markdown, out_dir=out_cfg["local"]["path"],
            title=title, platform=platform, duration_seconds=duration,
            frontmatter=out_cfg["local"].get("frontmatter", True),
        )
        result["local_path"] = str(local_path)
        print(f"      ✓ {local_path}", file=sys.stderr)

    if out_cfg.get("feishu", {}).get("enabled"):
        print("[6/6] 上传飞书", file=sys.stderr)
        try:
            url_feishu = output_feishu.upload(
                markdown=markdown,
                filename=Path(result.get("local_path", title)).stem
                         if result.get("local_path") else title,
                feishu_cfg=out_cfg["feishu"],
            )
            result["feishu_url"] = url_feishu
            print(f"      ✓ {url_feishu}", file=sys.stderr)
        except Exception as e:
            result["feishu_error"] = str(e)
            print(f"      ✗ 飞书失败: {e}", file=sys.stderr)

    if out_cfg.get("notion", {}).get("enabled"):
        print("[6/6] 上传 Notion", file=sys.stderr)
        try:
            url_notion = output_notion.upload(
                markdown=markdown, filename=title, notion_cfg=out_cfg["notion"])
            result["notion_url"] = url_notion
            print(f"      ✓ {url_notion}", file=sys.stderr)
        except Exception as e:
            result["notion_error"] = str(e)
            print(f"      ✗ Notion 失败: {e}", file=sys.stderr)

    return result


def format_receipt(result: dict) -> str:
    lines = []
    if "feishu_url" in result:
        lines.append(f"✅ 完成 → {result['feishu_url']}")
    elif "feishu_error" in result:
        lines.append(f"⚠️ 完成(飞书上传失败:{result['feishu_error']})")
    else:
        lines.append("✅ 完成")
    if "notion_url" in result:
        lines.append(f"Notion:{result['notion_url']}")
    elif "notion_error" in result:
        lines.append(f"⚠️ Notion 上传失败:{result['notion_error']}")
    if "local_path" in result:
        lines.append(f"本地:{result['local_path']}")
    mins = result["duration"] // 60
    secs = result["duration"] % 60
    lines.append("")
    lines.append(f"{result['title']} · {mins} 分 {secs} 秒")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="总裁速览")
    parser.add_argument("url", help="视频/音频链接")
    parser.add_argument("--config", help="配置文件路径(默认 ~/.总裁速览/config.yaml)")
    args = parser.parse_args(argv)

    try:
        result = process(args.url, args.config)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"❌ 处理失败: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(format_receipt(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

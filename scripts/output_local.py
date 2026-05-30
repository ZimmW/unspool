"""本地 Markdown 输出。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')
_TITLE_MAX_CHARS = 60      # 标题在文件名里的最大字符数


def _sanitize(s: str) -> str:
    s = _ILLEGAL.sub("_", s).strip()
    # 折叠多个空白成一个空格
    s = re.sub(r"\s+", " ", s)
    return s


def _short_title(title: str) -> str:
    """从可能很长的"标题/描述"里取一个文件名友好的简短标题。

    抖音/小红书视频的 title 经常是几百字的文案。策略:
    1. 取第一行(以 \\n 或 ! 或 ? 或 . 或 ;  断开)
    2. 截断到 _TITLE_MAX_CHARS 字符
    """
    title = title.strip()
    # 按句末符号取第一段
    for sep in ["\n", "。", "!", "?", "！", "？", ";", "；"]:
        if sep in title:
            title = title.split(sep, 1)[0]
            break
    title = _sanitize(title)
    if len(title) > _TITLE_MAX_CHARS:
        title = title[:_TITLE_MAX_CHARS].rstrip() + "…"
    return title


def _yaml_str(v: str) -> str:
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _frontmatter(markdown: str, platform: str, duration_seconds: int) -> str:
    """生成 Obsidian 友好的 YAML frontmatter(只用于本地文件)。

    平台/时长由调用方传入;原链接从正文表头解析;日期取当天。
    """
    mins = max(1, round(duration_seconds / 60))
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = ["---",
             f"平台: {_yaml_str(platform)}",
             f"时长分钟: {mins}",
             f"日期: {date_str}"]
    m = re.search(r"\*\*原链接\*\*[:：]\s*(\S+)", markdown)
    if m:
        lines.append(f"原链接: {_yaml_str(m.group(1))}")
    lines += ["---", ""]
    return "\n".join(lines)


def save(*, markdown: str, out_dir: str, title: str, platform: str,
         duration_seconds: int, frontmatter: bool = True) -> Path:
    if frontmatter:
        markdown = _frontmatter(markdown, platform, duration_seconds) + markdown
    dir_path = Path(out_dir).expanduser()
    dir_path.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    mins = max(1, round(duration_seconds / 60))
    short = _short_title(title)
    filename = f"{date_str}_[{_sanitize(platform)}]_{short}_{mins}min.md"
    # 兜底:文件系统单元名限制约 255 字节,中文 3 byte/字
    if len(filename.encode("utf-8")) > 200:
        # 进一步截断
        short = short[:30] + "…"
        filename = f"{date_str}_[{_sanitize(platform)}]_{short}_{mins}min.md"
    path = dir_path / filename
    path.write_text(markdown, encoding="utf-8")
    return path

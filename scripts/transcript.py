"""Transcript 数据结构,以及 VTT/SRT 解析。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float   # 秒
    end: float
    text: str
    speaker: str | None = None


@dataclass
class Transcript:
    segments: list[Segment]
    has_speakers: bool = False

    def to_prompt_text(self) -> str:
        """转成传给 LLM 的纯文本(带时间戳和说话人)。"""
        lines = []
        for s in self.segments:
            ts = _fmt_ts(s.start)
            prefix = f"[{ts}]"
            if s.speaker:
                prefix += f" {s.speaker}:"
            lines.append(f"{prefix} {s.text}")
        return "\n".join(lines)

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments)


def _fmt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


_VTT_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})")


def _parse_ts(ts: str) -> float:
    m = _VTT_TS.match(ts)
    if not m:
        return 0.0
    h, mm, s, ms = map(int, m.groups())
    return h * 3600 + mm * 60 + s + ms / 1000


def parse_vtt(path: Path) -> Transcript:
    """简易 VTT 解析(不处理样式标签)。"""
    content = path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", content)
    segs: list[Segment] = []
    for block in blocks:
        if "-->" not in block:
            continue
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        ts_line = next((l for l in lines if "-->" in l), None)
        if not ts_line:
            continue
        parts = ts_line.split("-->")
        start = _parse_ts(parts[0].strip())
        end = _parse_ts(parts[1].strip().split()[0])
        text_lines = [l for l in lines if "-->" not in l and not l.isdigit()
                      and not l.startswith("WEBVTT") and not l.startswith("NOTE")]
        text = re.sub(r"<[^>]+>", "", " ".join(text_lines)).strip()
        if text:
            segs.append(Segment(start=start, end=end, text=text))
    # 去重(自动字幕常有滚动重复)
    dedup: list[Segment] = []
    for s in segs:
        if dedup and dedup[-1].text == s.text:
            dedup[-1].end = s.end
            continue
        dedup.append(s)
    return Transcript(segments=dedup, has_speakers=False)

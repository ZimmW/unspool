"""章节切分:平台原生 > Shownotes 时间戳 > AI 兜底(独立调 LLM 取章节)。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .transcript import Transcript


@dataclass
class Chapter:
    title: str
    start: float        # 秒
    end: float


def from_native(chapters_raw: list[dict], duration: int) -> list[Chapter] | None:
    """yt-dlp 返回的 chapters 字段。质量检查不过则返回 None,让流程退回自动生成。"""
    if not chapters_raw:
        return None
    out: list[Chapter] = []
    for c in chapters_raw:
        out.append(Chapter(
            title=(c.get("title") or "").strip() or "未命名章节",
            start=float(c.get("start_time") or 0),
            end=float(c.get("end_time") or duration),
        ))
    if not out or _looks_unusable(out, duration):
        return None
    return out


_TS_LINE = re.compile(
    r"(?P<ts>(?:\d{1,2}:)?\d{1,2}:\d{2})\s*[\-—–|]?\s*(?P<title>.+?)$"
)


def from_shownotes(description: str, duration: int) -> list[Chapter] | None:
    """从 description 中解析 `00:00 标题` 类时间戳。"""
    if not description:
        return None
    found: list[tuple[float, str]] = []
    for line in description.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _TS_LINE.match(line)
        if not m:
            continue
        ts = _ts_to_sec(m.group("ts"))
        title = m.group("title").strip(" -—–|")
        if title:
            found.append((ts, title))
    if len(found) < 2:
        return None
    found.sort()
    chapters: list[Chapter] = []
    for i, (start, title) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else duration
        chapters.append(Chapter(title=title[:30], start=start, end=end))
    if _looks_unusable(chapters, duration):
        return None
    return chapters


# 质量阈值
_TITLE_MAX_CHARS = 60                    # 标题极限长度(英文 vs. 介绍等可较长)
_AVG_CHAPTER_MAX_SECONDS = 15 * 60       # 平均章节 > 15 分钟视为太稀


def _looks_unusable(chs: list[Chapter], duration: int) -> bool:
    """判定一组章节是否"标记不好",不好就退回自动生成。"""
    if not chs:
        return True
    for c in chs:
        t = c.title.strip()
        # 1. Untitled placeholder
        if "Untitled" in t or not t:
            return True
        # 2. 标题过长(60+),大概率是描述错入标题
        if len(t) > _TITLE_MAX_CHARS:
            return True
        # 3. 句中含 "." 或 "。" 且不在末尾,说明把前段描述并进了标题
        for sep in ("。", ". "):
            idx = t.find(sep)
            if 0 < idx < len(t) - len(sep):
                return True
    # 4. 太稀:平均章节超 15 分钟,跟 Cat Wu/Manus v3 的密章节风格不一致
    avg = duration / len(chs)
    if avg > _AVG_CHAPTER_MAX_SECONDS:
        return True
    return False


def _ts_to_sec(ts: str) -> float:
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0.0


# ─────────────────────────────────────────────────────────────────
# AI 章节切分:独立调 LLM,只返回章节边界,不生成文档正文
# ─────────────────────────────────────────────────────────────────

_AI_CHAPTERS_SYSTEM = """你是一个内容分析助手。任务:把一份 transcript 切成若干章节,只返回章节列表 JSON。

规则:
1. 章节按内容主题切分,不是均分时间
2. 章节标题 ≤ 15 字,描述性而非营销性
3. 章节连续不重叠:每章 end == 下一章 start
4. 第一章 start = 0,最后一章 end = transcript 最后时间戳
5. 时长参考:
   - <15 分钟:1-3 章
   - 15-60 分钟:3-8 章
   - 60-180 分钟:8-20 章
   - >180 分钟:15-30 章

只输出 JSON,不要任何前后说明。格式:
[
  {"title": "章节标题", "start": 0, "end": 360},
  {"title": "下一章", "start": 360, "end": 720}
]
start/end 为秒数(整数)。"""


def from_ai(transcript: "Transcript", duration: int,
            llm_cfg: dict[str, Any]) -> list[Chapter]:
    """用 LLM 切章节,返回 Chapter 列表。失败抛异常。

    传给 LLM 的不是完整 transcript(可能太长),而是按 1 分钟采样的概要。
    """
    # 按 60 秒粒度采样:每分钟取 1-2 个 segment 的开头
    samples: list[str] = []
    last_minute = -1
    for s in transcript.segments:
        minute = int(s.start) // 60
        if minute != last_minute:
            last_minute = minute
            ts_str = _sec_to_ts(int(s.start))
            samples.append(f"[{ts_str}] {s.text[:80]}")
    sample_text = "\n".join(samples)

    user_msg = (
        f"transcript 总时长 {duration} 秒(约 {duration//60} 分钟)。\n"
        f"以下是按分钟采样的内容摘要(每分钟一条):\n\n"
        f"{sample_text}\n\n"
        f"请输出章节 JSON。"
    )

    # 用 summarizer 里已有的 _LLM,但避免循环 import,这里直接复刻一份调用
    from .summarizer import _LLM
    llm = _LLM(llm_cfg)
    raw = llm.complete(_AI_CHAPTERS_SYSTEM, user_msg, max_tokens=4000)

    # 抽取 JSON(LLM 偶尔会包 ```json ... ```)
    raw = raw.strip()
    m = re.search(r"\[[\s\S]*\]", raw)
    if not m:
        raise RuntimeError(f"AI 章节切分:LLM 未返回 JSON 数组。原文:{raw[:200]}")
    data = json.loads(m.group(0))

    chapters: list[Chapter] = []
    for i, item in enumerate(data):
        start = float(item.get("start", 0))
        end = float(item.get("end", duration))
        title = (item.get("title") or f"章节 {i+1}").strip()
        # 闭区间健壮性:end 不超过总时长
        end = min(end, duration)
        if end <= start:
            continue
        chapters.append(Chapter(title=title[:30], start=start, end=end))

    if not chapters:
        raise RuntimeError("AI 章节切分:解析后为空")

    # 修正连续性:章节间填补
    chapters.sort(key=lambda c: c.start)
    for i in range(len(chapters) - 1):
        if chapters[i].end != chapters[i + 1].start:
            chapters[i].end = chapters[i + 1].start
    chapters[-1].end = duration
    chapters[0].start = 0.0
    return chapters


def _sec_to_ts(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

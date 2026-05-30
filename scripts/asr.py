"""ASR 适配层。

业界 ASR API 主要分 3 个协议族(provider 选哪个就决定走哪条):

| 协议 | endpoint | provider 举例 | 限制 |
|---|---|---|---|
| openai_transcriptions | POST /v1/audio/transcriptions (multipart) | openai, groq, fireworks, qwen | 单文件 ≤25MB |
| multimodal_chat | POST /v1/chat/completions (audio in content) | mimo, gemini | 单段较短,本地切片 |
| async_submit | 自家 REST(提交 URL + 轮询) | tongyi (阿里通义听悟) | 大文件友好,异步 |

新增 provider:
1. 在 PROTOCOL_MAP 加 `"my_provider": "openai_transcriptions"` 等
2. 或者实现新协议,加一个 `_transcribe_xxx()` adapter,在 dispatch 里挂上
"""
from __future__ import annotations

import base64
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .transcript import Segment, Transcript


# provider → protocol 映射
PROTOCOL_MAP: dict[str, str] = {
    "openai": "openai_transcriptions",
    "groq": "openai_transcriptions",
    "fireworks": "openai_transcriptions",
    "qwen": "openai_transcriptions",   # 阿里 Qwen3-ASR(DashScope OpenAI 兼容模式)
    "mimo": "multimodal_chat",
    "gemini": "multimodal_chat",
    # "tongyi": "async_submit",  # 待实现
}

# multimodal_chat 协议下单次请求音频时长上限(秒)。超出则 ffmpeg 切片。
MULTIMODAL_CHUNK_SECONDS = 300
# 并发上限:chunk 间互相独立,可并发请求。太高会触发 rate limit(429)。
MULTIMODAL_MAX_WORKERS = 3
# 单 chunk 遇 429/限流时的重试次数与退避基数(秒)
MULTIMODAL_MAX_RETRIES = 5
MULTIMODAL_BACKOFF_BASE = 4


def transcribe(audio_path: Path, asr_cfg: dict[str, Any]) -> Transcript:
    """根据 provider 自动 dispatch。也可在 cfg 里写 `protocol:` 强制指定。"""
    provider = asr_cfg.get("provider", "mimo")
    protocol = asr_cfg.get("protocol") or PROTOCOL_MAP.get(provider)
    if protocol == "openai_transcriptions":
        return _transcribe_openai_transcriptions(audio_path, asr_cfg)
    if protocol == "multimodal_chat":
        return _transcribe_multimodal_chat(audio_path, asr_cfg)
    raise NotImplementedError(
        f"ASR provider={provider!r} 未知。"
        f"已知 provider:{list(PROTOCOL_MAP.keys())};"
        f"或在 config.asr.protocol 显式指定 'openai_transcriptions' / 'multimodal_chat'。"
    )


# ─────────────────────────────────────────────────────────────────
# 协议 A:OpenAI Audio Transcriptions(Whisper 系)
# ─────────────────────────────────────────────────────────────────

def _transcribe_openai_transcriptions(audio_path: Path, cfg: dict[str, Any]) -> Transcript:
    """适用于 OpenAI Whisper、Groq Whisper、Fireworks 等遵循
    /v1/audio/transcriptions multipart 协议的服务。"""
    from openai import OpenAI

    client = OpenAI(api_key=cfg["api_key"], base_url=cfg.get("base_url"))
    model = cfg.get("model", "whisper-1")
    diarize = cfg.get("enable_speaker_diarization", False)

    extra: dict[str, Any] = {}
    if diarize:
        # 部分实现支持(如某些 Whisper 网关),不支持的会忽略
        extra["enable_speaker_diarization"] = True

    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=model,
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            extra_body=extra or None,
        )

    data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
    raw_segs = data.get("segments") or []

    segs: list[Segment] = []
    has_speakers = False
    for s in raw_segs:
        spk = s.get("speaker") or s.get("speaker_id")
        if spk is not None:
            has_speakers = True
            spk = f"说话人 {spk}" if str(spk).isdigit() else str(spk)
        segs.append(Segment(
            start=float(s.get("start", 0)),
            end=float(s.get("end", 0)),
            text=(s.get("text") or "").strip(),
            speaker=spk,
        ))

    if not segs:
        text = (data.get("text") or "").strip()
        if text:
            segs = [Segment(start=0, end=0, text=text)]

    return Transcript(segments=segs, has_speakers=has_speakers)


# ─────────────────────────────────────────────────────────────────
# 协议 B:Multimodal Chat(MiMo omni / Gemini 系)
# ─────────────────────────────────────────────────────────────────

def _transcribe_multimodal_chat(audio_path: Path, cfg: dict[str, Any]) -> Transcript:
    """适用于 MiMo omni、Gemini 等多模态聊天接收音频的服务。

    长音频按 MULTIMODAL_CHUNK_SECONDS 切片,逐段转写,按 offset 拼接。
    """
    from openai import OpenAI

    client = OpenAI(api_key=cfg["api_key"], base_url=cfg.get("base_url"))
    model = cfg.get("model", "mimo-v2-omni")
    diarize = cfg.get("enable_speaker_diarization", False)

    duration = _probe_duration(audio_path)
    print(f"      音频时长 {duration:.0f}s,切片大小 {MULTIMODAL_CHUNK_SECONDS}s",
          flush=True)

    chunks = _split_audio(audio_path, MULTIMODAL_CHUNK_SECONDS)
    # 并发跑各 chunk(独立,顺序无关)
    results: dict[int, tuple[list[Segment], bool]] = {}
    workers = min(MULTIMODAL_MAX_WORKERS, len(chunks))
    print(f"      并发 workers={workers}", flush=True)
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(_multimodal_call, client, model, p, diarize): (i, off)
                for i, (p, off) in enumerate(chunks)
            }
            done = 0
            for fut in as_completed(futures):
                idx, offset = futures[fut]
                try:
                    text = fut.result()
                except Exception as e:
                    print(f"      [chunk {idx+1}] 失败: {e}", flush=True)
                    results[idx] = ([], False)
                    continue
                segs, fs = _parse_freeform_transcript(text, offset)
                results[idx] = (segs, fs)
                done += 1
                print(f"      [chunk {idx+1}/{len(chunks)}] ✓ ({done}/{len(chunks)} 完成)",
                      flush=True)
    finally:
        if len(chunks) > 1:
            for chunk_path, _ in chunks:
                try:
                    chunk_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # 按 chunk 顺序拼接
    all_segments: list[Segment] = []
    has_speakers = False
    for i in range(len(chunks)):
        segs, fs = results.get(i, ([], False))
        all_segments.extend(segs)
        if fs:
            has_speakers = True

    if not all_segments:
        raise RuntimeError("ASR 未返回任何 transcript 段")

    return Transcript(segments=all_segments, has_speakers=has_speakers)


def _multimodal_call(client, model: str, audio_path: Path, diarize: bool) -> str:
    """单段音频走 chat completions,返回自由格式转写文本。"""
    with open(audio_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    speaker_hint = (
        "如果有多个说话人,用「说话人 1」「说话人 2」等标注每段对应说话人。"
        if diarize else ""
    )
    prompt = (
        "请把这段音频完整转写为文字。要求:\n"
        "1. 每句话独立一行,格式严格为:`[MM:SS] 文本`(或 `[MM:SS] 说话人 X: 文本`)\n"
        "2. 时间戳从音频开头计起,精确到秒\n"
        "3. 不要总结、不要省略、不要加任何额外说明\n"
        "4. 保留所有口语化表达、停顿、重复\n"
        f"{speaker_hint}\n"
        "直接输出转写文本,不要前后任何解释。"
    )

    last_err: Exception | None = None
    for attempt in range(MULTIMODAL_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=8192,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "input_audio",
                         "input_audio": {"data": b64, "format": "mp3"}},
                    ],
                }],
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            last_err = e
            # 429 / 限流 / 5xx → 退避重试;其他错误直接抛
            msg = str(e)
            retriable = ("429" in msg or "limitation" in msg
                         or "Too many requests" in msg or "rate" in msg.lower()
                         or "timeout" in msg.lower() or "503" in msg or "502" in msg)
            if not retriable or attempt == MULTIMODAL_MAX_RETRIES - 1:
                raise
            wait = MULTIMODAL_BACKOFF_BASE * (2 ** attempt)
            print(f"      [限流重试] {wait}s 后重试(第 {attempt+1} 次)", flush=True)
            time.sleep(wait)
    raise last_err  # 不会到这,保险


# ─────────────────────────────────────────────────────────────────
# ffmpeg 工具 + transcript 文本解析(multimodal_chat 专用)
# ─────────────────────────────────────────────────────────────────

def _probe_duration(audio: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True, timeout=30,
    )
    return float(result.stdout.strip() or 0)


def _split_audio(audio: Path, chunk_seconds: int) -> list[tuple[Path, int]]:
    """切片返回 [(path, offset_seconds), ...]。短音频不切。"""
    duration = _probe_duration(audio)
    if duration <= chunk_seconds + 5:
        return [(audio, 0)]

    out_dir = Path(tempfile.mkdtemp(prefix="asr_chunks_"))
    chunks: list[tuple[Path, int]] = []
    offset = 0
    idx = 0
    while offset < duration:
        chunk_path = out_dir / f"chunk_{idx:03d}.mp3"
        cmd = [
            "ffmpeg", "-y", "-ss", str(offset), "-t", str(chunk_seconds),
            "-i", str(audio), "-vn", "-acodec", "libmp3lame", "-q:a", "5",
            str(chunk_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not chunk_path.exists():
            raise RuntimeError(f"ffmpeg 切片失败: {r.stderr[-300:]}")
        chunks.append((chunk_path, offset))
        offset += chunk_seconds
        idx += 1
    return chunks


_LINE_RE = re.compile(
    r"^\s*\[?(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\]?\s*"
    r"(?:(?P<speaker>(?:说话人|主持人|嘉宾)\s*[A-Z\d]+)\s*[::]\s*)?"
    r"(?P<text>.+?)\s*$"
)


def _parse_ts_to_sec(ts: str) -> float:
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0.0


def _parse_freeform_transcript(text: str, offset: int) -> tuple[list[Segment], bool]:
    """解析 LLM 输出的 `[MM:SS] 说话人: 文本` 格式,所有时间戳加上 offset。"""
    segs: list[Segment] = []
    has_speakers = False
    last_ts = 0.0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            # 无时间戳的纯文本行,挂到上一段末尾
            if segs:
                segs[-1].text += " " + line
            continue
        ts = _parse_ts_to_sec(m.group("ts"))
        if ts < last_ts - 30:
            # 时间戳跳变(模型偶尔错位),沿用 last_ts
            ts = last_ts
        last_ts = ts
        spk = m.group("speaker")
        if spk:
            has_speakers = True
            spk = spk.replace(":", "").replace(":", "").strip()
        segs.append(Segment(
            start=ts + offset,
            end=ts + offset,
            text=m.group("text").strip(),
            speaker=spk,
        ))
    # 推算 end:下一段的 start
    for i in range(len(segs) - 1):
        segs[i].end = segs[i + 1].start
    return segs, has_speakers

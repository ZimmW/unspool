"""抖音/TikTok 的 JoeanAmier 后端(备选,与 Evil0ctal 二选一)。

JoeanAmier/TikTokDownloader 是日活维护的项目,通过它的 Web API 模式调用:
启动本地 API server(端口 5555)→ POST /douyin/detail → 拿 downloads 视频直链。

cookie 注入它的 Volume/settings.json。server 用完即杀。
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

DEFAULT_VENDOR_PATH = Path.home() / ".总裁速览" / "vendor" / "TikTokDownloader"
SERVER_PORT = 5555


def available(vendor_path: Path | None = None) -> bool:
    vp = vendor_path or DEFAULT_VENDOR_PATH
    return (vp / "main.py").exists()


def fetch_detail(aweme_id: str, cookies: dict[str, str], *,
                 vendor_path: Path | None = None) -> dict:
    """启动 JoeanAmier API server,POST detail,返回解析后的字段 dict。

    返回:{title, uploader, duration_sec, video_url}
    """
    vp = vendor_path or DEFAULT_VENDOR_PATH
    if not available(vp):
        raise RuntimeError(
            f"JoeanAmier 未安装。请:\n"
            f"  git clone https://github.com/JoeanAmier/TikTokDownloader.git {vp}\n"
            f"  cd {vp} && pip install -r requirements.txt"
        )

    _inject_cookies(vp, cookies)
    proc = _start_server(vp)
    try:
        _wait_ready(timeout=25)
        data = _post_detail(aweme_id)
    finally:
        _stop_server(proc)

    if not data:
        raise RuntimeError("JoeanAmier 返回空数据(cookie 可能失效)")

    video_url = data.get("downloads") or ""
    if not video_url:
        raise RuntimeError("JoeanAmier 未返回视频直链(downloads 字段为空)")

    return {
        "title": data.get("desc") or "未命名抖音视频",
        "uploader": data.get("nickname") or "",
        "duration_sec": _parse_duration(data.get("duration")),
        "video_url": video_url,
    }


def _inject_cookies(vp: Path, cookies: dict[str, str]) -> None:
    sp = vp / "Volume" / "settings.json"
    s = json.loads(sp.read_text(encoding="utf-8"))
    s["cookie"] = cookies
    sp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def _start_server(vp: Path) -> subprocess.Popen:
    # stdin 序列:语言(1=简中)、同意免责声明(Y)、选 5=Web API 模式
    proc = subprocess.Popen(
        ["python3", "main.py"],
        cwd=str(vp),
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        proc.stdin.write("1\nY\n5\n")
        proc.stdin.flush()
    except Exception:
        pass
    return proc


def _wait_ready(timeout: int = 25) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/docs", timeout=3)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("JoeanAmier API server 启动超时")


def _post_detail(aweme_id: str) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{SERVER_PORT}/douyin/detail",
        data=json.dumps({"detail_id": aweme_id}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return resp.get("data") or {}


def _stop_server(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _parse_duration(s) -> int:
    """'00:09:34' / '09:34' → 秒。"""
    if isinstance(s, (int, float)):
        return int(s)
    if not s or not isinstance(s, str):
        return 0
    parts = [int(p) for p in s.split(":") if p.isdigit()]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return 0

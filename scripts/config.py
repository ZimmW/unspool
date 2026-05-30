"""配置加载。从 ~/.总裁速览/config.yaml 读取,环境变量可覆盖密钥。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".总裁速览" / "config.yaml"


def _expand(p: str | None) -> str | None:
    if not p:
        return p
    return str(Path(p).expanduser())


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {cfg_path}\n"
            "请复制 config.example.yaml 到 ~/.总裁速览/config.yaml 并填写凭证。"
        )
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # LLM 默认复用 agent 的模型:未显式配置 llm.api_key 时,回退到
    # ANTHROPIC_API_KEY(在 Claude Code / OpenClaw 等 agent 环境里通常已存在)。
    # 已配置非 anthropic 的 key(如 deepseek)则不动,避免被环境变量覆盖。
    llm = cfg.setdefault("llm", {})
    if not llm.get("api_key"):
        if env_key := os.getenv("ANTHROPIC_API_KEY"):
            llm.setdefault("provider", "anthropic")
            llm["api_key"] = env_key
    if env_key := os.getenv("ASR_API_KEY"):
        cfg.setdefault("asr", {})["api_key"] = env_key

    # 展开路径
    out = cfg.get("output", {})
    if "local" in out:
        out["local"]["path"] = _expand(out["local"].get("path"))
    cookies = cfg.get("cookies", {})
    if "cookies_file" in cookies:
        cookies["cookies_file"] = _expand(cookies["cookies_file"])

    return cfg

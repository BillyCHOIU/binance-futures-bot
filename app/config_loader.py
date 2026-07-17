from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from app.paths import app_dir, ensure_user_files

# 兼容旧引用
ROOT = app_dir()


def _truthy(val: str | None, default: bool = False) -> bool:
    if val is None or val == "":
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def setup_logging(log_dir: Path | None = None) -> logging.Logger:
    root = ensure_user_files()
    log_dir = log_dir or (root / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "fluxbot.log"

    logger = logging.getLogger("fluxbot")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def _merge_env_secrets(cfg: dict[str, Any]) -> None:
    """把 .env 里的密钥/代理注入配置（不落盘回写）。"""
    cfg.setdefault("exchange", {})
    cfg["exchange"]["api_key"] = os.getenv("BINANCE_API_KEY", "").strip()
    cfg["exchange"]["api_secret"] = os.getenv("BINANCE_API_SECRET", "").strip()
    cfg["exchange"]["testnet"] = _truthy(os.getenv("USE_TESTNET"), default=True)

    cfg.setdefault("news", {})
    cfg["news"]["reddit_client_id"] = os.getenv("REDDIT_CLIENT_ID", "").strip()
    cfg["news"]["reddit_client_secret"] = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    cfg["news"]["reddit_user_agent"] = os.getenv(
        "REDDIT_USER_AGENT", "FluxBot/0.1 by local-user"
    ).strip()
    cfg["news"]["x_bearer_token"] = os.getenv("X_BEARER_TOKEN", "").strip()
    cfg["news"]["cryptopanic_token"] = os.getenv("CRYPTOPANIC_TOKEN", "").strip()
    cfg["news"]["http_proxy"] = (
        os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("FLUXBOT_PROXY") or ""
    ).strip()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def load_config(path: Path | None = None) -> dict[str, Any]:
    root = ensure_user_files()
    global ROOT
    ROOT = root

    load_dotenv(root / ".env")
    cfg_path = path or (root / "config.yaml")
    if not cfg_path.exists():
        cfg_path = root / "config.example.yaml"
    cfg = load_yaml(cfg_path)
    _merge_env_secrets(cfg)
    cfg["_root"] = str(root)
    return cfg


def save_config_patch(patch: dict[str, Any], path: Path | None = None) -> Path:
    """浅合并写回 config.yaml（用于 GUI 保存策略等）。"""
    root = ensure_user_files()
    cfg_path = path or (root / "config.yaml")
    data = load_yaml(cfg_path)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            data[k] = {**data[k], **v}
        else:
            data[k] = v
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return cfg_path

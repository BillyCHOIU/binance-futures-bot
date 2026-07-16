from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from app.paths import app_dir, ensure_user_files

# 兼容旧引用：ROOT = 可写应用目录
ROOT = app_dir()


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


def load_config(path: Path | None = None) -> dict[str, Any]:
    root = ensure_user_files()
    # 刷新模块级 ROOT（打包后可能变）
    global ROOT
    ROOT = root

    load_dotenv(root / ".env")
    cfg_path = path or (root / "config.yaml")
    if not cfg_path.exists():
        cfg_path = root / "config.example.yaml"
    if not cfg_path.exists():
        cfg: dict[str, Any] = {}
    else:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    use_testnet = os.getenv("USE_TESTNET", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }

    cfg.setdefault("exchange", {})
    cfg["exchange"]["api_key"] = api_key
    cfg["exchange"]["api_secret"] = api_secret
    cfg["exchange"]["testnet"] = use_testnet

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

    cfg["_root"] = str(root)
    return cfg

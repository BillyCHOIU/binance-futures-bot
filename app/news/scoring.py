from __future__ import annotations

import re

BULL_WORDS = {
    "etf approved": 1.2,
    "etf": 0.4,
    "approval": 0.5,
    "approved": 0.6,
    "partnership": 0.4,
    "launch": 0.3,
    "listing": 0.5,
    "上线": 0.5,
    "上币": 0.6,
    "利好": 0.7,
    "adoption": 0.4,
    "inflow": 0.5,
    "all-time high": 0.5,
    "ath": 0.3,
    "bullish": 0.6,
    "pump": 0.2,
    "record high": 0.4,
    "breakthrough": 0.3,
    "positive": 0.3,
}

BEAR_WORDS = {
    "hack": 1.2,
    "hacked": 1.2,
    "exploit": 1.0,
    "sec": 0.4,
    "lawsuit": 0.8,
    "ban": 0.9,
    "delist": 1.1,
    "delisting": 1.1,
    "下架": 1.1,
    "暂停": 0.6,
    "利空": 0.7,
    "fraud": 1.0,
    "investigation": 0.6,
    "crash": 0.7,
    "bankrupt": 1.0,
    "insolvent": 1.0,
    "bearish": 0.6,
    "outflow": 0.5,
    "restriction": 0.5,
    "security incident": 1.0,
    "暂停充值": 0.8,
    "暂停提现": 0.9,
    "negative": 0.3,
}

COIN_ALIASES = {
    "BTC": ["bitcoin", "btc", "xbt"],
    "ETH": ["ethereum", "eth", "ether"],
    "SOL": ["solana", "sol"],
    "BNB": ["bnb", "binance coin"],
}


def score_text(text: str) -> float:
    t = text.lower()
    score = 0.0
    for w, wgt in BULL_WORDS.items():
        if w in t:
            score += wgt
    for w, wgt in BEAR_WORDS.items():
        if w in t:
            score -= wgt
    return score


def detect_coins(text: str) -> list[str]:
    t = text.lower()
    found: list[str] = []
    for coin, aliases in COIN_ALIASES.items():
        if any(re.search(rf"\b{re.escape(a)}\b", t) for a in aliases):
            found.append(coin)
    if "比特币" in text:
        found.append("BTC")
    if "以太" in text:
        found.append("ETH")
    return list(dict.fromkeys(found))


def score_to_label(score: float, bull_threshold: float = 0.25, bear_threshold: float = -0.25) -> str:
    if score >= bull_threshold:
        return "BULL"
    if score <= bear_threshold:
        return "BEAR"
    return "NEUTRAL"

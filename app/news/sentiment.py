from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

from app.news import scoring as scoring_mod
from app.news.scoring import COIN_ALIASES

logger = logging.getLogger("fluxbot.news")

Sentiment = Literal["BULL", "BEAR", "NEUTRAL"]

DEFAULT_X_ACCOUNTS = [
    "Binance",
    "cz_binance",
    "coinbase",
    "CoinDesk",
    "Cointelegraph",
    "whale_alert",
    "lookonchain",
    "DocumentingBTC",
]


@dataclass
class NewsItem:
    source: str
    title: str
    url: str = ""
    ts: float = 0.0
    coins: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class SentimentEngine:
    bull_threshold: float = 0.25
    bear_threshold: float = -0.25
    refresh_seconds: int = 120
    enable_binance: bool = True
    enable_rss: bool = True
    enable_reddit: bool = True
    enable_x: bool = True
    enable_cryptopanic: bool = True
    # 可选凭证（.env）
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "FluxBot/0.1 by local-user"
    x_bearer_token: str = ""
    cryptopanic_token: str = ""
    http_proxy: str = ""
    x_accounts: list[str] = field(default_factory=lambda: list(DEFAULT_X_ACCOUNTS))
    on_log: Callable[[str], None] = field(default=lambda m: None)

    _cache_ts: float = 0.0
    _global_score: float = 0.0
    _per_coin: dict[str, float] = field(default_factory=dict)
    _items: list[NewsItem] = field(default_factory=list)
    _session: requests.Session = field(default_factory=requests.Session)
    _reddit_token: str = ""
    _reddit_token_exp: float = 0.0
    _warned: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        # 代理：解决国内访问 Reddit/X
        proxy = self.http_proxy or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or ""
        proxy = proxy.strip()
        if proxy:
            self._session.proxies.update({"http": proxy, "https": proxy})
            self.log(f"舆情代理已启用: {proxy[:32]}...")

    def log(self, msg: str) -> None:
        logger.info(msg)
        self.on_log(msg)

    def log_once(self, key: str, msg: str) -> None:
        if key in self._warned:
            return
        self._warned.add(key)
        self.log(msg)

    def score_text(self, text: str) -> float:
        return scoring_mod.score_text(text)

    def detect_coins(self, text: str) -> list[str]:
        return scoring_mod.detect_coins(text)

    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, application/rss+xml, text/xml, */*",
        }
        if extra:
            h.update(extra)
        return h

    def _get(
        self,
        url: str,
        timeout: int = 12,
        headers: dict | None = None,
        quiet_statuses: set[int] | None = None,
        source_key: str = "",
    ) -> requests.Response | None:
        quiet_statuses = quiet_statuses or set()
        try:
            r = self._session.get(url, headers=headers or self._headers(), timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in quiet_statuses and source_key:
                self.log_once(
                    f"{source_key}:{r.status_code}",
                    f"{source_key} HTTP {r.status_code}（已降级跳过，可配代理/API，详见 NEWS_SOURCES.md）",
                )
            else:
                self.log(f"HTTP {r.status_code}: {url[:80]}")
        except Exception as e:
            if source_key:
                self.log_once(f"{source_key}:exc", f"{source_key} 请求失败: {e}")
            else:
                self.log(f"请求失败 {url[:60]}: {e}")
        return None

    def fetch_binance_announcements(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        url = (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
            "?catalogId=48&pageNo=1&pageSize=20"
        )
        r = self._get(url, source_key="binance")
        if not r:
            url2 = (
                "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
                "?type=1&pageNo=1&pageSize=20"
            )
            r = self._get(url2, source_key="binance")
        if not r:
            return items
        try:
            data = r.json()
            body = data.get("data") or {}
            articles = body.get("articles") or body.get("catalogs") or []
            if articles and isinstance(articles[0], dict) and "articles" in articles[0]:
                articles = articles[0].get("articles") or []
            for a in articles[:20]:
                title = a.get("title") or a.get("code") or ""
                if not title:
                    continue
                link = a.get("code") or ""
                if link and not str(link).startswith("http"):
                    link = f"https://www.binance.com/en/support/announcement/{link}"
                sc = self.score_text(title) * 1.5
                items.append(
                    NewsItem(
                        source="binance",
                        title=title,
                        url=str(link),
                        ts=time.time(),
                        coins=self.detect_coins(title),
                        score=sc,
                    )
                )
        except Exception as e:
            self.log(f"解析币安公告失败: {e}")
        return items

    def fetch_rss(self) -> list[NewsItem]:
        feeds = [
            ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
            ("cointelegraph", "https://cointelegraph.com/rss"),
            ("decrypt", "https://decrypt.co/feed"),
        ]
        items: list[NewsItem] = []
        for name, url in feeds:
            r = self._get(url, source_key=f"rss:{name}")
            if not r:
                continue
            try:
                root = ET.fromstring(r.content)
                channels = root.findall("channel")
                nodes = channels[0].findall("item") if channels else []
                if not nodes:
                    ns = {"a": "http://www.w3.org/2005/Atom"}
                    nodes = root.findall("a:entry", ns) or root.findall("entry")
                for node in nodes[:15]:
                    title_el = node.find("title")
                    if title_el is None:
                        title_el = node.find("{http://www.w3.org/2005/Atom}title")
                    title = (title_el.text or "").strip() if title_el is not None else ""
                    if not title:
                        continue
                    items.append(
                        NewsItem(
                            source=name,
                            title=title,
                            ts=time.time(),
                            coins=self.detect_coins(title),
                            score=self.score_text(title),
                        )
                    )
            except Exception as e:
                self.log(f"RSS 解析失败 {name}: {e}")
        return items

    def _reddit_oauth_token(self) -> str:
        if not self.reddit_client_id or not self.reddit_client_secret:
            return ""
        if self._reddit_token and time.time() < self._reddit_token_exp - 60:
            return self._reddit_token
        try:
            auth = (self.reddit_client_id, self.reddit_client_secret)
            headers = {"User-Agent": self.reddit_user_agent}
            data = {"grant_type": "client_credentials"}
            r = self._session.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                data=data,
                headers=headers,
                timeout=15,
            )
            if r.status_code != 200:
                self.log_once(
                    "reddit_oauth",
                    f"Reddit OAuth 失败 HTTP {r.status_code}（检查 CLIENT_ID/SECRET 或代理）",
                )
                return ""
            body = r.json()
            self._reddit_token = body.get("access_token") or ""
            self._reddit_token_exp = time.time() + float(body.get("expires_in") or 3600)
            if self._reddit_token:
                self.log("Reddit OAuth 已就绪")
            return self._reddit_token
        except Exception as e:
            self.log_once("reddit_oauth_exc", f"Reddit OAuth 异常: {e}")
            return ""

    def fetch_reddit(self) -> list[NewsItem]:
        """优先官方 OAuth；否则尝试公开 JSON（国内常 403）。"""
        subs = ["CryptoCurrency", "Bitcoin", "ethereum"]
        items: list[NewsItem] = []
        token = self._reddit_oauth_token()

        for sub in subs:
            if token:
                url = f"https://oauth.reddit.com/r/{sub}/hot?limit=15"
                r = self._get(
                    url,
                    headers=self._headers(
                        {
                            "Authorization": f"bearer {token}",
                            "User-Agent": self.reddit_user_agent,
                        }
                    ),
                    quiet_statuses={403, 401, 429},
                    source_key="reddit",
                )
            else:
                urls = [
                    f"https://old.reddit.com/r/{sub}/hot.json?limit=15",
                    f"https://www.reddit.com/r/{sub}/hot.json?limit=15",
                ]
                r = None
                for url in urls:
                    r = self._get(
                        url,
                        quiet_statuses={403, 429},
                        source_key="reddit",
                    )
                    if r:
                        break
            if not r:
                continue
            try:
                children = (r.json().get("data") or {}).get("children") or []
                for ch in children:
                    d = ch.get("data") or {}
                    title = d.get("title") or ""
                    if not title:
                        continue
                    sc = self.score_text(title)
                    ups = float(d.get("ups") or 0)
                    if ups > 1000:
                        sc *= 1.2
                    items.append(
                        NewsItem(
                            source=f"reddit/{sub}",
                            title=title,
                            url="https://reddit.com" + (d.get("permalink") or ""),
                            ts=time.time(),
                            coins=self.detect_coins(title),
                            score=sc,
                        )
                    )
            except Exception as e:
                self.log(f"Reddit 解析失败 {sub}: {e}")

        if not items and self.enable_reddit:
            if not token:
                self.log_once(
                    "reddit_hint",
                    "Reddit 无数据：国内直连常 403。请在 .env 填 REDDIT_CLIENT_ID/SECRET，"
                    "或设 HTTPS_PROXY，或关掉 news.sources.reddit",
                )
        return items

    def fetch_x(self) -> list[NewsItem]:
        """X API v2 recent search（需要 Bearer Token，Basic 起）。"""
        items: list[NewsItem] = []
        if not self.x_bearer_token:
            self.log_once(
                "x_hint",
                "X 未配置：在 .env 填 X_BEARER_TOKEN（开发者平台申请）后自动启用",
            )
            return items

        # 查询：加密关键词 + 可选 from:账号
        accounts = [a.strip().lstrip("@") for a in self.x_accounts if a.strip()]
        from_q = " OR ".join(f"from:{a}" for a in accounts[:8])
        query = f"(bitcoin OR ethereum OR crypto OR BTC OR ETH) ({from_q})" if from_q else "(bitcoin OR ethereum OR crypto)"
        # recent search 要求 query URL 编码
        from urllib.parse import quote

        url = (
            "https://api.twitter.com/2/tweets/search/recent"
            f"?query={quote(query)}"
            "&max_results=20"
            "&tweet.fields=created_at,lang,public_metrics"
        )
        r = self._get(
            url,
            headers=self._headers({"Authorization": f"Bearer {self.x_bearer_token}"}),
            quiet_statuses={401, 403, 429},
            source_key="x",
            timeout=20,
        )
        if not r:
            return items
        try:
            data = r.json().get("data") or []
            for tw in data:
                text = tw.get("text") or ""
                if not text:
                    continue
                sc = self.score_text(text)
                # 互动加权
                metrics = tw.get("public_metrics") or {}
                likes = float(metrics.get("like_count") or 0)
                if likes > 200:
                    sc *= 1.15
                items.append(
                    NewsItem(
                        source="x",
                        title=text.replace("\n", " ")[:200],
                        url=f"https://x.com/i/web/status/{tw.get('id', '')}",
                        ts=time.time(),
                        coins=self.detect_coins(text),
                        score=sc,
                    )
                )
            if items:
                self.log(f"X 拉取 {len(items)} 条")
        except Exception as e:
            self.log(f"X 解析失败: {e}")
        return items

    def fetch_cryptopanic(self) -> list[NewsItem]:
        """
        CryptoPanic 聚合（含新闻/部分社交情绪）。
        免费可无 token（限额低）；有 token 更稳。
        国内若超时，同样可配代理。
        """
        items: list[NewsItem] = []
        base = "https://cryptopanic.com/api/v1/posts/"
        params = "public=true&kind=news&filter=important"
        if self.cryptopanic_token:
            url = f"{base}?auth_token={self.cryptopanic_token}&{params}"
        else:
            url = f"{base}?{params}"
        r = self._get(url, quiet_statuses={401, 403, 429}, source_key="cryptopanic", timeout=15)
        if not r:
            return items
        try:
            results = r.json().get("results") or []
            for row in results[:25]:
                title = row.get("title") or ""
                if not title:
                    continue
                # API 自带 votes
                votes = row.get("votes") or {}
                pos = float(votes.get("positive") or 0)
                neg = float(votes.get("negative") or 0)
                sc = self.score_text(title)
                if pos + neg > 0:
                    sc += (pos - neg) / max(pos + neg, 1) * 0.8
                currencies = row.get("currencies") or []
                coins = []
                for c in currencies:
                    code = (c.get("code") or "").upper()
                    if code in COIN_ALIASES:
                        coins.append(code)
                if not coins:
                    coins = self.detect_coins(title)
                items.append(
                    NewsItem(
                        source="cryptopanic",
                        title=title,
                        url=row.get("url") or "",
                        ts=time.time(),
                        coins=coins,
                        score=sc,
                    )
                )
            if items:
                self.log(f"CryptoPanic 拉取 {len(items)} 条")
        except Exception as e:
            self.log(f"CryptoPanic 解析失败: {e}")
        return items

    def refresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._cache_ts) < self.refresh_seconds:
            return

        items: list[NewsItem] = []
        if self.enable_binance:
            items.extend(self.fetch_binance_announcements())
        if self.enable_rss:
            items.extend(self.fetch_rss())
        if self.enable_cryptopanic:
            items.extend(self.fetch_cryptopanic())
        if self.enable_reddit:
            items.extend(self.fetch_reddit())
        if self.enable_x:
            items.extend(self.fetch_x())

        self._items = items
        self._cache_ts = now

        if not items:
            self._global_score = 0.0
            self._per_coin = {}
            self.log("舆情：未拉到有效新闻，方向=NEUTRAL")
            return

        scores = [it.score for it in items]
        self._global_score = sum(scores) / max(len(scores), 1)

        per: dict[str, list[float]] = {}
        for it in items:
            if not it.coins:
                continue
            for c in it.coins:
                per.setdefault(c, []).append(it.score)
        self._per_coin = {c: sum(v) / len(v) for c, v in per.items()}

        by_src: dict[str, int] = {}
        for it in items:
            src = it.source.split("/")[0]
            by_src[src] = by_src.get(src, 0) + 1

        top = sorted(items, key=lambda x: abs(x.score), reverse=True)[:5]
        brief = " | ".join(f"[{t.source}]{t.title[:40]}({t.score:+.2f})" for t in top)
        self.log(
            f"舆情刷新 n={len(items)} sources={by_src} global={self._global_score:+.3f} "
            f"coins={self._per_coin} :: {brief}"
        )

    def score_to_label(self, score: float) -> Sentiment:
        return scoring_mod.score_to_label(score, self.bull_threshold, self.bear_threshold)  # type: ignore[return-value]

    def sentiment_for_symbol(self, symbol: str) -> Sentiment:
        self.refresh()
        base = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()
        if base in self._per_coin:
            return self.score_to_label(self._per_coin[base])
        return self.score_to_label(self._global_score)

    def global_sentiment(self) -> Sentiment:
        self.refresh()
        return self.score_to_label(self._global_score)

    def latest_brief(self, n: int = 8) -> list[str]:
        self.refresh()
        lines = []
        for it in sorted(self._items, key=lambda x: abs(x.score), reverse=True)[:n]:
            lines.append(f"{it.score:+.2f} [{it.source}] {it.title[:80]}")
        return lines

    def source_status(self) -> dict[str, str]:
        """给 GUI/日志用的源状态摘要。"""
        return {
            "binance": "on" if self.enable_binance else "off",
            "rss": "on" if self.enable_rss else "off",
            "cryptopanic": "on" if self.enable_cryptopanic else "off",
            "reddit": (
                "oauth"
                if self.reddit_client_id and self.reddit_client_secret
                else ("public(易403)" if self.enable_reddit else "off")
            ),
            "x": "bearer" if self.x_bearer_token else ("need_token" if self.enable_x else "off"),
            "proxy": "yes" if (self.http_proxy or os.getenv("HTTPS_PROXY")) else "no",
        }

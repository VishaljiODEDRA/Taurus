from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import re
from html import unescape
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from agent.config import NewsSettings
from models import NewsContext, NewsItem

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - the regex fallback is tested instead.
    BeautifulSoup = None


POSITIVE_TERMS = {
    "beat",
    "beats",
    "raise",
    "raises",
    "raised",
    "upgrade",
    "upgraded",
    "guidance",
    "strong",
    "growth",
    "surge",
    "record",
    "profit",
    "outperform",
    "demand",
    "tailwind",
    "partnership",
    "contract",
    "approval",
    "buyback",
    "dividend",
    "margin",
    "accelerates",
    "expands",
}

NEGATIVE_TERMS = {
    "miss",
    "misses",
    "cut",
    "cuts",
    "downgrade",
    "downgraded",
    "weak",
    "loss",
    "probe",
    "lawsuit",
    "recall",
    "warning",
    "slowdown",
    "slump",
    "layoffs",
    "risk",
    "headwind",
    "investigation",
    "fraud",
    "restatement",
    "delay",
    "halts",
    "bankruptcy",
    "default",
    "sanction",
}

CATALYST_TERMS = {
    "earnings",
    "guidance",
    "revenue",
    "profit",
    "forecast",
    "acquisition",
    "merger",
    "partnership",
    "approval",
    "regulator",
    "analyst",
    "upgrade",
    "downgrade",
    "launch",
    "filing",
    "sec",
    "fed",
    "inflation",
    "rates",
    "ipo",
    "buyback",
    "dividend",
    "contract",
    "lawsuit",
    "investigation",
}


HIGH_RELIABILITY_SOURCES = {
    "reuters.com",
    "apnews.com",
    "dowjones",
    "marketwatch",
    "wsj",
    "sec.gov",
    "federalreserve.gov",
    "bls.gov",
    "bea.gov",
    "treasury.gov",
    "ft.com",
    "bloomberg.com",
    "spglobal.com",
}

LOW_RELIABILITY_SOURCES = {
    "twitter",
    "x.com",
    "stocktwits",
    "reddit",
    "social",
}


ENTITY_RELATION_WEIGHTS = {
    "company_names": 1.10,
    "aliases": 1.00,
    "products": 1.00,
    "subsidiaries": 0.95,
    "executives": 1.05,
    "suppliers": 0.72,
    "customers": 0.72,
    "competitors": 0.58,
}


DEFAULT_ENTITY_MAP: dict[str, dict[str, list[str]]] = {
    "AAPL": {
        "company_names": ["Apple", "Apple Inc"],
        "products": ["iPhone", "iPad", "Mac", "MacBook", "Apple Watch", "App Store", "Vision Pro", "AirPods"],
        "subsidiaries": ["Beats", "Shazam"],
        "suppliers": ["TSMC", "Taiwan Semiconductor", "Foxconn", "Hon Hai", "Pegatron", "Luxshare"],
        "competitors": ["Samsung", "Google Pixel", "Android"],
        "executives": ["Tim Cook", "Luca Maestri"],
    },
    "MSFT": {
        "company_names": ["Microsoft"],
        "products": ["Azure", "Windows", "Office", "Microsoft 365", "Copilot", "Xbox", "LinkedIn"],
        "subsidiaries": ["GitHub", "Activision Blizzard"],
        "competitors": ["Amazon Web Services", "Google Cloud"],
        "executives": ["Satya Nadella", "Amy Hood"],
    },
    "NVDA": {
        "company_names": ["Nvidia", "NVIDIA"],
        "products": ["Blackwell", "H100", "H200", "GB200", "CUDA", "GeForce"],
        "suppliers": ["TSMC", "Taiwan Semiconductor", "SK Hynix", "Micron"],
        "competitors": ["AMD", "Intel"],
        "executives": ["Jensen Huang"],
    },
    "AMD": {
        "company_names": ["Advanced Micro Devices", "AMD"],
        "products": ["Ryzen", "EPYC", "Instinct", "MI300"],
        "suppliers": ["TSMC", "Taiwan Semiconductor"],
        "competitors": ["Nvidia", "Intel"],
        "executives": ["Lisa Su"],
    },
    "GOOGL": {
        "company_names": ["Alphabet", "Google"],
        "products": ["Google Search", "YouTube", "Android", "Google Cloud", "Gemini", "Waymo", "Pixel"],
        "subsidiaries": ["YouTube", "Waymo", "DeepMind"],
        "competitors": ["Microsoft", "OpenAI", "Meta"],
        "executives": ["Sundar Pichai", "Ruth Porat"],
    },
    "META": {
        "company_names": ["Meta", "Meta Platforms", "Facebook"],
        "products": ["Instagram", "WhatsApp", "Threads", "Reels", "Quest", "Reality Labs"],
        "subsidiaries": ["Instagram", "WhatsApp", "Oculus"],
        "competitors": ["TikTok", "Snap", "YouTube"],
        "executives": ["Mark Zuckerberg", "Susan Li"],
    },
    "AMZN": {
        "company_names": ["Amazon"],
        "products": ["AWS", "Prime", "Amazon Web Services", "Kindle", "Alexa"],
        "subsidiaries": ["Whole Foods", "Twitch", "Zoox"],
        "competitors": ["Walmart", "Microsoft Azure", "Google Cloud"],
        "executives": ["Andy Jassy"],
    },
    "TSLA": {
        "company_names": ["Tesla"],
        "products": ["Model 3", "Model Y", "Cybertruck", "FSD", "Supercharger", "Optimus"],
        "subsidiaries": ["SolarCity"],
        "suppliers": ["Panasonic", "CATL", "LG Energy Solution"],
        "competitors": ["BYD", "Rivian", "Lucid"],
        "executives": ["Elon Musk"],
    },
    "TSM": {
        "company_names": ["TSMC", "Taiwan Semiconductor"],
        "products": ["CoWoS", "3nm", "2nm", "advanced packaging"],
        "customers": ["Apple", "Nvidia", "AMD", "Qualcomm"],
        "competitors": ["Samsung Foundry", "Intel Foundry"],
        "executives": ["C.C. Wei", "Mark Liu"],
    },
}


@dataclass(frozen=True)
class EntityMatch:
    symbol: str
    term: str
    relation: str
    weight: float


class NewsProvider:
    def __init__(self, settings: NewsSettings) -> None:
        self.settings = settings

    def load_items(self) -> list[NewsItem]:
        if not self.settings.enabled:
            return []
        cutoff = datetime.now(tz=UTC) - timedelta(hours=self.settings.lookback_hours)
        items = self._load_local_items(self.settings.local_news_path, default_source="local") + self._load_local_items(
            self.settings.local_social_path,
            default_source="social",
        ) + self._load_rss_items()
        recent_items = [
            item
            for item in items
            if item.published_at is None or item.published_at.astimezone(UTC) >= cutoff
        ]
        if not self.settings.scrape_articles:
            return recent_items
        return self._enrich_article_text(recent_items)

    def _load_local_items(self, path_value: str, *, default_source: str) -> list[NewsItem]:
        path = Path(path_value)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        raw_items = payload if isinstance(payload, list) else payload.get("items", [])
        items: list[NewsItem] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            items.append(
                NewsItem(
                    title=str(raw.get("title", raw.get("text", raw.get("content", "")))),
                    summary=str(raw.get("summary", raw.get("description", raw.get("text", "")))),
                    url=str(raw.get("url", "")),
                    published_at=_parse_datetime(raw.get("published_at") or raw.get("publishedAt")),
                    source=str(raw.get("source", default_source)),
                    symbols=tuple(str(symbol).upper() for symbol in raw.get("symbols", [])),
                )
            )
        return items

    def _load_rss_items(self) -> list[NewsItem]:
        urls = list(self.settings.rss_urls)
        if not urls:
            return []
        max_workers = max(min(self.settings.rss_max_workers, len(urls)), 1)
        items: list[NewsItem] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._load_one_rss, url) for url in urls]
            for future in as_completed(futures):
                items.extend(future.result())
        return items

    def _load_one_rss(self, url: str) -> list[NewsItem]:
        items: list[NewsItem] = []
        try:
            request = Request(url, headers={"User-Agent": "AutoTrading-Agent/0.1"})
            with urlopen(request, timeout=self.settings.rss_timeout_seconds) as response:
                raw = response.read()
        except (OSError, URLError):
            return items
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            return items
        for item in root.findall(".//item"):
            title = _text(item, "title")
            summary = _text(item, "description")
            published_at = _parse_datetime(_text(item, "pubDate"))
            link = _text(item, "link")
            items.append(
                NewsItem(
                    title=title,
                    summary=_strip_html(summary),
                    url=link,
                    published_at=published_at,
                    source=_source_name(url),
                )
            )
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", namespace):
            title = _text(entry, "{http://www.w3.org/2005/Atom}title")
            summary = _text(entry, "{http://www.w3.org/2005/Atom}summary") or _text(
                entry,
                "{http://www.w3.org/2005/Atom}content",
            )
            published_at = _parse_datetime(
                _text(entry, "{http://www.w3.org/2005/Atom}published")
                or _text(entry, "{http://www.w3.org/2005/Atom}updated")
            )
            link = ""
            for child in entry.findall("{http://www.w3.org/2005/Atom}link"):
                link = child.attrib.get("href", "")
                if link:
                    break
            items.append(
                NewsItem(
                    title=title,
                    summary=_strip_html(summary),
                    url=link,
                    published_at=published_at,
                    source=_source_name(url),
                )
            )
        return items

    def _enrich_article_text(self, items: list[NewsItem]) -> list[NewsItem]:
        max_articles = max(self.settings.scrape_max_articles_per_cycle, 0)
        if max_articles <= 0:
            return items

        indexed_targets = [
            (index, item)
            for index, item in enumerate(items)
            if item.url and item.url.startswith(("http://", "https://"))
        ][:max_articles]
        if not indexed_targets:
            return items

        enriched_by_index: dict[int, NewsItem] = {}
        max_workers = max(min(self.settings.rss_max_workers, len(indexed_targets)), 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._scrape_article_text, item.url): (index, item)
                for index, item in indexed_targets
            }
            for future in as_completed(futures):
                index, item = futures[future]
                article_text = future.result()
                if not article_text:
                    continue
                combined_summary = _merge_summary(
                    item.summary,
                    article_text[: self.settings.article_max_chars],
                )
                enriched_by_index[index] = NewsItem(
                    title=item.title,
                    summary=combined_summary,
                    url=item.url,
                    published_at=item.published_at,
                    source=item.source,
                    symbols=item.symbols,
                )

        return [enriched_by_index.get(index, item) for index, item in enumerate(items)]

    def _scrape_article_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": "AutoTrading-Agent/0.1"})
        try:
            with urlopen(request, timeout=self.settings.article_timeout_seconds) as response:
                content_type = response.headers.get("Content-Type", "")
                if "html" not in content_type.lower():
                    return ""
                raw = response.read(500_000).decode("utf-8", errors="replace")
        except (OSError, URLError):
            return ""
        return _extract_article_text(raw)


class NewsEntityResolver:
    def __init__(self, entity_map: dict[str, dict[str, list[str]]]) -> None:
        self.entity_map = _normalize_entity_map(entity_map)

    @classmethod
    def from_settings(cls, settings: NewsSettings) -> "NewsEntityResolver":
        entity_map = dict(DEFAULT_ENTITY_MAP)
        configured = _load_entity_map(settings.entity_map_path)
        for symbol, payload in configured.items():
            merged = {key: list(values) for key, values in entity_map.get(symbol, {}).items()}
            for relation, terms in payload.items():
                merged.setdefault(relation, [])
                merged[relation].extend(terms)
            entity_map[symbol] = merged
        return cls(entity_map)

    def matches_for_symbol(self, symbol: str, item: NewsItem) -> list[EntityMatch]:
        symbol_upper = symbol.upper()
        text = f"{item.title} {item.summary}"
        matches: list[EntityMatch] = []
        for relation, terms in self.entity_map.get(symbol_upper, {}).items():
            relation_weight = ENTITY_RELATION_WEIGHTS.get(relation, 0.75)
            for term in terms:
                if _mentions_entity_term(text, term):
                    matches.append(
                        EntityMatch(
                            symbol=symbol_upper,
                            term=term,
                            relation=relation,
                            weight=relation_weight,
                        )
                    )
        return matches

    def best_weight_for_symbol(self, symbol: str, item: NewsItem) -> float:
        if symbol.upper() in item.symbols:
            return 1.20
        if _mentions_symbol(symbol.upper(), item):
            return 1.05
        matches = self.matches_for_symbol(symbol, item)
        return max((match.weight for match in matches), default=0.0)


class NewsScorer:
    def __init__(
        self,
        entity_resolver: NewsEntityResolver | None = None,
        source_credibility: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.entity_resolver = entity_resolver or NewsEntityResolver(DEFAULT_ENTITY_MAP)
        self.source_credibility = source_credibility or {}

    def context_for_symbol(self, symbol: str, items: list[NewsItem]) -> NewsContext:
        symbol_upper = symbol.upper()
        matched_with_weights = [
            (item, self.entity_resolver.best_weight_for_symbol(symbol_upper, item))
            for item in items
        ]
        matched_items = [item for item, entity_weight in matched_with_weights if entity_weight > 0]
        matched = _dedupe_items(matched_items)
        if not matched:
            return NewsContext(symbol=symbol_upper)

        weights = [
            self._source_weight(item)
            * _recency_weight(item)
            * max(self.entity_resolver.best_weight_for_symbol(symbol_upper, item), 0.1)
            for item in matched
        ]
        total_weight = sum(weights) or 1.0
        sentiment = sum(_sentiment(item) * weight for item, weight in zip(matched, weights)) / total_weight
        catalyst = max(
            (_catalyst_score(item) * min(self._source_weight(item), 1.25) for item in matched),
            default=0.0,
        )
        entity_catalyst_boost = min(
            sum(max(self.entity_resolver.best_weight_for_symbol(symbol_upper, item) - 0.75, 0.0) for item in matched) / 12,
            0.15,
        )
        breadth_boost = min(len({item.source.lower() for item in matched if item.source}) / 8, 0.25)
        catalyst = min(catalyst + breadth_boost + entity_catalyst_boost, 1.0)
        summary = "; ".join(item.title for item in matched[:5])
        return NewsContext(
            symbol=symbol_upper,
            sentiment_score=max(min(sentiment, 1.0), -1.0),
            catalyst_score=max(min(catalyst, 1.0), 0.0),
            summary=summary,
            items=tuple(matched[:20]),
        )

    def source_quality_report(self, items: list[NewsItem]) -> list[dict[str, float | int | str]]:
        by_source: dict[str, list[NewsItem]] = {}
        for item in items:
            source = item.source or _source_name(item.url) or "unknown"
            by_source.setdefault(source, []).append(item)
        rows: list[dict[str, float | int | str]] = []
        for source, source_items in by_source.items():
            sentiments = [_sentiment(item) for item in source_items]
            catalysts = [_catalyst_score(item) for item in source_items]
            credibility = sum(self._source_weight(item) * _recency_weight(item) for item in source_items) / len(source_items)
            source_key = _normalize_source_name(source)
            learned = self.source_credibility.get(source_key, {})
            rows.append(
                {
                    "source": source,
                    "mentions": len(source_items),
                    "avg_sentiment": sum(sentiments) / len(sentiments) if sentiments else 0.0,
                    "avg_catalyst": sum(catalysts) / len(catalysts) if catalysts else 0.0,
                    "credibility_score": min(credibility, 1.5),
                    "learned_reliability": float(learned.get("reliability_score", 0.0) or 0.0),
                    "learned_samples": int(learned.get("sample_count", 0) or 0),
                    "noise_score": float(learned.get("noise_score", 0.0) or 0.0),
                    "speed_score": float(learned.get("speed_score", 0.0) or 0.0),
                }
            )
        rows.sort(key=lambda row: (float(row["credibility_score"]), int(row["mentions"])), reverse=True)
        return rows

    def _source_weight(self, item: NewsItem) -> float:
        base = _source_weight(item)
        source_key = _normalize_source_name(item.source or _source_name(item.url) or "unknown")
        learned = self.source_credibility.get(source_key)
        if not learned:
            return base
        multiplier = _float(learned.get("credibility_multiplier"), 1.0)
        return max(min(base * multiplier, 1.7), 0.25)


def _sentiment(item: NewsItem) -> float:
    text = f"{item.title} {item.summary}".lower()
    words = set(re.findall(r"[a-z]+", text))
    positive = len(words & POSITIVE_TERMS)
    negative = len(words & NEGATIVE_TERMS)
    if positive == 0 and negative == 0:
        return 0.0
    return (positive - negative) / max(positive + negative, 1)


def _catalyst_score(item: NewsItem) -> float:
    text = f"{item.title} {item.summary}".lower()
    words = set(re.findall(r"[a-z]+", text))
    return min(len(words & CATALYST_TERMS) / 3, 1.0)


def _mentions_symbol(symbol: str, item: NewsItem) -> bool:
    if symbol in item.symbols:
        return True

    text = f"{item.title} {item.summary}"
    escaped = re.escape(symbol)
    if len(symbol) == 1:
        return bool(
            re.search(rf"(?<![A-Z0-9])\${escaped}\b", text, re.I)
            or re.search(rf"\b(?:NYSE|NASDAQ|AMEX):{escaped}\b", text, re.I)
        )
    if len(symbol) <= 3:
        return bool(
            re.search(rf"(?<![A-Z0-9])\${escaped}\b", text, re.I)
            or re.search(rf"\b(?:NYSE|NASDAQ|AMEX):{escaped}\b", text, re.I)
            or re.search(rf"\b{escaped}\b", text)
        )
    return bool(re.search(rf"\b{escaped}\b", text, re.I))


def _mentions_entity_term(text: str, term: str) -> bool:
    clean_term = term.strip()
    if not clean_term:
        return False
    escaped = re.escape(clean_term)
    return bool(re.search(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", text, re.I))


def _load_entity_map(path_value: str) -> dict[str, dict[str, list[str]]]:
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    raw_entities = payload.get("entities", payload) if isinstance(payload, dict) else {}
    if not isinstance(raw_entities, dict):
        return {}
    return _normalize_entity_map(raw_entities)


def _normalize_entity_map(raw_entities: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    normalized: dict[str, dict[str, list[str]]] = {}
    for symbol, payload in raw_entities.items():
        if not isinstance(payload, dict):
            continue
        symbol_upper = str(symbol).upper()
        normalized[symbol_upper] = {}
        for relation, terms in payload.items():
            if isinstance(terms, str):
                values = [terms]
            elif isinstance(terms, list):
                values = [str(term) for term in terms if str(term).strip()]
            else:
                continue
            normalized[symbol_upper][str(relation)] = sorted(set(values), key=str.lower)
    return normalized


def _dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    output: list[NewsItem] = []
    for item in items:
        key = item.url.strip().lower() if item.url else re.sub(r"\W+", " ", item.title.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _source_weight(item: NewsItem) -> float:
    source = item.source.lower()
    url_host = urlparse(item.url).netloc.lower().removeprefix("www.") if item.url else ""
    source_text = f"{source} {url_host}"
    if any(name in source_text for name in HIGH_RELIABILITY_SOURCES):
        return 1.30
    if any(name in source_text for name in LOW_RELIABILITY_SOURCES):
        return 0.55
    if item.source and item.url:
        return 1.00
    return 0.75


def _normalize_source_name(source: str) -> str:
    return source.strip().lower()


def _float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _recency_weight(item: NewsItem) -> float:
    if item.published_at is None:
        return 0.80
    age_hours = max((datetime.now(tz=UTC) - item.published_at.astimezone(UTC)).total_seconds() / 3600, 0.0)
    if age_hours <= 6:
        return 1.15
    if age_hours <= 24:
        return 1.00
    if age_hours <= 72:
        return 0.82
    return 0.62


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _text(item: ElementTree.Element, tag: str) -> str:
    child = item.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def _extract_article_text(html: str) -> str:
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
            tag.decompose()
        container = soup.find("article") or soup.body or soup
        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in container.find_all("p")
            if paragraph.get_text(strip=True)
        ]
        if paragraphs:
            return " ".join(paragraphs)
        return container.get_text(" ", strip=True)

    cleaned = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    return re.sub(r"\s+", " ", unescape(cleaned)).strip()


def _merge_summary(summary: str, article_text: str) -> str:
    if not article_text:
        return summary
    if not summary:
        return article_text
    if article_text in summary:
        return summary
    return f"{summary}\n\n{article_text}"


def _source_name(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.") or url

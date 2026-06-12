"""News and agricultural advisory collector — Layer 1 Ingestion.

Collects agricultural news, weather alerts, and pest/disease advisories
from RSS feeds. All sources are free and require no API key.

Sources:
  1. IMD Agri-Met Advisories  — weather warnings for farmers
  2. Doordarshan Kisan RSS     — agricultural news
  3. ICAR Alerts              — pest and disease outbreak warnings

The news_collector does NOT affect ML predictions directly.
It feeds the dashboard's 'alerts' section and may trigger insight flags
when pest/disease keywords are detected for specific crops.
"""

import hashlib
from datetime import date, datetime, timezone
from typing import Any

import feedparser  # type: ignore[import-untyped]

from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import DD_KISAN_RSS_URL, DEFAULT_DISTRICT, IMD_RSS_URL
from crop_agent.database.connection import get_session
from crop_agent.database.models import RawNewsAlert
from crop_agent.ingestion.base_collector import BaseCollector

logger = get_logger(__name__)

# RSS feed definitions — source_name → URL
RSS_FEEDS: dict[str, str] = {
    "imd_agrimet": IMD_RSS_URL,
    "dd_kisan": DD_KISAN_RSS_URL,
}

# Additional public RSS feeds (no key needed)
ADDITIONAL_RSS_FEEDS: dict[str, str] = {
    "pib_agriculture": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
}

# Alert type detection — keywords → alert_type
ALERT_KEYWORDS: dict[str, list[str]] = {
    "pest":    ["pest", "locust", "aphid", "bollworm", "whitefly", "mealybug", "infestation"],
    "disease": ["disease", "blight", "rust", "wilt", "rot", "mosaic", "canker", "fungal"],
    "weather": ["cyclone", "flood", "drought", "heatwave", "frost", "hail", "heavy rain", "alert"],
    "market":  ["price", "msp", "procurement", "export", "import", "duty", "subsidy"],
}

# Severity detection keywords
SEVERITY_HIGH_KEYWORDS: list[str] = ["red alert", "warning", "severe", "emergency", "disaster"]
SEVERITY_MEDIUM_KEYWORDS: list[str] = ["watch", "advisory", "caution", "moderate"]


class NewsCollector(BaseCollector):
    """Collects agricultural news and alerts from RSS feeds.

    Performs deduplication by hashing each article's URL and title.
    Only new articles are inserted — existing ones are skipped silently.

    Attributes:
        district: District to filter/tag news for.
        feeds: Dict of source_name → RSS URL to collect from.
    """

    def __init__(
        self,
        district: str = DEFAULT_DISTRICT,
        feeds: dict[str, str] | None = None,
    ) -> None:
        """Initialize the news collector.

        Args:
            district: District name for DB tagging.
            feeds: Optional custom RSS feed mapping. Defaults to all configured feeds.
        """
        super().__init__(source_name="news_rss")
        self.district = district
        self.feeds = feeds or {**RSS_FEEDS, **ADDITIONAL_RSS_FEEDS}

    def collect(self, target_date: date) -> int:
        """Collect news articles from all configured RSS feeds.

        The target_date is used for logging context only — RSS feeds are
        collected in full (last ~20 articles) and deduplicated by hash.

        Args:
            target_date: The date context for this collection run.

        Returns:
            Total number of new articles written to the database.
        """
        total_rows = 0

        for source_name, feed_url in self.feeds.items():
            try:
                rows = self._collect_feed(source_name, feed_url)
                total_rows += rows
                logger.info(
                    "news.feed_collected",
                    source=source_name,
                    rows_written=rows,
                    date=str(target_date),
                )
            except Exception as exc:
                # Individual feed failure should not stop other feeds
                logger.warning(
                    "news.feed_failed",
                    source=source_name,
                    url=feed_url,
                    error=str(exc),
                )

        return total_rows

    def _collect_feed(self, source_name: str, feed_url: str) -> int:
        """Parse and store all new articles from a single RSS feed.

        Args:
            source_name: Identifier for this news source.
            feed_url: The RSS feed URL to parse.

        Returns:
            Number of new articles inserted.
        """
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            logger.warning(
                "news.feed_parse_error",
                source=source_name,
                url=feed_url,
                error=str(feed.bozo_exception) if feed.bozo_exception else "Unknown parse error",
            )

        rows_written = 0
        for entry in feed.entries:
            try:
                if self._save_article(entry, source_name):
                    rows_written += 1
            except Exception as exc:
                logger.warning(
                    "news.article_save_failed",
                    source=source_name,
                    error=str(exc),
                )

        return rows_written

    def _save_article(self, entry: Any, source_name: str) -> bool:
        """Save a single RSS entry to the database if it is new.

        Args:
            entry: A feedparser entry object.
            source_name: Source identifier string.

        Returns:
            True if the article was newly inserted, False if already exists.
        """
        headline = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()

        if not headline:
            return False

        # Deduplicate using a hash of source + URL + headline
        article_hash = hashlib.md5(  # noqa: S324 — not for security, just dedup
            f"{source_name}|{url}|{headline}".encode()
        ).hexdigest()

        # Parse published date
        published_at = self._parse_published_date(entry)

        # Detect alert type and severity from headline text
        headline_lower = headline.lower()
        alert_type = self._detect_alert_type(headline_lower)
        severity = self._detect_severity(headline_lower)

        # Detect crop and district mentions
        crops_mentioned = self._detect_crops(headline_lower)
        district_mentioned = self.district if self.district.lower() in headline_lower else None

        try:
            with get_session() as session:
                # Check for duplicate using URL match (simpler than hash storage)
                existing = session.query(RawNewsAlert).filter_by(url=url).first()
                if existing:
                    return False

                row = RawNewsAlert(
                    published_at=published_at,
                    source=source_name,
                    headline=headline[:2000],  # Cap at 2000 chars
                    alert_type=alert_type,
                    crop_mentioned=", ".join(crops_mentioned) if crops_mentioned else None,
                    district_mentioned=district_mentioned,
                    severity=severity,
                    url=url if url else None,
                )
                session.add(row)
            return True

        except Exception as exc:
            logger.error(
                "news.db_write_failed",
                headline=headline[:100],
                error=str(exc),
            )
            return False

    @staticmethod
    def _parse_published_date(entry: Any) -> datetime | None:
        """Extract and parse the publication date from an RSS entry.

        Args:
            entry: A feedparser entry object.

        Returns:
            UTC datetime or None if not available.
        """
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                import time
                ts = time.mktime(entry.published_parsed)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                pass
        return None

    @staticmethod
    def _detect_alert_type(text: str) -> str | None:
        """Detect the category of agricultural alert from article text.

        Args:
            text: Lowercase article headline text.

        Returns:
            Alert type string or None if uncategorized.
        """
        for alert_type, keywords in ALERT_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return alert_type
        return None

    @staticmethod
    def _detect_severity(text: str) -> str:
        """Detect severity level from article headline text.

        Args:
            text: Lowercase article headline text.

        Returns:
            Severity string: HIGH, MEDIUM, or LOW.
        """
        if any(kw in text for kw in SEVERITY_HIGH_KEYWORDS):
            return "HIGH"
        if any(kw in text for kw in SEVERITY_MEDIUM_KEYWORDS):
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _detect_crops(text: str) -> list[str]:
        """Detect crop names mentioned in the article headline.

        Uses a simple keyword match against common crop names.
        A proper NER model could be added here in a future phase.

        Args:
            text: Lowercase article headline text.

        Returns:
            List of detected crop names (may be empty).
        """
        # Common crop name keywords to scan for
        crop_keywords: dict[str, list[str]] = {
            "Paddy": ["paddy", "rice", "dhan"],
            "Wheat": ["wheat", "gehun"],
            "Maize": ["maize", "corn", "makka"],
            "Tomato": ["tomato", "tamatar"],
            "Onion": ["onion", "pyaz", "kanda"],
            "Potato": ["potato", "aloo"],
            "Sugarcane": ["sugarcane", "ganna"],
            "Cotton": ["cotton", "kapas"],
            "Groundnut": ["groundnut", "peanut", "moongphali"],
            "Soybean": ["soybean", "soya"],
            "Chilli": ["chilli", "chili", "mirch"],
            "Turmeric": ["turmeric", "haldi"],
            "Ragi": ["ragi", "finger millet"],
            "Horsegram": ["horsegram", "hurali"],
        }

        found: list[str] = []
        for crop_name, keywords in crop_keywords.items():
            if any(kw in text for kw in keywords):
                found.append(crop_name)

        return found

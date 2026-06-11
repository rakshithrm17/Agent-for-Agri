"""Abstract base class for all data collectors (Layer 1 — Ingestion).

All collectors inherit from BaseCollector and implement the collect() method.
The base class provides:
  - Retry logic with configurable attempts and delay
  - Structured logging (every success and failure is logged)
  - Anomaly logging (every permanent failure writes to anomaly_log)
  - HTTP session management with proper timeouts

Design Rule: If a collector fails after all retries, it must write to
anomaly_log. No collector can fail silently.
"""

import time
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import MAX_INGESTION_RETRIES, RETRY_DELAY_SECONDS
from crop_agent.database.connection import get_session
from crop_agent.database.models import AnomalyLog

logger = get_logger(__name__)

# HTTP request timeout in seconds
HTTP_CONNECT_TIMEOUT: int = 10
HTTP_READ_TIMEOUT: int = 30


class BaseCollector(ABC):
    """Abstract base class for all Layer 1 data collectors.

    Subclasses must implement the collect() method.
    The base class handles retry logic, logging, and anomaly recording.

    Attributes:
        source_name: Unique identifier for this data source (e.g. "open_meteo").
        max_retries: Maximum number of retry attempts before marking as failed.
        retry_delay_seconds: Seconds to wait between retry attempts.
    """

    def __init__(
        self,
        source_name: str,
        max_retries: int = MAX_INGESTION_RETRIES,
        retry_delay_seconds: int = RETRY_DELAY_SECONDS,
    ) -> None:
        """Initialize the collector with source metadata and retry config.

        Args:
            source_name: Unique identifier string for this source.
            max_retries: How many times to retry on failure before giving up.
            retry_delay_seconds: Seconds between retry attempts.
        """
        self.source_name = source_name
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self._session = self._build_http_session()

    def _build_http_session(self) -> requests.Session:
        """Build a requests Session with automatic retry on transient HTTP errors.

        Returns:
            A configured requests.Session with retry adapter mounted.
        """
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a GET request with timeout. Raises on non-2xx response.

        Args:
            url: The URL to request.
            params: Optional query parameters.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            requests.HTTPError: On 4xx/5xx responses.
            requests.ConnectionError: On network errors.
            requests.Timeout: On request timeout.
        """
        response = self._session.get(
            url,
            params=params,
            timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT),
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    @abstractmethod
    def collect(self, target_date: date) -> int:
        """Collect data for the given date and persist to the database.

        Args:
            target_date: The date to collect data for.

        Returns:
            Number of rows successfully written to the database.
        """

    def run(self, target_date: date) -> int:
        """Run the collector with retry logic and anomaly logging on failure.

        This is the public entry point called by the night agent.
        It wraps collect() with retry logic and anomaly recording.

        Args:
            target_date: The date to collect data for.

        Returns:
            Number of rows written (0 if all retries failed).
        """
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                rows_written = self.collect(target_date)
                logger.info(
                    "collector.success",
                    source=self.source_name,
                    date=str(target_date),
                    rows_written=rows_written,
                    attempt=attempt,
                )
                return rows_written
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "collector.retry",
                    source=self.source_name,
                    date=str(target_date),
                    attempt=attempt,
                    max_retries=self.max_retries,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds)

        # All retries exhausted — log to anomaly_log (no silent failure)
        self._record_anomaly(
            issue_detail=f"All {self.max_retries} attempts failed for {target_date}. "
                         f"Last error: {last_error}",
        )
        logger.error(
            "collector.failed_all_retries",
            source=self.source_name,
            date=str(target_date),
            max_retries=self.max_retries,
            error=str(last_error),
        )
        return 0

    def _record_anomaly(self, issue_detail: str, severity: str = "HIGH") -> None:
        """Write a failure record to the anomaly_log table.

        Called automatically when all retries are exhausted.
        This ensures no failure is silent — the dashboard will show a warning.

        Args:
            issue_detail: Human-readable description of what failed.
            severity: Severity level — LOW | MEDIUM | HIGH.
        """
        try:
            with get_session() as session:
                anomaly = AnomalyLog(
                    table_name=f"raw_{self.source_name.replace('-', '_')}",
                    issue_type="ingestion_failure",
                    issue_detail=issue_detail,
                    severity=severity,
                )
                session.add(anomaly)
        except Exception as db_exc:
            # Last resort — if we can't even write to anomaly_log, just log it
            logger.error(
                "collector.anomaly_log_failed",
                source=self.source_name,
                db_error=str(db_exc),
            )

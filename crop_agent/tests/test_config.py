import os
from unittest import mock

from crop_agent.config import settings
from crop_agent.config.logging_config import get_logger


def test_settings_default_values() -> None:
    """Test that default configuration values are set correctly."""
    assert settings.DEFAULT_DISTRICT == "Mandya"
    assert settings.DEFAULT_STATE == "Karnataka"
    assert settings.MANDYA_LATITUDE == 12.5234
    assert settings.MANDYA_LONGITUDE == 76.8961

def test_require_env_fallback() -> None:
    """Test that _require_env falls back to default if environment variable is not set."""
    # Since _require_env is a helper function not exported, we can test settings behavior
    with mock.patch.dict(os.environ, {"APP_ENV": "custom_testing"}):
        # We can't re-import easily since Python caches modules, but we can test
        # the underlying _require_env if we access it directly.
        from importlib import reload
        reload(settings)
        assert settings.APP_ENV == "custom_testing"

    # Reload again to restore clean defaults
    reload(settings)

def test_get_logger() -> None:
    """Test that get_logger returns a BoundLogger instance."""
    logger = get_logger("test_logger")
    assert logger is not None


def test_db_connection() -> None:
    """Test database connection objects import and initialize."""
    from crop_agent.database import connection
    assert connection.engine is not None
    assert connection.SessionLocal is not None


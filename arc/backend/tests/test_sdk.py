"""
Tests for ARC SDK (client, agent wrapper, init).
"""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

try:
    from db.database import Base
except ImportError:
    from arc.backend.db.database import Base


@pytest_asyncio.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )

    async with SessionLocal() as session:
        yield session

    await engine.dispose()


def test_arc_sdk_imports():
    """Test that arc-sdk imports work correctly after consolidation."""
    # Test that the canonical arc-sdk package is importable
    import arc  # noqa: F401 - the canonical arc package
    from arc import ARC, ARCConfig  # noqa: F401
    from arc.config import DEFAULT_SERVER_URL, DEFAULT_DASHBOARD_URL  # noqa: F401
    from arc.version import __version__  # noqa: F401

    # Verify core exports
    assert arc.__version__ is not None
    assert ARC is not None
    assert ARCConfig is not None
    assert DEFAULT_SERVER_URL is not None
    assert DEFAULT_DASHBOARD_URL is not None


def test_arc_config_from_env():
    """Test ARCConfig can be built from environment."""
    from arc import ARCConfig

    config = ARCConfig.from_env(
        api_key="test_key_123",
        provider_api_key="test_anthropic_456",
    )
    assert config.api_key == "test_key_123"
    assert config.provider_api_key == "test_anthropic_456"
    assert config.provider == "anthropic"  # default


def test_arc_wrapped_agent():
    """Test WrappedAgent detection and wrapping."""
    from arc._agent import _detect_framework, WrappedAgent

    # Test framework detection
    assert _detect_framework({"messages": ["hi"]}) == "generic"

    # Test that WrappedAgent class exists
    assert WrappedAgent is not None



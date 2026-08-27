"""ARC — client configuration contract.

Defines :class:`ARCConfig`, the immutable settings object consumed by the
:class:`~arc.ARC` facade. Values fall back to environment variables so the SDK
can be configured without code changes. No I/O or connection logic lives here.
"""

from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_DASHBOARD_URL = "http://localhost:3000"


class ARCConfig(BaseModel):
    """Resolved configuration for an :class:`~arc.ARC` instance."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, frozen=True)

    api_key: Optional[str] = Field(default=None, description="ARC control-plane API key")
    provider_api_key: Optional[str] = Field(
        default=None, description="Underlying model provider key (e.g. Anthropic)"
    )
    server_url: str = Field(default=DEFAULT_SERVER_URL, description="ARC control-plane base URL")
    dashboard_url: str = Field(default=DEFAULT_DASHBOARD_URL, description="ARC dashboard base URL")
    provider: str = Field(default="anthropic", description="Default provider adapter name")
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum transient-error retries")
    offline: bool = Field(default=False, description="Skip control-plane calls when True")
    confidence_threshold: float = Field(
        default=0.2, description="Below this recorded confidence a step is treated as failed"
    )
    auto_recover: bool = Field(
        default=False,
        description="Re-invoke the provider once when a non-streaming response scores below "
        "confidence_threshold. Off by default: a retry re-bills the model call.",
    )

    @classmethod
    def from_env(
        cls,
        api_key: Optional[str] = None,
        provider_api_key: Optional[str] = None,
        server_url: Optional[str] = None,
        dashboard_url: Optional[str] = None,
        **overrides: object,
    ) -> "ARCConfig":
        """Build a config, preferring explicit args then environment variables.

        This resolves defaults only; it performs no validation beyond Pydantic's
        and never contacts the network.
        """
        return cls(
            api_key=api_key or os.getenv("ARC_API_KEY"),
            provider_api_key=provider_api_key or os.getenv("ANTHROPIC_API_KEY"),
            server_url=server_url or os.getenv("ARC_SERVER_URL", DEFAULT_SERVER_URL),
            dashboard_url=dashboard_url or os.getenv("ARC_DASHBOARD_URL", DEFAULT_DASHBOARD_URL),
            **overrides,  # type: ignore[arg-type]
        )


__all__ = ["ARCConfig", "DEFAULT_SERVER_URL", "DEFAULT_DASHBOARD_URL"]
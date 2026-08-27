"""Provider adapters for ARC runtime.

Translates abstract graph decisions into provider SDK kwargs.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, Optional


def make_provider_adapter(provider: str = "anthropic"):
    """Create a provider adapter for the given provider.
    
    Returns an adapter callable that translates graph decisions
    into provider SDK keyword arguments.
    """
    warnings.warn("Provider adapter not fully implemented in scaffold", always_warn=True)
    return None
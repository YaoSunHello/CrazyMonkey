"""The deliberately small, local-only UI integration surface.

The bridge is namespaced so the existing API and command-line pipeline keep
their contracts.  It only orchestrates deterministic code already present in
the backend; it never imports or invokes the agent, model, or sandbox layers.
"""

from app.ui_bridge.router import router

__all__ = ["router"]

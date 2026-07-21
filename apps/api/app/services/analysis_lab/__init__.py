"""Interactive Demo Lab: deterministic, stateless preview analysis over structured signals.

Reuses the existing context and placement engines — no filesystem scan, no repository clone, no
code execution, no GPT, no persistence. Path-like strings in the input are descriptive metadata
only and are never opened.
"""

from app.services.analysis_lab.preview import AnalysisPreviewService

__all__ = ["AnalysisPreviewService"]

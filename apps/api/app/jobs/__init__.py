"""Standalone lifecycle jobs (retention, incident lifecycle, reconstruction worker).

These run as separate worker/cron entrypoints, not inside API replicas, so cleanup and
reconstruction work never runs implicitly on every request path.
"""

# Purpose: enforce per-sandbox budgets for the restricted judge workspace.
# Responsibilities: decide whether an action is within its budget, produce a safe denial carrying a
#   Retry-After only when waiting actually helps, and record consumption durably on the sandbox row.
# Design: budgets are per SESSION, not sliding windows. A sandbox is already TTL-bound, so a spent
#   budget is bounded in time by the session itself, and the accounting survives reset — resetting
#   restores the sandbox's data, never its budget. Counters live on the sandbox row rather than in
#   Redis so a cache eviction cannot silently refill a judge's allowance.
# Dependencies: settings, records. No HTTP.
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.config.settings import Settings
from app.models.records import JudgeSandboxRecord

# Actions a judge may spend budget on. Names are stable — they appear in denial messages.
ANALYZE = "analyze"
INTERACT = "interact"
EXPORT = "export"
RESET = "reset"


@dataclass(frozen=True)
class QuotaDenial:
    """A refused action. `retry_after_seconds` is set ONLY when waiting will actually help."""

    action: str
    reason: str
    detail: str
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class QuotaState:
    """What a judge has spent and what remains. Surfaced so the UI never guesses."""

    action: str
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


class JudgeQuotaService:
    """Budget decisions for one sandbox session."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ---- inspection ------------------------------------------------------------------------

    def state(self, record: JudgeSandboxRecord) -> dict[str, QuotaState]:
        return {
            ANALYZE: QuotaState(ANALYZE, record.analysis_runs, self._limit(ANALYZE)),
            INTERACT: QuotaState(INTERACT, record.interactions, self._limit(INTERACT)),
            EXPORT: QuotaState(EXPORT, record.exports, self._limit(EXPORT)),
        }

    # ---- decisions -------------------------------------------------------------------------

    def check(
        self,
        record: JudgeSandboxRecord,
        action: str,
        *,
        now: datetime | None = None,
    ) -> QuotaDenial | None:
        """Return a denial, or None when the action is within budget."""
        moment = now or datetime.now(UTC)
        if action == RESET:
            return self._check_reset(record, moment)
        limit = self._limit(action)
        used = self._used(record, action)
        if used < limit:
            return None
        # A spent session budget is not a wait — resetting will not refill it and neither will
        # time. Deliberately no Retry-After: sending one would tell the client to sleep and retry
        # an action that can never succeed in this session.
        return QuotaDenial(
            action=action,
            reason="budget_exhausted",
            detail=(
                f"this sandbox session has used its {action} budget ({used}/{limit}); "
                "start a new sandbox session to continue"
            ),
        )

    def _check_reset(self, record: JudgeSandboxRecord, now: datetime) -> QuotaDenial | None:
        cooldown = self._settings.judge_reset_cooldown_seconds
        last = record.last_reset_at
        if cooldown <= 0 or last is None:
            return None
        if last.tzinfo is None:
            # Some drivers round-trip without a timezone; treat stored values as UTC.
            last = last.replace(tzinfo=UTC)
        elapsed = (now - last).total_seconds()
        if elapsed >= cooldown:
            return None
        # Here waiting genuinely helps, so a Retry-After is honest. Rounded up so a client that
        # sleeps exactly this long is past the cooldown rather than one call short of it.
        remaining = int(cooldown - elapsed) + 1
        return QuotaDenial(
            action=RESET,
            reason="cooldown",
            detail=f"sandbox reset is rate limited; retry in {remaining}s",
            retry_after_seconds=remaining,
        )

    # ---- consumption -----------------------------------------------------------------------

    def consume(
        self,
        record: JudgeSandboxRecord,
        action: str,
        *,
        now: datetime | None = None,
    ) -> None:
        """Record one use. Callers must `check` first; this does not re-decide."""
        moment = now or datetime.now(UTC)
        if action == ANALYZE:
            record.analysis_runs += 1
        elif action == INTERACT:
            record.interactions += 1
        elif action == EXPORT:
            record.exports += 1
        elif action == RESET:
            record.resets += 1
            record.last_reset_at = moment
        else:
            raise ValueError(f"unknown judge action: {action}")

    # ---- internals -------------------------------------------------------------------------

    def _limit(self, action: str) -> int:
        limits = {
            ANALYZE: self._settings.judge_max_analysis_runs,
            INTERACT: self._settings.judge_max_interactions,
            EXPORT: self._settings.judge_max_exports,
        }
        if action not in limits:
            raise ValueError(f"unknown judge action: {action}")
        return limits[action]

    @staticmethod
    def _used(record: JudgeSandboxRecord, action: str) -> int:
        used = {
            ANALYZE: record.analysis_runs,
            INTERACT: record.interactions,
            EXPORT: record.exports,
        }
        if action not in used:
            raise ValueError(f"unknown judge action: {action}")
        return used[action]

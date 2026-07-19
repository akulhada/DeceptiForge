# Purpose: orchestrate the safe database-honey lifecycle for approved deployments.
# Responsibilities: execute (re-check safety, connect with TLS/timeouts, insert one approved row
#   transactionally, read back and verify, then activate monitoring), and retire/rollback (delete
#   only the exact owned row after an ownership/drift revalidation). Idempotent, org-scoped,
#   audited; never logs credentials or full rows. Dependencies: repository, port, settings.
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from app.config.settings import Settings
from app.models.domain.database_honey import HoneyDeploymentStatus
from app.repositories.database_honey import DatabaseHoneyRepository
from app.services.database.connector_port import (
    ConnectionSpec,
    ConnectorError,
    DatabaseConnectorClient,
)
from app.services.database.generation import generate_row
from app.services.database.policy import evaluate_table
from app.services.metrics import emit


class DatabaseHoneyService:
    def __init__(
        self,
        repo: DatabaseHoneyRepository,
        client: DatabaseConnectorClient,
        settings: Settings,
        *,
        request_id: str = "worker",
    ) -> None:
        self._repo = repo
        self._client = client
        self._settings = settings
        self._request_id = request_id

    def _spec(self, connector) -> ConnectionSpec:  # type: ignore[no-untyped-def]
        secret = self._repo.resolve_secret(connector)
        return ConnectionSpec(
            host=connector.host_reference,
            database=connector.database_name,
            user=str(secret.get("user", "")),
            password=str(secret.get("password", "")),
            ssl_mode=connector.ssl_mode,
            connect_timeout_seconds=self._settings.database_connect_timeout_seconds,
            statement_timeout_ms=self._settings.database_statement_timeout_ms,
        )

    def _audit(self, org: UUID, dep_id: UUID, event: str, meta: str = "") -> None:
        self._repo.add_audit(
            organization_id=org, deployment_id=dep_id, event_type=event,
            request_id=self._request_id, safe_metadata=meta,
        )

    def _fail(self, record, code: str, message: str) -> None:  # type: ignore[no-untyped-def]
        self._repo.transition(
            record, HoneyDeploymentStatus.FAILED, failure_code=code,
            safe_failure_message=message[:512],
        )
        self._audit(record.organization_id, record.id, "deployment_failed", code)

    # -- execute: insert + verify + activate --------------------------------------------------

    def execute(self, organization_id: UUID, deployment_id: UUID) -> None:
        record = self._repo.get_deployment(organization_id, deployment_id)
        if record.status != HoneyDeploymentStatus.DEPLOYING.value:
            return
        preview = self._repo.load_preview(record)
        if preview is None:
            self._fail(record, "no_preview", "deployment has no preview")
            return
        snapshot = self._repo.get_snapshot(organization_id, record.schema_snapshot_id)

        # Re-run safety immediately before writing (schema may have drifted).
        table = next(
            (
                t for t in snapshot.tables
                if t.schema_name == record.target_schema and t.table_name == record.target_table
            ),
            None,
        )
        eligibility = (
            evaluate_table(
                table,
                allowed_schemas=tuple(self._settings.database_allowed_schemas),
                blocked_patterns=tuple(self._settings.database_blocked_table_patterns),
            )
            if table is not None
            else None
        )
        if table is None or eligibility is None or not eligibility.deployable:
            self._fail(record, "safety_failed", "table failed the safety re-check")
            return

        # The exact row is regenerated deterministically from the same table + trace, so the preview
        # can store masked values only. A fingerprint mismatch means the plan drifted -> refuse.
        row = generate_row(
            table, trace_id=preview.trace_id, required_fields=eligibility.required_fields
        )
        if row.row_fingerprint != preview.row_fingerprint:
            self._fail(record, "plan_drift", "regenerated row does not match the approved preview")
            return
        row_values: dict[str, str | int | float | bool | None] = dict(row.values)

        # Idempotency: the same fingerprint is never inserted twice.
        if self._repo.record_exists(deployment_id, preview.row_fingerprint):
            self._activate(record, deployment_id, organization_id, expected=1)
            return

        connector = self._repo.get_connector(organization_id, record.connector_id)
        try:
            self._audit(organization_id, deployment_id, "transaction_started")
            result = self._client.insert_row(
                self._spec(connector),
                schema=record.target_schema,
                table=record.target_table,
                values=row_values,
                pk_columns=table.primary_key,
            )
        except ConnectorError as error:
            self._fail(record, "insert_failed", str(error))
            return
        if not (result.inserted and result.verified):
            self._repo.transition(
                record, HoneyDeploymentStatus.VERIFICATION_FAILED,
                failure_code="verify_failed",
                safe_failure_message="inserted row failed read-back verification",
            )
            self._audit(organization_id, deployment_id, "verification_failed")
            return
        self._audit(organization_id, deployment_id, "row_inserted")
        self._audit(organization_id, deployment_id, "verification_passed")
        persisted = self._repo.add_record(
            organization_id=organization_id,
            deployment_id=deployment_id,
            trace_id=preview.trace_id,
            primary_key=result.primary_key,
            row_fingerprint=preview.row_fingerprint,
            inserted_values=row_values,
            verification_hash=result.verification_hash,
        )
        _ = persisted  # a False race result is fine; activation counts the truth in the database
        self._activate(record, deployment_id, organization_id, expected=1)

    def _activate(self, record, deployment_id, organization_id, *, expected: int) -> None:  # type: ignore[no-untyped-def]
        now = datetime.now(UTC)
        active = self._repo.active_record_count(deployment_id)
        if active >= expected and active > 0:
            self._repo.transition(
                record, HoneyDeploymentStatus.DEPLOYED, deployed_at=now,
                monitoring_activated_at=now,
            )
            self._audit(organization_id, deployment_id, "monitoring_activated", f"records={active}")
        else:
            self._repo.transition(
                record, HoneyDeploymentStatus.DEPLOYED_UNMONITORED, deployed_at=now,
                failure_code="activation_failed",
                safe_failure_message="row inserted but monitoring activation was incomplete",
            )
            emit(
                "database_honey_activation_failed", severity="high",
                deployment_id=str(deployment_id), organization_id=str(organization_id),
            )
            self._audit(organization_id, deployment_id, "monitoring_activation_failed")

    # -- retire / rollback: delete exact owned rows -------------------------------------------

    def retire(self, organization_id: UUID, deployment_id: UUID) -> None:
        self._remove(organization_id, deployment_id, HoneyDeploymentStatus.RETIRED, "retirement")

    def rollback(self, organization_id: UUID, deployment_id: UUID) -> None:
        self._remove(organization_id, deployment_id, HoneyDeploymentStatus.ROLLED_BACK, "rollback")

    def _remove(
        self, organization_id: UUID, deployment_id: UUID,
        terminal: HoneyDeploymentStatus, kind: str,
    ) -> None:
        record = self._repo.get_deployment(organization_id, deployment_id)
        expected = (
            HoneyDeploymentStatus.RETIRING if kind == "retirement"
            else HoneyDeploymentStatus.ROLLBACK_PENDING
        )
        if record.status != expected.value:
            return
        self._audit(organization_id, deployment_id, f"{kind}_started")
        connector = self._repo.get_connector(organization_id, record.connector_id)
        for honey in self._repo.records_for(deployment_id):
            if honey.status == "retired":
                continue
            primary_key = json.loads(honey.target_primary_key)
            expected_row = self._repo.decrypt_values(honey)
            try:
                result = self._client.delete_owned_row(
                    self._spec(connector),
                    schema=record.target_schema,
                    table=record.target_table,
                    primary_key=primary_key,
                    expected_row=expected_row,
                )
            except ConnectorError as error:
                self._fail(record, "delete_failed", str(error))
                return
            if result.drift:
                # The row changed unexpectedly: do not delete; require manual review.
                self._repo.transition(
                    record, HoneyDeploymentStatus.DRIFT_DETECTED,
                    failure_code="row_drift",
                    safe_failure_message="owned row changed; manual review required",
                )
                self._audit(organization_id, deployment_id, "drift_detected")
                return
            self._repo.set_record_status(honey, "retired")
        self._repo.transition(record, terminal, retired_at=datetime.now(UTC))
        self._audit(organization_id, deployment_id, f"{kind}_completed")

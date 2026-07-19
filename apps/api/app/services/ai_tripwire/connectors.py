# Purpose: define the RAG and MCP connector ports and deterministic fake adapters.
# Responsibilities: express the operations the tripwire flow needs (test, list, deploy, verify,
#   delete/retire, metadata, health) for vector stores and MCP servers, without binding to a paid
#   provider. Deployment is idempotent by asset id; verify/delete carry a content-hash ownership
#   check so a modified external asset is detected as drift. Fakes are in-memory and token-free.
#   Dependencies: stdlib only.
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ConnSpec:
    reference: str  # collection/index or MCP server reference (resolved in memory)
    secret: str | None
    tls: bool


@dataclass(frozen=True)
class ConnTest:
    reachable: bool
    tls_ok: bool
    authenticated: bool
    safe_error_code: str | None = None


@dataclass(frozen=True)
class DeployResult:
    external_asset_id: str
    deployed: bool
    verification_hash: str


@dataclass(frozen=True)
class VerifyResult:
    exists: bool
    hash_match: bool
    trace_present: bool


@dataclass(frozen=True)
class DeleteResult:
    deleted: bool
    drift: bool


class ConnectorError(Exception):
    """Provider-side failure. Messages are safe (no secrets, no raw content)."""


def _vhash(collection: str, asset_id: str, content_hash: str) -> str:
    return hashlib.sha256(f"{collection}:{asset_id}:{content_hash}".encode()).hexdigest()


class RagConnectorAdapter(Protocol):
    def test_connection(self, spec: ConnSpec) -> ConnTest: ...
    def list_collections(self, spec: ConnSpec) -> tuple[str, ...]: ...
    def deploy_document(
        self, spec: ConnSpec, *, collection: str, document_id: str,
        title: str, body: str, content_hash: str, metadata: dict[str, str], trace_token: str,
    ) -> DeployResult: ...
    def verify_document(
        self, spec: ConnSpec, *, collection: str, external_asset_id: str,
        expected_hash: str, trace_token: str,
    ) -> VerifyResult: ...
    def delete_document(
        self, spec: ConnSpec, *, collection: str, external_asset_id: str, expected_hash: str,
    ) -> DeleteResult: ...
    def health_check(self, spec: ConnSpec) -> bool: ...


class McpConnectorAdapter(Protocol):
    def test_connection(self, spec: ConnSpec) -> ConnTest: ...
    def list_resources(self, spec: ConnSpec) -> tuple[str, ...]: ...
    def deploy_resource(
        self, spec: ConnSpec, *, uri: str, name: str, description: str,
        content_hash: str, metadata: dict[str, str], trace_token: str,
    ) -> DeployResult: ...
    def verify_resource(
        self, spec: ConnSpec, *, external_asset_id: str, expected_hash: str, trace_token: str,
    ) -> VerifyResult: ...
    def retire_resource(
        self, spec: ConnSpec, *, external_asset_id: str, expected_hash: str,
    ) -> DeleteResult: ...
    def health_check(self, spec: ConnSpec) -> bool: ...


@dataclass
class _Asset:
    content_hash: str
    trace_token: str
    metadata: dict[str, str]


class FakeRagAdapter:
    """Deterministic in-memory vector-store. Seed collections with register_collection()."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, _Asset]] = {}
        self.fail_deploy = False

    def register_collection(self, name: str) -> None:
        self._collections.setdefault(name, {})

    def test_connection(self, spec: ConnSpec) -> ConnTest:
        return ConnTest(reachable=True, tls_ok=spec.tls, authenticated=spec.secret is not None)

    def list_collections(self, spec: ConnSpec) -> tuple[str, ...]:
        return tuple(sorted(self._collections))

    def deploy_document(
        self, spec: ConnSpec, *, collection: str, document_id: str,
        title: str, body: str, content_hash: str, metadata: dict[str, str], trace_token: str,
    ) -> DeployResult:
        if self.fail_deploy:
            raise ConnectorError("deploy not permitted")
        store = self._collections.setdefault(collection, {})
        asset_id = f"rag:{collection}:{document_id}"  # deterministic -> idempotent
        store[asset_id] = _Asset(content_hash, trace_token, metadata)
        return DeployResult(asset_id, True, _vhash(collection, asset_id, content_hash))

    def verify_document(
        self, spec: ConnSpec, *, collection: str, external_asset_id: str,
        expected_hash: str, trace_token: str,
    ) -> VerifyResult:
        asset = self._collections.get(collection, {}).get(external_asset_id)
        if asset is None:
            return VerifyResult(False, False, False)
        return VerifyResult(
            True, asset.content_hash == expected_hash, asset.trace_token == trace_token
        )

    def delete_document(
        self, spec: ConnSpec, *, collection: str, external_asset_id: str, expected_hash: str,
    ) -> DeleteResult:
        store = self._collections.get(collection, {})
        asset = store.get(external_asset_id)
        if asset is None:
            return DeleteResult(False, False)
        if asset.content_hash != expected_hash:
            return DeleteResult(False, True)  # modified -> drift, do not delete
        del store[external_asset_id]
        return DeleteResult(True, False)

    def health_check(self, spec: ConnSpec) -> bool:
        return True

    # test helpers
    def asset_count(self, collection: str) -> int:
        return len(self._collections.get(collection, {}))

    def mutate(self, collection: str, asset_id: str, content_hash: str) -> None:
        self._collections[collection][asset_id].content_hash = content_hash


class FakeMcpAdapter:
    """Deterministic in-memory MCP server. Resources keyed by URI."""

    def __init__(self) -> None:
        self._resources: dict[str, _Asset] = {}
        self.fail_deploy = False

    def test_connection(self, spec: ConnSpec) -> ConnTest:
        return ConnTest(reachable=True, tls_ok=spec.tls, authenticated=True)

    def list_resources(self, spec: ConnSpec) -> tuple[str, ...]:
        return tuple(sorted(self._resources))

    def deploy_resource(
        self, spec: ConnSpec, *, uri: str, name: str, description: str,
        content_hash: str, metadata: dict[str, str], trace_token: str,
    ) -> DeployResult:
        if self.fail_deploy:
            raise ConnectorError("deploy not permitted")
        self._resources[uri] = _Asset(content_hash, trace_token, metadata)
        return DeployResult(uri, True, _vhash("mcp", uri, content_hash))

    def verify_resource(
        self, spec: ConnSpec, *, external_asset_id: str, expected_hash: str, trace_token: str,
    ) -> VerifyResult:
        asset = self._resources.get(external_asset_id)
        if asset is None:
            return VerifyResult(False, False, False)
        return VerifyResult(
            True, asset.content_hash == expected_hash, asset.trace_token == trace_token
        )

    def retire_resource(
        self, spec: ConnSpec, *, external_asset_id: str, expected_hash: str,
    ) -> DeleteResult:
        asset = self._resources.get(external_asset_id)
        if asset is None:
            return DeleteResult(False, False)
        if asset.content_hash != expected_hash:
            return DeleteResult(False, True)
        del self._resources[external_asset_id]
        return DeleteResult(True, False)

    def health_check(self, spec: ConnSpec) -> bool:
        return True

    def resource_count(self) -> int:
        return len(self._resources)

    def mutate(self, uri: str, content_hash: str) -> None:
        self._resources[uri].content_hash = content_hash

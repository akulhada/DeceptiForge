"""Deterministic safety and obvious-trap checks over generated asset values."""

from app.models.domain.decoy import (
    DecoyAsset,
    GeneratedDatabaseRecord,
    GeneratedDocument,
    GeneratedSecret,
)

_BANNED_MARKERS = ("fake_secret", "canary_token", "do_not_use", "honeytoken")


class SafetyValidator:
    def evaluate(self, asset: DecoyAsset) -> tuple[float, float, float, tuple[str, ...]]:
        values = self._values(asset)
        combined = " ".join(values).lower()
        failures: list[str] = []
        inert = 100.0
        if (
            asset.safety_metadata.contains_real_credentials
            or asset.safety_metadata.contains_real_customer_data
            or not asset.safety_metadata.safe_for_demo
            or asset.safety_metadata.authentication_capability != "none"
        ):
            inert = 0.0
            failures.append("asset safety metadata does not guarantee inert demo-safe content")
        if isinstance(asset.payload, GeneratedSecret) and not asset.payload.fake_value.startswith(
            "dfg_inert_"
        ):
            inert = 0.0
            failures.append("secret value is not the approved inert format")
        trap = 100.0 if any(marker in combined for marker in _BANNED_MARKERS) else 0.0
        if trap:
            failures.append("payload contains an obvious deception marker")
        accidental = 0.0
        if isinstance(asset.payload, GeneratedSecret):
            accidental = 15.0
        if isinstance(asset.payload, GeneratedDatabaseRecord):
            accidental = 10.0
            if asset.payload.no_real_person_safeguard != "no_personal_data":
                accidental = 100.0
                failures.append("database payload lacks the no-personal-data safeguard")
        return inert, accidental, trap, tuple(failures)

    @staticmethod
    def _values(asset: DecoyAsset) -> tuple[str, ...]:
        payload = asset.payload
        if isinstance(payload, GeneratedSecret):
            return (payload.key_name, payload.fake_value)
        if isinstance(payload, GeneratedDocument):
            return (payload.title, payload.body)
        if isinstance(payload, GeneratedDatabaseRecord):
            return (payload.table_name, *(field.display_value for field in payload.fields))
        return ()

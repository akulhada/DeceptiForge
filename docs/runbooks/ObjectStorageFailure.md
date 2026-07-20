<!-- Runbook: object/evidence storage failure. -->

# Runbook: object storage failure

1. Core alert/incident state continues if no artifact write is required.
2. Evidence-package generation and artifact-dependent operations pause and fail safely.
3. Investigate replication/KMS access; a legal-hold replication failure is a high-severity incident.
4. On recovery, verify a restored object (`verify_object_storage.sh`) — checksum matches, encryption/
   key access works, classification + legal-hold status preserved.

# Customer onboarding

Onboarding is an opt-in, tenant-scoped activation workspace. Its status is reconciled from
authoritative product records; clients cannot complete a setup step directly.

Activation requires a verified identity policy, an inventoried surface, a scan, a reviewed and
verified monitored deployment, a controlled signed detection, coverage, and an active integration.
If SSO verification has no persisted identity-provider source, the identity step intentionally stays
blocked rather than inferring success from an API key.

The only default first-deployment recommendation is low risk: an inert documentation or
configuration decoy. Accepting it records intent only; the existing approval and deployment flow
remains mandatory.

`POST /onboarding/detection-tests` creates a pending controlled test only for a verified deployment
with an active tripwire. It never inserts an alert or incident. A test completes solely when the
existing signed monitoring ingestion path persists a matching event.

Onboarding APIs are disabled until `ONBOARDING_ENABLED=true`. Controlled test creation additionally
requires `ONBOARDING_DETECTION_TEST_ENABLED=true`. No onboarding route invokes `/demo/*`.

# Runbook — judge and demo access

Provisioning, lifetime, and teardown for the credentials handed to external evaluators.

## Principle

Judge access is server-verified with no anonymous fallback. The `judge` and `demo` roles are absent
from `TENANT_GRANTABLE_ROLES`, so no tenant administrator can mint them and there is no public
endpoint that hands one out. An operator provisions them out-of-band and distributes them.

## Sizing the sandbox lifetime

**This is the decision that most often gets made wrong.** The default
(`JUDGE_SANDBOX_TTL_HOURS=8`) suits a single sitting. Evaluation windows usually span days, and a
credential that expires mid-review looks like a broken product rather than an expired session.

Set the TTL to cover the **entire evaluation window plus a margin**, at provisioning time:

```sh
# One judge, evaluating across a five-day window, with a day of slack.
python scripts/provision_judge_sandbox.py --ttl-hours 144
```

| Scenario | Suggested `--ttl-hours` |
| --- | --- |
| Live walkthrough or single sitting | 8 (default) |
| Judging over a weekend | 72 |
| Week-long evaluation window | 168 |
| Open-ended pilot | reprovision weekly rather than issuing an unbounded credential |

Do not disable expiry. The TTL is what bounds how long judge-created records persist and what
limits the damage of a leaked credential; an unbounded sandbox is an unbounded liability. Prefer a
generous, explicit deadline over no deadline.

The lifetime is fixed when the sandbox is created. There is deliberately no extend operation: a
client cannot lengthen its own session, and an operator issues a fresh sandbox instead.

## Provisioning

One sandbox per judge. Each gets its own generated organization, so no judge can see another's
work, and quota accounting is per session.

```sh
cd apps/api
python scripts/provision_judge_sandbox.py --ttl-hours 168
```

Prints `JUDGE_ORG_ID`, `JUDGE_API_KEY`, `JUDGE_SESSION_ID` and `JUDGE_EXPIRES_AT`. **The key is
shown once and is not recoverable.** Treat the output — and any CI log or terminal scrollback that
captured it — as credential material.

The script refuses to run when the deployment mode does not host the workspace or
`JUDGE_WORKSPACE_ENABLED` is false, rather than creating an organization and a credential that no
route serves.

For the curated demo, reads are open and need no credential. Only the mutating routes (seed,
simulate, trigger, reset, run) require one:

```sh
python scripts/provision_judge_sandbox.py --demo-credential --ttl-hours 168
```

## Distribution

Send each judge their own base URL, organization id, and key over a channel you would use for any
other credential. Do not commit them, do not put them in the submission README, and do not reuse one
credential across judges — shared credentials defeat the per-session isolation and make the quota
accounting meaningless.

## What a judge sees when a sandbox expires

The workspace shows "This sandbox session has ended" and stops working. The API answers `410` on
every judge route. Nothing is silently degraded.

Recovery is to issue a new sandbox; the expired one cannot be revived. If this happens during an
evaluation, the TTL was sized too short — reprovision with a longer window and reissue.

## Teardown

After evaluation closes:

1. Let the sandboxes expire, or expire them early by setting `status = 'expired'` on the
   `judge_sandboxes` rows. Expiry is evaluated server-side on every request, so a sandbox stops
   working immediately without waiting for a sweep.
2. Revoke the API keys (`status` on the `api_keys` rows) if you want the credentials dead before
   their own expiry.
3. Judge-created records live in the sandbox organization and are removed with it. They never share
   an organization with a tenant, so no tenant data is involved in cleanup.

Expired sandboxes retain their rows for audit. `SecurityAuditRecord` entries are append-only and are
deliberately outside the reset allowlist — a judge cannot erase their own audit trail, and neither
does teardown.

## Verifying before an evaluation begins

```sh
# The workspace answers with backend state, not a hardcoded page.
curl -s -H "X-DeceptiForge-Org-Id: $JUDGE_ORG_ID" \
     -H "X-DeceptiForge-API-Key: $JUDGE_API_KEY" \
     "$BASE_URL/api/v1/judge/workspace" | jq '{label, expires_at, quotas}'
```

Confirm `expires_at` covers the full evaluation window before sending anything to a judge.

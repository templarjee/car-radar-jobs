# Car Radar Jobs

Minimal public Arval catalog runner. The application, database and production operations remain private.

## Production policy

**Production policy: DAILY FULL CATALOG, INDEFINITE.**

The sole automatic catalog scheduler is `.github/workflows/arval-scheduled.yml`,
with `17 7 * * *` on main. Every day includes weekends and Mondays. There is no
November 4/9 switch, expiration, targeted daily job or weekly-only fallback.
This owner decision was reaffirmed on 2026-11-02 (V2.30).

GitHub cron is best effort, not an execution-time guarantee. Existing owner-only
monitoring checks actual complete catalog imports and price counts, separately
from availability receipts; it is on demand, not continuous alert delivery.
Investigate a missing current-day import after 14:17 UTC through Actions and
receipts before authorizing recovery. Do not add an automatic second crawler.

## Execution

- Standard GitHub-hosted `ubuntu-24.04` runners.
- Daily complete catalog at 07:17 UTC. Manual modes: smoke, dry-run, import.
- Pushes to main run offline tests only.
- The emergency workflow runs only when an authorized main-branch push changes `recovery-request.json`; it validates a dry crawl before importing the same snapshot.
- Completed imports trigger server-verified availability confirmation.
- External market onboarding runs every 15 minutes; maintenance runs Mondays at 06:17 UTC. Source planning, budgets, cooldowns and archives remain private; only aggregate run counters enter public logs.
- Cached market evaluation and photo workers remain in Supabase Cron. A separate targeted catalog job is unnecessary while the full catalog runs daily.

## Authentication and data handling

No database credentials or long-lived secrets. Short-lived GitHub OIDC tokens authorize only the exact repository ID, owner ID, main ref, workflow and event. Forks and pull requests cannot ingest.

Snapshots remain transient on the runner. No data commits, caches or uploaded artifacts. Logs expose only aggregate counts. Imports fail on incomplete pagination, duplicate IDs, missing mandatory fields, implausible baseline drops or stale capture times. The backend rechecks stored counts and commits ingestion atomically. A green smoke/dry-run is not a successful production import.

Cards explicitly marked `Cenu připravujeme` are recorded separately as pending-price
pagination evidence, including pages containing only those cards. They create no
price observations; import totals remain counts of priced offers. Arbitrary empty
pages, missing prices without that source marker, and unknown error responses do
not establish a catalog end. Presence tracking for unpriced offers is a separate
backend concern; the existing availability contract still receives priced offers.

Availability is confirmed only after the backend independently retrieves successful source-run evidence and matching immutable database receipts. A crawl cannot directly authorize archival.

## Local verification

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Production commands require GitHub Actions OIDC and cannot authenticate from a personal machine. All deployment and rollback procedures remain in the private backend repository.

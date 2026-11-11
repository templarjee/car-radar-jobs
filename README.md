# Car Radar Jobs

Minimal public Arval catalog runner. The application, database and production operations remain private.

## Production policy

**Production policy: DAILY FULL CATALOG, INDEFINITE.**

The sole catalog collection workflow is `.github/workflows/arval-scheduled.yml`,
on main: primary at `07:17 UTC`, conditional recovery opportunities at
`14:47 UTC` and `18:47 UTC`. Every day includes weekends and Mondays, with
no calendar cutoff. Recovery opportunities check the trusted production baseline
via GitHub OIDC and **do not crawl** when today's complete import already exists.
The runs are serialized by a shared concurrency group; manual imports remain
explicit. This updates the 2026-11-02 policy after the 2026-11-10 incident.

GitHub cron is best effort, not an execution-time guarantee. A separate
`.github/workflows/arval-daily-slo.yml` checks the GitHub audit trail at
20:47 UTC for a successful verified import checkpoint (not merely smoke, dry-run
or a skipped backup). If missing, it fails and opens one dated GitHub issue.
This is a best-effort alert, not a guaranteed push notification. A missing day
is never filled with prices copied from a later crawl.

## Execution

- Standard GitHub-hosted `ubuntu-24.04` runners.
- Daily complete catalog at 07:17 UTC, conditional no-op-or-recovery attempts at
  14:47/18:47 UTC. Manual modes: smoke, dry-run, import.
- Pushes to main run offline tests only.
- The emergency workflow runs only when an authorized main-branch push changes `recovery-request.json`; it validates a dry crawl before importing the same snapshot.
- Completed imports trigger server-verified availability confirmation.
- External market onboarding runs every 15 minutes; maintenance runs Mondays at 06:17 UTC. Source planning, budgets, cooldowns and archives remain private; only aggregate run counters enter public logs.
- Cached market evaluation and photo workers remain in Supabase Cron. A separate targeted catalog job is unnecessary while the full catalog runs daily.

## Authentication and data handling

No database credentials or long-lived secrets. Short-lived GitHub OIDC tokens authorize only the exact repository ID, owner ID, main ref, workflow and event. Forks and pull requests cannot ingest.

Snapshots remain transient on the runner. No data commits, caches or uploaded artifacts.
On source-collection or snapshot-validation errors, the crawler makes up to
three fresh attempts with bounded delay before failing closed. Validation logs
emit error categories and a small sample of public listing IDs for root-cause
analysis; no raw snapshot or access credentials are published. Source evidence
cannot be reconstructed after the failed runner exits. Imports still fail on
incomplete pagination, duplicate priced IDs, missing mandatory fields,
implausible baseline drops or stale capture times. The backend rechecks stored
counts and commits ingestion atomically. A green smoke/dry-run is not a successful
production import.

Cards explicitly marked `Cenu připravujeme` are recorded separately as pending-price
pagination evidence, including pages containing only those cards. IDs repeated
across page boundaries or transitioning from pending to a real price are
reconciled without creating fictional prices. They create no price observations;
import totals remain counts of priced offers. Arbitrary empty
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

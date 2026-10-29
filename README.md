# Car Radar Jobs

Minimal public Arval catalog runner. The application, database and production operations remain private.

## Execution

- Standard GitHub-hosted `ubuntu-24.04` runners.
- Daily complete catalog at 07:17 UTC. Manual modes: smoke, dry-run, import.
- Pushes to main run offline tests only.
- The emergency workflow runs only when an authorized main-branch push changes `recovery-request.json`; it validates a dry crawl before importing the same snapshot.
- Completed imports trigger server-verified availability confirmation.

## Authentication and data handling

No database credentials or long-lived secrets. Short-lived GitHub OIDC tokens authorize only the exact repository ID, owner ID, main ref, workflow and event. Forks and pull requests cannot ingest.

Snapshots remain transient on the runner. No data commits, caches or uploaded artifacts. Logs expose only aggregate counts. Imports fail on incomplete pagination, duplicate IDs, missing mandatory fields, implausible baseline drops or stale capture times. The backend rechecks stored counts and commits ingestion atomically. A green smoke/dry-run is not a successful production import.

Availability is confirmed only after the backend independently retrieves successful source-run evidence and matching immutable database receipts. A crawl cannot directly authorize archival.

## Local verification

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Production commands require GitHub Actions OIDC and cannot authenticate from a personal machine. All deployment and rollback procedures remain in the private backend repository.

# ReliefOS Database Backup & Disaster Recovery Runbook

This document defines the standard operating procedures for backing up, verifying, and restoring the ReliefOS persistent PostgreSQL + PostGIS database.

---

## 1. Database Architecture Overview

ReliefOS persists all operational and analytical state inside a PostgreSQL 15+ database equipped with PostGIS 3.3+.
Key persistent tables include:
- **Core Operations**: `settlements`, `roads`, `bridges`, `medical_facilities`, `needs`, `resource_offers`, `operations`, `organizations`, `activity_events`, `notifications`
- **Geospatial Snapshots**: `flood_snapshots` (with PostGIS geometries and confidence metrics)
- **Coordination & Privacy**: `coordination_proposals` (sanitized public views + org-scoped evaluations)
- **Event-Driven Outbox**: `agent_events` (persistent outbox with status tracking, retry counters, error payloads)
- **Security & Multi-Tenancy**: `users`, `organization_memberships`
- **Compliance & Auditability**: `audit_logs` (immutable records of human approvals, overrides, status changes)

---

## 2. Automated & Manual Backup Procedures

### 2.1 Full Logical Backup (pg_dump)

Run a compressed binary dump (`custom` format) containing all schemas, tables, and PostGIS geometries:

```bash
# Set database credentials
export PGHOST="localhost"
export PGPORT="5433"
export PGUSER="reliefos"
export PGDATABASE="reliefos"
export PGPASSWORD="your_secure_password"

# Timestamped dump
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="/var/backups/reliefos/reliefos_backup_${TIMESTAMP}.dump"

pg_dump -Fc -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE -f "$BACKUP_FILE"
```

### 2.2 Plain Text SQL Schema & Data Dump

For cross-version migration or textual inspection:

```bash
pg_dump -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE --clean --if-exists -f "/var/backups/reliefos/reliefos_dump_${TIMESTAMP}.sql"
```

### 2.3 Automated Cron Schedule (Recommended)

Add the following to the system crontab (`crontab -e`) to execute nightly dumps at 02:00 UTC with 30-day retention:

```cron
0 2 * * * pg_dump -Fc -h localhost -p 5433 -U reliefos -d reliefos -f /var/backups/reliefos/reliefos_$(date +\%Y\%m\%d).dump && find /var/backups/reliefos/ -name "*.dump" -mtime +30 -delete
```

---

## 3. Disaster Recovery & Restoration Procedure

### 3.1 Scenario: Complete Database Rebuild

If the database server fails or data corruption occurs, follow these steps:

1. **Provision Fresh PostgreSQL Instance with PostGIS**:
   ```sql
   CREATE USER reliefos WITH PASSWORD 'your_secure_password';
   CREATE DATABASE reliefos OWNER reliefos;
   \c reliefos
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```

2. **Restore from Dump**:
   ```bash
   pg_restore -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE --clean --if-exists -v "$BACKUP_FILE"
   ```

3. **Verify Schema & Integrity**:
   Run the verification script:
   ```bash
   python -m agent.data.migrate_proposals
   python -c "from agent.config import get_settings; from agent.data.repository import get_repository; r = get_repository(); print('Settlements:', len(r.list_settlements()), 'Users:', len(r.list_users()))"
   ```

4. **Restart ReliefOS Backend**:
   ```bash
   python -m agent.prod_startup
   ```
   Upon startup, ReliefOS will automatically inspect the outbox, recover any interrupted events, and resume operational services.

---

## 4. Stale Claim & Outbox Recovery

In case of sudden server restarts or process termination while events are being processed:
- ReliefOS automatically recovers any events in `CLAIMED` or `PROCESSING` states older than `STALE_EVENT_THRESHOLD_SECONDS` (default: 300 seconds).
- Retryable events (`retry_count < MAX_RETRIES`) are returned to `PENDING` status.
- Non-retryable events are marked `FAILED` with diagnostic logs preserved.

To manually trigger outbox recovery at any time:
```python
from agent.data.repository import get_repository
from agent.agents.event_router import get_event_dispatcher

repo = get_repository()
dispatcher = get_event_dispatcher()
recovered = dispatcher.recover_stale_events(repo=repo, stale_threshold_seconds=0)
print(f"Manually recovered {recovered} stale events.")
```

---

## 5. What Must Be Backed Up vs. What Can Be Reconstructed

**Must be backed up (persistent, no external source of truth):**
- `needs`, `resource_offers`, `operations`, `organizations`, `operation_participants`
- `coordination_proposals` (including `org_evaluation` / `private_factors` — NGO-private data exists nowhere else)
- `notifications`, `activity_events` (operational memory)
- `audit_logs` (compliance record — loss is unrecoverable)
- `users`, `organization_memberships` (identity + authorization data)
- `agent_events` (outbox — unprocessed events represent undelivered coordination intent)
- `field_reports`, `overrides` (local knowledge that supersedes base maps)
- `flood_snapshots` (temporal hazard history)

**Reconstructable from upstream sources (lower backup priority):**
- `districts`, `settlements`, `roads`, `buildings`, `medical_facilities` — re-importable from OSM/Overpass pipelines
- File-backed private org workspace artifacts under `data/orgs/<org_id>/` — backed up separately if used in the deployment

---

## 6. Automated Restore Verification

A backup that has never been restored is a hypothesis, not a backup. Verify the
full round-trip against a LOCAL/TEST instance only (never production):

```bash
export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
python scripts/verify_backup_restore.py --dump-file /tmp/reliefos_verify.dump
```

The script seeds tagged synthetic data, runs `pg_dump`, drops/recreates the
database, restores with `pg_restore`, then verifies that needs, offers,
operations, coordination proposals (with org evaluations intact),
notifications, activity events, audit records, users, memberships, and
AgentEvents all survived — and that stale CLAIMED events remain recoverable.
It cleans up its own rows afterwards.

### Post-restore AgentEvent behavior

After any restore:
1. `PENDING` events are processed normally by the outbox worker.
2. Events that were `CLAIMED`/`PROCESSING` at dump time keep their timestamps;
   the standard stale recovery (boot-time one-shot + periodic loop) requeues
   those older than `STALE_EVENT_THRESHOLD_SECONDS` and marks exhausted ones
   `FAILED`. Duplicate processing is prevented by idempotency tracking.
3. Run `python -m agent.prod_startup` — startup performs the one-shot recovery
   automatically before the worker begins claiming fresh events.

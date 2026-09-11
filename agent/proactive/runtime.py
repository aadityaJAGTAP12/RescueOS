"""
ReliefOS Proactive Intelligence Runtime — Phase 2B

Implements the server-side proactive inspection engine that periodically
examines disaster operational state, executes deterministic detectors,
reconciles finding lifecycles (NEW -> ACTIVE -> RESOLVED), deduplicates
advisory notifications, and maintains strict human-in-the-loop and privacy boundaries.
"""

from __future__ import annotations

import time
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agent.data.repository import DataRepository, get_repository
from agent.data.models import Notification
from agent.proactive.models import (
    ProactiveScan,
    ProactiveFinding,
    ScanStatus,
    FindingLifecycleStatus,
)
from agent.proactive.detectors.base import ProactiveContext
from agent.proactive.detectors.registry import select_relevant_detectors, list_detectors


class ProactiveRuntime:
    """
    Server-side Proactive Intelligence Runtime.
    """
    _lock = threading.Lock()

    def __init__(self, repo: Optional[DataRepository] = None):
        self._repo = repo

    def get_repo(self) -> DataRepository:
        if self._repo is not None:
            return self._repo
        return get_repository()

    def run_once(
        self,
        scope: Optional[dict[str, Any]] = None,
        repo: Optional[DataRepository] = None,
        trigger: str = "scheduled",
    ) -> ProactiveScan:
        """
        Execute a discrete proactive inspection cycle.

        Args:
            scope: Optional filtering criteria (e.g., {"district_id": "sivasagar", "domain": "exposure"})
            repo: DataRepository instance (optional, defaults to active repository)
            trigger: Reason for scan ("scheduled", "manual_api", "state_change")

        Returns:
            Completed ProactiveScan record.
        """
        active_repo = repo or self.get_repo()
        now = datetime.now(timezone.utc)
        t_start = time.time()

        scan = ProactiveScan(
            id=f"scan_{str(uuid.uuid4())[:12]}",
            started_at=now,
            trigger=trigger,
            status=ScanStatus.RUNNING.value,
            scope=scope,
        )
        active_repo.create_proactive_scan(scan)

        with self._lock:
            context = ProactiveContext(
                repo=active_repo,
                now=now,
                scope=scope,
            )

            # 1. Deterministically select detectors
            selected_detectors = select_relevant_detectors(context)
            detectors_run = [d.detector_id for d in selected_detectors]
            specialists_invoked: set[str] = set()
            for d in selected_detectors:
                specialists_invoked.update(d.relevant_specialists)

            detected_findings: list[ProactiveFinding] = []
            failures: list[dict[str, Any]] = []

            # 2. Run detectors with isolated error handling
            for detector in selected_detectors:
                try:
                    res = detector.detect(context)
                    if res:
                        for f in res:
                            f.scan_id = scan.id
                        detected_findings.extend(res)
                except Exception as e:
                    failures.append({
                        "detector_id": detector.detector_id,
                        "domain": detector.domain,
                        "error": str(e),
                    })

            # 3. Lifecycle Reconciliation & Fingerprint Deduplication
            detected_fingerprints = {f.fingerprint: f for f in detected_findings}
            new_count = 0
            active_count = 0
            resolved_count = 0
            notifs_created = 0

            # Process currently detected findings
            saved_findings: list[ProactiveFinding] = []
            for fp, finding in detected_fingerprints.items():
                existing = active_repo.get_proactive_finding_by_fingerprint(fp)
                should_notify = False
                notification_reason = ""

                if existing:
                    # Severity escalation check
                    old_severity = existing.severity
                    new_severity = finding.severity
                    severity_escalated = (
                        (old_severity in ("medium", "low", "stable", "information") and new_severity in ("critical", "urgent", "high")) or
                        (old_severity == "high" and new_severity in ("critical", "urgent"))
                    )

                    was_resolved = existing.status == FindingLifecycleStatus.RESOLVED.value

                    if was_resolved:
                        # Reopened finding
                        existing.status = FindingLifecycleStatus.NEW.value
                        existing.resolved_at = None
                        new_count += 1
                        if new_severity in ("critical", "urgent", "high"):
                            should_notify = True
                            notification_reason = "reopened"
                    else:
                        existing.status = FindingLifecycleStatus.ACTIVE.value
                        active_count += 1
                        if severity_escalated:
                            should_notify = True
                            notification_reason = "escalated"

                    if old_severity != new_severity:
                        history = list(existing.severity_history or [])
                        history.append({
                            "from": old_severity,
                            "to": new_severity,
                            "timestamp": now.isoformat(),
                        })
                        existing.severity_history = history

                    # Update fields
                    existing.scan_id = scan.id
                    existing.severity = new_severity
                    existing.title = finding.title
                    existing.summary = finding.summary
                    existing.evidence = finding.evidence
                    existing.provenance = finding.provenance
                    existing.uncertainty = finding.uncertainty
                    existing.data_gaps = finding.data_gaps
                    existing.suggested_action = finding.suggested_action
                    existing.last_detected_at = now

                    # Notification dispatch
                    if should_notify:
                        self._create_finding_notification(active_repo, existing, notification_reason)
                        existing.notification_sent_at = now
                        notifs_created += 1

                    saved = active_repo.upsert_proactive_finding(existing)
                    saved_findings.append(saved)
                else:
                    # Brand new finding
                    finding.status = FindingLifecycleStatus.NEW.value
                    finding.first_detected_at = now
                    finding.last_detected_at = now
                    finding.scan_id = scan.id
                    new_count += 1

                    if finding.severity in ("critical", "urgent", "high"):
                        self._create_finding_notification(active_repo, finding, "new_finding")
                        finding.notification_sent_at = now
                        notifs_created += 1

                    saved = active_repo.upsert_proactive_finding(finding)
                    saved_findings.append(saved)

            # 4. Resolve previously active findings not detected in this cycle
            domain_filter = context.domain_filter
            existing_active = active_repo.list_proactive_findings(status=FindingLifecycleStatus.ACTIVE.value, limit=500)
            existing_new = active_repo.list_proactive_findings(status=FindingLifecycleStatus.NEW.value, limit=500)
            all_active = existing_active + existing_new

            for prev_f in all_active:
                if prev_f.fingerprint in detected_fingerprints:
                    continue  # still detected

                # Check if this detector/domain was in scope for this run
                if domain_filter and prev_f.domain != domain_filter:
                    continue  # out of scope, do not resolve

                if prev_f.detector_id not in detectors_run:
                    continue  # detector didn't run, do not resolve

                # Transition to RESOLVED
                prev_f.status = FindingLifecycleStatus.RESOLVED.value
                prev_f.resolved_at = now
                active_repo.upsert_proactive_finding(prev_f)
                resolved_count += 1

            # 5. Finalize Scan Record
            duration = time.time() - t_start
            status = ScanStatus.PARTIAL.value if failures else ScanStatus.SUCCESS.value
            summary = (
                f"Proactive scan completed in {duration:.2f}s. "
                f"Detectors: {len(detectors_run)}, Findings: {len(detected_findings)} "
                f"({new_count} new, {active_count} active, {resolved_count} resolved)."
            )
            metrics = {
                "duration_seconds": round(duration, 3),
                "detectors_count": len(detectors_run),
                "specialists_count": len(specialists_invoked),
                "findings_total": len(detected_findings),
                "findings_new": new_count,
                "findings_active": active_count,
                "findings_resolved": resolved_count,
                "notifications_emitted": notifs_created,
                "failures_count": len(failures),
            }

            updated = active_repo.update_proactive_scan(
                scan_id=scan.id,
                status=status,
                completed_at=datetime.now(timezone.utc),
                findings_count=len(detected_findings),
                summary=summary,
                metrics=metrics,
                failures=failures,
                detectors_run=detectors_run,
                specialists_invoked=sorted(list(specialists_invoked)),
            )

            return updated or scan

    def _create_finding_notification(
        self,
        repo: DataRepository,
        finding: ProactiveFinding,
        reason: str,
    ) -> Optional[Notification]:
        """
        Create a human-facing notification for critical proactive findings.
        """
        try:
            prefix = "[CRITICAL ALERT]" if finding.severity == "critical" else "[OPERATIONAL ADVISORY]"
            notif = Notification(
                id=f"notif_fnd_{str(uuid.uuid4())[:10]}",
                recipient_id="all",
                notification_type="ai_recommendation",
                title=f"{prefix} {finding.title}",
                message=finding.summary,
                entity_type="proactive_finding",
                entity_id=finding.id,
                metadata={
                    "finding_id": finding.id,
                    "fingerprint": finding.fingerprint,
                    "domain": finding.domain,
                    "severity": finding.severity,
                    "detector_id": finding.detector_id,
                    "reason": reason,
                    "suggested_action": finding.suggested_action,
                },
            )
            return repo.create_notification(notif)
        except Exception:
            return None

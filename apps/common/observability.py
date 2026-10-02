import logging
from typing import Dict, Any, Optional
from apps.common.logging import (
    set_correlation_context,
    get_correlation_context,
    mask_sensitive_data
)

logger = logging.getLogger("vouch.observability")

class DistributedObservability:
    """
    Standardized observability event recorder for Vouch's distributed,
    offline-first accounting engine and CRDT synchronization protocol.
    """

    @classmethod
    def log_sync_event(
        cls,
        event_type: str,
        replica_id: str,
        operation_id: Optional[str] = None,
        status: str = "SUCCESS",
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Records client push/pull/stream replication synchronization progress.
        """
        extra = {
            "event_type": f"SYNC_{event_type.upper()}",
            "replica_id": replica_id,
            "operation_id": operation_id or "-",
            "status": status,
        }
        msg = f"Sync Event: {event_type} [replica={replica_id}, op={operation_id or '-'}] -> {status}"
        if error:
            extra["error"] = mask_sensitive_data(error)
            logger.error("%s | Error: %s", msg, error, extra=extra)
        else:
            logger.info(msg, extra=extra)

    @classmethod
    def log_crdt_conflict(
        cls,
        replica_id: str,
        operation_id: str,
        entity_type: str,
        resolution_strategy: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Records concurrent CRDT operation divergence and deterministic resolution.
        """
        extra = {
            "event_type": "CRDT_CONFLICT_RESOLVED",
            "replica_id": replica_id,
            "operation_id": operation_id,
            "entity_type": entity_type,
            "strategy": resolution_strategy
        }
        logger.warning(
            "CRDT Conflict on %s (op=%s, replica=%s) resolved via %s",
            entity_type,
            operation_id,
            replica_id,
            resolution_strategy,
            extra=extra
        )

    @classmethod
    def log_security_event(
        cls,
        event_type: str,
        reason: str,
        device_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Records cryptographic and authorization events (signature failures,
        KMS failures, device revocations).
        """
        extra = {
            "event_type": f"SECURITY_{event_type.upper()}",
            "device_id": device_id or "-",
            "reason": reason
        }
        logger.warning(
            "Security Event: %s (device=%s) Reason: %s",
            event_type,
            device_id or "-",
            reason,
            extra=extra
        )

    @classmethod
    def log_subsystem_failure(
        cls,
        subsystem: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Structured recording of failures in OCR, Bank reconciliation, Celery, or Database.
        """
        extra = {
            "event_type": f"{subsystem.upper()}_FAILURE",
            "subsystem": subsystem,
            "error_class": error.__class__.__name__
        }
        logger.error(
            "Subsystem failure in %s: %s",
            subsystem,
            str(error),
            exc_info=True,
            extra=extra
        )

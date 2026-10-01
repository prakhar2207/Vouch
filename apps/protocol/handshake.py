from enum import Enum, auto
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

class EdiState(Enum):
    """Rigorous state machine for distributed transaction coordination."""
    # Negotiation Phase
    DISCOVER = auto()
    CAPABILITY_EXCHANGE = auto()
    AUTHENTICATE = auto()
    
    # Transaction Phase
    PROPOSE = auto()
    RECEIVE = auto()
    VALIDATE = auto()
    
    # Consensus Phase (2PC)
    PREPARE = auto()
    READY = auto()
    ACCEPT = auto()
    COMMIT = auto()
    COMMITTED = auto()

    # Terminal Failure States
    REJECTED = auto()
    EXPIRED = auto()
    INVALID_SIGNATURE = auto()
    CONFLICT = auto()
    VALIDATION_FAILED = auto()
    ROLLBACK_REQUIRED = auto()

class IllegalStateTransitionError(Exception):
    pass

# States that are final — no further transitions allowed
TERMINAL_STATES = frozenset({
    EdiState.COMMITTED, EdiState.REJECTED, EdiState.EXPIRED,
    EdiState.INVALID_SIGNATURE, EdiState.CONFLICT,
    EdiState.VALIDATION_FAILED, EdiState.ROLLBACK_REQUIRED
})

class EdiStateMachine:
    """
    Enforces that a transaction strictly follows the distributed protocol sequence.
    Blocks illegal jumps (e.g., DISCOVER -> COMMIT).
    Auto-expires sessions that exceed the timeout threshold.
    """
    
    # Explicit mapping of allowed transitions
    VALID_TRANSITIONS = {
        EdiState.DISCOVER: [EdiState.CAPABILITY_EXCHANGE, EdiState.REJECTED],
        EdiState.CAPABILITY_EXCHANGE: [EdiState.AUTHENTICATE, EdiState.REJECTED],
        EdiState.AUTHENTICATE: [EdiState.PROPOSE, EdiState.INVALID_SIGNATURE, EdiState.REJECTED],
        EdiState.PROPOSE: [EdiState.RECEIVE, EdiState.EXPIRED],
        EdiState.RECEIVE: [EdiState.VALIDATE, EdiState.EXPIRED],
        EdiState.VALIDATE: [EdiState.PREPARE, EdiState.VALIDATION_FAILED],
        EdiState.PREPARE: [EdiState.READY, EdiState.CONFLICT, EdiState.EXPIRED],
        EdiState.READY: [EdiState.ACCEPT, EdiState.EXPIRED, EdiState.REJECTED],
        EdiState.ACCEPT: [EdiState.COMMIT, EdiState.ROLLBACK_REQUIRED],
        EdiState.COMMIT: [EdiState.COMMITTED, EdiState.ROLLBACK_REQUIRED],
        
        # Terminal States (No outward transitions allowed)
        EdiState.COMMITTED: [],
        EdiState.REJECTED: [],
        EdiState.EXPIRED: [],
        EdiState.INVALID_SIGNATURE: [],
        EdiState.CONFLICT: [],
        EdiState.VALIDATION_FAILED: [],
        EdiState.ROLLBACK_REQUIRED: []
    }

    def __init__(self, session_id: str, timeout_seconds: int = 300, persist: bool = True):
        self.session_id = session_id
        self.current_state = EdiState.DISCOVER
        self.created_at = datetime.now(timezone.utc)
        self.timeout_seconds = timeout_seconds
        self.persist = persist
        self.transition_log: List[Tuple[EdiState, datetime]] = [
            (EdiState.DISCOVER, self.created_at)
        ]

        if self.persist:
            try:
                from apps.protocol.models import EdiSession
                record = EdiSession.objects.filter(session_id=self.session_id).first()
                if record:
                    self.current_state = EdiState[record.current_state]
                    self.created_at = record.created_at
                    self.timeout_seconds = record.timeout_seconds
                    if record.transition_history:
                        self.transition_log = [
                            (EdiState[item['state']], datetime.fromisoformat(item['timestamp']))
                            for item in record.transition_history
                        ]
                else:
                    EdiSession.objects.create(
                        session_id=self.session_id,
                        current_state=self.current_state.name,
                        timeout_seconds=self.timeout_seconds,
                        transition_history=[{
                            "state": self.current_state.name,
                            "timestamp": self.created_at.isoformat()
                        }]
                    )
            except Exception:
                pass

    @property
    def is_terminal(self) -> bool:
        return self.current_state in TERMINAL_STATES

    @property
    def is_expired(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return elapsed > self.timeout_seconds

    def advance(self, next_state: EdiState, context_data: Optional[Dict] = None):
        """
        Attempts to transition the session to the next state.
        Raises an error if the transition violates protocol topology or the session has timed out.
        Persists state transitions to database when persist=True.
        """
        # Auto-expire if timeout exceeded (unless already terminal or explicitly going to EXPIRED)
        if self.is_expired and not self.is_terminal and next_state != EdiState.EXPIRED:
            self.current_state = EdiState.EXPIRED
            now = datetime.now(timezone.utc)
            self.transition_log.append((EdiState.EXPIRED, now))
            if self.persist:
                try:
                    from apps.protocol.models import EdiSession
                    record = EdiSession.objects.filter(session_id=self.session_id).first()
                    if record:
                        record.current_state = EdiState.EXPIRED.name
                        history = record.transition_history or []
                        history.append({"state": EdiState.EXPIRED.name, "timestamp": now.isoformat()})
                        record.transition_history = history
                        record.save(update_fields=['current_state', 'transition_history', 'updated_at'])
                except Exception:
                    pass
            raise IllegalStateTransitionError(
                f"Session {self.session_id} has expired after {self.timeout_seconds}s"
            )

        allowed = self.VALID_TRANSITIONS.get(self.current_state, [])
        if next_state not in allowed:
            raise IllegalStateTransitionError(
                f"Protocol Violation: Cannot transition from {self.current_state.name} directly to {next_state.name}"
            )
        
        now = datetime.now(timezone.utc)
        self.current_state = next_state
        self.transition_log.append((next_state, now))

        if self.persist:
            try:
                from apps.protocol.models import EdiSession
                record = EdiSession.objects.filter(session_id=self.session_id).first()
                if record:
                    record.current_state = next_state.name
                    history = record.transition_history or []
                    history.append({
                        "state": next_state.name,
                        "timestamp": now.isoformat(),
                        "context": context_data or {}
                    })
                    record.transition_history = history
                    if context_data and isinstance(context_data, dict):
                        c = record.context_data or {}
                        c.update(context_data)
                        record.context_data = c
                        if "transaction_id" in context_data:
                            record.transaction_id = context_data["transaction_id"]
                    record.save(update_fields=['current_state', 'transition_history', 'context_data', 'transaction_id', 'updated_at'])
            except Exception:
                pass

        return True



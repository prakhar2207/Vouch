from enum import Enum, auto
from typing import Dict, List, Optional

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

class EdiStateMachine:
    """
    Enforces that a transaction strictly follows the distributed protocol sequence.
    Blocks illegal jumps (e.g., DISCOVER -> COMMIT).
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

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.current_state = EdiState.DISCOVER
        self.transition_log: List[EdiState] = [EdiState.DISCOVER]

    def advance(self, next_state: EdiState, context_data: Optional[Dict] = None):
        """
        Attempts to transition the session to the next state.
        Raises an error if the transition violates protocol topology.
        """
        allowed = self.VALID_TRANSITIONS.get(self.current_state, [])
        if next_state not in allowed:
            raise IllegalStateTransitionError(
                f"Protocol Violation: Cannot transition from {self.current_state.name} directly to {next_state.name}"
            )
        
        self.current_state = next_state
        self.transition_log.append(next_state)
        # In a real implementation, context_data (like signature payloads) would be processed here.
        return True

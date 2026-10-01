from dataclasses import dataclass
from typing import Optional, List
from enum import Enum
import time

class MappingConfidence(str, Enum):
    MANUAL = "MANUAL"
    HEURISTIC = "HEURISTIC"
    ML_PREDICTED = "ML_PREDICTED"

class ApprovalState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

@dataclass(frozen=True)
class ProductMapping:
    """
    Immutable versioned record mapping a foreign entity's SKU to a local Vouch SKU.
    """
    mapping_id: str
    source_company_id: str
    destination_company_id: str
    foreign_sku: str
    local_sku: str
    mapping_version: int
    confidence_level: MappingConfidence
    approval_state: ApprovalState
    created_at: int
    
    # Optional semantic attributes
    conversion_multiplier: float = 1.0  # e.g., Seller sends '1 Box', Buyer logs '10 Units'. Multiplier = 10.0
    hsn_override: Optional[str] = None

class MappingResolutionEngine:
    """
    Boundary layer that translates foreign canonical identities into localized Vouch identities.
    Enforces strict historical versioning and approval barriers.
    """
    def __init__(self):
        # Simulated Database Table
        self._mappings_db: List[ProductMapping] = []

    def register_mapping(self, mapping: ProductMapping):
        """Inserts a new mapping version into the database."""
        self._mappings_db.append(mapping)

    def resolve_product(
        self, 
        source_company: str, 
        target_company: str, 
        foreign_sku: str, 
        transaction_mapping_version: int
    ) -> ProductMapping:
        """
        Resolves a foreign SKU to a local SKU based on the exact version 
        that was active when the transaction was originally negotiated.
        """
        # Filter for exact pathway and state
        valid_matches = [
            m for m in self._mappings_db 
            if m.source_company_id == source_company 
            and m.destination_company_id == target_company
            and m.foreign_sku == foreign_sku
            and m.approval_state == ApprovalState.APPROVED
            # CRUCIAL: Never use a mapping version created AFTER the transaction was negotiated
            and m.mapping_version <= transaction_mapping_version
        ]
        
        if not valid_matches:
            raise ValueError(
                f"Resolution Failed: No APPROVED mapping found for foreign SKU '{foreign_sku}' "
                f"at version <= {transaction_mapping_version}. Human intervention required."
            )
        
        # Return the most recent valid mapping chronologically
        return sorted(valid_matches, key=lambda x: x.mapping_version, reverse=True)[0]

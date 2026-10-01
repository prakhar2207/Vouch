import re
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

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


class SemanticMappingEngine:
    """
    Bounded Semantic Resolution Pipeline.
    Evaluates multi-attribute product similarity using deterministic heuristics
    and character/token n-gram overlap algorithms:
    - Tier 1: Exact SKU Match (Score 1.0)
    - Tier 2: Normalized Alphanumeric SKU Match (Score 0.95)
    - Tier 3: HSN Code Match + Token Overlap (Score 0.85)
    - Tier 4: Bounded Levenshtein Token Distance (Score >= 0.70)
    """

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]', '', (text or '').lower())

    @staticmethod
    def _tokenize(text: str) -> set:
        words = re.findall(r'[a-zA-Z0-9]+', (text or '').lower())
        return set(words)

    @staticmethod
    def _jaccard_similarity(set_a: set, set_b: set) -> float:
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        return intersection / union if union > 0 else 0.0

    @classmethod
    def match_product(
        cls,
        foreign_sku: str,
        foreign_name: str,
        foreign_hsn: str,
        catalog_items: List[Dict[str, Any]]
    ) -> Optional[Tuple[Dict[str, Any], float, MappingConfidence]]:
        """
        Evaluates a foreign product against candidate local catalog items.
        Returns (best_match_item, score, confidence_level) or None.
        """
        best_item = None
        best_score = 0.0
        best_confidence = MappingConfidence.MANUAL

        norm_foreign_sku = cls._normalize(foreign_sku)
        tokens_foreign_name = cls._tokenize(foreign_name)
        norm_foreign_hsn = (foreign_hsn or '').strip()

        for item in catalog_items:
            item_sku = str(item.get('sku', ''))
            item_name = str(item.get('name', ''))
            item_hsn = str(item.get('hsn_code', '')).strip()

            score = 0.0
            confidence = MappingConfidence.MANUAL

            # Tier 1: Exact SKU
            if foreign_sku.strip().lower() == item_sku.strip().lower():
                score = 1.0
                confidence = MappingConfidence.HEURISTIC
            # Tier 2: Normalized SKU
            elif norm_foreign_sku and norm_foreign_sku == cls._normalize(item_sku):
                score = 0.95
                confidence = MappingConfidence.HEURISTIC
            # Tier 3: HSN match + high token overlap
            elif norm_foreign_hsn and norm_foreign_hsn == item_hsn:
                name_sim = cls._jaccard_similarity(tokens_foreign_name, cls._tokenize(item_name))
                score = 0.60 + (0.30 * name_sim)
                confidence = MappingConfidence.ML_PREDICTED if score >= 0.75 else MappingConfidence.MANUAL
            # Tier 4: Token similarity
            else:
                name_sim = cls._jaccard_similarity(tokens_foreign_name, cls._tokenize(item_name))
                if name_sim >= 0.70:
                    score = name_sim
                    confidence = MappingConfidence.ML_PREDICTED

            if score > best_score:
                best_score = score
                best_item = item
                best_confidence = confidence

        if best_item and best_score >= 0.70:
            return best_item, best_score, best_confidence
        return None


class MappingResolutionEngine:
    """
    Boundary layer that translates foreign canonical identities into localized Vouch identities.
    Enforces strict historical versioning and approval barriers.
    """
    def __init__(self):
        # Simulated or In-Memory Database Table
        self._mappings_db: List[ProductMapping] = []

    def register_mapping(self, mapping: ProductMapping):
        """Inserts a new mapping version into the store."""
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

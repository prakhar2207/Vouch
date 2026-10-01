import json
import hashlib
from typing import Any
from decimal import Decimal

def normalize_value(val: Any) -> Any:
    """Recursively normalizes numbers, decimals, and collections for deterministic cross-language JSON serialization."""
    if isinstance(val, Decimal):
        if val == val.to_integral():
            return int(val)
        return str(val)
    elif isinstance(val, float):
        if val.is_integer():
            return int(val)
        return val
    elif isinstance(val, dict):
        return {str(k): normalize_value(v) for k, v in val.items()}
    elif isinstance(val, (list, tuple)):
        return [normalize_value(v) for v in val]
    return val

def canonical_json_dumps(obj: Any) -> str:
    """
    Vouch Canonical JSON Serialization, based on RFC 8785/JCS principles:
    1. Lexicographically sorted dictionary keys (Unicode codepoint ordering).
    2. Strict absence of insignificant whitespace (separators=(',', ':')).
    3. UTF-8 encoded characters preserved without ASCII escaping (ensure_ascii=False).
    4. Deterministic normalization of numbers and fixed-point decimals across Python and TypeScript runtimes.
    5. Bit-for-bit equivalence with frontend canonicalJsonStringify.
    """
    normalized = normalize_value(obj)
    return json.dumps(normalized, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def canonical_hash(obj: Any) -> str:
    """Computes deterministic SHA-256 digest over canonical JSON representation."""
    canonical_str = canonical_json_dumps(obj)
    return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()

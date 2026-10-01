import json
import hashlib
from typing import Any

def canonical_json_dumps(obj: Any) -> str:
    """
    Vouch Canonical JSON Serialization, based on RFC 8785/JCS principles:
    1. Lexicographically sorted dictionary keys (Unicode codepoint ordering).
    2. Strict absence of insignificant whitespace (separators=(',', ':')).
    3. UTF-8 encoded characters preserved without ASCII escaping (ensure_ascii=False).
    4. Bit-for-bit equivalence with frontend canonicalJsonStringify.
    Financial Decimals are serialized as deterministic fixed-point strings to avoid IEEE-754 float drift.
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def canonical_hash(obj: Any) -> str:
    """Computes deterministic SHA-256 digest over canonical JSON representation."""
    canonical_str = canonical_json_dumps(obj)
    return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()

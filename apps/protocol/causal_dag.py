from typing import Dict, List, Set, Optional, Tuple
from collections import deque
from .operation import AccountingOperation, OperationType

class CausalViolationError(Exception):
    """Raised when causal ordering or dependency invariants are broken."""
    pass

class CausalDAG:
    """
    Causal Directed Acyclic Graph for distributed accounting operations.
    Enforces that no operation executes before its causal dependencies are satisfied,
    quarantines orphan operations, and performs deterministic topological sorting.
    """

    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        self.operations: Dict[str, AccountingOperation] = {}
        self.children: Dict[str, Set[str]] = {}
        self.parents: Dict[str, Set[str]] = {}
        self.orphans: Dict[str, AccountingOperation] = {} # Awaiting missing causal parents

    def add_operation(self, op: AccountingOperation) -> bool:
        """
        Idempotently inserts an operation into the causal graph.
        If any parent is missing, op is placed in orphan quarantine until parents arrive.
        Returns True if newly added, False if duplicate.
        """
        if op.transaction_id != self.transaction_id:
            raise CausalViolationError(
                f"Transaction ID mismatch: DAG is {self.transaction_id}, operation belongs to {op.transaction_id}"
            )

        if op.operation_id in self.operations:
            return False # Duplicate / replay handled idempotently

        # Check if all causal parents exist in the graph
        missing_parents = [p for p in op.parents if p not in self.operations]
        if missing_parents:
            # Quarantine in orphans
            self.orphans[op.operation_id] = op
            return False

        # Add to graph
        self._insert_internal(op)

        # Check if any quarantined orphans can now be admitted
        self._resolve_orphans()
        return True

    def _insert_internal(self, op: AccountingOperation):
        self.operations[op.operation_id] = op
        self.parents[op.operation_id] = set(op.parents)
        if op.operation_id not in self.children:
            self.children[op.operation_id] = set()

        for parent_id in op.parents:
            if parent_id not in self.children:
                self.children[parent_id] = set()
            self.children[parent_id].add(op.operation_id)

    def _resolve_orphans(self):
        """Recursively checks and admits orphans whose causal parents have arrived."""
        resolved = True
        while resolved:
            resolved = False
            for orphan_id in list(self.orphans.keys()):
                orphan_op = self.orphans[orphan_id]
                missing = [p for p in orphan_op.parents if p not in self.operations]
                if not missing:
                    del self.orphans[orphan_id]
                    self._insert_internal(orphan_op)
                    resolved = True
                    break

    def get_missing_parents(self) -> Set[str]:
        """Returns the set of all parent IDs that are currently missing for orphaned ops."""
        missing = set()
        for orphan_op in self.orphans.values():
            for p in orphan_op.parents:
                if p not in self.operations:
                    missing.add(p)
        return missing

    def topological_sort(self) -> List[AccountingOperation]:
        """
        Deterministic Topological Sort using Kahn's Algorithm.
        Guarantees that every parent executes strictly before its children.
        Ties are broken deterministically using (logical_timestamp, operation_id).
        """
        # Calculate in-degrees within the admitted operation graph
        in_degree: Dict[str, int] = {op_id: len(self.parents.get(op_id, set())) for op_id in self.operations}
        
        # Priority queue / sorted buffer of operations with in-degree 0
        ready: List[str] = [op_id for op_id, deg in in_degree.items() if deg == 0]
        # Sort initial ready nodes deterministically
        ready.sort(key=lambda x: (self.operations[x].logical_timestamp, x))

        sorted_ops: List[AccountingOperation] = []

        while ready:
            curr_id = ready.pop(0)
            sorted_ops.append(self.operations[curr_id])

            # For each child, decrement in-degree
            newly_ready = []
            for child_id in sorted(self.children.get(curr_id, set())):
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    newly_ready.append(child_id)

            # Insert newly ready nodes maintaining deterministic order
            for nr in newly_ready:
                ready.append(nr)
            ready.sort(key=lambda x: (self.operations[x].logical_timestamp, x))

        if len(sorted_ops) != len(self.operations):
            raise CausalViolationError("Cycle detected in accounting operation DAG.")

        return sorted_ops

    def is_ancestor(self, ancestor_id: str, descendant_id: str) -> bool:
        """Returns True if ancestor_id is a causal predecessor of descendant_id."""
        if ancestor_id == descendant_id:
            return True
        visited = set()
        queue = deque([descendant_id])
        while queue:
            curr = queue.popleft()
            if curr in visited:
                continue
            visited.add(curr)
            for p in self.parents.get(curr, set()):
                if p == ancestor_id:
                    return True
                queue.append(p)
        return False

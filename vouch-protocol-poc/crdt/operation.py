import json

class AccountingOperation:
    def __init__(self, op_id, tx_id, replica_id, op_type, payload, logical_timestamp, parents=None):
        self.op_id = op_id
        self.tx_id = tx_id
        self.replica_id = replica_id
        self.op_type = op_type
        self.payload = payload
        self.logical_timestamp = logical_timestamp
        self.parents = parents or []

    def to_dict(self):
        return {
            "op_id": self.op_id, "tx_id": self.tx_id, "replica_id": self.replica_id,
            "type": self.op_type, "payload": self.payload, 
            "timestamp": self.logical_timestamp, "parents": self.parents
        }

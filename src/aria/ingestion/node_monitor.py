from datetime import datetime
from aria.timebase import sgt_now

STALE_AFTER_SECONDS = 5

class NodeMonitor:
    def __init__(self):
        self.nodes = {}

    def update(self, payload, received_at):
        if not isinstance(received_at, str) or not received_at.endswith("+08:00"):
            raise ValueError("received_at must use the +08:00 SGT offset")
        datetime.fromisoformat(received_at)
        node_id = payload["node_id"]
        sequence = payload["sequence"]
        boot_id = payload["boot_id"]
        messages = []

        previous = self.nodes.get(node_id)

        if previous is not None:
            previous_sequence = previous["sequence"]
            previous_boot_id = previous["boot_id"]

            if boot_id != previous_boot_id:
                messages.append(
                    f"WARNING: {node_id} restarted; "
                    f"boot_id {previous_boot_id} -> {boot_id}, "
                    f"sequence {previous_sequence} -> {sequence}"
                )
            elif sequence == previous_sequence:
                messages.append(
                    f"WARNING: duplicate packet from {node_id}, sequence {sequence}"
                )
            elif sequence < previous_sequence:
                messages.append(
                    f"WARNING: out-of-order packet from {node_id}, "
                    f"sequence {previous_sequence} -> {sequence}"
                )
            elif sequence > previous_sequence + 1:
                skipped = sequence - previous_sequence - 1
                messages.append(
                    f"WARNING: {node_id} skipped {skipped} packet(s)"
                )

        self.nodes[node_id] = {
            "sequence": sequence,
            "boot_id": boot_id,
            "received_at": received_at,
            "stale": False,
        }

        return messages

    def check_stale_nodes(self, now=None):
        now = now or sgt_now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        messages = []

        for node_id, node in self.nodes.items():
            last_seen = datetime.fromisoformat(node["received_at"])
            age = (now - last_seen).total_seconds()

            if age > STALE_AFTER_SECONDS and not node["stale"]:
                node["stale"] = True
                messages.append(f"WARNING: {node_id} is stale; no packet for {age:.1f} seconds")

        return messages
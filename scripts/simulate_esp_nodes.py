#!/usr/bin/env python3
"""send synthetic esp-a1 and esp-a2 packets to the local udp receiver"""

import json
import random
import socket
import time

LAPTOP_IP = "127.0.0.1"
LAPTOP_PORT = 5005
SEND_INTERVAL_SECONDS = 1
FIRMWARE_VERSION = "1.1.1"

NODES = {
    "ESP-A1": {
        "local_port": 4210,
        "sensor_config": "A_PIR_US_MIC",
    },
    "ESP-A2": {
        "local_port": 4211,
        "sensor_config": "A_PIR_MIC",
    },
}

BOOT_IDS = {node_id: random.getrandbits(32) for node_id in NODES}


def create_socket(local_port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", local_port))
    return sock

def create_common_packet(
    node_id: str,
    sequence: int,
    started_at: float,
    pir_motion: bool,
    recent_until: float,
) -> tuple[dict, float]:
    now = time.monotonic()

    if pir_motion:
        recent_until = now + 10

    packet = {
        "schema_version": 1,
        "firmware_version": FIRMWARE_VERSION,
        "sensor_config": NODES[node_id]["sensor_config"],
        "boot_id": BOOT_IDS[node_id],
        "node_id": node_id,
        "zone": "A",
        "sequence": sequence,
        "timestamp_ms": int((now - started_at) * 1000),
        "wifi_connected": True,
        "wifi_rssi_dbm": random.randint(-68, -55),
        "pir_motion": pir_motion,
        "pir_recent_activity": now < recent_until,
    }

    return packet, recent_until

def create_esp_a_packet(
    node_id: str,
    sequence: int,
    started_at: float,
    recent_until: float,
) -> tuple[dict, float]:
    pir_motion = random.random() < 0.25

    packet, recent_until = create_common_packet(
        node_id,
        sequence,
        started_at,
        pir_motion,
        recent_until,
    )

    packet.update(
        {
            "audio_peak_to_peak": random.randint(30, 90),
            "audio_activity": round(random.uniform(3.0, 14.0), 2),
            "audio_rms": round(random.uniform(4.0, 18.0), 2),
        }
    )

    if node_id == "ESP-A1":
        distance_valid = random.random() > 0.05
        packet.update(
            {
                "distance_cm": round(random.uniform(65, 220), 2)
                if distance_valid
                else -1.0,
                "distance_valid": distance_valid,
            }
        )

    return packet, recent_until

def main() -> None:
    sockets = {
        node_id: create_socket(config["local_port"])
        for node_id, config in NODES.items()
    }
    sequences = {node_id: 0 for node_id in NODES}
    recent_until = {node_id: 0.0 for node_id in NODES}
    started_at = time.monotonic()

    print("Simulating ESP-A1 and ESP-A2")
    print(f"Sending to {LAPTOP_IP}:{LAPTOP_PORT}")
    print("Press Control + C to stop.\n")

    try:
        while True:
            packets = {}
            for node_id in NODES:
                packet, recent_until[node_id] = create_esp_a_packet(
                    node_id,
                    sequences[node_id],
                    started_at,
                    recent_until[node_id],
                )
                packets[node_id] = packet

            for node_id, packet in packets.items():
                data = json.dumps(packet).encode("utf-8")
                sockets[node_id].sendto(data, (LAPTOP_IP, LAPTOP_PORT))

                print(
                    f'{node_id} :{NODES[node_id]["local_port"]} '
                    f'-> {LAPTOP_IP}:{LAPTOP_PORT} '
                    f'sequence={packet["sequence"]}'
                )

                sequences[node_id] += 1

            print()
            time.sleep(SEND_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nSimulation stopped.")

    finally:
        for node_socket in sockets.values():
            node_socket.close()


if __name__ == "__main__":
    main()

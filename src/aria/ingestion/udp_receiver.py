import hashlib
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .node_monitor import NodeMonitor
from .packet_parser import parse_packet
from .record_schema import validate_esp_record

HOST = "0.0.0.0"
PORT = 5005
BUFFER_SIZE = 4096

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
LOG_DIR = PROJECT_ROOT / "outputs" / "logs"

RAW_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

PACKET_FILE = RAW_DIR / "esp_packets.jsonl"
INVALID_FILE = RAW_DIR / "invalid_packets.jsonl"
LOG_FILE = LOG_DIR / "udp_receiver.log"

NODE_LOG_FILES = {
    "ESP-A1": LOG_DIR / "esp_a1.log",
    "ESP-A2": LOG_DIR / "esp_a2.log",
}

monitor = NodeMonitor()
SGT = timezone(timedelta(hours=8))

def sgt_now() -> str:
    return datetime.now(SGT).isoformat(timespec="milliseconds")

def write_json_line(file_path: Path, record: dict) -> None:
    with file_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")

def write_diagnostic(timestamp: str, message: str) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"{timestamp} {message}\n")

def build_invalid_record(
    received_at: str,
    source_ip: str,
    source_port: int,
    error_message: str,
    data: bytes,
) -> dict:
    return {
        "received_at_sgt": received_at,
        "source_ip": source_ip,
        "source_port": source_port,
        "error": error_message,
        "raw_packet_size_bytes": len(data),
        "raw_packet_sha256": hashlib.sha256(data).hexdigest(),
    }

def format_packet_output(
    received_at: str,
    source_ip: str,
    source_port: int,
    payload: dict,
) -> str:
    return (
        f"\n[{received_at}] From {source_ip}:{source_port}\n"
        f"{json.dumps(payload, indent=2)}\n"
    )

def write_node_output(
    node_id: str,
    received_at: str,
    source_ip: str,
    source_port: int,
    payload: dict,
) -> None:
    node_log_file = NODE_LOG_FILES.get(node_id)

    if node_log_file is None:
        return

    formatted_output = format_packet_output(
        received_at=received_at,
        source_ip=source_ip,
        source_port=source_port,
        payload=payload,
    )

    with node_log_file.open("a", encoding="utf-8") as file:
        file.write(formatted_output)
        file.flush()

def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.bind((HOST, PORT))
        sock.settimeout(1.0)

        started_at = sgt_now()
        startup_message = (f"UDP receiver started on {HOST}:{PORT}; accepting ESP-A1 and ESP-A2 only")

        print(startup_message)
        write_diagnostic(started_at, startup_message)

        while True:
            try:
                data, address = sock.recvfrom(BUFFER_SIZE)

            except socket.timeout:
                checked_at = sgt_now()

                for message in monitor.check_stale_nodes():
                    print(message)
                    write_diagnostic(checked_at, message)

                continue

            received_at = sgt_now()
            source_ip = address[0]
            source_port = address[1]

            try:
                payload = parse_packet(data)

                record = {
                    "received_at_sgt": received_at,
                    "source_ip": source_ip,
                    "source_port": source_port,
                    "payload": payload,
                }
                validate_esp_record(record)

                write_json_line(PACKET_FILE, record)
                node_id = payload["node_id"]

                write_node_output(
                    node_id=node_id,
                    received_at=received_at,
                    source_ip=source_ip,
                    source_port=source_port,
                    payload=payload,
                )

                messages = monitor.update(payload, received_at)

                formatted_output = format_packet_output(
                    received_at=received_at,
                    source_ip=source_ip,
                    source_port=source_port,
                    payload=payload,
                )

                print(formatted_output, end="", flush=True)

                for message in messages:
                    print(message, flush=True)
                    write_diagnostic(received_at, message)

            except (ValueError, KeyError) as error:
                if isinstance(error, KeyError):
                    error_message = f"Missing required field: {error}"
                else:
                    error_message = str(error)

                invalid_record = build_invalid_record(
                    received_at=received_at,
                    source_ip=source_ip,
                    source_port=source_port,
                    error_message=error_message,
                    data=data,
                )

                write_json_line(INVALID_FILE, invalid_record)

                message = (f"Invalid packet from "f"{source_ip}:{source_port}: {error_message}")

                print(f"\n[{received_at}] {message}", flush=True)
                write_diagnostic(received_at, message)

    except KeyboardInterrupt:
        stopped_at = sgt_now()
        message = "UDP receiver stopped by user"

        print(f"\n{message}")
        write_diagnostic(stopped_at, message)

    except OSError as error:
        failed_at = sgt_now()
        message = f"UDP receiver socket error: {error}"

        print(message)
        write_diagnostic(failed_at, message)
        raise

    finally:
        sock.close()

if __name__ == "__main__":
    main()
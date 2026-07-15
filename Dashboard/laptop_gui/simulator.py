import time
import math
import random
from .config import RIS_ELEMENTS
from shared.protocol import physical_to_wire_bits

PATTERNS = {
    0: "000000000000000000000000",
    1: "111111000000111111000000",
    2: "101010101010101010101010",
    3: "110011001100110011001100",
    4: "111100001111000011110000",
    5: "100110011001100110011001",
}


def pattern_for_angle(angle: float) -> tuple[int, str]:
    if angle < 15:
        pid = 0
    elif angle < 30:
        pid = 1
    elif angle < 45:
        pid = 2
    elif angle < 60:
        pid = 3
    elif angle < 75:
        pid = 4
    else:
        pid = 5
    return pid, PATTERNS[pid]


def generate_simulated_packet(mode: str = "AUTO", manual_bits: str | None = None, manual_pid: int = 0) -> dict:
    t = time.time()
    angle = 38 + 27 * math.sin(t / 5.0) + random.uniform(-2.5, 2.5)
    angle = max(5, min(82, angle))
    distance = 3.2 + 1.2 * math.sin(t / 7.0) + random.uniform(-0.1, 0.1)
    x = distance * math.cos(math.radians(angle))
    y = distance * math.sin(math.radians(angle))

    if mode == "MANUAL" and manual_bits is not None:
        cell_bits = "".join(ch for ch in str(manual_bits) if ch in "01")[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
        pid, state = manual_pid, "MANUAL_LOCAL"
        beam = angle if cell_bits.count("1") else 0.0
    else:
        pid, cell_bits = pattern_for_angle(angle)
        state, beam = "AUTO_TRACKING", round(angle / 5.0) * 5.0

    wire_bits = physical_to_wire_bits(cell_bits)

    alignment = max(0.0, 1.0 - abs(angle - beam) / 45.0) if beam else 0.25
    rssi = -69 + 24 * alignment + random.uniform(-1.8, 1.8)
    snr = 5 + 23 * alignment + random.uniform(-1.0, 1.0)
    throughput = max(1.0, 4 + 38 * alignment + random.uniform(-2.5, 2.5))
    loss = max(0.0, 8.0 - 7.0 * alignment + random.uniform(-0.5, 0.5))
    ber = max(0.00001, 0.0012 * (1.0 - alignment) + random.uniform(0.0, 0.00005))

    return {
        "type": "telemetry",
        "timestamp": t,
        "system": {"mode": mode, "connection": "SIMULATION", "demo_state": "RUNNING"},
        "user": {"x_m": x, "y_m": y, "z_m": 0.0, "angle_deg": angle, "distance_m": distance, "velocity_mps": abs(math.cos(t/4.0))*0.45, "source": "SIM/LD2450"},
        "channel": {"rssi_dbm": rssi, "snr_db": snr, "throughput_mbps": throughput, "packet_loss_percent": loss, "ber": ber},
        "ris": {
            "rows": 4,
            "cols": 6,
            "elements": 24,
            "pattern_id": pid,
            "beam_angle_deg": beam,
            "cell_bits": cell_bits,
            "bits": wire_bits,
            "wire_bits": wire_bits,
            "state": state,
            "garbage_bits_per_row": 2,
        },
        "radar": {"target_count": 1, "status": "OK"}
    }

import json
import math
import threading
import time
from typing import Optional, Dict, Any

from . import config

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except Exception:
    SERIAL_AVAILABLE = False


class RadarReceiver:
    """
    Reads user/RX position from ESP32 over USB serial.

    Expected ESP32 serial line, one JSON object per line:
        {"x":1.25,"y":2.40,"angle":62.5,"distance":2.70,"targets":1}

    Also accepts CSV fallback:
        x,y,angle,distance,targets

    Coordinate convention:
        x_m, y_m are metres in the same top-view coordinate system used by GUI.
        angle_deg is normally atan2(y, x) from RIS to user/RX.
    """

    def __init__(self, port: Optional[str] = None, baudrate: int = 115200, simulation: Optional[bool] = None):
        self.port = port if port is not None else config.RADAR_SERIAL_PORT
        self.baudrate = int(baudrate or config.RADAR_BAUDRATE)
        self.simulation = config.USE_SIMULATED_RADAR if simulation is None else bool(simulation)

        self.running = False
        self.thread = None
        self.ser = None
        self.t0 = time.time()
        self.last_rx_time = 0.0
        self.lock = threading.Lock()

        self.latest = self._make_simulated_packet()
        self.latest["source"] = "SIM_RADAR_INIT"
        self.latest["status"] = "STARTING"

    def start(self):
        self.running = True

        if not self.simulation:
            self._open_serial_or_fallback()

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass

    def get_position(self) -> Dict[str, Any]:
        with self.lock:
            data = dict(self.latest)

        # If real serial goes silent, mark stale but keep last known position.
        if not self.simulation and self.last_rx_time > 0:
            age = time.time() - self.last_rx_time
            if age > 2.0:
                data["status"] = f"STALE_{age:.1f}s"

        return data

    def _open_serial_or_fallback(self):
        if not SERIAL_AVAILABLE:
            print("[RADAR] pyserial not installed. Install with: pip install pyserial")
            print("[RADAR] Falling back to simulation.")
            self.simulation = True
            return

        if self.port is None:
            self.port = self._auto_detect_port()

        if self.port is None:
            print("[RADAR] No ESP32 serial port found. Falling back to simulation.")
            self.simulation = True
            return

        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
            time.sleep(2.0)  # ESP32 may reset when serial opens
            print(f"[RADAR] Connected to ESP32 radar on {self.port} @ {self.baudrate}")
        except Exception as e:
            print(f"[RADAR] Serial open failed on {self.port}: {e}")
            print("[RADAR] Falling back to simulation.")
            self.simulation = True

    def _auto_detect_port(self) -> Optional[str]:
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            return None

        print("[RADAR] Available serial ports:")
        for p in ports:
            print(f"        {p.device} | {p.description}")

        # Prefer common ESP32 USB-UART chips and ACM devices
        keywords = ["cp210", "ch340", "wch", "silicon", "usb", "uart", "acm"]
        for p in ports:
            desc = (p.description or "").lower()
            dev = (p.device or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in dev or k in hwid for k in keywords):
                print(f"[RADAR] Auto-selected serial port: {p.device}")
                return p.device

        print(f"[RADAR] Auto-selected first serial port: {ports[0].device}")
        return ports[0].device

    def _loop(self):
        while self.running:
            if self.simulation:
                pkt = self._make_simulated_packet()
                with self.lock:
                    self.latest = pkt
                time.sleep(0.25)
            else:
                self._read_serial_once()

    def _read_serial_once(self):
        try:
            raw = self.ser.readline().decode("utf-8", errors="ignore").strip()
            if not raw:
                return

            pkt = self._parse_line(raw)
            if pkt is not None:
                with self.lock:
                    self.latest = pkt
                self.last_rx_time = time.time()
                print(f"[RADAR] {pkt['source']} x={pkt['x_m']:.2f} y={pkt['y_m']:.2f} angle={pkt['angle_deg']:.1f} dist={pkt['distance_m']:.2f}")
            else:
                # Keep this visible while debugging ESP32 output.
                print(f"[RADAR] Ignored unparsable line: {raw}")

        except Exception as e:
            print(f"[RADAR] Read error: {e}")
            time.sleep(0.5)

    def _parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        # Preferred: JSON line from ESP32
        try:
            data = json.loads(line)
            return self._normalise_packet(data, source="ESP32_LD2450_JSON")
        except Exception:
            pass

        # Fallback: CSV line x,y,angle,distance,targets
        try:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                data = {
                    "x": float(parts[0]),
                    "y": float(parts[1]),
                    "angle": float(parts[2]),
                    "distance": float(parts[3]),
                    "targets": int(float(parts[4])) if len(parts) >= 5 else 1,
                }
                return self._normalise_packet(data, source="ESP32_LD2450_CSV")
        except Exception:
            pass

        return None

    def _normalise_packet(self, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        x = float(data.get("x", data.get("x_m", 0.0)))
        y = float(data.get("y", data.get("y_m", 0.0)))
        z = float(data.get("z", data.get("z_m", 0.0)))

        dist_default = math.sqrt(x * x + y * y)
        angle_default = math.degrees(math.atan2(y, x)) if dist_default > 1e-9 else 0.0

        distance = float(data.get("distance", data.get("distance_m", dist_default)))
        angle = float(data.get("angle", data.get("angle_deg", angle_default)))
        targets = int(data.get("targets", data.get("target_count", 1)))
        velocity = float(data.get("velocity", data.get("velocity_mps", 0.0)))

        return {
            "x_m": round(x, 3),
            "y_m": round(y, 3),
            "z_m": round(z, 3),
            "angle_deg": round(angle, 2),
            "distance_m": round(distance, 3),
            "velocity_mps": round(velocity, 3),
            "source": source,
            "target_count": targets,
            "status": "OK" if targets > 0 else "NO_TARGET",
        }

    def _make_simulated_packet(self) -> Dict[str, Any]:
        t = time.time() - self.t0
        angle = 40.0 + 25.0 * math.sin(t * 0.35)
        dist = 3.5 + 0.7 * math.sin(t * 0.21)
        x = dist * math.cos(math.radians(angle))
        y = dist * math.sin(math.radians(angle))
        return {
            "x_m": round(x, 3),
            "y_m": round(y, 3),
            "z_m": 0.0,
            "angle_deg": round(angle, 2),
            "distance_m": round(dist, 3),
            "velocity_mps": round(abs(0.25 * math.cos(t * 0.35)), 3),
            "source": "SIM_RADAR",
            "target_count": 1,
            "status": "SIMULATED",
        }

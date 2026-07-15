import socket
import threading
import time
import traceback
from typing import Optional

from shared.protocol import encode_json_line, decode_json_lines
from . import config
from .ris_controller import RISController
from .radar_receiver import RadarReceiver
from .channel_monitor import ChannelMonitor
from .ml_pattern_engine import MLPatternEngine
from .rssi_person_tracker import RssiPersonTracker


class RISPiServer:
    def __init__(self):
        self.host = config.HOST
        self.port = config.PORT
        self.running = False

        self.ris = RISController()
        self.radar = RadarReceiver(
            port=config.RADAR_SERIAL_PORT,
            baudrate=config.RADAR_BAUDRATE,
            simulation=config.USE_SIMULATED_RADAR,
        )
        self.channel = ChannelMonitor()
        self.ml = MLPatternEngine(config.MODEL_PATH)
        self.person_tracker = RssiPersonTracker()

        self.client_sock: Optional[socket.socket] = None
        self.client_lock = threading.Lock()
        self.latest_radar = None
        self.latest_prediction = None

    def start(self):
        self.running = True
        self.radar.start()
        self.person_tracker.start()

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(1)

        print("=" * 72)
        print("RIS Raspberry Pi Controller Server")
        print(f"Listening on {self.host}:{self.port}")
        print(f"Telemetry rate: {config.TELEMETRY_HZ} Hz")
        print(f"Model: {config.MODEL_PATH}")
        print(f"Radar serial: port={config.RADAR_SERIAL_PORT or 'AUTO'} baud={config.RADAR_BAUDRATE}")
        print("Connect the Laptop GUI to this Raspberry Pi IP and port 5050.")
        print("=" * 72)

        try:
            while self.running:
                print("[SERVER] Waiting for laptop GUI client...")
                client, addr = server.accept()
                print(f"[SERVER] Client connected: {addr}")

                with self.client_lock:
                    if self.client_sock:
                        try:
                            self.client_sock.close()
                        except Exception:
                            pass
                    self.client_sock = client

                rx_thread = threading.Thread(target=self._receive_loop, args=(client,), daemon=True)
                tx_thread = threading.Thread(target=self._telemetry_loop, args=(client,), daemon=True)
                rx_thread.start()
                tx_thread.start()

                rx_thread.join()
                print("[SERVER] Client disconnected.")

        except KeyboardInterrupt:
            print("\n[SERVER] Stopped by user.")
        finally:
            self.running = False
            self.radar.stop()
            self.person_tracker.stop()
            try:
                server.close()
            except Exception:
                pass

    def _receive_loop(self, client: socket.socket):
        buffer = ""
        while self.running:
            try:
                data = client.recv(4096)
                if not data:
                    break

                buffer += data.decode("utf-8", errors="replace")
                packets, buffer = decode_json_lines(buffer)

                for packet in packets:
                    self._handle_command(packet)

            except Exception as e:
                print(f"[RX] Error: {e}")
                traceback.print_exc()
                break

        with self.client_lock:
            if self.client_sock is client:
                self.client_sock = None
        try:
            client.close()
        except Exception:
            pass

    def _handle_command(self, packet):
        print(f"[CMD] {packet}")

        if packet.get("type") != "command":
            return

        cmd = str(packet.get("cmd", "")).upper()

        try:
            if cmd == "SET_MODE":
                self.ris.set_mode(packet.get("mode", "AUTO"))

            elif cmd in ("APPLY_PATTERN", "GPIO_WRITE", "DIRECT_WIRE_BITS", "SET_BITS"):
                print("[CMD APPLY] raw cell_bits=", packet.get("cell_bits"))
                print("[CMD APPLY] raw wire_bits=", packet.get("wire_bits") or packet.get("bits"))
                ok = self.ris.apply_manual_pattern(
                    cell_bits=packet.get("cell_bits"),
                    wire_bits=packet.get("wire_bits") or packet.get("bits"),
                    pattern_id=packet.get("pattern_id", 0),
                )
                self._send_packet({
                    "type": "ack" if ok else "error",
                    "cmd": cmd,
                    "message": "GPIO write completed. Check CLOCK/LATCH on oscilloscope now." if ok else "GPIO NOT ACTIVE: command received, but no electrical output was written.",
                    "wire_bits": self.ris.state.wire_bits,
                    "cell_bits": self.ris.state.cell_bits,
                    "gpio_ready": bool(self.ris.hw.ready),
                    "gpio_enabled": bool(self.ris.hw.enabled),
                    "gpio": self.ris.hw.status_dict(),
                })
                # Send immediate status back so GUI does not wait for next telemetry tick.
                self._send_packet(self._build_telemetry_packet())

            elif cmd == "RESET_RIS":
                self.ris.reset()
                self._send_packet(self._build_telemetry_packet())

            elif cmd == "EMERGENCY_OFF":
                self.ris.emergency_off()
                self._send_packet(self._build_telemetry_packet())

            elif cmd == "GET_STATUS":
                self._send_packet(self._build_telemetry_packet())

            else:
                print(f"[CMD] Unknown command: {cmd}")

        except Exception as e:
            print(f"[CMD] Failed: {e}")
            self._send_packet({
                "type": "error",
                "message": str(e),
                "bad_command": packet,
            })

    def _telemetry_loop(self, client: socket.socket):
        dt = 1.0 / max(config.TELEMETRY_HZ, 0.1)

        while self.running:
            with self.client_lock:
                if self.client_sock is not client:
                    break

            try:
                packet = self._build_telemetry_packet()
                client.sendall(encode_json_line(packet))
                time.sleep(dt)

            except Exception as e:
                print(f"[TX] Error: {e}")
                break

    def _build_telemetry_packet(self):
        radar = self.radar.get_position()
        self.latest_radar = radar
        self.person_tracker.update_radar(radar)
        person = self.person_tracker.get_selection()

        # AUTO mode: fused position when available -> ML prediction -> RIS pattern -> hardware/wire bits.
        # MANUAL mode: keep current GUI-selected pattern, but still show live radar/RSSI/fused positions.
        fusion = person.get("fusion", {}) if isinstance(person, dict) else {}
        use_fused = bool(getattr(config, "FUSION_USE_FOR_AUTO_BEAM", True)) and bool(fusion.get("have_pos", False))
        control_x = float(fusion.get("x_m", radar["x_m"])) if use_fused else radar["x_m"]
        control_y = float(fusion.get("y_m", radar["y_m"])) if use_fused else radar["y_m"]
        control_source = str(fusion.get("mode", "RADAR")) if use_fused else "RADAR"

        if self.ris.state.mode == "AUTO":
            pred = self.ml.predict_from_xy(control_x, control_y)
            self.latest_prediction = pred
            self.ris.apply_auto_prediction(pred)
            channel = self.channel.get_channel(
                predicted_snr_db=pred.snr_db,
                capacity_mbps=pred.capacity_mbps,
            )
        else:
            pred = self.latest_prediction
            channel = self.channel.get_channel(
                predicted_snr_db=pred.snr_db if pred else None,
                capacity_mbps=pred.capacity_mbps if pred else None,
            )
            self.ris.state.beam_angle_deg = float(fusion.get("angle_deg", radar["angle_deg"])) if use_fused else radar["angle_deg"]

        return {
            "type": "telemetry",
            "timestamp": time.time(),
            "system": {
                "mode": self.ris.state.mode,
                "connection": "OK",
                "demo_state": "RUNNING",
            },
            "user": {
                "x_m": radar["x_m"],
                "y_m": radar["y_m"],
                "z_m": radar["z_m"],
                "angle_deg": radar["angle_deg"],
                "distance_m": radar["distance_m"],
                "velocity_mps": radar["velocity_mps"],
                "source": radar["source"],
            },
            "channel": channel,
            "ris": self.ris.as_telemetry_dict(),
            "radar": {
                "target_count": radar["target_count"],
                "status": radar["status"],
            },
            "control": {
                "x_m": control_x,
                "y_m": control_y,
                "source": control_source,
                "using_fused_for_auto": bool(use_fused),
            },
            "person": person,
            "network_devices": self.person_tracker.get_devices()[:12],
            "anchors": self.person_tracker.get_anchors(),
        }

    def _send_packet(self, packet):
        with self.client_lock:
            sock = self.client_sock

        if not sock:
            return

        try:
            sock.sendall(encode_json_line(packet))
        except Exception as e:
            print(f"[SEND] Failed: {e}")


def main():
    RISPiServer().start()


if __name__ == "__main__":
    main()

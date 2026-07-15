import socket
import threading
import json
from typing import Callable, Optional
from shared.protocol import encode_message

class NetworkClient:
    def __init__(self, on_packet: Callable[[dict], None], log: Callable[[str], None], on_disconnect: Optional[Callable[[], None]] = None):
        self.on_packet = on_packet
        self.log = log
        self.on_disconnect = on_disconnect
        self.sock: Optional[socket.socket] = None
        self.connected = False
        self._thread: Optional[threading.Thread] = None

    def connect(self, host: str, port: int) -> None:
        self.disconnect()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(4.0)
        s.connect((host, int(port)))
        try:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        s.settimeout(None)
        self.sock = s
        self.connected = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self.connected = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def send(self, payload: dict) -> None:
        if not self.connected or not self.sock:
            raise RuntimeError("Not connected to Raspberry Pi server.")
        raw = encode_message(payload)
        self.log("TX to Pi: " + raw.decode("utf-8", errors="replace").strip())
        self.sock.sendall(raw)

    def _read_loop(self) -> None:
        buffer = ""
        try:
            while self.connected and self.sock:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self.on_packet(json.loads(line))
                    except json.JSONDecodeError as exc:
                        self.log(f"Invalid JSON from Pi: {exc}")
        except OSError as exc:
            if self.connected:
                self.log(f"Network read error: {exc}")
        finally:
            was_connected = self.connected
            self.disconnect()
            if was_connected and self.on_disconnect:
                self.on_disconnect()

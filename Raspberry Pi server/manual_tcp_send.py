import json
import socket
import sys

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5050
CELL_BITS = sys.argv[3] if len(sys.argv) > 3 else "101010" * 4

def physical_to_wire_bits(cell_bits, dummy="00"):
    cell_bits = "".join(ch for ch in str(cell_bits) if ch in "01")[:24].ljust(24, "0")
    return "".join(cell_bits[r*6:(r+1)*6] + dummy for r in range(4))

wire_bits = physical_to_wire_bits(CELL_BITS)
payload = {
    "type": "command",
    "cmd": "APPLY_PATTERN",
    "pattern_id": 999,
    "cell_bits": CELL_BITS[:24].ljust(24, "0"),
    "wire_bits": wire_bits,
    "bits": wire_bits,
}
print("Sending to", HOST, PORT)
print("cell_bits =", payload["cell_bits"])
print("wire_bits =", " ".join(wire_bits[i:i+8] for i in range(0,32,8)))
with socket.create_connection((HOST, PORT), timeout=4) as s:
    s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    s.settimeout(2)
    try:
        print("Reply:", s.recv(4096).decode("utf-8", errors="replace"))
    except socket.timeout:
        print("No reply before timeout, but command was sent.")

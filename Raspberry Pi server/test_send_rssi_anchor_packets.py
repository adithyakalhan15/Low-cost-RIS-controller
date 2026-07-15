#!/usr/bin/env python3
import json
import socket
import sys
import time

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 4210
mac = sys.argv[3] if len(sys.argv) > 3 else "AA:BB:CC:DD:EE:01"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
patterns = [
    ("A", -48),
    ("B", -62),
    ("C", -55),
]
print(f"Sending test RSSI anchor packets to {host}:{port} for MAC {mac}")
try:
    while True:
        for node, rssi in patterns:
            pkt = {"id": node, "mac": mac, "rssi": rssi, "csi_amp": []}
            sock.sendto((json.dumps(pkt) + "\n").encode(), (host, port))
            print(pkt)
            time.sleep(0.25)
except KeyboardInterrupt:
    pass

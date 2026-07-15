#!/usr/bin/env python3
"""Direct lgpio preflight test for Raspberry Pi GPIO pins 19/23/24.
Run from the Pi venv used for the server:
    source .venv/bin/activate
    python3 gpio_preflight.py
"""
import os, sys, time
try:
    import lgpio
except Exception as e:
    print("[FAIL] Python cannot import lgpio in this environment.")
    print("       Error:", repr(e))
    print("       Fix:")
    print("       sudo apt remove -y python3-rpi.gpio python3-rpi-lgpio")
    print("       sudo apt install -y python3-lgpio")
    print("       rm -rf .venv")
    print("       python3 -m venv .venv --system-site-packages")
    print("       source .venv/bin/activate")
    sys.exit(1)

DATA, CLOCK, LATCH = 10, 11, 8
chip_req = int(os.environ.get("RIS_GPIOCHIP", "0"))
print("[OK] lgpio imported:", lgpio)
print("[INFO] Testing BCM pins DATA=10(pin19), CLOCK=11(pin23), LATCH=8(pin24)")
print("[INFO] Requested gpiochip:", chip_req)

last = None
for chipnum in [chip_req] + [i for i in range(0, 6) if i != chip_req]:
    h = None
    try:
        h = lgpio.gpiochip_open(chipnum)
        for p in (DATA, CLOCK, LATCH):
            lgpio.gpio_claim_output(h, p, 0)
        print(f"[OK] Claimed GPIO pins on /dev/gpiochip{chipnum}")
        print("[TEST] Toggling CLOCK and LATCH 10 times. Probe physical pins 23 and 24.")
        for i in range(10):
            lgpio.gpio_write(h, DATA, i % 2)
            lgpio.gpio_write(h, CLOCK, 1); time.sleep(0.1)
            lgpio.gpio_write(h, CLOCK, 0); time.sleep(0.1)
            lgpio.gpio_write(h, LATCH, 1); time.sleep(0.1)
            lgpio.gpio_write(h, LATCH, 0); time.sleep(0.1)
        for p in (DATA, CLOCK, LATCH):
            lgpio.gpio_write(h, p, 0)
            lgpio.gpio_free(h, p)
        lgpio.gpiochip_close(h)
        print("[PASS] GPIO is active in this Python environment.")
        print(f"[TIP] Start server with: export RIS_GPIOCHIP={chipnum}; python3 -m raspberry_pi_server.pi_server")
        sys.exit(0)
    except Exception as e:
        last = e
        try:
            if h is not None:
                lgpio.gpiochip_close(h)
        except Exception:
            pass
        print(f"[WARN] /dev/gpiochip{chipnum} failed: {e}")
print("[FAIL] Could not claim GPIO pins on any gpiochip.")
print("       Last error:", repr(last))
print("       Try: sudo usermod -aG gpio $USER && sudo reboot")
print("       Also stop any other program using pins 8, 10, 11.")
sys.exit(2)

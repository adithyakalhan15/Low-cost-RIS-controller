import time
from raspberry_pi_server.hardware_driver import RISHardwareDriver
from raspberry_pi_server import config


def main():
    print("====================================")
    print(" RIS 74HC595 hardware output test")
    print("====================================")
    print(f"ENABLE_HARDWARE_OUTPUT={config.ENABLE_HARDWARE_OUTPUT}")
    print(f"GPIO_BIT_DELAY_S={config.GPIO_BIT_DELAY_S}")
    print(f"ONLY_WRITE_HARDWARE_ON_CHANGE={config.ONLY_WRITE_HARDWARE_ON_CHANGE}")
    print()
    print("Mapping:")
    print("  DATA  physical pin 19 / BCM GPIO10 -> RJ45 pin 1 -> 74HC595 SER pin 14")
    print("  CLOCK physical pin 23 / BCM GPIO11 -> RJ45 pin 2 -> 74HC595 SRCLK pin 11")
    print("  LATCH physical pin 24 / BCM GPIO8  -> RJ45 pin 3 -> 74HC595 RCLK pin 12")
    print("  GND   physical pin 6 or 9          -> RJ45 pin 8 -> 74HC595 GND pin 8")
    print()

    hw = RISHardwareDriver(
        enabled=True,
        bit_delay_s=config.GPIO_BIT_DELAY_S,
        only_write_on_change=False,
        verbose=True,
    )

    patterns = [
        "0" * 32,
        "1" * 32,
        "10101010" * 4,
        "01010101" * 4,
    ]

    try:
        for p in patterns:
            print(f"\n[TEST] Sending fixed pattern {p}")
            hw.apply_wire_bits(p)
            time.sleep(1.0)

        print("\n[TEST] Walking-one test")
        for i in range(32):
            bits = ["0"] * 32
            bits[i] = "1"
            pattern = "".join(bits)
            print(f"[TEST] Walking one bit position {i + 1}/32")
            hw.apply_wire_bits(pattern)
            time.sleep(0.25)

        print("\n[TEST] Clear all")
        hw.apply_wire_bits("0" * 32)

    except KeyboardInterrupt:
        print("\n[TEST] Interrupted by user")
    finally:
        hw.stop()


if __name__ == "__main__":
    main()

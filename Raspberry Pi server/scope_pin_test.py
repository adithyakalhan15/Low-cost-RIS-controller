import time

from raspberry_pi_server.hardware_driver import RISHardwareDriver
from raspberry_pi_server import config


def main():
    print("========================================")
    print(" Raspberry Pi 74HC595 SLOW Scope Test")
    print("========================================")
    print("This script forces real GPIO output ON, even if server config is changed later.")
    print()
    print("Probe these Raspberry Pi PHYSICAL pins:")
    print("  DATA  -> physical pin 19  / BCM GPIO10")
    print("  CLOCK -> physical pin 23  / BCM GPIO11")
    print("  LATCH -> physical pin 24  / BCM GPIO8")
    print("  GND   -> physical pin 6 or 9")
    print()
    print("Expected on oscilloscope:")
    print("  DATA  changes according to bit pattern")
    print("  CLOCK gives 32 slow pulses per pattern")
    print("  LATCH gives 1 slow pulse after 32 clocks")
    print("  HIGH  about 3.3 V")
    print("  LOW   about 0 V")
    print()
    print(f"Using SCOPE_TEST_BIT_DELAY_S={config.SCOPE_TEST_BIT_DELAY_S}")
    print(f"Using SCOPE_TEST_PATTERN_PAUSE_S={config.SCOPE_TEST_PATTERN_PAUSE_S}")
    print()

    driver = RISHardwareDriver(
        enabled=True,
        data_pin=config.GPIO_DATA_PIN,
        clock_pin=config.GPIO_CLOCK_PIN,
        latch_pin=config.GPIO_LATCH_PIN,
        bit_delay_s=config.SCOPE_TEST_BIT_DELAY_S,
        only_write_on_change=False,
        verbose=True,
    )

    patterns = [
        "10101010101010101010101010101010",
        "01010101010101010101010101010101",
        "11111111000000001111111100000000",
        "00000000111111110000000011111111",
        "11111111111111111111111111111111",
        "00000000000000000000000000000000",
    ]

    try:
        while True:
            for pattern in patterns:
                print(f"\n[SCOPE] Sending pattern: {pattern}")
                driver.apply_wire_bits(pattern)
                time.sleep(config.SCOPE_TEST_PATTERN_PAUSE_S)

    except KeyboardInterrupt:
        print("\n[SCOPE] Stopping scope test")
        driver.set_all_low()
        driver.stop()


if __name__ == "__main__":
    main()

import os
import time
from . import config

try:
    import lgpio
    LGPIO_AVAILABLE = True
    LGPIO_IMPORT_ERROR = None
except Exception as exc:
    lgpio = None
    LGPIO_AVAILABLE = False
    LGPIO_IMPORT_ERROR = exc


class RISHardwareDriver:
    """
    Raspberry Pi 3-wire bit-bang driver for cascaded 74HC595 shift registers.

    IMPORTANT:
    This version uses the real lgpio library directly.
    It does NOT import RPi.GPIO, so it avoids the python3-rpi.gpio / python3-rpi-lgpio conflict.

        DATA  -> physical pin 19 -> BCM GPIO10 -> 74HC595 SER
        CLOCK -> physical pin 23 -> BCM GPIO11 -> 74HC595 SRCLK
        LATCH -> physical pin 24 -> BCM GPIO8  -> 74HC595 RCLK
        GND   -> physical pin 6/9 -> GND

    Input wire_bits must be a 32-character string.
    For this 4x6 RIS panel:
        24 real cell bits -> 4 rows x (6 real bits + 2 dummy bits) = 32 bits
    """

    def __init__(
        self,
        enabled=None,
        data_pin=None,
        clock_pin=None,
        latch_pin=None,
        bit_delay_s=None,
        only_write_on_change=None,
        verbose=None,
        gpiochip=None,
    ):
        self.enabled = bool(config.ENABLE_HARDWARE_OUTPUT if enabled is None else enabled)
        self.data_pin = int(config.GPIO_DATA_PIN if data_pin is None else data_pin)
        self.clock_pin = int(config.GPIO_CLOCK_PIN if clock_pin is None else clock_pin)
        self.latch_pin = int(config.GPIO_LATCH_PIN if latch_pin is None else latch_pin)
        self.bit_delay_s = float(config.GPIO_BIT_DELAY_S if bit_delay_s is None else bit_delay_s)
        self.only_write_on_change = bool(
            config.ONLY_WRITE_HARDWARE_ON_CHANGE if only_write_on_change is None else only_write_on_change
        )
        self.verbose = bool(config.HARDWARE_VERBOSE_PRINT if verbose is None else verbose)

        env_chip = os.environ.get("RIS_GPIOCHIP")
        default_chip = getattr(config, "GPIO_CHIP", 0)
        self.requested_gpiochip = int(env_chip if env_chip is not None else (default_chip if gpiochip is None else gpiochip))
        self.chip = None
        self.active_gpiochip = None
        self.last_wire_bits = None
        self.ready = False
        self.frame_counter = 0
        self.start()

    def start(self):
        print("[HW] Driver starting...")
        print(f"[HW] GPIO backend=lgpio direct, no RPi.GPIO import")
        print(f"[HW] ENABLE_HARDWARE_OUTPUT={self.enabled}")
        print(f"[HW] ONLY_WRITE_HARDWARE_ON_CHANGE={self.only_write_on_change}")
        print(f"[HW] SHIFT_MSB_FIRST={config.SHIFT_MSB_FIRST}")
        print(f"[HW] GPIO_BIT_DELAY_S={self.bit_delay_s}")
        print(f"[HW] Requested GPIO chip={self.requested_gpiochip}  override with: export RIS_GPIOCHIP=0")
        print(f"[HW] REQUIRE_REAL_GPIO_ACTIVE={getattr(config, 'REQUIRE_REAL_GPIO_ACTIVE', True)}")
        self._print_mapping()

        if not self.enabled:
            print("[HW] Hardware output disabled. Print-only simulation mode.")
            return

        if not LGPIO_AVAILABLE:
            print("[HW] lgpio import failed. Hardware output is disabled.")
            print(f"[HW] Import error: {LGPIO_IMPORT_ERROR}")
            print("[HW] Install only lgpio, not RPi.GPIO:")
            print("[HW]   sudo apt update")
            print("[HW]   sudo apt remove -y python3-rpi.gpio python3-rpi-lgpio")
            print("[HW]   sudo apt install -y python3-lgpio")
            print("[HW]   python3 -m venv .venv --system-site-packages")
            self.enabled = False
            self.ready = False
            return

        pins = [self.data_pin, self.clock_pin, self.latch_pin]
        chips_to_try = [self.requested_gpiochip] + [c for c in range(0, 6) if c != self.requested_gpiochip]
        last_error = None

        for chip_number in chips_to_try:
            try:
                chip = lgpio.gpiochip_open(chip_number)
                for pin in pins:
                    lgpio.gpio_claim_output(chip, pin, 0)
                self.chip = chip
                self.active_gpiochip = chip_number
                self.ready = True
                break
            except Exception as exc:
                last_error = exc
                try:
                    if 'chip' in locals() and chip is not None:
                        lgpio.gpiochip_close(chip)
                except Exception:
                    pass

        if not self.ready:
            print("[HW] Could not open/claim GPIO pins using lgpio.")
            print(f"[HW] Last error: {last_error}")
            print("[HW] Try these checks:")
            print("[HW]   ls /dev/gpiochip*")
            print("[HW]   sudo usermod -aG gpio $USER && sudo reboot")
            print("[HW]   export RIS_GPIOCHIP=0   # or 1/2/3/4 depending on your Pi")
            print("[HW]   python3 scope_pin_test.py")
            self.enabled = False
            return

        print(f"[HW] Hardware output ENABLED using lgpio on /dev/gpiochip{self.active_gpiochip}.")
        print("[HW] Initial pin states: DATA=LOW, CLOCK=LOW, LATCH=LOW")

    def _print_mapping(self):
        print("[HW] Wiring by Raspberry Pi physical pin:")
        print("[HW]   DATA  physical pin 19 / BCM GPIO10 -> RJ45 pin 1 -> 74HC595 SER pin 14")
        print("[HW]   CLOCK physical pin 23 / BCM GPIO11 -> RJ45 pin 2 -> 74HC595 SRCLK pin 11")
        print("[HW]   LATCH physical pin 24 / BCM GPIO8  -> RJ45 pin 3 -> 74HC595 RCLK pin 12")
        print("[HW]   GND   physical pin 6 or 9          -> RJ45 pin 8 -> 74HC595 GND pin 8")

    def status_dict(self):
        return {
            "enabled": bool(self.enabled),
            "ready": bool(self.ready),
            "backend": "lgpio-direct",
            "lgpio_available": bool(LGPIO_AVAILABLE),
            "active_gpiochip": self.active_gpiochip,
            "requested_gpiochip": self.requested_gpiochip,
            "data_pin_bcm": self.data_pin,
            "clock_pin_bcm": self.clock_pin,
            "latch_pin_bcm": self.latch_pin,
            "last_wire_bits": self.last_wire_bits,
        }

    def stop(self):
        try:
            self.set_all_low(cleanup=False)
        except Exception:
            pass

        if LGPIO_AVAILABLE and self.ready and self.chip is not None:
            try:
                for pin in [self.data_pin, self.clock_pin, self.latch_pin]:
                    try:
                        lgpio.gpio_free(self.chip, pin)
                    except Exception:
                        pass
                lgpio.gpiochip_close(self.chip)
            except Exception:
                pass

        self.chip = None
        self.ready = False
        print("[HW] Hardware driver stopped.")

    def set_all_low(self, cleanup=False):
        if LGPIO_AVAILABLE and self.ready and self.chip is not None:
            lgpio.gpio_write(self.chip, self.data_pin, 0)
            lgpio.gpio_write(self.chip, self.clock_pin, 0)
            lgpio.gpio_write(self.chip, self.latch_pin, 0)
            if cleanup:
                self.stop()
        print("[HW] DATA/CLOCK/LATCH set LOW")

    def _write_data(self, value: bool):
        lgpio.gpio_write(self.chip, self.data_pin, 1 if value else 0)

    def _write_clock(self, value: bool):
        lgpio.gpio_write(self.chip, self.clock_pin, 1 if value else 0)

    def _write_latch(self, value: bool):
        lgpio.gpio_write(self.chip, self.latch_pin, 1 if value else 0)

    def _sleep(self):
        time.sleep(self.bit_delay_s)

    def _pulse_clock(self):
        self._write_clock(False)
        self._sleep()
        self._write_clock(True)
        self._sleep()
        self._write_clock(False)
        self._sleep()

    def _pulse_latch(self):
        self._write_latch(False)
        self._sleep()
        self._write_latch(True)
        self._sleep()
        self._write_latch(False)
        self._sleep()

    @staticmethod
    def _group_bits(bits: str) -> str:
        return " ".join(bits[i:i + 8] for i in range(0, len(bits), 8))

    def apply_wire_bits(self, wire_bits: str):
        """
        Send a 32-bit wire stream to the 74HC595 chain.
        """
        wire_bits = str(wire_bits).strip()

        if len(wire_bits) != 32:
            print(f"[HW ERROR] Invalid wire_bits length: {len(wire_bits)}. Expected 32.")
            print(f"[HW ERROR] wire_bits={wire_bits}")
            return False

        if any(bit not in "01" for bit in wire_bits):
            print("[HW ERROR] Invalid wire_bits. Only 0 and 1 allowed.")
            print(f"[HW ERROR] wire_bits={wire_bits}")
            return False

        if self.only_write_on_change and wire_bits == self.last_wire_bits:
            if self.verbose:
                print(f"[HW SKIP] Same 32-bit pattern, not rewriting: {self._group_bits(wire_bits)}")
            return True

        self.last_wire_bits = wire_bits
        self.frame_counter += 1
        bits_to_send = wire_bits if config.SHIFT_MSB_FIRST else wire_bits[::-1]

        print("-" * 72)
        print(f"[HW TX #{self.frame_counter}] Requested wire_bits : {self._group_bits(wire_bits)}")
        print(f"[HW TX #{self.frame_counter}] Shifted bit order  : {self._group_bits(bits_to_send)}")
        print(f"[HW TX #{self.frame_counter}] Pins: DATA=GPIO{self.data_pin}/pin19, "
              f"CLOCK=GPIO{self.clock_pin}/pin23, LATCH=GPIO{self.latch_pin}/pin24")
        print(f"[HW TX #{self.frame_counter}] Backend=lgpio gpiochip={self.active_gpiochip}")
        print(f"[HW TX #{self.frame_counter}] Timing: bit_delay={self.bit_delay_s}s, clocks=32, latch_pulses=1")

        if not self.enabled or not self.ready or self.chip is None:
            print(f"[HW ERROR #{self.frame_counter}] GPIO not active. No electrical output written.")
            print(f"[HW ERROR #{self.frame_counter}] enabled={self.enabled}, ready={self.ready}, chip={self.chip}, lgpio_available={LGPIO_AVAILABLE}")
            print(f"[HW ERROR #{self.frame_counter}] You are probably running the server from an old venv/folder, or lgpio cannot be imported/claimed.")
            if getattr(config, "REQUIRE_REAL_GPIO_ACTIVE", True):
                return False
            return True

        self._write_latch(False)
        self._write_clock(False)
        self._sleep()

        for index, bit in enumerate(bits_to_send, start=1):
            self._write_data(bit == "1")
            if self.verbose:
                print(f"[HW TX #{self.frame_counter}] bit {index:02d}/32 DATA={bit} -> CLOCK pulse")
            self._sleep()
            self._pulse_clock()

        self._write_data(False)
        self._pulse_latch()

        print(f"[HW DONE #{self.frame_counter}] 32 clock pulses sent, latch pulsed, DATA left LOW.")
        return True

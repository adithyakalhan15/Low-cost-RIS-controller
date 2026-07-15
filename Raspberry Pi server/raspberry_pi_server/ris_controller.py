from dataclasses import dataclass
from typing import Dict, Any

from shared.protocol import validate_cell_bits, validate_wire_bits, physical_to_wire_bits, wire_to_physical_bits


def invert_bits(bit_string: str) -> str:
    """Return bitwise inverse of a 0/1 string."""
    return "".join("1" if b == "0" else "0" for b in bit_string)
from . import config
from .hardware_driver import RISHardwareDriver


@dataclass
class RISState:
    mode: str = "AUTO"
    cell_bits: str = "0" * 24
    wire_bits: str = "0" * 32
    pattern_id: int = 0
    beam_angle_deg: float = 0.0
    state: str = "IDLE"
    model_status: str = "INIT"
    inference_ms: float = 0.0


class RISController:
    def __init__(self):
        self.hw = RISHardwareDriver()
        self.state = RISState()
        self._update_wire_bits()

    def _update_wire_bits(self):
        self.state.wire_bits = physical_to_wire_bits(
            self.state.cell_bits,
            dummy_bits=config.DUMMY_BITS_PER_ROW
        )

    def set_mode(self, mode: str):
        mode = str(mode).upper()
        if mode not in ("AUTO", "MANUAL"):
            raise ValueError("mode must be AUTO or MANUAL")
        self.state.mode = mode
        self.state.state = f"{mode}_MODE"

    def apply_manual_pattern(self, cell_bits=None, wire_bits=None, pattern_id=0):
        """Apply a GUI/manual pattern to the real GPIO output.

        Robust rule for the desktop GUI path:
          1. If GUI sends a valid 32-bit wire_bits/bits stream, WRITE THAT EXACT
             32-bit stream to DATA/CLOCK/LATCH. Do not remap it again.
          2. Use 24-bit cell_bits only for the visible 4x6 state.
          3. If GUI sends only 24-bit cell_bits, map it to 32 bits here.

        This prevents the server from silently changing the GUI's transmitted
        pattern before it reaches the shift registers.
        """
        clean_wire = None
        clean_cell = None

        if wire_bits is not None:
            wire_candidate = "".join(ch for ch in str(wire_bits) if ch in "01")
            if len(wire_candidate) == 32:
                clean_wire = validate_wire_bits(wire_candidate)
            elif len(wire_candidate) == 24 and cell_bits is None:
                # Some older GUI builds sent the 24-bit physical pattern under "bits".
                cell_bits = wire_candidate
            elif wire_candidate:
                raise ValueError(f"wire_bits/bits must be 32 transmitted bits or 24 physical bits, got {len(wire_candidate)}")

        if cell_bits is not None:
            cell_candidate = "".join(ch for ch in str(cell_bits) if ch in "01")
            clean_cell = validate_cell_bits(cell_candidate[:24].ljust(24, "0"))

        if clean_wire is None and clean_cell is None:
            raise ValueError("manual pattern requires 24-bit cell_bits or 32-bit wire_bits/bits")

        if clean_wire is None:
            clean_wire = physical_to_wire_bits(clean_cell, dummy_bits=config.DUMMY_BITS_PER_ROW)

        if clean_cell is None:
            clean_cell = wire_to_physical_bits(clean_wire)

        self.state.cell_bits = clean_cell
        self.state.wire_bits = clean_wire
        self.state.pattern_id = int(pattern_id or 0)
        self.state.mode = "MANUAL"
        self.state.state = "MANUAL_APPLIED_INVERTED_TO_GPIO" if config.INVERT_GUI_PATTERN_TO_GPIO else "MANUAL_APPLIED"

        gpio_wire_bits = invert_bits(self.state.wire_bits) if config.INVERT_GUI_PATTERN_TO_GPIO else self.state.wire_bits
        gpio_cell_bits = wire_to_physical_bits(gpio_wire_bits)

        print("[RIS MANUAL] pattern_id=", self.state.pattern_id)
        print("[RIS MANUAL] GUI cell_bits 24        =", self.state.cell_bits)
        print("[RIS MANUAL] GUI wire_bits 32        =", " ".join(self.state.wire_bits[i:i+8] for i in range(0, 32, 8)))
        print("[RIS MANUAL] INVERT_TO_GPIO         =", config.INVERT_GUI_PATTERN_TO_GPIO)
        print("[RIS MANUAL] GPIO cell_bits 24       =", gpio_cell_bits)
        print("[RIS MANUAL] GPIO wire_bits 32 SENT  =", " ".join(gpio_wire_bits[i:i+8] for i in range(0, 32, 8)))
        ok = self.hw.apply_wire_bits(gpio_wire_bits)
        if not ok:
            self.state.state = "GPIO_NOT_ACTIVE_ERROR"
            print("[RIS ERROR] GPIO write failed. Pattern was NOT electrically written.")
        return ok

    def apply_auto_prediction(self, prediction):
        self.state.cell_bits = validate_cell_bits(prediction.cell_bits)
        self._update_wire_bits()
        self.state.pattern_id = int(prediction.pattern_id)
        self.state.beam_angle_deg = float(prediction.beam_angle_deg)
        self.state.model_status = str(prediction.model_status)
        self.state.inference_ms = float(prediction.inference_ms)
        self.state.state = "AUTO_APPLIED"
        ok = self.hw.apply_wire_bits(self.state.wire_bits)
        if not ok:
            self.state.state = "GPIO_NOT_ACTIVE_ERROR"
        return ok

    def reset(self):
        self.state.cell_bits = "0" * config.RIS_CELLS
        self._update_wire_bits()
        self.state.pattern_id = 0
        self.state.state = "RESET"
        ok = self.hw.apply_wire_bits(self.state.wire_bits)
        if not ok:
            self.state.state = "GPIO_NOT_ACTIVE_ERROR"
        return ok

    def emergency_off(self):
        self.state.cell_bits = "0" * config.RIS_CELLS
        self._update_wire_bits()
        self.state.pattern_id = 0
        self.state.mode = "MANUAL"
        self.state.state = "OFF"
        ok = self.hw.apply_wire_bits(self.state.wire_bits)
        if not ok:
            self.state.state = "GPIO_NOT_ACTIVE_ERROR"
        return ok

    def _gpio_wire_bits_for_current_state(self):
        return invert_bits(self.state.wire_bits) if config.INVERT_GUI_PATTERN_TO_GPIO else self.state.wire_bits

    def as_telemetry_dict(self):
        gpio_wire_bits = self._gpio_wire_bits_for_current_state()
        gpio_cell_bits = wire_to_physical_bits(gpio_wire_bits)
        return {
            "rows": config.RIS_ROWS,
            "cols": config.RIS_COLS,
            "elements": config.RIS_CELLS,
            "pattern_id": self.state.pattern_id,
            "beam_angle_deg": round(self.state.beam_angle_deg, 2),
            "cell_bits": self.state.cell_bits,
            "bits": self.state.wire_bits,
            "wire_bits": self.state.wire_bits,
            "gpio_wire_bits": gpio_wire_bits,
            "gpio_cell_bits": gpio_cell_bits,
            "gpio_inverted": bool(config.INVERT_GUI_PATTERN_TO_GPIO),
            "state": self.state.state,
            "model_status": self.state.model_status,
            "inference_ms": round(self.state.inference_ms, 3),
            "gpio": self.hw.status_dict(),
            "gpio_ready": bool(self.hw.ready),
            "gpio_enabled": bool(self.hw.enabled),
        }

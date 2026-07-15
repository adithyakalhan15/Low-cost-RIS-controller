import json

RIS_ROWS = 4
RIS_COLS = 6
RIS_ELEMENTS = RIS_ROWS * RIS_COLS
WIRE_BITS_PER_ROW = 8
GARBAGE_BITS_PER_ROW = 2
WIRE_BITS_TOTAL = RIS_ROWS * WIRE_BITS_PER_ROW
DEFAULT_GARBAGE_BITS = "00"


def validate_cell_bits(bits: str) -> None:
    if len(bits) != RIS_ELEMENTS:
        raise ValueError(f"Physical RIS pattern must have exactly {RIS_ELEMENTS} bits for the 4x6 panel.")
    if any(ch not in "01" for ch in bits):
        raise ValueError("RIS pattern can contain only 0 and 1.")


def validate_wire_bits(bits: str) -> None:
    if len(bits) != WIRE_BITS_TOTAL:
        raise ValueError(f"Transmit pattern must have exactly {WIRE_BITS_TOTAL} bits: 4 rows x 8 bits.")
    if any(ch not in "01" for ch in bits):
        raise ValueError("Transmit pattern can contain only 0 and 1.")


# Backward compatible name used by older GUI code.
def validate_ris_bits(bits: str) -> None:
    validate_cell_bits(bits)


def physical_to_wire_bits(cell_bits: str, garbage_bits: str = DEFAULT_GARBAGE_BITS) -> str:
    """Convert 24 physical 4x6 cell bits into 32 transmitted bits.

    Mapping used here:
      row 1: 6 real cell bits + 2 dummy bits
      row 2: 6 real cell bits + 2 dummy bits
      row 3: 6 real cell bits + 2 dummy bits
      row 4: 6 real cell bits + 2 dummy bits

    Example: C0 C1 C2 C3 C4 C5 D D | C6 ... C11 D D | ...
    Change this one function later if your shift-register wiring expects dummy bits at the start of each row.
    """
    cell_bits = "".join(ch for ch in str(cell_bits) if ch in "01")[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
    garbage_bits = "".join(ch for ch in str(garbage_bits) if ch in "01")[:GARBAGE_BITS_PER_ROW].ljust(GARBAGE_BITS_PER_ROW, "0")
    out = []
    for r in range(RIS_ROWS):
        start = r * RIS_COLS
        out.append(cell_bits[start:start + RIS_COLS] + garbage_bits)
    wire_bits = "".join(out)
    validate_wire_bits(wire_bits)
    return wire_bits


def wire_to_physical_bits(wire_bits: str) -> str:
    """Extract 24 physical bits from a 32-bit transmitted row format.
    It assumes each 8-bit row is 6 real bits followed by 2 dummy bits.
    """
    wire_bits = "".join(ch for ch in str(wire_bits) if ch in "01")
    if len(wire_bits) < WIRE_BITS_TOTAL:
        # Treat old 24-bit telemetry as physical cell bits.
        return wire_bits[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
    out = []
    for r in range(RIS_ROWS):
        start = r * WIRE_BITS_PER_ROW
        out.append(wire_bits[start:start + RIS_COLS])
    return "".join(out)[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")


def encode_message(payload: dict) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


def command_set_mode(mode: str) -> dict:
    return {"type": "command", "cmd": "SET_MODE", "mode": mode.upper()}


def command_apply_pattern(pattern_id: int, bits: str) -> dict:
    """Command payload for manual RIS apply.

    `cell_bits` is the visible 4x6 = 24-bit physical panel state.
    `bits` is the actual 32-bit stream to send to the controller/shift-register chain.
    """
    cell_bits = "".join(ch for ch in str(bits) if ch in "01")[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
    validate_cell_bits(cell_bits)
    wire_bits = physical_to_wire_bits(cell_bits)
    return {
        "type": "command",
        "cmd": "APPLY_PATTERN",
        "pattern_id": int(pattern_id),
        "cell_bits": cell_bits,
        "bits": wire_bits,
        "wire_bits": wire_bits,
        "rows": RIS_ROWS,
        "cols": RIS_COLS,
        "wire_bits_per_row": WIRE_BITS_PER_ROW,
        "garbage_bits_per_row": GARBAGE_BITS_PER_ROW,
    }


def command_reset_ris() -> dict:
    return {"type": "command", "cmd": "RESET_RIS"}


def command_emergency_off() -> dict:
    return {"type": "command", "cmd": "EMERGENCY_OFF"}


def command_get_status() -> dict:
    return {"type": "command", "cmd": "GET_STATUS"}

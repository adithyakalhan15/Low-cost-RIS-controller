import json
from typing import Any, Dict

RIS_ROWS = 4
RIS_COLS = 6
RIS_CELLS = RIS_ROWS * RIS_COLS
WIRE_BITS_PER_ROW = 8
WIRE_BITS = RIS_ROWS * WIRE_BITS_PER_ROW


def validate_cell_bits(cell_bits: str) -> str:
    cell_bits = str(cell_bits).strip()
    if len(cell_bits) != RIS_CELLS:
        raise ValueError(f"cell_bits must be {RIS_CELLS} bits, got {len(cell_bits)}")
    if any(b not in "01" for b in cell_bits):
        raise ValueError("cell_bits must contain only 0 and 1")
    return cell_bits


def validate_wire_bits(wire_bits: str) -> str:
    wire_bits = str(wire_bits).strip()
    if len(wire_bits) != WIRE_BITS:
        raise ValueError(f"wire_bits must be {WIRE_BITS} bits, got {len(wire_bits)}")
    if any(b not in "01" for b in wire_bits):
        raise ValueError("wire_bits must contain only 0 and 1")
    return wire_bits


def physical_to_wire_bits(cell_bits: str, dummy_bits: str = "00") -> str:
    """
    Convert 4x6 physical RIS bits into 32 wire bits:
    each row = 6 cell bits + 2 dummy/garbage bits.
    """
    cell_bits = validate_cell_bits(cell_bits)
    if len(dummy_bits) != 2 or any(b not in "01" for b in dummy_bits):
        raise ValueError("dummy_bits must be exactly two bits, e.g. '00'")

    out = []
    for r in range(RIS_ROWS):
        row = cell_bits[r * RIS_COLS:(r + 1) * RIS_COLS]
        out.append(row + dummy_bits)
    return "".join(out)


def wire_to_physical_bits(wire_bits: str) -> str:
    """
    Reverse mapping, assuming last 2 bits of each 8-bit row are dummy bits.
    """
    wire_bits = validate_wire_bits(wire_bits)
    out = []
    for r in range(RIS_ROWS):
        row8 = wire_bits[r * WIRE_BITS_PER_ROW:(r + 1) * WIRE_BITS_PER_ROW]
        out.append(row8[:RIS_COLS])
    return "".join(out)


def encode_json_line(packet: Dict[str, Any]) -> bytes:
    return (json.dumps(packet, separators=(",", ":")) + "\n").encode("utf-8")


def decode_json_lines(buffer: str):
    """
    Generator returning complete JSON packets and remaining buffer.
    Usage:
        packets, buffer = decode_json_lines(buffer)
    """
    packets = []
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        line = line.strip()
        if not line:
            continue
        packets.append(json.loads(line))
    return packets, buffer

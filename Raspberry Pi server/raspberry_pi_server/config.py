from pathlib import Path

# ================= TCP SERVER =================
HOST = "0.0.0.0"
PORT = 5050

# Slow enough that GPIO writes do not spam while debugging with oscilloscope.
# You can increase later after hardware is confirmed.
TELEMETRY_HZ = 4.0

# ================= RIS PANEL =================
# Physical panel: 4 rows x 6 columns = 24 real controllable cells
RIS_ROWS = 4
RIS_COLS = 6
RIS_CELLS = RIS_ROWS * RIS_COLS

# Driver/wire stream: each row sends 8 bits = 6 real bits + 2 dummy bits.
# Current mapping: Row = C0 C1 C2 C3 C4 C5 D D
# IMPORTANT: GUI sends 24 physical bits plus 32 wire_bits. The server now writes
# GUI-provided wire_bits exactly for manual mode, and only maps physical bits when
# no 32-bit wire stream is supplied.
DUMMY_BITS_PER_ROW = "00"


# ================= GPIO TEST INVERSION =================
# True = server receives normal GUI bits, but writes the INVERSE to GPIO.
# This is useful when your driver/shift-register/transistor stage is active-low
# or when you want to verify inverted bit patterns on the oscilloscope.
# Example GUI cell_bits 1010... -> GPIO wire_bits 0101... including dummy bits.
INVERT_GUI_PATTERN_TO_GPIO = True

# ================= ML MODEL =================
BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_PATH = BASE_DIR / "models" / "GTN_24.onnx"

# Physics / ML geometry
FREQ_HZ = 2.4e9
C_LIGHT = 3e8
TX_AZ_DEG = 45.0
TX_EL_DEG = 0.0
TX_DIST_M = 10.0
RIS_CENTER = (0.0, 0.0, 2.0)

# ================= RADAR SERIAL =================
# ESP32 -> Raspberry Pi through USB serial.
# Keep None for auto-detect. Set "/dev/ttyUSB0" or "/dev/ttyACM0" if needed.
RADAR_SERIAL_PORT = None
RADAR_BAUDRATE = 115200

# Set False to use real ESP32 serial radar.
# If serial fails, it automatically falls back to simulation.
USE_SIMULATED_RADAR = False

# ================= CHANNEL =================
# For now channel values are based on ML prediction + demo noise.
USE_SIMULATED_CHANNEL = True

# ================= HARDWARE OUTPUT =================
# True = bit-bang DATA/CLOCK/LATCH GPIO to 74HC595 through RJ45.
# False = print 32-bit wire stream only.
# Final demo default is now TRUE because you asked for real GPIO output.
ENABLE_HARDWARE_OUTPUT = True

# Avoid hammering hardware with same repeated pattern in normal server mode.
# Set False only when you intentionally want repeated identical waveforms.
ONLY_WRITE_HARDWARE_ON_CHANGE = True

# Print clear GPIO/write details for every hardware frame.
HARDWARE_VERBOSE_PRINT = False

# True = if GPIO cannot be imported/claimed, commands return ERROR instead of silently simulating.
# This prevents the GUI/server from pretending that GPIO was written when it was not.
REQUIRE_REAL_GPIO_ACTIVE = True

# Raspberry Pi GPIO numbering used by Python code: BCM numbering.
# Wire using PHYSICAL pin numbers on the Raspberry Pi header:
#   Physical pin 19 -> DATA  / MOSI  -> RJ45 pin 1 -> 74HC595 SER pin 14
#   Physical pin 23 -> CLOCK / SCLK  -> RJ45 pin 2 -> 74HC595 SRCLK pin 11
#   Physical pin 24 -> LATCH / CE0   -> RJ45 pin 3 -> 74HC595 RCLK pin 12
#   Physical pin 6  -> GND           -> RJ45 pin 8 -> 74HC595 GND pin 8

# lgpio GPIO chip number. Usually 0 on Raspberry Pi OS.
# If claiming pins fails, try: export RIS_GPIOCHIP=4 then rerun scope_pin_test.py
GPIO_CHIP = 0

# BCM numbers for those same physical pins:
GPIO_DATA_PIN = 10    # physical pin 19
GPIO_CLOCK_PIN = 11   # physical pin 23
GPIO_LATCH_PIN = 8    # physical pin 24

# Bit-bang delay between GPIO transitions.
# 0.005 s = very easy to see on oscilloscope.
# Approx frame time is around 0.65 s for 32 bits.
# For even slower viewing, use 0.010.
# For final fast operation later, use 0.00005 to 0.0001.
GPIO_BIT_DELAY_S = 0.0001

# Dedicated slower delay for scope_pin_test.py.
# This overrides GPIO_BIT_DELAY_S only inside the scope test.
SCOPE_TEST_BIT_DELAY_S = 0.010

# Time between full 32-bit patterns in scope_pin_test.py.
SCOPE_TEST_PATTERN_PAUSE_S = 1.0

# Backward-compatible alias used by older driver code.
SHIFT_BIT_DELAY_S = GPIO_BIT_DELAY_S

# True = first character in wire_bits is shifted first.
# If your physical output order appears reversed, change this to False.
SHIFT_MSB_FIRST = True

# ================= RSSI + NETWORK PERSON TRACKING =================
# This is an add-on. It does not replace the existing LD2450 RadarReceiver.
# ESP32 anchor nodes send UDP JSON to Raspberry Pi:
#   {"id":"A","mac":"AA:BB:CC:DD:EE:FF","rssi":-55,"csi_amp":[]}
ENABLE_RSSI_PERSON_TRACKING = True
RSSI_UDP_BIND_IP = "0.0.0.0"
RSSI_UDP_PORT = 4210
RSSI_PRINT_PACKETS = False

# Simple room/anchor geometry for RSSI weighted-centroid estimation.
ROOM_WIDTH_M = 2.0
ROOM_HEIGHT_M = 2.0
RIS_REF_X_M = 1.0
RIS_REF_Y_M = 0.0

RSSI_ANCHORS = {
    "A": {"name": "Anchor A", "ip": "192.168.50.11", "x_m": 0.0, "y_m": 0.0, "rssi_ref_dbm": -33.0, "path_loss_exp": 2.99},
    "B": {"name": "Anchor B", "ip": "192.168.50.12", "x_m": 2.0, "y_m": 0.0, "rssi_ref_dbm": -32.0, "path_loss_exp": 4.65},
    "C": {"name": "Anchor C", "ip": "192.168.50.13", "x_m": 1.0, "y_m": 2.0, "rssi_ref_dbm": -42.0, "path_loss_exp": 5.00},
}

RSSI_ANCHOR_MAX_AGE_S = 2.0
RSSI_DEVICE_TIMEOUT_S = 20.0
RSSI_RADAR_MATCH_MAX_DISTANCE_M = 1.25
PERSON_SELECT_PREFER_RADAR = True

# ================= RADAR + RSSI FUSION =================
# Adds a real fused position estimate to telemetry and optionally uses it for AUTO beam/control.
ENABLE_RADAR_RSSI_FUSION = True
FUSION_USE_FOR_AUTO_BEAM = True
# Radar is more trusted than RSSI because RSSI is noisy/multipath-heavy.
FUSION_RADAR_WEIGHT_BASE = 0.75
FUSION_RADAR_WEIGHT_MIN = 0.60
FUSION_RADAR_WEIGHT_MAX = 0.95
FUSION_EMA_ALPHA = 0.45



# ================= DEVICE NAMING / FILTERING =================
# RSSI packets only contain MAC addresses. Put your demo phone/laptop MAC here
# so the GUI can show a readable name instead of only "unknown device".
# On Android, connect to RIS_NET, open Wi‑Fi details, disable Private/Random MAC,
# then copy the device MAC shown there. Use uppercase or lowercase; both work.
KNOWN_WIFI_DEVICES = {
    # "AA:BB:CC:DD:EE:FF": "Adithya Phone",
    # "11:22:33:44:55:66": "Demo Laptop",
}

# Put ESP32 anchor MACs/router MACs here if they pollute the device list.
RSSI_IGNORE_MACS = {
    # "AA:AA:AA:AA:AA:AA",
}

# False = show all devices heard by anchors, with unknown/random labels.
# True  = only track MACs listed in KNOWN_WIFI_DEVICES. Useful for final demo.
RSSI_ONLY_TRACK_KNOWN_DEVICES = False

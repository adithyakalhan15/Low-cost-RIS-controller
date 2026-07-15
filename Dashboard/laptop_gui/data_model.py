from dataclasses import dataclass, field
from typing import Dict, Any, List
import time
from .config import RIS_ROWS, RIS_COLS, RIS_ELEMENTS
from shared.protocol import physical_to_wire_bits, wire_to_physical_bits

@dataclass
class SystemState:
    mode: str = "AUTO"
    connection: str = "SIMULATION"
    demo_state: str = "RUNNING"

@dataclass
class UserState:
    x_m: float = 2.0
    y_m: float = 2.0
    z_m: float = 0.0
    angle_deg: float = 35.0
    distance_m: float = 2.8
    velocity_mps: float = 0.0
    source: str = "SIM"

@dataclass
class ChannelState:
    rssi_dbm: float = -60.0
    snr_db: float = 15.0
    throughput_mbps: float = 18.0
    packet_loss_percent: float = 2.0
    ber: float = 0.0002

@dataclass
class RISState:
    rows: int = RIS_ROWS
    cols: int = RIS_COLS
    elements: int = RIS_ELEMENTS
    pattern_id: int = 0
    beam_angle_deg: float = 0.0
    bits: str = "0" * RIS_ELEMENTS  # 24 physical 4x6 cell bits
    wire_bits: str = physical_to_wire_bits("0" * RIS_ELEMENTS)  # GUI/requested 32-bit stream
    gpio_wire_bits: str = physical_to_wire_bits("1" * RIS_ELEMENTS)  # actual 32-bit stream written to GPIO if inverted
    gpio_cell_bits: str = "1" * RIS_ELEMENTS
    gpio_inverted: bool = False
    state: str = "IDLE"

@dataclass
class RadarState:
    target_count: int = 1
    status: str = "OK"

@dataclass
class PersonState:
    selected: bool = False
    mac: str = ""
    name: str = "Unknown device"
    is_known: bool = False
    is_random_mac: bool = False
    source: str = "NONE"
    status: str = "INIT"
    confidence: float = 0.0
    match_distance_m: float = 0.0
    device_count: int = 0
    wifi_x_m: float = 0.0
    wifi_y_m: float = 0.0
    wifi_angle_deg: float = 0.0
    wifi_distance_m: float = 0.0
    wifi_rssi_dbm: float = -100.0
    anchor_count: int = 0
    fused_have_pos: bool = False
    fused_mode: str = "NO_POSITION"
    fused_x_m: float = 0.0
    fused_y_m: float = 0.0
    fused_angle_deg: float = 0.0
    fused_distance_m: float = 0.0
    fused_confidence: float = 0.0
    fused_radar_weight: float = 0.0
    fused_rssi_weight: float = 0.0


@dataclass
class NetworkDeviceState:
    mac: str = ""
    name: str = "Unknown device"
    is_known: bool = False
    is_random_mac: bool = False
    per_anchor_rssi: Dict[str, float] = field(default_factory=dict)
    last_seen_age_s: float = 0.0
    have_pos: bool = False
    x_m: float = 0.0
    y_m: float = 0.0
    angle_deg: float = 0.0
    distance_m: float = 0.0
    anchor_count: int = 0
    strongest_rssi_dbm: float = -100.0
    selected_count: int = 0

@dataclass
class AnchorState:
    id: str = ""
    name: str = ""
    ip: str = ""
    x_m: float = 0.0
    y_m: float = 0.0
    rssi_ref_dbm: float = -35.0
    path_loss_exp: float = 3.0
    last_seen_age_s: float = -1.0
    packet_count: int = 0
    last_sender: str = ""
    last_mac: str = ""
    last_rssi_dbm: float = -100.0

@dataclass
class TelemetryState:
    timestamp: float = field(default_factory=time.time)
    system: SystemState = field(default_factory=SystemState)
    user: UserState = field(default_factory=UserState)
    channel: ChannelState = field(default_factory=ChannelState)
    ris: RISState = field(default_factory=RISState)
    radar: RadarState = field(default_factory=RadarState)
    person: PersonState = field(default_factory=PersonState)
    network_devices: List[NetworkDeviceState] = field(default_factory=list)
    anchors: List[AnchorState] = field(default_factory=list)

    def update_from_packet(self, packet: Dict[str, Any]) -> None:
        self.timestamp = float(packet.get("timestamp", time.time()))
        system = packet.get("system", {})
        user = packet.get("user", {})
        channel = packet.get("channel", {})
        ris = packet.get("ris", {})
        radar = packet.get("radar", {})
        person = packet.get("person", {})

        self.system.mode = str(system.get("mode", self.system.mode)).upper()
        self.system.connection = str(system.get("connection", self.system.connection))
        self.system.demo_state = str(system.get("demo_state", self.system.demo_state))

        self.user.x_m = float(user.get("x_m", self.user.x_m))
        self.user.y_m = float(user.get("y_m", self.user.y_m))
        self.user.z_m = float(user.get("z_m", self.user.z_m))
        self.user.angle_deg = float(user.get("angle_deg", self.user.angle_deg))
        self.user.distance_m = float(user.get("distance_m", self.user.distance_m))
        self.user.velocity_mps = float(user.get("velocity_mps", self.user.velocity_mps))
        self.user.source = str(user.get("source", self.user.source))

        self.channel.rssi_dbm = float(channel.get("rssi_dbm", self.channel.rssi_dbm))
        self.channel.snr_db = float(channel.get("snr_db", self.channel.snr_db))
        self.channel.throughput_mbps = float(channel.get("throughput_mbps", self.channel.throughput_mbps))
        self.channel.packet_loss_percent = float(channel.get("packet_loss_percent", self.channel.packet_loss_percent))
        self.channel.ber = float(channel.get("ber", self.channel.ber))

        self.ris.rows = int(ris.get("rows", RIS_ROWS))
        self.ris.cols = int(ris.get("cols", RIS_COLS))
        self.ris.elements = int(ris.get("elements", RIS_ELEMENTS))
        self.ris.pattern_id = int(ris.get("pattern_id", self.ris.pattern_id))
        self.ris.beam_angle_deg = float(ris.get("beam_angle_deg", self.ris.beam_angle_deg))

        # Accept both formats:
        #   cell_bits = 24 physical panel bits
        #   bits/wire_bits = 32 transmitted bits with 2 dummy bits per row
        raw_cell_bits = ris.get("cell_bits", None)
        raw_bits = str(ris.get("bits", self.ris.bits))
        raw_wire_bits = str(ris.get("wire_bits", raw_bits))

        if raw_cell_bits is not None:
            cell_bits = str(raw_cell_bits)
        elif len("".join(ch for ch in raw_bits if ch in "01")) >= 32:
            cell_bits = wire_to_physical_bits(raw_bits)
        else:
            cell_bits = raw_bits

        self.ris.bits = "".join(ch for ch in cell_bits if ch in "01")[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")

        if len("".join(ch for ch in raw_wire_bits if ch in "01")) >= 32:
            self.ris.wire_bits = "".join(ch for ch in raw_wire_bits if ch in "01")[:32]
        else:
            self.ris.wire_bits = physical_to_wire_bits(self.ris.bits)

        raw_gpio_wire = str(ris.get("gpio_wire_bits", self.ris.wire_bits))
        if len("".join(ch for ch in raw_gpio_wire if ch in "01")) >= 32:
            self.ris.gpio_wire_bits = "".join(ch for ch in raw_gpio_wire if ch in "01")[:32]
        else:
            self.ris.gpio_wire_bits = self.ris.wire_bits
        self.ris.gpio_cell_bits = str(ris.get("gpio_cell_bits", wire_to_physical_bits(self.ris.gpio_wire_bits)))
        self.ris.gpio_inverted = bool(ris.get("gpio_inverted", False))
        self.ris.state = str(ris.get("state", self.ris.state))

        self.radar.target_count = int(radar.get("target_count", self.radar.target_count))
        self.radar.status = str(radar.get("status", self.radar.status))

        self.person.selected = bool(person.get("selected", self.person.selected))
        self.person.mac = str(person.get("mac", self.person.mac))
        self.person.name = str(person.get("name", self.person.name))
        self.person.is_known = bool(person.get("is_known", self.person.is_known))
        self.person.is_random_mac = bool(person.get("is_random_mac", self.person.is_random_mac))
        self.person.source = str(person.get("source", self.person.source))
        self.person.status = str(person.get("status", self.person.status))
        self.person.confidence = float(person.get("confidence", self.person.confidence))
        md = person.get("match_distance_m", self.person.match_distance_m)
        self.person.match_distance_m = 0.0 if md is None else float(md)
        self.person.device_count = int(person.get("device_count", self.person.device_count))
        wifi = person.get("wifi", {}) if isinstance(person.get("wifi", {}), dict) else {}
        self.person.wifi_x_m = float(wifi.get("x_m", self.person.wifi_x_m))
        self.person.wifi_y_m = float(wifi.get("y_m", self.person.wifi_y_m))
        self.person.wifi_angle_deg = float(wifi.get("angle_deg", self.person.wifi_angle_deg))
        self.person.wifi_distance_m = float(wifi.get("distance_m", self.person.wifi_distance_m))
        self.person.wifi_rssi_dbm = float(wifi.get("strongest_rssi_dbm", self.person.wifi_rssi_dbm))
        self.person.anchor_count = int(wifi.get("anchor_count", self.person.anchor_count))
        fusion = person.get("fusion", {}) if isinstance(person.get("fusion", {}), dict) else {}
        self.person.fused_have_pos = bool(fusion.get("have_pos", self.person.fused_have_pos))
        self.person.fused_mode = str(fusion.get("mode", self.person.fused_mode))
        self.person.fused_x_m = float(fusion.get("x_m", self.person.fused_x_m))
        self.person.fused_y_m = float(fusion.get("y_m", self.person.fused_y_m))
        self.person.fused_angle_deg = float(fusion.get("angle_deg", self.person.fused_angle_deg))
        self.person.fused_distance_m = float(fusion.get("distance_m", self.person.fused_distance_m))
        self.person.fused_confidence = float(fusion.get("confidence", self.person.fused_confidence))
        self.person.fused_radar_weight = float(fusion.get("radar_weight", self.person.fused_radar_weight))
        self.person.fused_rssi_weight = float(fusion.get("rssi_weight", self.person.fused_rssi_weight))

        devices = packet.get("network_devices", [])
        self.network_devices = []
        if isinstance(devices, list):
            for d in devices[:12]:
                if not isinstance(d, dict):
                    continue
                try:
                    self.network_devices.append(NetworkDeviceState(
                        mac=str(d.get("mac", "")),
                        name=str(d.get("name", "Unknown device")),
                        is_known=bool(d.get("is_known", False)),
                        is_random_mac=bool(d.get("is_random_mac", False)),
                        per_anchor_rssi=dict(d.get("per_anchor_rssi", {})) if isinstance(d.get("per_anchor_rssi", {}), dict) else {},
                        last_seen_age_s=float(d.get("last_seen_age_s", 0.0)),
                        have_pos=bool(d.get("have_pos", False)),
                        x_m=float(d.get("x_m", 0.0)),
                        y_m=float(d.get("y_m", 0.0)),
                        angle_deg=float(d.get("angle_deg", 0.0)),
                        distance_m=float(d.get("distance_m", 0.0)),
                        anchor_count=int(d.get("anchor_count", 0)),
                        strongest_rssi_dbm=float(d.get("strongest_rssi_dbm", -100.0)),
                        selected_count=int(d.get("selected_count", 0)),
                    ))
                except Exception:
                    continue

        anchors = packet.get("anchors", [])
        self.anchors = []
        if isinstance(anchors, list):
            for a in anchors[:12]:
                if not isinstance(a, dict):
                    continue
                try:
                    age = a.get("last_seen_age_s", -1.0)
                    rssi = a.get("last_rssi_dbm", -100.0)
                    self.anchors.append(AnchorState(
                        id=str(a.get("id", "")),
                        name=str(a.get("name", "")),
                        ip=str(a.get("ip", "")),
                        x_m=float(a.get("x_m", 0.0)),
                        y_m=float(a.get("y_m", 0.0)),
                        rssi_ref_dbm=float(a.get("rssi_ref_dbm", -35.0)),
                        path_loss_exp=float(a.get("path_loss_exp", 3.0)),
                        last_seen_age_s=-1.0 if age is None else float(age),
                        packet_count=int(a.get("packet_count", 0)),
                        last_sender=str(a.get("last_sender", "")),
                        last_mac=str(a.get("last_mac", "")),
                        last_rssi_dbm=-100.0 if rssi is None else float(rssi),
                    ))
                except Exception:
                    continue

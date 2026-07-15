import json
import math
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Tuple, List

from . import config


def _now() -> float:
    return time.monotonic()


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _mac_norm(mac: str) -> str:
    return str(mac or "").strip().upper()


@dataclass
class AnchorReading:
    rssi: float = -100.0
    csi_len: int = 0
    ts: float = 0.0

    def fresh(self, max_age_s: float) -> bool:
        return self.ts > 0 and (_now() - self.ts) <= max_age_s


@dataclass
class WifiPerson:
    mac: str
    anchors: Dict[str, AnchorReading] = field(default_factory=dict)
    last_seen: float = 0.0
    have_pos: bool = False
    x_m: float = 0.0
    y_m: float = 0.0
    angle_deg: float = 0.0
    distance_m: float = 0.0
    anchor_count: int = 0
    strongest_rssi: float = -100.0
    selected_count: int = 0
    name: str = "Unknown device"
    is_known: bool = False
    is_random_mac: bool = False


class RssiPersonTracker:
    """RSSI/network-person tracker added on top of the existing LD2450 backend.

    It does NOT control GPIO and it does NOT replace RadarReceiver. It only listens
    for UDP packets from Wi-Fi/RSSI anchor nodes and associates the best network MAC
    with the moving LD2450 radar target already produced by the backend server.

    Expected UDP packet from each anchor:
      {"id":"A","mac":"AA:BB:CC:DD:EE:FF","rssi":-55,"csi_amp":[...]}

    Anchor id must be A/B/C by default. The same moving client MAC should be heard
    by multiple anchors. The selected MAC is the Wi-Fi device whose RSSI-estimated
    position is nearest to the current LD2450 radar position.
    """

    def __init__(self):
        self.enabled = bool(getattr(config, "ENABLE_RSSI_PERSON_TRACKING", True))
        self.bind_ip = getattr(config, "RSSI_UDP_BIND_IP", "0.0.0.0")
        self.udp_port = int(getattr(config, "RSSI_UDP_PORT", 4210))
        self.anchor_max_age_s = float(getattr(config, "RSSI_ANCHOR_MAX_AGE_S", 2.0))
        self.device_timeout_s = float(getattr(config, "RSSI_DEVICE_TIMEOUT_S", 20.0))
        self.match_max_distance_m = float(getattr(config, "RSSI_RADAR_MATCH_MAX_DISTANCE_M", 1.25))
        self.prefer_radar_when_fresh = bool(getattr(config, "PERSON_SELECT_PREFER_RADAR", True))
        self.print_packets = bool(getattr(config, "RSSI_PRINT_PACKETS", True))
        self.known_devices = {_mac_norm(k): str(v) for k, v in dict(getattr(config, "KNOWN_WIFI_DEVICES", {})).items()}
        self.ignore_macs = {_mac_norm(m) for m in set(getattr(config, "RSSI_IGNORE_MACS", set()))}
        self.only_known = bool(getattr(config, "RSSI_ONLY_TRACK_KNOWN_DEVICES", False))
        self.anchor_status: Dict[str, Dict[str, Any]] = {}

        self.room_w = float(getattr(config, "ROOM_WIDTH_M", 2.0))
        self.room_h = float(getattr(config, "ROOM_HEIGHT_M", 2.0))
        self.ris_x = float(getattr(config, "RIS_REF_X_M", self.room_w / 2.0))
        self.ris_y = float(getattr(config, "RIS_REF_Y_M", 0.0))
        self.anchors_cfg = dict(getattr(config, "RSSI_ANCHORS", {}))

        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.devices: Dict[str, WifiPerson] = {}
        self.last_radar: Dict[str, Any] = {}

        # Fusion state MUST be initialized before _empty_selection(), because
        # _empty_selection() calls _make_fusion() during __init__.
        # Keep both names for compatibility with older server/GUI patches.
        self.fusion_enabled = bool(getattr(config, "ENABLE_RADAR_RSSI_FUSION", True))
        self.fusion_enable = self.fusion_enabled
        self.fusion_radar_weight_base = float(getattr(config, "FUSION_RADAR_WEIGHT_BASE", 0.75))
        self.fusion_radar_weight_min = float(getattr(config, "FUSION_RADAR_WEIGHT_MIN", 0.60))
        self.fusion_radar_weight_max = float(getattr(config, "FUSION_RADAR_WEIGHT_MAX", 0.95))
        self.fusion_ema_alpha = float(getattr(config, "FUSION_EMA_ALPHA", 0.45))
        self._fused_have = False
        self._fused_x = 0.0
        self._fused_y = 0.0

        self.last_selected: Dict[str, Any] = self._empty_selection("INIT")

    def start(self):
        if not self.enabled:
            print("[RSSI ] person tracker disabled in config")
            return
        if not self.anchors_cfg:
            print("[RSSI ] no anchors configured; tracker disabled")
            self.enabled = False
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._udp_loop, name="rssi_person_udp", daemon=True)
        self.thread.start()
        print(f"[RSSI ] listening for anchor packets on {self.bind_ip}:{self.udp_port}")
        print("[RSSI ] expected packet: {\"id\":\"A\",\"mac\":\"AA:BB:CC:DD:EE:FF\",\"rssi\":-55}")
        print(f"[RSSI ] known device names loaded: {len(self.known_devices)} | only_known={self.only_known}")

    def stop(self):
        self.stop_event.set()

    def update_radar(self, radar_packet: Dict[str, Any]):
        with self.lock:
            self.last_radar = dict(radar_packet or {})
            self._recompute_locked()

    def get_selection(self) -> Dict[str, Any]:
        with self.lock:
            self._expire_old_locked()
            self._recompute_locked()
            return dict(self.last_selected)

    def get_devices(self) -> List[Dict[str, Any]]:
        with self.lock:
            out = []
            for dev in sorted(self.devices.values(), key=lambda d: d.last_seen, reverse=True):
                out.append({
                    "mac": dev.mac,
                    "name": dev.name,
                    "is_known": bool(dev.is_known),
                    "is_random_mac": bool(dev.is_random_mac),
                    "last_seen_age_s": round(max(0.0, _now() - dev.last_seen), 2),
                    "have_pos": bool(dev.have_pos),
                    "x_m": round(dev.x_m, 3),
                    "y_m": round(dev.y_m, 3),
                    "angle_deg": round(dev.angle_deg, 2),
                    "distance_m": round(dev.distance_m, 3),
                    "anchor_count": int(dev.anchor_count),
                    "strongest_rssi_dbm": round(dev.strongest_rssi, 1),
                    "selected_count": int(dev.selected_count),
                    "per_anchor_rssi": {aid: round(ar.rssi, 1) for aid, ar in dev.anchors.items() if ar.fresh(self.anchor_max_age_s)},
                })
            return out

    def get_anchors(self) -> List[Dict[str, Any]]:
        """Return configured anchor positions and whether packets were seen recently."""
        with self.lock:
            now = _now()
            out = []
            for aid, ac in sorted(self.anchors_cfg.items()):
                st = self.anchor_status.get(aid, {})
                age = None if not st.get("last_seen") else round(now - float(st.get("last_seen", now)), 2)
                out.append({
                    "id": aid,
                    "name": str(ac.get("name", f"Anchor {aid}")),
                    "ip": str(ac.get("ip", "")),
                    "x_m": float(ac.get("x_m", 0.0)),
                    "y_m": float(ac.get("y_m", 0.0)),
                    "rssi_ref_dbm": float(ac.get("rssi_ref_dbm", -35.0)),
                    "path_loss_exp": float(ac.get("path_loss_exp", 3.0)),
                    "last_seen_age_s": age,
                    "packet_count": int(st.get("packet_count", 0)),
                    "last_sender": str(st.get("last_sender", "")),
                    "last_mac": str(st.get("last_mac", "")),
                    "last_rssi_dbm": st.get("last_rssi_dbm", None),
                })
            return out

    def handle_udp_payload(self, payload: bytes, sender=None):
        try:
            doc = json.loads(payload.decode("utf-8", errors="replace"))
        except Exception:
            print(f"[RSSI ] bad UDP JSON from {sender}: {payload[:80]!r}")
            return

        # heartbeat packet from anchor, not a client measurement
        if str(doc.get("type", "")).lower() == "heartbeat":
            node = str(doc.get("id", "?")).upper()[:1]
            print(f"[RSSI ] heartbeat anchor={node} from={sender}")
            return

        node_id = str(doc.get("id", "")).upper()[:1]
        if node_id not in self.anchors_cfg:
            return

        mac = _mac_norm(doc.get("mac", ""))
        if len(mac) < 8:
            return
        if mac in self.ignore_macs:
            return
        if self.only_known and mac not in self.known_devices:
            return

        try:
            rssi = float(doc.get("rssi"))
        except Exception:
            return

        with self.lock:
            st = self.anchor_status.setdefault(node_id, {"packet_count": 0})
            st["packet_count"] = int(st.get("packet_count", 0)) + 1
            st["last_seen"] = _now()
            st["last_sender"] = f"{sender[0]}:{sender[1]}" if isinstance(sender, tuple) and len(sender) >= 2 else str(sender)
            st["last_mac"] = mac
            st["last_rssi_dbm"] = round(rssi, 1)

        csi = doc.get("csi_amp") or []
        csi_len = len(csi) if isinstance(csi, list) else 0
        t = _now()

        with self.lock:
            dev = self.devices.get(mac)
            if dev is None:
                name, is_known, is_random = self._device_name(mac)
                dev = WifiPerson(mac=mac, name=name, is_known=is_known, is_random_mac=is_random)
                self.devices[mac] = dev
                print(f"[RSSI ] new network device seen: {mac} -> {name}")
            dev.last_seen = t
            dev.anchors[node_id] = AnchorReading(rssi=rssi, csi_len=csi_len, ts=t)
            if self.print_packets:
                print(f"[RSSI ] anchor={node_id} mac={mac} rssi={rssi:.1f} dBm csi_len={csi_len}")
            self._update_device_position_locked(dev)
            self._expire_old_locked()
            self._recompute_locked()

    def _udp_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.bind_ip, self.udp_port))
            sock.settimeout(0.5)
        except Exception as e:
            print(f"[RSSI ] UDP bind failed on {self.bind_ip}:{self.udp_port}: {e}")
            return
        while not self.stop_event.is_set():
            try:
                payload, sender = sock.recvfrom(8192)
                self.handle_udp_payload(payload, sender)
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    print(f"[RSSI ] UDP error: {e}")
                break
        try:
            sock.close()
        except Exception:
            pass

    def _is_random_mac(self, mac: str) -> bool:
        try:
            first = int(mac.split(":")[0], 16)
            return bool(first & 0x02)
        except Exception:
            return False

    def _device_name(self, mac: str) -> Tuple[str, bool, bool]:
        mac = _mac_norm(mac)
        if mac in self.known_devices:
            return self.known_devices[mac], True, self._is_random_mac(mac)
        if self._is_random_mac(mac):
            return "Unknown / random MAC", False, True
        return "Unknown device", False, False

    def _rssi_to_dist(self, rssi: float, node_id: str) -> float:
        ac = self.anchors_cfg[node_id]
        ref = float(ac.get("rssi_ref_dbm", -35.0))
        ple = float(ac.get("path_loss_exp", 3.0))
        d = 10.0 ** ((ref - rssi) / max(0.1, 10.0 * ple))
        return max(0.10, min(20.0, d))

    def _angle_from_ris(self, x: float, y: float) -> float:
        dx = x - self.ris_x
        dy = max(y - self.ris_y, 0.01)
        return math.degrees(math.atan2(dx, dy))

    def _dist_from_ris(self, x: float, y: float) -> float:
        return math.hypot(x - self.ris_x, y - self.ris_y)

    def _update_device_position_locked(self, dev: WifiPerson):
        t = _now()
        wx = wy = tw = 0.0
        fresh_count = 0
        strongest = -100.0
        for node_id, ac in self.anchors_cfg.items():
            reading = dev.anchors.get(node_id)
            if reading is None or t - reading.ts > self.anchor_max_age_s:
                continue
            fresh_count += 1
            strongest = max(strongest, reading.rssi)
            d = self._rssi_to_dist(reading.rssi, node_id)
            w = 1.0 / (d * d + 1e-6)
            wx += float(ac.get("x_m", 0.0)) * w
            wy += float(ac.get("y_m", 0.0)) * w
            tw += w

        dev.anchor_count = fresh_count
        dev.strongest_rssi = strongest
        if fresh_count <= 0 or tw <= 1e-9:
            dev.have_pos = False
            return
        x = _clamp(wx / tw, 0.0, self.room_w)
        y = _clamp(wy / tw, 0.0, self.room_h)
        # Small EMA to avoid jumping too hard when packets arrive unevenly.
        alpha = 0.35 if dev.have_pos else 1.0
        dev.x_m = alpha * x + (1.0 - alpha) * dev.x_m
        dev.y_m = alpha * y + (1.0 - alpha) * dev.y_m
        dev.angle_deg = self._angle_from_ris(dev.x_m, dev.y_m)
        dev.distance_m = self._dist_from_ris(dev.x_m, dev.y_m)
        dev.have_pos = True

    def _expire_old_locked(self):
        t = _now()
        for mac in list(self.devices.keys()):
            if t - self.devices[mac].last_seen > self.device_timeout_s:
                del self.devices[mac]

    def _radar_xy(self) -> Optional[Tuple[float, float]]:
        r = self.last_radar or {}
        status = str(r.get("status", "")).upper()
        if status.startswith("NO_TARGET") or status.startswith("STALE"):
            return None
        try:
            return float(r.get("x_m", 0.0)), float(r.get("y_m", 0.0))
        except Exception:
            return None

    def _make_fusion(self, mode: str, x: float = 0.0, y: float = 0.0, confidence: float = 0.0,
                     radar_weight: float = 0.0, rssi_weight: float = 0.0, have_pos: bool = False) -> Dict[str, Any]:
        fusion_on = bool(getattr(self, "fusion_enabled", getattr(self, "fusion_enable", True)))
        if have_pos and fusion_on:
            x = _clamp(float(x), 0.0, self.room_w)
            y = _clamp(float(y), 0.0, self.room_h)
            # EMA smoothing so the fused point does not jump when RSSI packets fluctuate.
            if self._fused_have:
                a = _clamp(self.fusion_ema_alpha, 0.0, 1.0)
                x = a * x + (1.0 - a) * self._fused_x
                y = a * y + (1.0 - a) * self._fused_y
            self._fused_x, self._fused_y, self._fused_have = x, y, True
            return {
                "enabled": True,
                "have_pos": True,
                "mode": mode,
                "x_m": round(x, 3),
                "y_m": round(y, 3),
                "angle_deg": round(self._angle_from_ris(x, y), 2),
                "distance_m": round(self._dist_from_ris(x, y), 3),
                "confidence": round(_clamp(confidence, 0.0, 1.0), 3),
                "radar_weight": round(_clamp(radar_weight, 0.0, 1.0), 3),
                "rssi_weight": round(_clamp(rssi_weight, 0.0, 1.0), 3),
            }
        return {
            "enabled": bool(getattr(self, "fusion_enabled", getattr(self, "fusion_enable", True))),
            "have_pos": False,
            "mode": mode,
            "x_m": 0.0,
            "y_m": 0.0,
            "angle_deg": 0.0,
            "distance_m": 0.0,
            "confidence": 0.0,
            "radar_weight": 0.0,
            "rssi_weight": 0.0,
        }

    def _empty_selection(self, reason: str) -> Dict[str, Any]:
        radar_xy = self._radar_xy()
        fusion = self._make_fusion("RADAR_ONLY" if radar_xy is not None else "NO_POSITION",
                                   radar_xy[0] if radar_xy is not None else 0.0,
                                   radar_xy[1] if radar_xy is not None else 0.0,
                                   confidence=0.45 if radar_xy is not None else 0.0,
                                   radar_weight=1.0 if radar_xy is not None else 0.0,
                                   rssi_weight=0.0,
                                   have_pos=radar_xy is not None)
        return {
            "enabled": bool(self.enabled),
            "status": reason,
            "selected": False,
            "mac": "",
            "name": "",
            "source": fusion.get("mode", "NONE"),
            "match_distance_m": None,
            "confidence": float(fusion.get("confidence", 0.0)),
            "wifi": {},
            "radar": dict(self.last_radar or {}),
            "fusion": fusion,
            "device_count": 0,
        }

    def _recompute_locked(self):
        devices = [d for d in self.devices.values() if d.have_pos and (_now() - d.last_seen) <= self.device_timeout_s]
        radar_xy = self._radar_xy()

        if not devices:
            self.last_selected = self._empty_selection("NO_WIFI_DEVICES")
            self.last_selected["device_count"] = len(self.devices)
            return

        chosen = None
        match_dist = None
        source = "WIFI_STRONGEST"
        confidence = 0.35

        if radar_xy is not None:
            rx, ry = radar_xy
            scored = []
            for d in devices:
                dist = math.hypot(d.x_m - rx, d.y_m - ry)
                anchor_bonus = 0.2 * max(0, d.anchor_count - 1)
                score = dist - anchor_bonus
                scored.append((score, dist, d))
            scored.sort(key=lambda item: item[0])
            _, match_dist, chosen = scored[0]
            source = "RADAR_WIFI_MATCH" if match_dist <= self.match_max_distance_m else "RADAR_NEAREST_WIFI_WEAK_MATCH"
            confidence = max(0.0, min(1.0, 1.0 - (match_dist / max(0.1, self.match_max_distance_m))))
            confidence = min(1.0, confidence + 0.15 * max(0, chosen.anchor_count - 1))

            # Dynamic weighted fusion. Strong match allows RSSI to contribute more;
            # weak match lets radar dominate so the position does not jump to a wrong MAC.
            rw = self.fusion_radar_weight_base + 0.20 * (1.0 - confidence)
            rw = _clamp(rw, self.fusion_radar_weight_min, self.fusion_radar_weight_max)
            ww = 1.0 - rw
            fx = rw * rx + ww * chosen.x_m
            fy = rw * ry + ww * chosen.y_m
            fusion_mode = "RADAR_RSSI_FUSED" if source == "RADAR_WIFI_MATCH" else "RADAR_RSSI_FUSED_WEAK"
            fusion = self._make_fusion(fusion_mode, fx, fy, confidence, rw, ww, True)
        else:
            chosen = max(devices, key=lambda d: (d.anchor_count, d.strongest_rssi, d.last_seen))
            match_dist = None
            fusion = self._make_fusion("RSSI_ONLY", chosen.x_m, chosen.y_m, confidence, 0.0, 1.0, True)

        chosen.selected_count += 1
        self.last_selected = {
            "enabled": bool(self.enabled),
            "status": "OK",
            "selected": True,
            "mac": chosen.mac,
            "name": chosen.name,
            "is_known": bool(chosen.is_known),
            "is_random_mac": bool(chosen.is_random_mac),
            "source": source,
            "match_distance_m": round(match_dist, 3) if match_dist is not None else None,
            "confidence": round(confidence, 3),
            "device_count": len(self.devices),
            "wifi": {
                "x_m": round(chosen.x_m, 3),
                "y_m": round(chosen.y_m, 3),
                "angle_deg": round(chosen.angle_deg, 2),
                "distance_m": round(chosen.distance_m, 3),
                "anchor_count": int(chosen.anchor_count),
                "strongest_rssi_dbm": round(chosen.strongest_rssi, 1),
            },
            "radar": dict(self.last_radar or {}),
            "fusion": fusion,
        }

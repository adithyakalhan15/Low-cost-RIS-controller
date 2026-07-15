import math
import time
from dataclasses import dataclass
from typing import Dict, Any, Tuple

import numpy as np

from . import config

try:
    import onnxruntime as ort
except Exception:
    ort = None


@dataclass
class PredictionResult:
    cell_bits: str
    pattern_id: int
    beam_angle_deg: float
    distance_m: float
    snr_db: float
    capacity_mbps: float
    model_status: str
    inference_ms: float


class MLPatternEngine:
    """
    ONNX-based RIS phase pattern selector.

    The uploaded 3D.py used:
        x_tok:  shape (1, N, 8)
        x_flat: shape (1, N*8)

    compare.py also has a shape-aware helper for ONNX inputs.
    This engine keeps that idea, but uses the real 4x6 = 24 element panel.
    If the ONNX model expects 24*8 features, it uses the physical 4x6 geometry.
    If the model expects another shape, it falls back to simple angle features.
    """

    def __init__(self, model_path=None):
        self.model_path = str(model_path or config.MODEL_PATH)
        self.session = None
        self.model_status = "not_loaded"

        self.freq = config.FREQ_HZ
        self.c = config.C_LIGHT
        self.lam = self.c / self.freq
        self.k = 2.0 * np.pi / self.lam
        self.spacing = self.lam / 2.0

        self.rows = config.RIS_ROWS
        self.cols = config.RIS_COLS
        self.n = self.rows * self.cols

        self.p_tx = 10 ** ((20 - 30) / 10)  # 20 dBm -> 0.1 W
        self.bw = 20e6
        self.nf_db = 7
        self.t0 = 290
        self.kb = 1.38e-23
        self.sigma2 = self.kb * self.t0 * self.bw * 10 ** (self.nf_db / 10)
        self.gamma_amp = 1.0

        self.ris_center = np.array(config.RIS_CENTER, dtype=float)
        self.all_pos_m, self.all_pos_lam = self._build_positions()
        self.p_rel = self.all_pos_m - self.ris_center
        self.u_tx = self._unit_vec(config.TX_AZ_DEG, config.TX_EL_DEG)

        self._load_model()

    def _load_model(self):
        if ort is None:
            self.model_status = "onnxruntime_missing"
            print("[ML] onnxruntime not installed. Using fallback pattern generator.")
            return

        try:
            self.session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
            self.model_status = "onnx_loaded"
            print(f"[ML] Loaded ONNX model: {self.model_path}")
            for inp in self.session.get_inputs():
                print(f"[ML] Input: {inp.name} shape={inp.shape} type={inp.type}")
            for out in self.session.get_outputs():
                print(f"[ML] Output: {out.name} shape={out.shape} type={out.type}")

            # Warm-up
            feed = self._build_onnx_input_from_angle(30.0)
            for _ in range(2):
                self.session.run(None, feed)

        except Exception as e:
            self.session = None
            self.model_status = f"model_load_failed: {e}"
            print(f"[ML] Could not load ONNX model: {e}")
            print("[ML] Using fallback pattern generator.")

    def _build_positions(self):
        all_pos_m = np.zeros((self.n, 3), dtype=np.float64)
        all_pos_lam = np.zeros((self.n, 2), dtype=np.float32)

        for r in range(self.rows):
            for c in range(self.cols):
                # 4 rows vertical z, 6 columns horizontal y
                y = (c - (self.cols - 1) / 2.0) * self.spacing
                z = (r - (self.rows - 1) / 2.0) * self.spacing
                i = r * self.cols + c
                all_pos_m[i] = [self.ris_center[0], self.ris_center[1] + y, self.ris_center[2] + z]
                all_pos_lam[i] = [y / self.lam, z / self.lam]

        return all_pos_m, all_pos_lam

    @staticmethod
    def _unit_vec(az_deg, el_deg=0.0):
        az = np.radians(az_deg)
        el = np.radians(el_deg)
        return np.array([
            np.cos(el) * np.cos(az),
            np.cos(el) * np.sin(az),
            np.sin(el)
        ], dtype=float)

    def _channel_from_xy(self, rx_x: float, rx_y: float):
        vec_rx = np.array([rx_x, rx_y, 0.0], dtype=float)
        rx_dist = float(np.linalg.norm(vec_rx))
        if rx_dist < 0.1:
            rx_dist = 0.1

        u_rx = vec_rx / rx_dist
        rx_az_deg = float(np.degrees(np.arctan2(u_rx[1], u_rx[0])))

        phi_el = self.k * (self.p_rel @ (self.u_tx + u_rx))
        a = (self.lam ** 2 / (4 * np.pi) ** 2) / (config.TX_DIST_M * rx_dist)
        phi_c = -self.k * (config.TX_DIST_M + rx_dist)
        h_geom = (a * np.exp(1j * (phi_c + phi_el))).reshape(self.rows, self.cols)

        return h_geom, rx_az_deg, rx_dist

    def _channel_from_angle(self, angle_deg: float, distance_m: float = 3.0):
        rx_x = distance_m * math.cos(math.radians(angle_deg))
        rx_y = distance_m * math.sin(math.radians(angle_deg))
        return self._channel_from_xy(rx_x, rx_y)

    def _features_from_channel(self, h_geom):
        hr = h_geom.real.flatten()
        hi = h_geom.imag.flatten()
        mag = np.sqrt(hr ** 2 + hi ** 2)
        scale = max(float(np.sqrt((mag ** 2).mean())), 1e-30)
        psi = np.arctan2(-hi, hr)
        phase_margin = np.abs(np.abs(np.arctan2(np.sin(psi), np.cos(psi))) - np.pi / 2)

        feats = np.stack([
            hr / scale,
            hi / scale,
            phase_margin,
            np.cos(psi),
            np.sin(psi),
            mag / scale,
            self.all_pos_lam[:, 0],
            self.all_pos_lam[:, 1],
        ], axis=1)

        return feats.astype(np.float32)

    def _build_onnx_input_from_angle(self, angle_deg: float):
        h_geom, _, _ = self._channel_from_angle(angle_deg)
        return self._build_onnx_input(h_geom, angle_deg)

    def _build_onnx_input(self, h_geom, angle_deg):
        if self.session is None:
            return {}

        feats = self._features_from_channel(h_geom)
        x_tok = feats.reshape(1, self.n, 8)
        x_flat = x_tok.reshape(1, self.n * 8)

        ar = np.radians(angle_deg)
        simple = np.array([
            np.sin(ar), np.cos(ar),
            np.sin(2 * ar), np.cos(2 * ar),
            angle_deg / 180.0,
            np.sin(ar) ** 2,
            np.cos(ar) ** 2,
            np.tan(ar / 2 + 1e-6),
        ], dtype=np.float32)

        feed = {}
        for inp in self.session.get_inputs():
            shape = inp.shape
            name = inp.name

            # Direct name support from uploaded 3D.py
            if name == "x_tok":
                feed[name] = x_tok
                continue
            if name == "x_flat":
                feed[name] = x_flat
                continue

            # Shape-aware fallback
            dims = []
            total = 1
            for d in shape[1:]:
                if isinstance(d, int) and d > 0:
                    dims.append(d)
                    total *= d
                else:
                    # Unknown dynamic dimension: prefer N x 8
                    dims.append(self.n if len(dims) == 0 else 8)
                    total *= dims[-1]

            if total == self.n * 8:
                if len(shape) == 3:
                    feed[name] = x_tok
                else:
                    feed[name] = x_flat
            else:
                n = int(total)
                arr = np.tile(simple, (n // len(simple) + 1))[:n]
                feed[name] = arr.reshape([1] + dims).astype(np.float32)

        return feed

    def _normalise_output_to_bits(self, raw_out):
        out = np.asarray(raw_out).flatten().astype(np.float64)

        # Adjust output length to 24 cells
        if len(out) >= self.n:
            out = out[:self.n]
        else:
            out = np.concatenate([out, np.zeros(self.n - len(out))])

        mn = float(out.min())
        mx = float(out.max())
        abs_max = max(abs(mn), abs(mx))

        # Probabilities -> threshold
        if mn >= -0.01 and mx <= 1.01:
            bits = (out >= 0.5).astype(int)
            return "".join(str(int(b)) for b in bits)

        # Logits -> sigmoid -> threshold
        if abs_max > 3.5 and mn < 0:
            probs = 1.0 / (1.0 + np.exp(-np.clip(out, -50, 50)))
            bits = (probs >= 0.5).astype(int)
            return "".join(str(int(b)) for b in bits)

        # Raw phase -> 1-bit decision. Phase near pi means bit=1.
        phases = out % (2 * np.pi)
        bits = (phases >= np.pi / 2).astype(int)
        return "".join(str(int(b)) for b in bits)

    def compute_metrics(self, h_geom, cell_bits: str):
        phases = np.array([np.pi if b == "1" else 0.0 for b in cell_bits], dtype=float)
        h_eff = np.sum(h_geom.flatten() * self.gamma_amp * np.exp(1j * phases))
        pwr_w = self.p_tx * np.abs(h_eff) ** 2

        snr_lin = pwr_w / self.sigma2
        snr_db = float(10 * np.log10(snr_lin + 1e-30))
        cap_mbps = float((self.bw * np.log2(1 + snr_lin)) / 1e6)
        return snr_db, cap_mbps

    def fallback_bits_from_angle(self, angle_deg: float) -> Tuple[str, int]:
        """
        Simple deterministic 4x6 pattern set.
        This keeps the demo alive even if ONNX Runtime fails.
        """
        patterns = [
            "000000000000000000000000",
            "111111000000111111000000",
            "000000111111000000111111",
            "101010101010101010101010",
            "010101010101010101010101",
            "111000111000111000111000",
            "000111000111000111000111",
        ]

        if angle_deg < 15:
            pid = 0
        elif angle_deg < 30:
            pid = 1
        elif angle_deg < 45:
            pid = 2
        elif angle_deg < 60:
            pid = 3
        elif angle_deg < 75:
            pid = 4
        elif angle_deg < 90:
            pid = 5
        else:
            pid = 6

        return patterns[pid], pid

    def predict_from_xy(self, rx_x: float, rx_y: float) -> PredictionResult:
        h_geom, angle_deg, distance_m = self._channel_from_xy(rx_x, rx_y)
        t0 = time.perf_counter()

        if self.session is not None:
            try:
                feed = self._build_onnx_input(h_geom, angle_deg)
                raw_out = self.session.run(None, feed)[0]
                cell_bits = self._normalise_output_to_bits(raw_out)
                pattern_id = int(abs(hash(cell_bits)) % 10000)
                status = "ONNX"
            except Exception as e:
                cell_bits, pattern_id = self.fallback_bits_from_angle(angle_deg)
                status = f"FALLBACK_AFTER_ONNX_ERROR: {e}"
        else:
            cell_bits, pattern_id = self.fallback_bits_from_angle(angle_deg)
            status = self.model_status

        inference_ms = (time.perf_counter() - t0) * 1000.0
        snr_db, cap_mbps = self.compute_metrics(h_geom, cell_bits)

        return PredictionResult(
            cell_bits=cell_bits,
            pattern_id=pattern_id,
            beam_angle_deg=angle_deg,
            distance_m=distance_m,
            snr_db=snr_db,
            capacity_mbps=cap_mbps,
            model_status=status,
            inference_ms=inference_ms,
        )

import time
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from .config import *
from .data_model import TelemetryState
from .network_client import NetworkClient
from .simulator import generate_simulated_packet
from .visualizers import RoomVisualizer2D, RoomVisualizer3D
from .charts import LiveCharts
from shared.protocol import (
    command_set_mode,
    command_apply_pattern,
    command_reset_ris,
    command_emergency_off,
    command_get_status,
    validate_ris_bits,
    physical_to_wire_bits,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class RISMasterTabbedGUI:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(APP_GEOMETRY)
        self.root.minsize(1280, 760)
        self.root.configure(fg_color=C_BG)

        self.running = True
        self.state = TelemetryState()
        self._packet_lock = threading.Lock()
        self._pending_packet = None
        self._last_plot_draw = 0.0
        self._last_3d_draw = 0.0
        self._last_chart_draw = 0.0
        self.pi_ip = ctk.StringVar(value=DEFAULT_PI_IP)
        self.pi_port = ctk.StringVar(value=str(DEFAULT_PI_PORT))
        self.simulation_enabled = ctk.BooleanVar(value=True)
        self.mode = ctk.StringVar(value="AUTO")
        self.manual_pattern_id = ctk.StringVar(value="0")
        self.manual_bits = ctk.StringVar(value="0" * RIS_ELEMENTS)

        self.vars = {key: ctk.StringVar(value="--") for key in [
            "x", "y", "angle", "distance", "velocity", "targets", "radar", "rssi", "snr",
            "throughput", "loss", "ber", "pid", "beam", "ris_state", "bits", "wire_bits", "gpio_wire_bits", "gpio_note", "on_count", "off_count",
            "person_mac", "person_device", "person_source", "person_conf", "person_match", "wifi_pos", "wifi_rssi",
            "radar_pos", "radar_src", "radar_angle", "radar_dist", "radar_vel", "radar_targets",
            "rssi_pos", "rssi_angle", "rssi_dist", "rssi_anchors", "rssi_devices",
            "fused_pos", "fused_angle", "fused_dist", "fused_mode", "fused_weights", "fused_status", "fused_note", "anchor_summary"
        ]}

        self.network = NetworkClient(self._on_network_packet, self.log, self._on_network_disconnect)
        self.ris_cells = []
        self._build_layout()
        self._refresh_ui_from_state(force_plots=True)
        self._ui_render_loop()
        self._simulation_loop()

    def _build_layout(self):
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self._build_header()
        self._build_main_tabs()

    def _build_header(self):
        header = ctk.CTkFrame(self.root, height=76, fg_color=C_PANEL, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="RIS SMART CONTROLLER", font=ctk.CTkFont(size=25, weight="bold"), text_color=C_TEXT).grid(row=0, column=0, padx=22, pady=(13, 0), sticky="w")
        ctk.CTkLabel(header, text="Tabbed Master Dashboard • Actual RIS panel: 4 × 6 tiles • Manual click control enabled", font=ctk.CTkFont(size=13), text_color=C_MUTED).grid(row=1, column=0, padx=24, pady=(0, 10), sticky="w")
        self.mode_pill = ctk.CTkLabel(header, text="AUTO", width=120, height=34, corner_radius=18, fg_color=C_GREEN, text_color=C_ON_TEXT, font=ctk.CTkFont(size=13, weight="bold"))
        self.mode_pill.grid(row=0, column=1, rowspan=2, padx=(8, 6), sticky="e")
        self.status_pill = ctk.CTkLabel(header, text="SIMULATION", width=155, height=34, corner_radius=18, fg_color=C_YELLOW, text_color="#111827", font=ctk.CTkFont(size=13, weight="bold"))
        self.status_pill.grid(row=0, column=2, rowspan=2, padx=(6, 22), sticky="e")

    def _build_main_tabs(self):
        self.tabs = ctk.CTkTabview(
            self.root,
            fg_color=C_PANEL,
            segmented_button_fg_color=C_CARD,
            segmented_button_selected_color=C_BLUE,
            segmented_button_selected_hover_color="#2563EB",
            segmented_button_unselected_color=C_CARD,
            segmented_button_unselected_hover_color=C_CARD_2,
            corner_radius=18,
            border_width=1,
            border_color=C_BORDER,
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=14)

        self.tab_overview = self.tabs.add("Overview")
        self.tab_ris = self.tabs.add("RIS 4×6 Tiles")
        self.tab_position = self.tabs.add("Position")
        self.tab_visual = self.tabs.add("2D / 3D Visual")
        self.tab_channel = self.tabs.add("Channel")
        self.tab_logs = self.tabs.add("Logs")

        self._build_overview_tab()
        self._build_position_tab()
        self._build_ris_tab()
        self._build_visual_tab()
        self._build_channel_tab()
        self._build_logs_tab()

    def _card(self, parent, title=None):
        card = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=16, border_width=1, border_color=C_BORDER)
        if title:
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=C_TEXT).pack(anchor="w", padx=16, pady=(14, 8))
        return card

    def _value_row(self, parent, label, var, unit=""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(row, text=label, text_color=C_MUTED, width=130, anchor="w").pack(side="left")
        ctk.CTkLabel(row, textvariable=var, text_color=C_TEXT, font=ctk.CTkFont(size=14, weight="bold"), anchor="e").pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(row, text=unit, text_color=C_MUTED, width=44, anchor="e").pack(side="right")

    def _build_overview_tab(self):
        t = self.tab_overview
        t.grid_rowconfigure(1, weight=1)
        t.grid_rowconfigure(3, weight=1)
        t.grid_columnconfigure(0, weight=1)
        t.grid_columnconfigure(1, weight=1)
        t.grid_columnconfigure(2, weight=1)

        kpi = ctk.CTkFrame(t, fg_color="transparent")
        kpi.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(12, 8))
        kpi.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.kpi_cards = {}
        for i, (key, title, unit) in enumerate([
            ("rssi", "RSSI", "dBm"),
            ("snr", "SNR", "dB"),
            ("throughput", "Throughput", "Mbps"),
            ("beam", "Beam", "deg"),
        ]):
            card = self._card(kpi)
            card.grid(row=0, column=i, sticky="ew", padx=6)
            ctk.CTkLabel(card, text=title, text_color=C_MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(14, 0))
            ctk.CTkLabel(card, textvariable=self.vars[key], text_color=C_TEXT, font=ctk.CTkFont(size=29, weight="bold")).pack(anchor="w", padx=16, pady=(0, 0))
            ctk.CTkLabel(card, text=unit, text_color=C_MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0, 14))
            self.kpi_cards[key] = card

        left = self._card(t, "Connection & Mode")
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=8)
        ctk.CTkEntry(left, textvariable=self.pi_ip, placeholder_text="Raspberry Pi IP", height=38, fg_color=C_PANEL_2, border_color=C_BORDER).pack(fill="x", padx=14, pady=5)
        ctk.CTkEntry(left, textvariable=self.pi_port, placeholder_text="Port", height=38, fg_color=C_PANEL_2, border_color=C_BORDER).pack(fill="x", padx=14, pady=5)
        ctk.CTkButton(left, text="Connect to Pi", height=38, fg_color=C_BLUE, command=self.connect_to_pi).pack(fill="x", padx=14, pady=(10, 5))
        ctk.CTkButton(left, text="Disconnect", height=36, fg_color="#334155", hover_color="#475569", command=self.disconnect_from_pi).pack(fill="x", padx=14, pady=5)
        ctk.CTkSwitch(left, text="Simulation Mode", variable=self.simulation_enabled, progress_color=C_YELLOW, text_color=C_TEXT).pack(anchor="w", padx=14, pady=(10, 16))
        ctk.CTkSegmentedButton(left, values=["AUTO", "MANUAL"], variable=self.mode, command=self._mode_segment_changed, selected_color=C_GREEN).pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(left, text="Reset RIS", height=38, fg_color=C_YELLOW, text_color="#111827", hover_color="#D97706", command=self.reset_ris).pack(fill="x", padx=14, pady=5)
        ctk.CTkButton(left, text="EMERGENCY OFF", height=42, fg_color=C_RED, hover_color="#DC2626", command=self.emergency_off).pack(fill="x", padx=14, pady=(5, 16))

        mid = self._card(t, "Radar / Matched Person")
        mid.grid(row=1, column=1, sticky="nsew", padx=6, pady=8)
        for label, key, unit in [
            ("X position", "x", "m"), ("Y position", "y", "m"), ("Angle", "angle", "°"),
            ("Distance", "distance", "m"), ("Velocity", "velocity", "m/s"), ("Targets", "targets", ""), ("Radar", "radar", ""),
            ("RSSI position", "wifi_pos", "m"), ("RSSI level", "wifi_rssi", "dBm"),
            ("Selected device", "person_device", ""), ("Selected MAC", "person_mac", ""), ("Person source", "person_source", ""), ("Match", "person_match", "m"), ("Confidence", "person_conf", "")
        ]:
            self._value_row(mid, label, self.vars[key], unit)

        right = self._card(t, "RIS / Channel Summary")
        right.grid(row=1, column=2, sticky="nsew", padx=(6, 10), pady=8)
        for label, key, unit in [
            ("Pattern ID", "pid", ""), ("Beam angle", "beam", "°"), ("RIS state", "ris_state", ""),
            ("ON cells", "on_count", ""), ("OFF cells", "off_count", ""),
            ("Packet loss", "loss", "%"), ("BER", "ber", "")
        ]:
            self._value_row(right, label, self.vars[key], unit)
        ctk.CTkButton(right, text="Request Status", height=36, fg_color=C_CYAN, command=self.request_status).pack(fill="x", padx=14, pady=(12, 14))

    def _build_position_tab(self):
        t = self.tab_position
        t.grid_columnconfigure(0, weight=1)
        t.grid_columnconfigure(1, weight=1)
        t.grid_columnconfigure(2, weight=1)
        t.grid_rowconfigure(1, weight=1)
        t.grid_rowconfigure(3, weight=1)
        t.grid_rowconfigure(3, weight=1)

        title = ctk.CTkFrame(t, fg_color="transparent")
        title.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(12, 4))
        ctk.CTkLabel(title, text="Position Reading — LD2450 Radar + RSSI Wi‑Fi Anchors", font=ctk.CTkFont(size=22, weight="bold"), text_color=C_TEXT).pack(anchor="w")
        ctk.CTkLabel(title, text="Radar gives moving target position. RSSI anchors estimate which connected Wi‑Fi device/person matches that moving target.", text_color=C_MUTED, font=ctk.CTkFont(size=13)).pack(anchor="w", pady=(2, 0))

        radar_card = self._card(t, "LD2450 Radar Position")
        radar_card.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=8)
        for label, key, unit in [
            ("Radar X,Y", "radar_pos", "m"),
            ("Angle", "radar_angle", "°"),
            ("Distance", "radar_dist", "m"),
            ("Velocity", "radar_vel", "m/s"),
            ("Targets", "radar_targets", ""),
            ("Source", "radar_src", ""),
            ("Status", "radar", ""),
        ]:
            self._value_row(radar_card, label, self.vars[key], unit)

        rssi_card = self._card(t, "RSSI / Network Device Position")
        rssi_card.grid(row=1, column=1, sticky="nsew", padx=6, pady=8)
        for label, key, unit in [
            ("Selected device", "person_device", ""),
            ("Selected MAC", "person_mac", ""),
            ("RSSI X,Y", "rssi_pos", "m"),
            ("RSSI angle", "rssi_angle", "°"),
            ("RSSI distance", "rssi_dist", "m"),
            ("Strongest RSSI", "wifi_rssi", "dBm"),
            ("Anchors heard", "rssi_anchors", ""),
            ("Devices seen", "rssi_devices", ""),
        ]:
            self._value_row(rssi_card, label, self.vars[key], unit)

        fused_card = self._card(t, "Matched / Selected Person")
        fused_card.grid(row=1, column=2, sticky="nsew", padx=(6, 10), pady=8)
        for label, key, unit in [
            ("Fused X,Y", "fused_pos", "m"),
            ("Fused angle", "fused_angle", "°"),
            ("Fused distance", "fused_dist", "m"),
            ("Fusion mode", "fused_mode", ""),
            ("Radar/RSSI weight", "fused_weights", ""),
            ("Match confidence", "person_conf", ""),
            ("Match distance", "person_match", "m"),
            ("Decision note", "fused_note", ""),
        ]:
            self._value_row(fused_card, label, self.vars[key], unit)

        anchor_card = self._card(t, "Configured ESP32 RSSI Anchor Positions")
        anchor_card.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(4, 6))
        self.anchors_text = ctk.CTkTextbox(anchor_card, height=92, fg_color=C_PANEL_2, text_color=C_TEXT, border_color=C_BORDER, border_width=1)
        self.anchors_text.pack(fill="x", expand=False, padx=14, pady=(0, 14))
        self.anchors_text.insert("1.0", "Anchor positions will appear here after Pi telemetry arrives.\n")
        self.anchors_text.configure(state="disabled")

        dev_card = self._card(t, "Live Network Devices Heard by ESP32 Anchors")
        dev_card.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=10, pady=(4, 12))
        self.devices_text = ctk.CTkTextbox(dev_card, height=210, fg_color=C_PANEL_2, text_color=C_TEXT, border_color=C_BORDER, border_width=1)
        self.devices_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.devices_text.insert("1.0", "No RSSI packets yet. ESP32 anchors should send UDP JSON to Pi port 4210.\n")
        self.devices_text.configure(state="disabled")

    def _build_ris_tab(self):
        t = self.tab_ris
        t.grid_columnconfigure(0, weight=1)
        t.grid_columnconfigure(1, weight=2)
        t.grid_rowconfigure(0, weight=1)

        controls = self._card(t, "Manual 4×6 RIS Control")
        controls.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=12)
        ctk.CTkLabel(controls, text="Click individual cells to toggle ON/OFF. The visible panel is 24 real cells, but the transmitted driver stream is 32 bits: each 6-cell row plus 2 dummy bits.", text_color=C_MUTED, wraplength=370, justify="left").pack(anchor="w", padx=16, pady=(0, 12))
        ctk.CTkEntry(controls, textvariable=self.manual_pattern_id, placeholder_text="Pattern ID", height=38, fg_color=C_PANEL_2, border_color=C_BORDER).pack(fill="x", padx=16, pady=5)
        self.bits_entry = ctk.CTkEntry(controls, textvariable=self.manual_bits, placeholder_text="24-bit physical cell pattern", height=40, fg_color=C_PANEL_2, border_color=C_BORDER, font=ctk.CTkFont(family="Consolas", size=13))
        self.bits_entry.pack(fill="x", padx=16, pady=5)
        self.bits_entry.bind("<KeyRelease>", lambda event: self._manual_bits_entry_changed())

        ctk.CTkLabel(controls, text="GUI/requested 32-bit stream, 6 real bits + 2 dummy bits per row", text_color=C_MUTED, wraplength=370, justify="left").pack(anchor="w", padx=16, pady=(10, 2))
        ctk.CTkLabel(controls, textvariable=self.vars["wire_bits"], text_color=C_CYAN, fg_color="#050A12", corner_radius=10, font=ctk.CTkFont(family="Consolas", size=13), anchor="w").pack(fill="x", padx=16, pady=(0, 5), ipady=8)
        ctk.CTkLabel(controls, text="Actual 32-bit GPIO stream written by Raspberry Pi", text_color=C_MUTED, wraplength=370, justify="left").pack(anchor="w", padx=16, pady=(8, 2))
        ctk.CTkLabel(controls, textvariable=self.vars["gpio_wire_bits"], text_color=C_YELLOW, fg_color="#050A12", corner_radius=10, font=ctk.CTkFont(family="Consolas", size=13), anchor="w").pack(fill="x", padx=16, pady=(0, 2), ipady=8)
        ctk.CTkLabel(controls, textvariable=self.vars["gpio_note"], text_color=C_MUTED, wraplength=370, justify="left").pack(anchor="w", padx=16, pady=(0, 5))

        ctk.CTkButton(controls, text="Set MANUAL Mode", height=38, fg_color=C_PURPLE, hover_color="#9333EA", command=self.set_manual_mode).pack(fill="x", padx=16, pady=(12, 5))
        ctk.CTkButton(controls, text="Apply Clicked Pattern", height=42, fg_color=C_GREEN, hover_color="#16A34A", text_color=C_ON_TEXT, command=self.apply_manual_pattern).pack(fill="x", padx=16, pady=5)

        quick = ctk.CTkFrame(controls, fg_color="transparent")
        quick.pack(fill="x", padx=16, pady=(12, 5))
        quick.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(quick, text="All OFF", height=34, fg_color="#334155", command=lambda: self.set_manual_bits("0" * RIS_ELEMENTS, auto_apply=True)).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=4)
        ctk.CTkButton(quick, text="All ON", height=34, fg_color="#166534", command=lambda: self.set_manual_bits("1" * RIS_ELEMENTS, auto_apply=True)).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=4)
        ctk.CTkButton(quick, text="Checker", height=34, fg_color="#0E7490", command=lambda: self.set_manual_bits("10" * (RIS_ELEMENTS // 2), auto_apply=True)).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=4)
        ctk.CTkButton(quick, text="Inverse", height=34, fg_color="#7C3AED", command=lambda: self.invert_manual_bits(auto_apply=True)).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=4)
        ctk.CTkButton(controls, text="Reset RIS", height=38, fg_color=C_YELLOW, text_color="#111827", command=self.reset_ris).pack(fill="x", padx=16, pady=(12, 5))
        ctk.CTkButton(controls, text="EMERGENCY OFF", height=40, fg_color=C_RED, command=self.emergency_off).pack(fill="x", padx=16, pady=(5, 16))

        grid_card = self._card(t, "RIS Tile Map — 4 Rows × 6 Columns")
        grid_card.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=12)
        grid_card.grid_rowconfigure(1, weight=1)
        grid_card.grid_columnconfigure(0, weight=1)
        legend = ctk.CTkFrame(grid_card, fg_color="transparent")
        legend.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkLabel(legend, text="ON", width=60, height=26, corner_radius=13, fg_color=C_GREEN, text_color=C_ON_TEXT, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(legend, text="OFF", width=60, height=26, corner_radius=13, fg_color=C_OFF, text_color=C_MUTED, font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(legend, text="Cell bits: row-major 24-bit view | TX stream appends 00 after each row", text_color=C_MUTED).pack(side="right")

        grid = ctk.CTkFrame(grid_card, fg_color="#08111F", corner_radius=18, border_width=1, border_color=C_BORDER)
        grid.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        for r in range(RIS_ROWS):
            grid.grid_rowconfigure(r, weight=1)
        for c in range(RIS_COLS):
            grid.grid_columnconfigure(c, weight=1)

        self.ris_cells = []
        idx = 0
        for r in range(RIS_ROWS):
            row = []
            for c in range(RIS_COLS):
                btn = ctk.CTkButton(
                    grid,
                    text="0",
                    font=ctk.CTkFont(size=28, weight="bold"),
                    fg_color=C_OFF,
                    hover_color="#334155",
                    text_color=C_MUTED,
                    corner_radius=16,
                    border_width=1,
                    border_color="#334155",
                    command=lambda i=idx: self.toggle_cell(i),
                )
                btn.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)
                row.append(btn)
                idx += 1
            self.ris_cells.append(row)

    def _build_visual_tab(self):
        t = self.tab_visual
        t.grid_columnconfigure(0, weight=1)
        t.grid_columnconfigure(1, weight=1)
        t.grid_rowconfigure(0, weight=1)
        left = self._card(t, "2D Beam Map")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=12)
        self.visualizer2d = RoomVisualizer2D(left)
        self.visualizer2d.widget.pack(fill="both", expand=True, padx=10, pady=10)

        right = self._card(t, "3D Scene")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=12)
        self.visualizer3d = RoomVisualizer3D(right)
        self.visualizer3d.widget.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_channel_tab(self):
        t = self.tab_channel
        t.grid_columnconfigure(0, weight=2)
        t.grid_columnconfigure(1, weight=1)
        t.grid_rowconfigure(0, weight=1)
        chart_card = self._card(t, "Channel Trends")
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=12)
        self.charts = LiveCharts(chart_card)
        self.charts.widget.pack(fill="both", expand=True, padx=10, pady=10)

        values = self._card(t, "Live Channel Values")
        values.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=12)
        for label, key, unit in [
            ("RSSI", "rssi", "dBm"), ("SNR", "snr", "dB"), ("Throughput", "throughput", "Mbps"),
            ("Packet loss", "loss", "%"), ("BER", "ber", ""), ("Beam angle", "beam", "°"), ("Pattern ID", "pid", "")
        ]:
            self._value_row(values, label, self.vars[key], unit)

    def _build_logs_tab(self):
        t = self.tab_logs
        t.grid_rowconfigure(0, weight=1)
        t.grid_columnconfigure(0, weight=1)
        box_card = self._card(t, "System Logs")
        box_card.grid(row=0, column=0, sticky="nsew", padx=10, pady=12)
        self.log_box = ctk.CTkTextbox(box_card, fg_color="#050A12", text_color=C_TEXT, border_width=1, border_color=C_BORDER, corner_radius=14, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.pack(fill="both", expand=True, padx=12, pady=12)
        self.log("Dashboard started. Simulation mode is ON.")

    def log(self, message):
        if not hasattr(self, "log_box"):
            return
        ts = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{ts}] {message}\n")
        self.log_box.see("end")

    def _safe_int(self, value, default=0):
        try:
            text = str(value).strip()
            if text == "":
                return default
            return int(float(text))
        except Exception:
            return default

    def connect_to_pi(self):
        try:
            self.network.connect(self.pi_ip.get().strip(), self._safe_int(self.pi_port.get(), DEFAULT_PI_PORT))
            self.simulation_enabled.set(False)
            self._set_status("CONNECTED")
            self.log(f"Connected to Raspberry Pi at {self.pi_ip.get()}:{self.pi_port.get()}")
        except Exception as exc:
            self._set_status("FAILED")
            self.log(f"Connection failed: {exc}")
            messagebox.showerror("Connection Failed", str(exc))

    def disconnect_from_pi(self):
        self.network.disconnect()
        self._set_status("DISCONNECTED" if not self.simulation_enabled.get() else "SIMULATION")
        self.log("Disconnected from Raspberry Pi.")

    def _on_network_packet(self, packet):
        # Network thread may receive packets faster than Tkinter can render.
        # Keep only the newest packet; the UI render loop consumes it at a safe rate.
        with self._packet_lock:
            self._pending_packet = packet

    def _on_network_disconnect(self):
        self.root.after(0, lambda: (self._set_status("DISCONNECTED"), self.log("Raspberry Pi connection closed.")))

    def update_from_packet(self, packet, render=True):
        try:
            ptype = packet.get("type")
            if ptype == "ack":
                self.log(f"ACK from Pi: {packet.get('message', 'OK')}")
                return
            if ptype == "error":
                self.log(f"ERROR from Pi: {packet.get('message', packet)}")
                messagebox.showerror("Pi Server Error", str(packet.get("message", packet)))
                return
            if ptype not in (None, "telemetry"):
                self.log(f"Ignored non-telemetry packet: {packet}")
                return
            self.state.update_from_packet(packet)
            self.mode.set(self.state.system.mode)
            if render:
                self._refresh_ui_from_state()
        except Exception as exc:
            self.log(f"Telemetry update failed: {exc}")

    def _refresh_ui_from_state(self, force_plots=False):
        s = self.state
        values = {
            "x": f"{s.user.x_m:.2f}", "y": f"{s.user.y_m:.2f}", "angle": f"{s.user.angle_deg:.1f}",
            "distance": f"{s.user.distance_m:.2f}", "velocity": f"{s.user.velocity_mps:.2f}",
            "targets": str(s.radar.target_count), "radar": s.radar.status,
            "rssi": f"{s.channel.rssi_dbm:.1f}", "snr": f"{s.channel.snr_db:.1f}",
            "throughput": f"{s.channel.throughput_mbps:.2f}", "loss": f"{s.channel.packet_loss_percent:.2f}",
            "ber": f"{s.channel.ber:.6f}", "pid": str(s.ris.pattern_id), "beam": f"{s.ris.beam_angle_deg:.1f}",
            "ris_state": s.ris.state, "bits": s.ris.bits, "wire_bits": s.ris.wire_bits, "gpio_wire_bits": s.ris.gpio_wire_bits, "gpio_note": "GPIO is inverted from GUI bits" if getattr(s.ris, "gpio_inverted", False) else "GPIO matches GUI bits", "on_count": str(s.ris.bits.count("1")), "off_count": str(s.ris.bits.count("0")),
            "person_mac": s.person.mac if s.person.selected else "--",
            "person_device": s.person.name if s.person.selected else "--",
            "person_source": s.person.source,
            "person_conf": f"{s.person.confidence:.2f}",
            "person_match": f"{s.person.match_distance_m:.2f}",
            "wifi_pos": f"{s.person.wifi_x_m:.2f},{s.person.wifi_y_m:.2f}",
            "wifi_rssi": f"{s.person.wifi_rssi_dbm:.1f}",
            "radar_pos": f"{s.user.x_m:.2f}, {s.user.y_m:.2f}",
            "radar_src": s.user.source,
            "radar_angle": f"{s.user.angle_deg:.1f}",
            "radar_dist": f"{s.user.distance_m:.2f}",
            "radar_vel": f"{s.user.velocity_mps:.2f}",
            "radar_targets": str(s.radar.target_count),
            "rssi_pos": f"{s.person.wifi_x_m:.2f}, {s.person.wifi_y_m:.2f}" if s.person.selected else "--",
            "rssi_angle": f"{s.person.wifi_angle_deg:.1f}" if s.person.selected else "--",
            "rssi_dist": f"{getattr(s.person, 'wifi_distance_m', 0.0):.2f}" if hasattr(s.person, 'wifi_distance_m') and s.person.selected else "--",
            "rssi_anchors": str(s.person.anchor_count),
            "rssi_devices": str(s.person.device_count),
            "fused_pos": f"{s.person.fused_x_m:.2f}, {s.person.fused_y_m:.2f}" if s.person.fused_have_pos else "--",
            "fused_angle": f"{s.person.fused_angle_deg:.1f}" if s.person.fused_have_pos else "--",
            "fused_dist": f"{s.person.fused_distance_m:.2f}" if s.person.fused_have_pos else "--",
            "fused_mode": s.person.fused_mode,
            "fused_weights": f"R {s.person.fused_radar_weight:.2f} / WiFi {s.person.fused_rssi_weight:.2f}" if s.person.fused_have_pos else "--",
            "fused_status": s.person.status,
            "fused_note": "True fused radar + RSSI position" if s.person.fused_mode == "RADAR_RSSI_FUSED" else ("Weak fusion: radar dominates" if "WEAK" in s.person.fused_mode else s.person.fused_mode),
        }
        for key, value in values.items():
            self.vars[key].set(value)
        if hasattr(self, "devices_text"):
            self._update_devices_text()
        if hasattr(self, "anchors_text"):
            self._update_anchors_text()
        # Do NOT overwrite the user's typed/clicked manual bits just because live
        # telemetry arrived. That was the main GUI bug: while connected to the Pi,
        # telemetry could replace the pattern before/after the user pressed Apply.
        self.manual_pattern_id.set(str(s.ris.pattern_id))
        if self.mode.get() == "AUTO":
            self.manual_bits.set(s.ris.bits)
        self._update_ris_grid(self.manual_bits.get() if self.mode.get() == "MANUAL" else s.ris.bits)
        self._update_state_colors()

        # Heavy Matplotlib redraws are throttled and only refreshed on the relevant tab.
        # This prevents Tkinter from becoming messy/freezing when telemetry arrives quickly.
        active_tab = self.tabs.get() if hasattr(self, "tabs") else "Overview"
        now = time.monotonic()

        if force_plots or (active_tab == "2D / 3D Visual" and now - self._last_plot_draw >= 0.25):
            self.visualizer2d.draw(s)
            self._last_plot_draw = now

        if force_plots or (active_tab == "2D / 3D Visual" and now - self._last_3d_draw >= 1.00):
            self.visualizer3d.draw(s)
            self._last_3d_draw = now

        if force_plots or (active_tab == "Channel" and now - self._last_chart_draw >= 0.35):
            self.charts.update(s)
            self._last_chart_draw = now

    def _update_anchors_text(self):
        lines = []
        s = self.state
        if not getattr(s, "anchors", []):
            lines.append("No anchor config received yet. Check Raspberry Pi config.RSSI_ANCHORS.")
        else:
            lines.append("ID  name        x(m)  y(m)  live  age(s)  packets  last_rssi  last_mac")
            lines.append("-" * 96)
            for a in s.anchors:
                live = a.last_seen_age_s >= 0 and a.last_seen_age_s <= 5.0
                age = "--" if a.last_seen_age_s < 0 else f"{a.last_seen_age_s:5.1f}"
                last_rssi = "--" if a.last_seen_age_s < 0 else f"{a.last_rssi_dbm:7.1f}"
                lines.append(
                    f"{a.id:2s}  {a.name[:10]:10s}  {a.x_m:4.2f}  {a.y_m:4.2f}  "
                    f"{'YES' if live else 'NO ':4s}  {age}  {a.packet_count:7d}  {last_rssi:>9s}  {a.last_mac[:19]}"
                )
        self.anchors_text.configure(state="normal")
        self.anchors_text.delete("1.0", "end")
        self.anchors_text.insert("1.0", "\n".join(lines))
        self.anchors_text.configure(state="disabled")

    def _update_devices_text(self):
        lines = []
        s = self.state
        if not s.network_devices:
            lines.append("No live Wi‑Fi/RSSI devices yet. Check ESP32 anchors, Pi UDP port 4210, and phone private MAC setting.")
            lines.append("Tip: put your phone MAC in Raspberry Pi config.KNOWN_WIFI_DEVICES to show a real name.")
        else:
            lines.append("device/name           MAC address          age  x(m)  y(m)  anchors  RSSI  A/B/C RSSI     selected")
            lines.append("-" * 116)
            selected_mac = (s.person.mac or "").upper()
            for d in s.network_devices:
                selected = "YES" if d.mac.upper() == selected_mac and s.person.selected else ""
                pos_x = f"{d.x_m:4.2f}" if d.have_pos else " -- "
                pos_y = f"{d.y_m:4.2f}" if d.have_pos else " -- "
                name = d.name or "Unknown device"
                if d.is_random_mac and not d.is_known:
                    name = "Unknown/random"
                rssi_parts = []
                for aid in ("A", "B", "C", "D"):
                    if aid in d.per_anchor_rssi:
                        try:
                            rssi_parts.append(f"{aid}:{float(d.per_anchor_rssi[aid]):.0f}")
                        except Exception:
                            pass
                rssi_text = " ".join(rssi_parts) if rssi_parts else "--"
                lines.append(
                    f"{name[:20]:20s} {d.mac:19s} {d.last_seen_age_s:4.1f}  {pos_x}  {pos_y}  "
                    f"{d.anchor_count:2d}      {d.strongest_rssi_dbm:5.1f}  {rssi_text[:15]:15s}  {selected}"
                )
        self.devices_text.configure(state="normal")
        self.devices_text.delete("1.0", "end")
        self.devices_text.insert("1.0", "\n".join(lines))
        self.devices_text.configure(state="disabled")

    def _update_state_colors(self):
        s = self.state
        if s.system.mode == "AUTO":
            self.mode_pill.configure(text="AUTO", fg_color=C_GREEN, text_color=C_ON_TEXT)
        else:
            self.mode_pill.configure(text="MANUAL", fg_color=C_PURPLE, text_color="#F5D0FE")

        if self.network.connected:
            self._set_status("CONNECTED")
        elif self.simulation_enabled.get():
            self._set_status("SIMULATION")

        rssi_color = C_GREEN if s.channel.rssi_dbm > -55 else C_YELLOW if s.channel.rssi_dbm > -68 else C_RED
        snr_color = C_GREEN if s.channel.snr_db > 18 else C_YELLOW if s.channel.snr_db > 9 else C_RED
        thr_color = C_GREEN if s.channel.throughput_mbps > 25 else C_YELLOW if s.channel.throughput_mbps > 10 else C_RED
        self.kpi_cards["rssi"].configure(border_color=rssi_color)
        self.kpi_cards["snr"].configure(border_color=snr_color)
        self.kpi_cards["throughput"].configure(border_color=thr_color)
        self.kpi_cards["beam"].configure(border_color=C_ACCENT)

    def _set_status(self, text):
        colors = {
            "CONNECTED": (C_GREEN, C_ON_TEXT),
            "SIMULATION": (C_YELLOW, "#111827"),
            "FAILED": (C_RED, "#FEE2E2"),
            "DISCONNECTED": ("#334155", C_TEXT),
        }
        fg, tc = colors.get(text, ("#334155", C_TEXT))
        self.status_pill.configure(text=text, fg_color=fg, text_color=tc)

    def _update_ris_grid(self, bits):
        bits = bits[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
        for i, bit in enumerate(bits):
            r, c = divmod(i, RIS_COLS)
            self.ris_cells[r][c].configure(
                text=bit,
                fg_color=C_GREEN if bit == "1" else C_OFF,
                hover_color="#16A34A" if bit == "1" else "#334155",
                text_color=C_ON_TEXT if bit == "1" else C_MUTED,
                border_color="#86EFAC" if bit == "1" else "#334155",
            )

    def _manual_bits_entry_changed(self):
        bits = self.manual_bits.get().strip()
        filtered = "".join(ch for ch in bits if ch in "01")[:RIS_ELEMENTS]
        if filtered != bits:
            self.manual_bits.set(filtered)
        physical_bits = filtered.ljust(RIS_ELEMENTS, "0")
        self._update_ris_grid(physical_bits)
        self.vars["bits"].set(physical_bits)
        wire = physical_to_wire_bits(physical_bits)
        self.vars["wire_bits"].set(wire)
        self.vars["gpio_wire_bits"].set("".join("1" if b == "0" else "0" for b in wire))
        self.vars["gpio_note"].set("Local estimate: GPIO stream is inverted")
        self.vars["on_count"].set(str(physical_bits.count("1")))
        self.vars["off_count"].set(str(physical_bits.count("0")))

    def toggle_cell(self, index: int):
        bits = self.manual_bits.get().strip()[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
        as_list = list(bits)
        as_list[index] = "0" if as_list[index] == "1" else "1"
        new_bits = "".join(as_list)
        self.mode.set("MANUAL")
        self.state.system.mode = "MANUAL"
        self.manual_bits.set(new_bits)
        self.state.ris.bits = new_bits
        self.state.ris.wire_bits = physical_to_wire_bits(new_bits)
        self.vars["wire_bits"].set(self.state.ris.wire_bits)
        self.vars["gpio_wire_bits"].set("".join("1" if b == "0" else "0" for b in self.state.ris.wire_bits))
        self.vars["gpio_note"].set("Local estimate: GPIO stream is inverted")
        self.state.ris.state = "LOCAL_EDITING"
        self._update_ris_grid(new_bits)
        self._update_state_colors()
        # IMPORTANT: clicking a cell now immediately writes the pattern to the Pi GPIO,
        # instead of only changing the GUI. This avoids the common confusion where
        # the GUI display changes but DATA/CLOCK/LATCH never pulse.
        self.apply_manual_pattern()

    def set_manual_bits(self, bits: str, auto_apply: bool = False):
        bits = bits[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
        self.mode.set("MANUAL")
        self.state.system.mode = "MANUAL"
        self.manual_bits.set(bits)
        self.state.ris.bits = bits
        self.state.ris.wire_bits = physical_to_wire_bits(bits)
        self.vars["wire_bits"].set(self.state.ris.wire_bits)
        self.vars["gpio_wire_bits"].set("".join("1" if b == "0" else "0" for b in self.state.ris.wire_bits))
        self.vars["gpio_note"].set("Local estimate: GPIO stream is inverted")
        self.state.ris.state = "LOCAL_EDITING"
        self._update_ris_grid(bits)
        self._refresh_ui_from_state()
        if auto_apply:
            self.apply_manual_pattern()

    def invert_manual_bits(self, auto_apply: bool = False):
        bits = self.manual_bits.get().strip()[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
        self.set_manual_bits("".join("0" if b == "1" else "1" for b in bits), auto_apply=auto_apply)

    def _send_command(self, payload):
        try:
            self.network.send(payload)
            if payload.get("cmd") == "APPLY_PATTERN":
                self.log(f"Sent APPLY_PATTERN: cell_bits={payload.get('cell_bits')} wire_bits={payload.get('wire_bits')}")
            else:
                self.log(f"Sent: {payload}")
        except Exception as exc:
            self.log(f"Command not sent: {exc}")

    def _mode_segment_changed(self, value):
        self.set_auto_mode() if value == "AUTO" else self.set_manual_mode()

    def set_auto_mode(self):
        self.mode.set("AUTO")
        self.state.system.mode = "AUTO"
        self._send_command(command_set_mode("AUTO"))
        self._refresh_ui_from_state()
        self.log("Mode set to AUTO.")

    def set_manual_mode(self):
        self.mode.set("MANUAL")
        self.state.system.mode = "MANUAL"
        self._send_command(command_set_mode("MANUAL"))
        self._refresh_ui_from_state()
        self.log("Mode set to MANUAL.")

    def apply_manual_pattern(self):
        bits = self.manual_bits.get().strip()[:RIS_ELEMENTS].ljust(RIS_ELEMENTS, "0")
        try:
            validate_ris_bits(bits)
        except Exception as exc:
            messagebox.showerror("Invalid RIS Pattern", str(exc))
            return
        pid = self._safe_int(self.manual_pattern_id.get(), 0)
        self.mode.set("MANUAL")
        self.state.system.mode = "MANUAL"
        self.state.ris.pattern_id = pid
        self.state.ris.bits = bits
        self.state.ris.wire_bits = physical_to_wire_bits(bits)
        self.state.ris.state = "LOCAL_MANUAL_APPLIED"
        payload = command_apply_pattern(pid, bits)
        self._send_command(payload)
        self._refresh_ui_from_state()
        self.log(f"GPIO WRITE REQUESTED: ID={pid}, cell_bits={bits}, wire_bits={physical_to_wire_bits(bits)}")

    def reset_ris(self):
        self._send_command(command_reset_ris())
        self.set_manual_bits("0" * RIS_ELEMENTS)
        self.state.ris.state = "LOCAL_RESET"
        self._refresh_ui_from_state()
        self.log("RIS reset requested.")

    def emergency_off(self):
        self._send_command(command_emergency_off())
        self.set_manual_bits("0" * RIS_ELEMENTS)
        self.state.ris.state = "LOCAL_EMERGENCY_OFF"
        self.state.system.mode = "MANUAL"
        self._refresh_ui_from_state()
        self.log("Emergency OFF requested.")

    def request_status(self):
        self._send_command(command_get_status())
        self.log("Requested latest status.")

    def _ui_render_loop(self):
        # Single UI heartbeat. It consumes latest telemetry, then renders at a controlled rate.
        packet = None
        with self._packet_lock:
            if self._pending_packet is not None:
                packet = self._pending_packet
                self._pending_packet = None

        if packet is not None:
            self.update_from_packet(packet, render=False)

        self._refresh_ui_from_state()

        if self.running:
            self.root.after(250, self._ui_render_loop)

    def _simulation_loop(self):
        if self.running and self.simulation_enabled.get() and not self.network.connected:
            mode = self.mode.get()
            packet = generate_simulated_packet(mode, self.manual_bits.get(), self._safe_int(self.manual_pattern_id.get(), 0))
            with self._packet_lock:
                self._pending_packet = packet
        if self.running:
            self.root.after(SIMULATION_INTERVAL_MS, self._simulation_loop)

    def on_close(self):
        self.running = False
        try:
            self.network.disconnect()
        except Exception:
            pass
        self.root.destroy()

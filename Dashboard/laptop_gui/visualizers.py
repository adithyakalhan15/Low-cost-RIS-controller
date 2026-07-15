from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from .config import *

MPL_BG = C_PANEL
GRID = "#263449"
TEXT = "#DDEBFF"
ACCENT = C_ACCENT
GREEN = C_GREEN
PURPLE = C_PURPLE
YELLOW = C_YELLOW
RED = C_RED

class RoomVisualizer2D:
    def __init__(self, parent):
        self.fig = Figure(figsize=(8, 5.8), dpi=100, facecolor=MPL_BG)
        self.ax = self.fig.add_subplot(111, facecolor="#070B12")
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.widget = self.canvas.get_tk_widget()
        self.widget.configure(bg=C_PANEL)

    def draw(self, state):
        ax = self.ax
        ax.clear()
        ax.set_facecolor("#070B12")
        for sp in ax.spines.values():
            sp.set_color(GRID)
        ax.tick_params(colors=TEXT)
        ax.set_title("2D Top View — TX → RIS → User/RX", color=TEXT, pad=12, fontsize=13, fontweight="bold")
        ax.set_xlabel("X position / m", color=TEXT)
        ax.set_ylabel("Y position / m", color=TEXT)
        ax.set_xlim(ROOM_X_MIN, ROOM_X_MAX)
        ax.set_ylim(ROOM_Y_MIN, ROOM_Y_MAX)
        ax.grid(True, color=GRID, linewidth=0.8, alpha=0.75)

        room_x = [ROOM_X_MIN + 0.5, ROOM_X_MAX - 0.5, ROOM_X_MAX - 0.5, ROOM_X_MIN + 0.5, ROOM_X_MIN + 0.5]
        room_y = [0, 0, ROOM_Y_MAX - 0.5, ROOM_Y_MAX - 0.5, 0]
        ax.plot(room_x, room_y, color="#475569", linewidth=1.3)

        ris_x, ris_y, _ = RIS_POSITION
        tx_x, tx_y, _ = TX_POSITION
        ux, uy = state.user.x_m, state.user.y_m
        wx, wy = state.person.wifi_x_m, state.person.wifi_y_m
        has_wifi = bool(state.person.selected)
        has_fused = bool(getattr(state.person, "fused_have_pos", False))
        fx, fy = getattr(state.person, "fused_x_m", 0.0), getattr(state.person, "fused_y_m", 0.0)

        ax.plot([tx_x, ris_x], [tx_y, ris_y], color=YELLOW, linestyle="--", linewidth=1.7, alpha=0.9)
        ax.plot([ris_x, ux], [ris_y, uy], color=ACCENT, linewidth=3.2, alpha=0.96)
        ax.plot([ris_x, ux], [ris_y, uy], color="#BAE6FD", linewidth=9.0, alpha=0.12)

        ax.scatter([ris_x], [ris_y], s=270, marker="s", color=PURPLE, edgecolor="#F5D0FE", linewidth=1.2, zorder=5)
        ax.scatter([tx_x], [tx_y], s=190, marker="^", color=YELLOW, edgecolor="#FEF3C7", linewidth=1.0, zorder=5)
        ax.scatter([ux], [uy], s=230, marker="o", color=GREEN, edgecolor="#DCFCE7", linewidth=1.2, zorder=6)
        ax.text(ris_x + 0.13, ris_y + 0.13, "RIS 4×6", color=TEXT, fontsize=10, fontweight="bold")
        ax.text(tx_x + 0.13, tx_y + 0.13, "TX", color=TEXT, fontsize=10, fontweight="bold")
        ax.text(ux + 0.13, uy + 0.13, "Radar target", color=TEXT, fontsize=10, fontweight="bold")

        # Draw configured RSSI anchor positions from Raspberry Pi config.RSSI_ANCHORS.
        for a in getattr(state, "anchors", []):
            live = getattr(a, "last_seen_age_s", -1.0) >= 0 and getattr(a, "last_seen_age_s", 999) <= 5.0
            ax.scatter([a.x_m], [a.y_m], s=170, marker="X", color=C_CYAN if live else "#64748B", edgecolor="#E0F2FE", linewidth=1.0, zorder=8)
            label = f"Anchor {a.id}"
            if live:
                label += f" ({a.last_rssi_dbm:.0f} dBm)"
            ax.text(a.x_m + 0.10, a.y_m + 0.10, label, color="#CFFAFE" if live else "#94A3B8", fontsize=9, fontweight="bold")

        if has_wifi:
            ax.scatter([wx], [wy], s=250, marker="D", color=C_CYAN, edgecolor="#CFFAFE", linewidth=1.3, zorder=7)
            ax.plot([ux, wx], [uy, wy], color=RED, linestyle=":", linewidth=2.0, alpha=0.9)
            ax.text(wx + 0.13, wy - 0.18, "RSSI device", color="#CFFAFE", fontsize=10, fontweight="bold")

        if has_fused:
            ax.scatter([fx], [fy], s=330, marker="*", color="#FDE047", edgecolor="#FEF9C3", linewidth=1.4, zorder=9)
            ax.plot([ris_x, fx], [ris_y, fy], color="#FDE047", linestyle="-.", linewidth=2.4, alpha=0.9)
            ax.text(fx + 0.13, fy + 0.20, "FUSED position", color="#FEF9C3", fontsize=10, fontweight="bold")

        quality = "GOOD" if state.channel.snr_db >= 18 else "MEDIUM" if state.channel.snr_db >= 9 else "LOW"
        info = f"Mode {state.system.mode} | Beam {state.ris.beam_angle_deg:.1f}° | Pattern {state.ris.pattern_id} | SNR {state.channel.snr_db:.1f} dB | {quality} | Person {state.person.source}"
        ax.text(ROOM_X_MIN + 0.25, ROOM_Y_MAX - 0.45, info, color="#BAE6FD", fontsize=10,
                bbox=dict(facecolor="#0F172A", edgecolor="#334155", alpha=0.94, boxstyle="round,pad=0.4"))
        self.canvas.draw_idle()

class RoomVisualizer3D:
    def __init__(self, parent):
        self.fig = Figure(figsize=(8, 5.8), dpi=100, facecolor=MPL_BG)
        self.ax = self.fig.add_subplot(111, projection="3d", facecolor="#070B12")
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.widget = self.canvas.get_tk_widget()
        self.widget.configure(bg=C_PANEL)

    def draw(self, state):
        ax = self.ax
        ax.clear()
        ax.set_facecolor("#070B12")
        ax.set_title("3D Scene — Demo Geometry", color=TEXT, pad=12, fontsize=13, fontweight="bold")
        ax.set_xlim(ROOM_X_MIN, ROOM_X_MAX)
        ax.set_ylim(ROOM_Y_MIN, ROOM_Y_MAX)
        ax.set_zlim(ROOM_Z_MIN, ROOM_Z_MAX)
        ax.set_xlabel("X / m", color=TEXT)
        ax.set_ylabel("Y / m", color=TEXT)
        ax.set_zlabel("Z / m", color=TEXT)
        ax.tick_params(colors=TEXT)
        ax.xaxis.pane.set_facecolor((0.04, 0.06, 0.10, 1))
        ax.yaxis.pane.set_facecolor((0.04, 0.06, 0.10, 1))
        ax.zaxis.pane.set_facecolor((0.04, 0.06, 0.10, 1))
        ax.grid(True)

        ris = RIS_POSITION
        tx = TX_POSITION
        user = (state.user.x_m, state.user.y_m, RX_HEIGHT)
        wifi = (state.person.wifi_x_m, state.person.wifi_y_m, RX_HEIGHT)
        fused = (getattr(state.person, "fused_x_m", 0.0), getattr(state.person, "fused_y_m", 0.0), RX_HEIGHT + 0.10)
        has_wifi = bool(state.person.selected)
        has_fused = bool(getattr(state.person, "fused_have_pos", False))
        ax.plot([tx[0], ris[0]], [tx[1], ris[1]], [tx[2], ris[2]], color=YELLOW, linestyle="--", linewidth=2)
        ax.plot([ris[0], user[0]], [ris[1], user[1]], [ris[2], user[2]], color=ACCENT, linewidth=3)
        ax.scatter([ris[0]], [ris[1]], [ris[2]], s=160, marker="s", color=PURPLE, edgecolor="#F5D0FE")
        ax.scatter([tx[0]], [tx[1]], [tx[2]], s=120, marker="^", color=YELLOW, edgecolor="#FEF3C7")
        ax.scatter([user[0]], [user[1]], [user[2]], s=140, marker="o", color=GREEN, edgecolor="#DCFCE7")
        for a in getattr(state, "anchors", []):
            live = getattr(a, "last_seen_age_s", -1.0) >= 0 and getattr(a, "last_seen_age_s", 999) <= 5.0
            ax.scatter([a.x_m], [a.y_m], [0.25], s=115, marker="X", color=C_CYAN if live else "#64748B", edgecolor="#E0F2FE")
            ax.text(a.x_m, a.y_m, 0.45, f"A{a.id}", color="#CFFAFE" if live else "#94A3B8")
        if has_wifi:
            ax.scatter([wifi[0]], [wifi[1]], [wifi[2]], s=150, marker="D", color=C_CYAN, edgecolor="#CFFAFE")
            ax.plot([user[0], wifi[0]], [user[1], wifi[1]], [user[2], wifi[2]], color=RED, linestyle=":", linewidth=2)
        if has_fused:
            ax.scatter([fused[0]], [fused[1]], [fused[2]], s=210, marker="*", color="#FDE047", edgecolor="#FEF9C3")
            ax.plot([ris[0], fused[0]], [ris[1], fused[1]], [ris[2], fused[2]], color="#FDE047", linestyle="-.", linewidth=2)

        # Draw a small 4×6 RIS panel mesh in the vertical plane
        panel_w = 1.8
        panel_h = 1.2
        x0, y0, z0 = ris
        for c in range(RIS_COLS + 1):
            x = x0 - panel_w / 2 + c * panel_w / RIS_COLS
            ax.plot([x, x], [y0, y0], [z0 - panel_h / 2, z0 + panel_h / 2], color=PURPLE, alpha=0.35, linewidth=1)
        for r in range(RIS_ROWS + 1):
            z = z0 - panel_h / 2 + r * panel_h / RIS_ROWS
            ax.plot([x0 - panel_w / 2, x0 + panel_w / 2], [y0, y0], [z, z], color=PURPLE, alpha=0.35, linewidth=1)

        ax.text(ris[0], ris[1], ris[2] + 0.25, "RIS 4×6", color=TEXT)
        ax.text(tx[0], tx[1], tx[2] + 0.2, "TX", color=TEXT)
        ax.text(user[0], user[1], user[2] + 0.2, "Radar", color=TEXT)
        if has_wifi:
            ax.text(wifi[0], wifi[1], wifi[2] + 0.2, "RSSI", color="#CFFAFE")
        if has_fused:
            ax.text(fused[0], fused[1], fused[2] + 0.2, "FUSED", color="#FEF9C3")
        ax.view_init(elev=24, azim=-58)
        self.canvas.draw_idle()

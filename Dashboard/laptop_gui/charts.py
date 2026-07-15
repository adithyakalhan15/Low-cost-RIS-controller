from collections import deque
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from .config import *

class LiveCharts:
    def __init__(self, parent):
        self.rssi = deque(maxlen=MAX_HISTORY_POINTS)
        self.snr = deque(maxlen=MAX_HISTORY_POINTS)
        self.throughput = deque(maxlen=MAX_HISTORY_POINTS)
        self.fig = Figure(figsize=(8, 5.8), dpi=100, facecolor=C_PANEL)
        self.ax = self.fig.add_subplot(111, facecolor="#070B12")
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.widget = self.canvas.get_tk_widget()
        self.widget.configure(bg=C_PANEL)

    def update(self, state):
        self.rssi.append(state.channel.rssi_dbm)
        self.snr.append(state.channel.snr_db)
        self.throughput.append(state.channel.throughput_mbps)
        self.draw()

    def draw(self):
        ax = self.ax
        ax.clear()
        ax.set_facecolor("#070B12")
        for sp in ax.spines.values():
            sp.set_color(C_BORDER)
        ax.tick_params(colors=C_TEXT)
        ax.set_title("Live Channel Trends", color=C_TEXT, pad=12, fontsize=13, fontweight="bold")
        ax.set_xlabel("Samples", color=C_TEXT)
        ax.grid(True, color="#263449", alpha=0.7)
        x = list(range(len(self.rssi)))
        ax.plot(x, list(self.rssi), label="RSSI / dBm", linewidth=2)
        ax.plot(x, list(self.snr), label="SNR / dB", linewidth=2)
        ax.plot(x, list(self.throughput), label="Throughput / Mbps", linewidth=2)
        legend = ax.legend(facecolor="#0F172A", edgecolor=C_BORDER)
        for txt in legend.get_texts():
            txt.set_color(C_TEXT)
        self.canvas.draw_idle()

import random


class ChannelMonitor:
    """
    Simulated channel monitor.

    Later replace this with real:
      - Wi-Fi RSSI from iw/wavemon/iperf3
      - ESP32 RSSI data
      - SDR/VNA/spectrum analyzer data
      - measured packet loss / throughput
    """

    def get_channel(self, predicted_snr_db=None, capacity_mbps=None):
        if predicted_snr_db is None:
            predicted_snr_db = random.uniform(8, 25)

        # Map predicted SNR into plausible demo values
        rssi = -75 + min(max(predicted_snr_db, 0), 35) * 0.9 + random.uniform(-1.5, 1.5)
        throughput = capacity_mbps if capacity_mbps is not None else random.uniform(5, 40)

        return {
            "rssi_dbm": round(rssi, 2),
            "snr_db": round(float(predicted_snr_db), 2),
            "throughput_mbps": round(float(max(0.0, min(throughput, 120.0))), 2),
            "packet_loss_percent": round(max(0.0, 8.0 - predicted_snr_db * 0.25 + random.uniform(-0.5, 0.5)), 2),
            "ber": round(max(1e-7, 1e-3 / (1.0 + max(predicted_snr_db, 0.0))), 8),
        }

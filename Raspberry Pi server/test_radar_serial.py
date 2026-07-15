from raspberry_pi_server.radar_receiver import RadarReceiver
import time

radar = RadarReceiver(simulation=False)
radar.start()

try:
    while True:
        print(radar.get_position())
        time.sleep(0.5)
except KeyboardInterrupt:
    radar.stop()

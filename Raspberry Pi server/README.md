# Raspberry Pi RIS Server — GPIO Scope Debug Final

This package is configured to **drive real Raspberry Pi GPIO pins by default** using a slow SPI-like bit-banged interface with the direct lgpio backend for a 74HC595 shift-register chain.

It also prints very clear hardware logs, including:

- whether GPIO output is enabled
- which physical pins and BCM GPIO numbers are used
- the exact 32-bit wire pattern
- the shifted bit order
- every DATA bit and CLOCK pulse during scope tests
- the final LATCH pulse confirmation
- direct lgpio backend, with no RPi.GPIO import

---

## Physical wiring

Wire by **physical pin number** on the Raspberry Pi header:

| Signal | Raspberry Pi physical pin | BCM GPIO used in Python | RJ45 pin | 74HC595 pin |
|---|---:|---:|---:|---:|
| DATA / MOSI-like | 19 | GPIO10 | 1 | 14 SER |
| CLOCK / SCLK-like | 23 | GPIO11 | 2 | 11 SRCLK |
| LATCH / RCLK-like | 24 | GPIO8 | 3 | 12 RCLK |
| GND | 6 or 9 | GND | 8 | 8 GND |

74HC595 fixed pins:

| 74HC595 pin | Connect to |
|---:|---|
| 16 VCC | 3.3 V recommended |
| 8 GND | Raspberry Pi GND |
| 13 OE | GND |
| 10 MR / SRCLR | VCC |

> Important: Raspberry Pi GPIO is 3.3 V logic. If your shift-register board is powered at 5 V, use a proper level shifter.

---

## What changed in this version

In `raspberry_pi_server/config.py`:

```python
ENABLE_HARDWARE_OUTPUT = True
GPIO_BIT_DELAY_S = 0.005
SCOPE_TEST_BIT_DELAY_S = 0.010
TELEMETRY_HZ = 1.0
HARDWARE_VERBOSE_PRINT = True
```

So the normal RIS server now writes to real GPIO pins by default. The scope test is even slower than the server output.

---

## Install on Raspberry Pi

Copy/extract this folder to the Raspberry Pi, then run:

```bash
cd ~/Desktop/raspberry_pi_ris_server_final_gpio_scope_debug
sudo apt update
sudo apt remove -y python3-rpi.gpio python3-rpi-lgpio
sudo apt install -y python3-venv python3-pip python3-lgpio
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
python -m pip install --upgrade pip
pip install numpy onnxruntime pyserial
```

If serial permission fails:

```bash
sudo usermod -a -G dialout $USER
sudo reboot
```

Then activate again:

```bash
cd ~/Desktop/raspberry_pi_ris_server_final_gpio_scope_debug
source .venv/bin/activate
```

---

## GPIO library conflict fix

This version does **not** use `RPi.GPIO`. It imports `lgpio` directly.

Do not install both of these together for this package:

```bash
python3-rpi.gpio
python3-rpi-lgpio
```

Use only:

```bash
sudo apt install -y python3-lgpio
```

If GPIO claiming fails, try a different gpiochip:

```bash
ls /dev/gpiochip*
export RIS_GPIOCHIP=0
python3 scope_pin_test.py

# If needed, try:
export RIS_GPIOCHIP=4
python3 scope_pin_test.py
```

---

## Best oscilloscope test

Run this first before connecting the full RIS panel:

```bash
cd ~/Desktop/raspberry_pi_ris_server_final_gpio_scope_debug
source .venv/bin/activate
python3 scope_pin_test.py
```

Oscilloscope connections:

```text
Scope GND    -> Raspberry Pi physical pin 6 or 9
DATA probe   -> Raspberry Pi physical pin 19
CLOCK probe  -> Raspberry Pi physical pin 23
LATCH probe  -> Raspberry Pi physical pin 24
```

Expected:

```text
DATA  changes 0 V / 3.3 V according to the pattern
CLOCK gives 32 slow pulses per pattern
LATCH gives 1 pulse after each 32-bit transfer
```

The test prints every bit:

```text
[HW TX #1] bit 01/32 DATA=1 -> CLOCK pulse
[HW TX #1] bit 02/32 DATA=0 -> CLOCK pulse
...
[HW DONE #1] 32 clock pulses sent, latch pulsed, DATA left LOW.
```

To make it even slower, edit:

```bash
nano raspberry_pi_server/config.py
```

Change:

```python
SCOPE_TEST_BIT_DELAY_S = 0.020
```

---

## Shift-register hardware test

This also forces output ON and sends fixed patterns plus a walking-one test:

```bash
cd ~/Desktop/raspberry_pi_ris_server_final_gpio_scope_debug
source .venv/bin/activate
python3 test_shift_register.py
```

---

## Run final RIS server

```bash
cd ~/Desktop/raspberry_pi_ris_server_final_gpio_scope_debug
source .venv/bin/activate
python3 -m raspberry_pi_server.pi_server
```

Then connect the laptop GUI to the Raspberry Pi:

```text
IP: <your Raspberry Pi IP address>
Port: 5050
```

Useful command to find the Pi IP:

```bash
hostname -I
```

---

## If GPIO does not output

If you see this:

```text
[HW] RPi.GPIO import failed. Hardware output is disabled.
```

run:

```bash
sudo apt update
sudo apt install -y python3-rpi-lgpio python3-rpi.gpio
rm -rf .venv
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install numpy onnxruntime pyserial
python3 scope_pin_test.py
```

---

## Is this real SPI?

It is **SPI-like bit-banged GPIO**, not hardware `/dev/spidev` SPI.

That is intentional for debugging:

```text
DATA  = MOSI-like
CLOCK = SCLK-like
LATCH = CS/LOAD/RCLK-like
```

For the 74HC595 this is correct and easy to verify on the oscilloscope.

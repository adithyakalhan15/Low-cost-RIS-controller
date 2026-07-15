# RIS Master Modern Tabbed GUI — Performance Fixed

This version fixes UI freezing/messy rendering by throttling heavy Matplotlib redraws.

Key changes:
- Network packets are buffered; only the newest packet is rendered.
- Main UI refresh runs at 4 Hz.
- 2D plot redraws only when the Visual tab is active.
- 3D plot redraws slower, about 1 Hz, because 3D Matplotlib is expensive.
- Channel chart redraws only when the Channel tab is active.
- RIS panel remains 4 x 6 physical cells.
- Wire stream remains 32 bits: each 6-cell row + 2 dummy bits.

Run:

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
python -m laptop_gui.main
```

Linux/Raspberry Pi OS/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m laptop_gui.main
```

For Raspberry Pi connection:
- IP: your Pi Ethernet IP, for example 192.168.10.2
- Port: 5050
- Turn Simulation Mode OFF before connecting.

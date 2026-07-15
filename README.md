## Intelligent RIS Controller and User-Tracking System

This repository contains the hardware-control, embedded firmware, edge-processing, and desktop-visualization components developed for a low-cost Reconfigurable Intelligent Surface system operating near 2.4 GHz.

The system controls a 6 × 4, 1-bit RIS panel through a 24-channel shift-register and MOSFET driver architecture. An ESP32-S3 collects target information from dual LD2450 mmWave radar sensors, while RSSI measurements provide additional wireless-positioning information. A Raspberry Pi processes the sensor data, selects RIS control patterns, and communicates with a Python-based desktop application for visualization, manual control, logging, and system monitoring.

The project demonstrates the integration of RF hardware, embedded systems, wireless sensing, edge processing, and software interfaces in a single experimental RIS platform.

### Main Features

* Independent control of 24 RIS cells
* ESP32-S3-based dual-radar data acquisition
* Radar and RSSI-assisted user tracking
* Raspberry Pi edge server and GPIO control
* Manual and automatic RIS pattern selection
* Python desktop dashboard for monitoring and visualization
* RF experimentation using Vivaldi antennas, an NI USRP N210, and spectrum-analysis equipment

![RIS setup with controller](https://github.com/adithyakalhan15/Low-cost-RIS-controller/blob/main/Images/IMG-20260708-WA0007.jpeg)

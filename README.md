# Leaf Sensor Bench · iGEM 2026

Bench calibration of a single RS485 (Modbus RTU) leaf temperature / wetness sensor with an ESP32, an SHT31/SHT40 reference and a humidifier. No soldering, no field work.

**Open the guide:** https://timmy97-tw.github.io/igem2026-leaf-sensor-bench/ (中文 / EN toggle top-right)

```
firmware/leafsensor/leafsensor.ino   ESP32 logger, no libraries (set SHT_MODEL)
tools/logger.py                      serial -> data/<TEST>_<time>.csv, type markers + Enter
tools/analyze.py                     data -> figures/*.png + results/summary.json
tools/config.json                    register mapping, wet threshold, dose unit
docs/example/                        SIMULATED example figures (not measurements)
```

Quick start

```bash
python3 -m pip install -r requirements.txt
python3 tools/logger.py --test T0
python3 tools/analyze.py T0 data/T0_*.csv
```

Tests: T0 side-by-side baseline · C1 humidity box · C2 water dose · C3 dry-down threshold · C4 cold-leaf dew · T5 overnight.

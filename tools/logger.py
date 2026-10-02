"""Record the ESP32 serial output to data/<test>_<date>.csv.

Usage:
    python tools/logger.py --test C2            # auto-detects the port
    python tools/logger.py --test C2 --port /dev/cu.usbserial-110

While it runs, type a marker and press Enter, e.g.  dose 4  /  wet  /  dry  /  out.
The marker is written to the next row, so the analysis knows what happened when.
Stop with Ctrl+C.
"""
import argparse
import datetime as dt
import glob
import os
import queue
import sys
import threading

import serial

HEADER = "host_time,ms,ok,r0,r1,sht_t,sht_rh,marker\n"


def find_port():
    pats = ["/dev/cu.usbserial*", "/dev/cu.wchusbserial*", "/dev/cu.SLAB*",
            "/dev/ttyUSB*", "/dev/ttyACM*"]
    ports = sorted(p for pat in pats for p in glob.glob(pat))
    if not ports and sys.platform.startswith("win"):
        from serial.tools import list_ports
        ports = [p.device for p in list_ports.comports()]
    if not ports:
        sys.exit("No ESP32 port found. Plug in the USB cable, close Arduino Serial Monitor, "
                 "or pass --port.")
    return ports[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", required=True, help="T0, C1, C2, C3, C4, T5 ...")
    ap.add_argument("--port")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    a = ap.parse_args()

    port = a.port or find_port()
    os.makedirs(a.outdir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(a.outdir, f"{a.test}_{stamp}.csv")

    marks = queue.Queue()
    threading.Thread(target=lambda: [marks.put(l.strip()) for l in sys.stdin], daemon=True).start()

    ser = serial.Serial(port, 115200, timeout=2)
    print(f"port {port}  ->  {path}\nType a marker + Enter at any time. Ctrl+C to stop.\n")
    n = 0
    with open(path, "w") as f:
        f.write(HEADER)
        try:
            while True:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("#") or line.startswith("ms,"):
                    print(line)
                    continue
                if line.count(",") != 5:
                    continue
                mark = ""
                while not marks.empty():
                    mark = (mark + " " + marks.get()).strip()
                now = dt.datetime.now().isoformat(timespec="seconds")
                f.write(f"{now},{line},{mark.replace(',', ' ')}\n")
                f.flush()
                n += 1
                print(f"{now}  {line}  {('<< ' + mark) if mark else ''}")
        except KeyboardInterrupt:
            print(f"\nsaved {n} rows to {path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PS5 browser watchdog: auto-clear system dialogs via TV ADB keys.
Screenshots are HDCP-black, so the signal is the BEACON LOG:
  - if the beacon log file's mtime is stale (> STALE_S seconds),
    the browser is likely blocked by a dialog or crashed.
  - send a key sequence via the TV (HDMI-CEC forwards to the PS5):
    OK (DPAD_CENTER) x2, then BACK, then OK again.
  - keep trying until beacons resume (log mtime updates).
Logs every action to watchdog.log. Run in background.
"""
import os
import subprocess
import time
import glob
import datetime

ADB = "adb"
TV = "192.168.1.142:5555"
LOG_DIR = r"C:\xampp\htdocs\me\PS5\tools\browser_runner\beacon_logs"
WATCHLOG = os.path.join(LOG_DIR, "watchdog.log")
STALE_S = 75          # silence threshold
CHECK_S = 20          # poll interval
KEY_SEQ = [           # cycles through these on each stale round
    ["KEYCODE_DPAD_CENTER", "KEYCODE_DPAD_CENTER"],
    ["KEYCODE_BACK"],
    ["KEYCODE_DPAD_CENTER"],
    ["KEYCODE_DPAD_CENTER", "KEYCODE_DPAD_DOWN", "KEYCODE_DPAD_CENTER"],
]

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(WATCHLOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")

def latest_beacon_mtime():
    files = glob.glob(os.path.join(LOG_DIR, "beacons_*.log"))
    if not files:
        return 0
    latest = max(files, key=os.path.getmtime)
    return os.path.getmtime(latest)

def send_keys(keys):
    for k in keys:
        r = subprocess.run([ADB, "-s", TV, "shell", "input", "keyevent", k],
                           capture_output=True, text=True, timeout=15)
        time.sleep(1.2)

def main():
    log("watchdog started (stale>75s triggers keys)")
    seq = 0
    while True:
        try:
            m = latest_beacon_mtime()
            now = time.time()
            if now - m > STALE_S:
                keys = KEY_SEQ[seq % len(KEY_SEQ)]
                log(f"STALE {int(now-m)}s -> sending {keys}")
                send_keys(keys)
                seq += 1
                # give the browser time to act
                time.sleep(10)
            time.sleep(CHECK_S)
        except Exception as e:
            log(f"ERROR: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()

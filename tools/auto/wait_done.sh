#!/usr/bin/env bash
# wait_done.sh <tag> [hardcap_seconds]
# Watches today's apache beacon log for the outcome of a probe.
# Prints exactly one RESULT= line and exits:
#   RESULT=DONE    (0)  probe completed normally (<tag>-DONE seen)
#   RESULT=STALL   (2)  beacons started then stopped with no DONE -> crash/freeze
#   RESULT=TIMEOUT (3)  hard cap reached
#   RESULT=NOSTART (4)  no beacon for this tag ever arrived (page not loaded / didn't advance)
#   RESULT=FLOOD   (5)  runaway beacon rate (re-entrancy loop / hang) -> needs manual reload
TAG="$1"; HARDCAP="${2:-180}"
LOGDIR="C:/xampp/htdocs/me/PS5/tools/browser_runner/beacon_logs"
pick_log(){ ls -1t "$LOGDIR"/beacons_*_apache.log 2>/dev/null | head -1; }
count(){ local L="$1"; local c; c=$(grep -c "$TAG-" "$L" 2>/dev/null); [ -z "$c" ] && c=0; echo "$c"; }

start=$(date +%s); prev=0; stall=0; everseen=0
while :; do
  L="$(pick_log)"
  if [ -n "$L" ] && grep -q "$TAG-DONE" "$L" 2>/dev/null; then echo "RESULT=DONE"; exit 0; fi
  cnt=0; [ -n "$L" ] && cnt=$(count "$L")
  [ "$cnt" -gt 0 ] 2>/dev/null && everseen=1
  delta=$((cnt - prev))
  # Flood: more than 150 new beacons in one 3s tick = runaway re-entrancy loop.
  if [ "$delta" -gt 150 ] 2>/dev/null; then echo "RESULT=FLOOD count=$cnt delta=$delta"; exit 5; fi
  if [ "$cnt" -gt "$prev" ] 2>/dev/null; then prev=$cnt; stall=0; else stall=$((stall+1)); fi
  # Stall: beacons seen but none new for ~21s (7 x 3s) and no DONE -> crash/freeze.
  if [ "$everseen" -eq 1 ] && [ "$stall" -ge 7 ]; then echo "RESULT=STALL count=$cnt"; exit 2; fi
  now=$(date +%s); el=$((now - start))
  if [ "$everseen" -eq 0 ] && [ "$el" -ge 45 ]; then echo "RESULT=NOSTART"; exit 4; fi
  if [ "$el" -ge "$HARDCAP" ]; then echo "RESULT=TIMEOUT count=$cnt"; exit 3; fi
  sleep 3
done

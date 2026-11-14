#!/usr/bin/env python3
"""PS5 Research Control Panel — manage DNS spoof, Apache, PS5 connection from one place."""

import datetime
import os
import pathlib
import signal
import socket
import subprocess
import sys
import time
import threading

# ── Paths ──────────────────────────────────────────────
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
DNS_SCRIPT = SCRIPT_DIR / 'dns_spoof.py'
BEACON_LOG_DIR = SCRIPT_DIR / 'beacon_logs'
LATEST_TXT = BEACON_LOG_DIR / 'LATEST.txt'
RELOAD_TXT = pathlib.Path(r'C:\xampp\htdocs\reload.txt')
INDEX_HTML = pathlib.Path(r'C:\xampp\htdocs\document\en\ps5\index.html')
APACHE_EXE = pathlib.Path(r'C:\xampp\apache\bin\httpd.exe')

# ── Config ─────────────────────────────────────────────
PC_IP = '192.168.1.100'
PS5_IP = '192.168.1.106'
DNS_PORT = 53
UPSTREAM_DNS = '8.8.8.8'

# ── ANSI Colors ────────────────────────────────────────
os.system('')  # enable ANSI on Windows

RST  = '\033[0m'
BOLD = '\033[1m'
DIM  = '\033[2m'
R    = '\033[91m'   # red
G    = '\033[92m'   # green
Y    = '\033[93m'   # yellow
B    = '\033[94m'   # blue
M    = '\033[95m'   # magenta
C    = '\033[96m'   # cyan
W    = '\033[97m'   # white
BG_G = '\033[42m'   # green bg
BG_R = '\033[41m'   # red bg
BG_Y = '\033[43m'   # yellow bg
BG_B = '\033[44m'   # blue bg

# ── State ──────────────────────────────────────────────
dns_process = None
dns_lock = threading.Lock()


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def now():
    return datetime.datetime.now().strftime('%H:%M:%S')


# ── Status checks ─────────────────────────────────────

def is_port_open(host, port, timeout=1):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if port == 53 else socket.SOCK_STREAM)
        s.settimeout(timeout)
        if port == 53:
            # UDP: send a dummy DNS query and see if we get a response
            # Just check if our process is alive instead
            return dns_process is not None and dns_process.poll() is None
        else:
            s.connect((host, port))
            s.close()
            return True
    except Exception:
        return False


def check_dns_running():
    with dns_lock:
        if dns_process and dns_process.poll() is None:
            return True
    # Also check if port 53 is in use by something else
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(('0.0.0.0', 53))
        s.close()
        return False  # port was free, nothing running
    except OSError:
        return True  # port in use (maybe external)


def check_apache():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(('127.0.0.1', 443))
        s.close()
        return True
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(('127.0.0.1', 80))
        s.close()
        return True
    except Exception:
        return False


def ping_ps5():
    try:
        r = subprocess.run(
            ['ping', '-n', '1', '-w', '500', PS5_IP],
            capture_output=True, text=True, timeout=3
        )
        return r.returncode == 0
    except Exception:
        return False


def get_latest_beacon():
    try:
        txt = LATEST_TXT.read_text(encoding='utf-8').strip()
        mtime = datetime.datetime.fromtimestamp(LATEST_TXT.stat().st_mtime)
        age = (datetime.datetime.now() - mtime).total_seconds()
        return txt[:120], age
    except Exception:
        return '(none)', 999999


def get_today_beacon_count():
    today = datetime.datetime.now().strftime('%Y%m%d')
    logfile = BEACON_LOG_DIR / f'beacons_{today}_apache.log'
    if not logfile.exists():
        logfile = BEACON_LOG_DIR / f'beacons_{today}.log'
    if not logfile.exists():
        return 0
    try:
        with open(logfile, 'r', encoding='utf-8', errors='replace') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def get_deployed_probe():
    try:
        txt = RELOAD_TXT.read_text(encoding='utf-8').strip()
        return txt if txt else '(empty)'
    except Exception:
        return '(unknown)'


def get_dns_query_count():
    """Read query count from dns_spoof stdout if available."""
    with dns_lock:
        if dns_process and dns_process.poll() is None:
            return 'running'
    return 'stopped'


# ── Actions ────────────────────────────────────────────

def start_dns():
    global dns_process
    with dns_lock:
        if dns_process and dns_process.poll() is None:
            print(f'  {Y}DNS spoofer already running (PID {dns_process.pid}){RST}')
            return

    # Check if port 53 is already in use
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(('0.0.0.0', 53))
        s.close()
    except OSError:
        print(f'  {R}Port 53 already in use! Stop the other DNS process first.{RST}')
        print(f'  {DIM}Try: netstat -aon | findstr :53{RST}')
        return

    cmd = [
        sys.executable, str(DNS_SCRIPT),
        '--ip', PC_IP,
        '--upstream', UPSTREAM_DNS,
    ]
    try:
        dns_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
        )
        time.sleep(0.5)
        if dns_process.poll() is not None:
            out = dns_process.stdout.read().decode(errors='replace')
            print(f'  {R}DNS failed to start:{RST}')
            print(f'  {out[:200]}')
            dns_process = None
        else:
            print(f'  {G}DNS spoofer started!{RST} PID {dns_process.pid}')
            print(f'  {C}Spoofing PlayStation domains -> {PC_IP}{RST}')
    except Exception as e:
        print(f'  {R}Failed: {e}{RST}')


def stop_dns():
    global dns_process
    with dns_lock:
        if not dns_process or dns_process.poll() is not None:
            print(f'  {Y}DNS spoofer not running{RST}')
            dns_process = None
            return

        pid = dns_process.pid
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                             capture_output=True, timeout=5)
            else:
                dns_process.terminate()
                dns_process.wait(timeout=3)
        except Exception:
            try:
                dns_process.kill()
            except Exception:
                pass
        dns_process = None
        print(f'  {G}DNS spoofer stopped{RST} (was PID {pid})')


def reload_ps5():
    tag = get_deployed_probe()
    try:
        RELOAD_TXT.write_text(tag + '-reload-' + now(), encoding='utf-8')
        time.sleep(0.3)
        RELOAD_TXT.write_text(tag, encoding='utf-8')
        print(f'  {G}Reload triggered!{RST} PS5 should refresh in ~3s')
    except Exception as e:
        print(f'  {R}Failed: {e}{RST}')


def show_recent_beacons(n=15):
    today = datetime.datetime.now().strftime('%Y%m%d')
    logfile = BEACON_LOG_DIR / f'beacons_{today}_apache.log'
    if not logfile.exists():
        logfile = BEACON_LOG_DIR / f'beacons_{today}.log'
    if not logfile.exists():
        print(f'  {Y}No beacon log for today{RST}')
        return
    try:
        with open(logfile, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        recent = lines[-n:] if len(lines) >= n else lines
        print(f'  {C}Last {len(recent)} beacons:{RST}')
        for line in recent:
            line = line.strip()
            if 'ANOMALY' in line or 'HIT' in line or 'KPTR' in line:
                print(f'  {M}{line}{RST}')
            elif 'THROW' in line or 'ERR' in line:
                print(f'  {R}{line}{RST}')
            elif 'DONE' in line or 'RESULT' in line:
                print(f'  {G}{line}{RST}')
            else:
                print(f'  {DIM}{line}{RST}')
    except Exception as e:
        print(f'  {R}Error: {e}{RST}')


def kill_external_dns():
    """Kill any process using port 53 (for when dns_spoof was left by another terminal)."""
    if os.name != 'nt':
        print(f'  {Y}Use: sudo lsof -i :53{RST}')
        return
    try:
        r = subprocess.run(
            ['netstat', '-aon'],
            capture_output=True, text=True, timeout=5
        )
        pids = set()
        for line in r.stdout.splitlines():
            if ':53 ' in line and ('UDP' in line or 'LISTENING' in line):
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit() and pid != '0':
                        pids.add(pid)
        if not pids:
            print(f'  {Y}No process found on port 53{RST}')
            return
        for pid in pids:
            print(f'  {Y}Killing PID {pid}...{RST}')
            subprocess.run(['taskkill', '/F', '/PID', pid],
                         capture_output=True, timeout=5)
        print(f'  {G}Done. Port 53 should be free now.{RST}')
    except Exception as e:
        print(f'  {R}Error: {e}{RST}')


# ── Dashboard ──────────────────────────────────────────

def print_dashboard():
    dns_on = check_dns_running()
    apache_on = check_apache()
    ps5_on = ping_ps5()
    beacon_txt, beacon_age = get_latest_beacon()
    beacon_count = get_today_beacon_count()
    probe = get_deployed_probe()

    dns_label = f'{BG_G}{BOLD} ON  {RST}' if dns_on else f'{BG_R}{BOLD} OFF {RST}'
    apache_label = f'{BG_G}{BOLD} ON  {RST}' if apache_on else f'{BG_R}{BOLD} OFF {RST}'
    ps5_label = f'{BG_G}{BOLD} ONLINE  {RST}' if ps5_on else f'{BG_R}{BOLD} OFFLINE {RST}'

    if beacon_age < 60:
        age_str = f'{G}{int(beacon_age)}s ago{RST}'
    elif beacon_age < 3600:
        age_str = f'{Y}{int(beacon_age/60)}m ago{RST}'
    else:
        age_str = f'{R}{int(beacon_age/3600)}h ago{RST}'

    pid_str = ''
    with dns_lock:
        if dns_process and dns_process.poll() is None:
            pid_str = f' {DIM}(PID {dns_process.pid}){RST}'

    print(f'''
{BOLD}{C}╔══════════════════════════════════════════════════╗
║         PS5 RESEARCH CONTROL PANEL               ║
╚══════════════════════════════════════════════════╝{RST}

  {BOLD}DNS Spoof:{RST}    {dns_label}{pid_str}    {DIM}Spoofing -> {PC_IP}{RST}
  {BOLD}Apache:{RST}       {apache_label}         {DIM}HTTPS :443{RST}
  {BOLD}PS5:{RST}          {ps5_label}     {DIM}{PS5_IP}{RST}

  {BOLD}Deployed:{RST}     {Y}{probe}{RST}
  {BOLD}Beacons:{RST}      {W}{beacon_count} today{RST}  |  Last: {age_str}
  {BOLD}Latest:{RST}       {DIM}{beacon_txt[:80]}{RST}

{BOLD}{C}──────────────────────────────────────────────────{RST}
  {G}1{RST}) Toggle DNS spoof (start/stop)
  {G}2{RST}) Reload PS5 browser
  {G}3{RST}) Show recent beacons
  {G}4{RST}) Ping PS5
  {G}5{RST}) Kill external DNS (port 53 conflict)
  {G}6{RST}) Refresh dashboard
  {G}0{RST}) Exit
{BOLD}{C}──────────────────────────────────────────────────{RST}''')


# ── Main loop ──────────────────────────────────────────

def main():
    clear()
    print(f'{BOLD}{C}  Starting PS5 Research Control Panel...{RST}')
    time.sleep(0.3)

    while True:
        clear()
        print_dashboard()

        try:
            choice = input(f'\n  {BOLD}>{RST} ').strip()
        except (EOFError, KeyboardInterrupt):
            choice = '0'

        if choice == '1':
            if check_dns_running():
                with dns_lock:
                    is_ours = dns_process and dns_process.poll() is None
                if is_ours:
                    stop_dns()
                else:
                    print(f'  {Y}DNS on port 53 is running but not managed by this panel.{RST}')
                    print(f'  {Y}Use option 5 to kill it, then start from here.{RST}')
            else:
                start_dns()
            input(f'\n  {DIM}Press Enter...{RST}')

        elif choice == '2':
            reload_ps5()
            input(f'\n  {DIM}Press Enter...{RST}')

        elif choice == '3':
            show_recent_beacons(20)
            input(f'\n  {DIM}Press Enter...{RST}')

        elif choice == '4':
            print(f'  {C}Pinging {PS5_IP}...{RST}')
            if ping_ps5():
                print(f'  {G}PS5 is ONLINE!{RST}')
            else:
                print(f'  {R}PS5 not responding{RST}')
            input(f'\n  {DIM}Press Enter...{RST}')

        elif choice == '5':
            kill_external_dns()
            input(f'\n  {DIM}Press Enter...{RST}')

        elif choice == '6':
            continue  # just refresh

        elif choice == '0' or choice.lower() in ('q', 'quit', 'exit'):
            with dns_lock:
                if dns_process and dns_process.poll() is None:
                    print(f'\n  {Y}Stopping DNS spoofer...{RST}')
                    stop_dns()
            print(f'\n  {C}Bye!{RST}\n')
            break


if __name__ == '__main__':
    main()

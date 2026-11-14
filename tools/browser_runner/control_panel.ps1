<#
.SYNOPSIS
    PS5 Research Control Panel
.DESCRIPTION
    Run as Administrator (port 53 needs it).
    powershell -ExecutionPolicy Bypass -File control_panel.ps1
#>

$PC_IP       = '192.168.1.100'
$PS5_IP      = '192.168.1.106'
$DNS_PORT    = 53
$UPSTREAM    = '8.8.8.8'

$SCRIPT_DIR  = Split-Path -Parent $MyInvocation.MyCommand.Path
$DNS_SCRIPT  = Join-Path $SCRIPT_DIR 'dns_spoof.py'
$BEACON_DIR  = Join-Path $SCRIPT_DIR 'beacon_logs'
$LATEST_TXT  = Join-Path $BEACON_DIR 'LATEST.txt'
$RELOAD_TXT  = 'C:\xampp\htdocs\reload.txt'

$script:DnsProcess = $null

function Write-C {
    param([string]$Text, [ConsoleColor]$Color = 'White', [switch]$NL)
    if ($NL) { Write-Host $Text -ForegroundColor $Color }
    else     { Write-Host $Text -ForegroundColor $Color -NoNewline }
}

function Test-Port53 {
    try {
        $udp = New-Object System.Net.Sockets.UdpClient
        $udp.Client.Bind([System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 53))
        $udp.Close()
        return $false
    } catch { return $true }
}

function Test-DnsRunning {
    if ($script:DnsProcess -and -not $script:DnsProcess.HasExited) {
        return @{ Running = $true; Ours = $true; PID = $script:DnsProcess.Id }
    }
    if (Test-Port53) {
        $pid2 = 0
        $lines = netstat -aon 2>$null
        foreach ($ln in $lines) {
            if ($ln -match ':53\s' -and $ln -match 'UDP') {
                $parts = $ln.Trim() -split '\s+'
                $pid2 = [int]$parts[-1]
                break
            }
        }
        return @{ Running = $true; Ours = $false; PID = $pid2 }
    }
    return @{ Running = $false; Ours = $false; PID = 0 }
}

function Test-Apache {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect('127.0.0.1', 443)
        $tcp.Close()
        return $true
    } catch {
        try {
            $tcp2 = New-Object System.Net.Sockets.TcpClient
            $tcp2.Connect('127.0.0.1', 80)
            $tcp2.Close()
            return $true
        } catch { return $false }
    }
}

function Test-PS5 {
    try { return (Test-Connection -ComputerName $PS5_IP -Count 1 -Quiet -ErrorAction Stop) }
    catch { return $false }
}

function Get-LatestBeacon {
    if (Test-Path $LATEST_TXT) {
        $content2 = (Get-Content $LATEST_TXT -Raw -ErrorAction SilentlyContinue)
        if ($content2) { $content2 = $content2.Trim() } else { $content2 = '(none)' }
        $mtime = (Get-Item $LATEST_TXT).LastWriteTime
        $age = (Get-Date) - $mtime
        return @{ Text = $content2; Age = $age }
    }
    return @{ Text = '(none)'; Age = [TimeSpan]::FromHours(999) }
}

function Get-BeaconCount {
    $today = Get-Date -Format 'yyyyMMdd'
    $logFile = Join-Path $BEACON_DIR ('beacons_' + $today + '_apache.log')
    if (-not (Test-Path $logFile)) {
        $logFile = Join-Path $BEACON_DIR ('beacons_' + $today + '.log')
    }
    if (Test-Path $logFile) {
        return (Get-Content $logFile -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
    }
    return 0
}

function Get-DeployedProbe {
    if (Test-Path $RELOAD_TXT) {
        $val = (Get-Content $RELOAD_TXT -Raw -ErrorAction SilentlyContinue)
        if ($val) { return $val.Trim() }
    }
    return '(unknown)'
}

function Start-Dns {
    $status = Test-DnsRunning
    if ($status.Running) {
        if ($status.Ours) {
            Write-C ('  DNS already running (PID ' + $status.PID + ')') Yellow -NL
        } else {
            Write-C ('  Port 53 in use by PID ' + $status.PID + ' (external)') Yellow -NL
            Write-C '  Use [5] to kill it first' DarkGray -NL
        }
        return
    }
    $pyExe = $null
    foreach ($c in @(
        'C:\Python312\python.exe','C:\Python311\python.exe','C:\Python310\python.exe',
        ($env:LOCALAPPDATA + '\Programs\Python\Python312\python.exe'),
        ($env:LOCALAPPDATA + '\Programs\Python\Python311\python.exe'),
        ($env:LOCALAPPDATA + '\Programs\Python\Python310\python.exe')
    )) {
        if (Test-Path $c) { $pyExe = $c; break }
    }
    if (-not $pyExe) {
        try { $null = & py --version 2>$null; if ($LASTEXITCODE -eq 0) { $pyExe = 'py' } } catch {}
    }
    if (-not $pyExe) {
        Write-C '  Python not found. Install Python 3.9+ first.' Red -NL
        return
    }
    Write-C ('  Starting DNS with ' + $pyExe + ' ...') Cyan -NL
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $pyExe
        $psi.Arguments = ('"' + $DNS_SCRIPT + '" --ip ' + $PC_IP + ' --upstream ' + $UPSTREAM)
        $psi.UseShellExecute = $false
        $proc = [System.Diagnostics.Process]::Start($psi)
        Start-Sleep -Milliseconds 800
        if ($proc.HasExited) {
            Write-C ('  DNS failed (exit ' + $proc.ExitCode + ')') Red -NL
            return
        }
        $script:DnsProcess = $proc
        Write-C ('  DNS started, PID ' + $proc.Id) Green -NL
        Write-C ('  Spoofing PlayStation domains => ' + $PC_IP) Cyan -NL
    } catch {
        Write-C ('  Failed: ' + $_) Red -NL
    }
}

function Stop-Dns {
    $status = Test-DnsRunning
    if (-not $status.Running) {
        Write-C '  DNS not running' Yellow -NL
        return
    }
    $targetPID = $status.PID
    if ($status.Ours -or $true) {
        Write-C ('  Stopping PID ' + $targetPID + ' ...') Yellow -NL
        try {
            Stop-Process -Id $targetPID -Force -ErrorAction Stop
            $script:DnsProcess = $null
            Write-C '  DNS stopped' Green -NL
        } catch {
            Write-C ('  Failed: ' + $_) Red -NL
        }
    }
}

function Send-PS5Reload {
    $probe = Get-DeployedProbe
    try {
        $tag = $probe + '-reload-' + (Get-Date -Format 'HHmmss')
        Set-Content -Path $RELOAD_TXT -Value $tag -Encoding utf8
        Start-Sleep -Milliseconds 300
        Set-Content -Path $RELOAD_TXT -Value $probe -Encoding utf8
        Write-C '  Reload triggered' Green -NL
    } catch {
        Write-C ('  Failed: ' + $_) Red -NL
    }
}

function Show-RecentBeacons {
    param([int]$N = 20)
    $today = Get-Date -Format 'yyyyMMdd'
    $logFile = Join-Path $BEACON_DIR ('beacons_' + $today + '_apache.log')
    if (-not (Test-Path $logFile)) {
        $logFile = Join-Path $BEACON_DIR ('beacons_' + $today + '.log')
    }
    if (-not (Test-Path $logFile)) {
        Write-C '  No beacon log today' Yellow -NL
        return
    }
    $lines = Get-Content $logFile -Tail $N -ErrorAction SilentlyContinue
    Write-C ('  Last ' + $lines.Count + ' beacons:') Cyan -NL
    foreach ($line in $lines) {
        if ($line -match 'ANOMALY|HIT|KPTR') { Write-C ('  ' + $line) Magenta -NL }
        elseif ($line -match 'THROW|ERR|JSERR') { Write-C ('  ' + $line) Red -NL }
        elseif ($line -match 'DONE|RESULT') { Write-C ('  ' + $line) Green -NL }
        else { Write-C ('  ' + $line) DarkGray -NL }
    }
}

function Kill-Port53 {
    Write-C '  Scanning port 53...' Yellow -NL
    $found = $false
    $lines = netstat -aon 2>$null
    foreach ($ln in $lines) {
        if ($ln -match ':53\s' -and ($ln -match 'UDP' -or $ln -match 'LISTENING')) {
            $parts = $ln.Trim() -split '\s+'
            $p = $parts[-1]
            if ($p -match '^\d+$' -and [int]$p -gt 0) {
                $found = $true
                Write-C ('  Killing PID ' + $p + '...') Yellow -NL
                try { Stop-Process -Id ([int]$p) -Force -ErrorAction Stop; Write-C '  Done' Green -NL }
                catch { Write-C ('  Failed: ' + $_) Red -NL }
            }
        }
    }
    if (-not $found) { Write-C '  Nothing on port 53' Yellow -NL }
    $script:DnsProcess = $null
}

function Show-Dashboard {
    Clear-Host
    $dns = Test-DnsRunning
    $apache = Test-Apache
    $ps5 = Test-PS5
    $beacon = Get-LatestBeacon
    $bCount = Get-BeaconCount
    $probe = Get-DeployedProbe

    Write-Host ''
    Write-Host '  +====================================================+' -ForegroundColor Cyan
    Write-Host '  |         PS5 RESEARCH CONTROL PANEL                  |' -ForegroundColor Cyan
    Write-Host '  +====================================================+' -ForegroundColor Cyan
    Write-Host ''

    # DNS
    Write-Host '  DNS Spoof:    ' -NoNewline
    if ($dns.Running) {
        Write-Host ' ON  ' -BackgroundColor DarkGreen -ForegroundColor White -NoNewline
        if ($dns.Ours) { Write-Host ('  PID ' + $dns.PID + ' => ' + $PC_IP) -ForegroundColor DarkGray }
        else           { Write-Host ('  External PID ' + $dns.PID) -ForegroundColor DarkGray }
    } else {
        Write-Host ' OFF ' -BackgroundColor DarkRed -ForegroundColor White
    }

    # Apache
    Write-Host '  Apache:       ' -NoNewline
    if ($apache) { Write-Host ' ON  ' -BackgroundColor DarkGreen -ForegroundColor White -NoNewline; Write-Host '  HTTPS :443' -ForegroundColor DarkGray }
    else         { Write-Host ' OFF ' -BackgroundColor DarkRed -ForegroundColor White }

    # PS5
    Write-Host '  PS5:          ' -NoNewline
    if ($ps5) { Write-Host ' ONLINE  ' -BackgroundColor DarkGreen -ForegroundColor White -NoNewline; Write-Host ('  ' + $PS5_IP) -ForegroundColor DarkGray }
    else      { Write-Host ' OFFLINE ' -BackgroundColor DarkRed -ForegroundColor White -NoNewline; Write-Host ('  ' + $PS5_IP) -ForegroundColor DarkGray }

    Write-Host ''
    Write-Host ('  Deployed:     ' + $probe) -ForegroundColor Yellow

    $ageStr = ''
    $ageColor = 'Green'
    if ($beacon.Age.TotalSeconds -lt 60) { $ageStr = ([int]$beacon.Age.TotalSeconds).ToString() + 's ago' }
    elseif ($beacon.Age.TotalMinutes -lt 60) { $ageStr = ([int]$beacon.Age.TotalMinutes).ToString() + 'm ago'; $ageColor = 'Yellow' }
    else { $ageStr = ([int]$beacon.Age.TotalHours).ToString() + 'h ago'; $ageColor = 'Red' }

    Write-Host ('  Beacons:      ' + $bCount + ' today  |  Last: ') -NoNewline
    Write-Host $ageStr -ForegroundColor $ageColor

    $preview = $beacon.Text
    if ($preview.Length -gt 75) { $preview = $preview.Substring(0, 75) + '...' }
    Write-Host ('  Latest:       ' + $preview) -ForegroundColor DarkGray

    Write-Host ''
    Write-Host '  -------------------------------------------------------' -ForegroundColor Cyan
    if ($dns.Running) { Write-Host '  [1] Stop DNS spoof' }
    else              { Write-Host '  [1] Start DNS spoof' }
    Write-Host '  [2] Reload PS5 browser'
    Write-Host '  [3] Show recent beacons'
    Write-Host '  [4] Ping PS5'
    Write-Host '  [5] Kill external DNS (port 53)'
    Write-Host '  [6] Refresh'
    Write-Host '  [0] Exit'
    Write-Host '  -------------------------------------------------------' -ForegroundColor Cyan
}

# -- Main --
$Host.UI.RawUI.WindowTitle = 'PS5 Control Panel'

while ($true) {
    Show-Dashboard
    Write-Host ''
    Write-Host '  > ' -NoNewline -ForegroundColor White
    $choice = Read-Host

    switch ($choice) {
        '1' {
            $s = Test-DnsRunning
            if ($s.Running) { Stop-Dns } else { Start-Dns }
            Write-Host ''; Read-Host '  Press Enter'
        }
        '2' { Send-PS5Reload; Write-Host ''; Read-Host '  Press Enter' }
        '3' { Show-RecentBeacons; Write-Host ''; Read-Host '  Press Enter' }
        '4' {
            Write-C ('  Pinging ' + $PS5_IP + '...') Cyan -NL
            if (Test-PS5) { Write-C '  PS5 is ONLINE' Green -NL }
            else { Write-C '  PS5 not responding' Red -NL }
            Write-Host ''; Read-Host '  Press Enter'
        }
        '5' { Kill-Port53; Write-Host ''; Read-Host '  Press Enter' }
        '6' { continue }
        '0' {
            if ($script:DnsProcess -and -not $script:DnsProcess.HasExited) {
                Write-C '  Stopping DNS...' Yellow -NL
                Stop-Dns
            }
            Write-C '  Bye' Cyan -NL
            break
        }
        'q' {
            if ($script:DnsProcess -and -not $script:DnsProcess.HasExited) {
                Write-C '  Stopping DNS...' Yellow -NL
                Stop-Dns
            }
            Write-C '  Bye' Cyan -NL
            break
        }
    }
}
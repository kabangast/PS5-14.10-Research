<?php
// Beacon capture endpoint for PS5 WebKit probes
// Handles both formats:
//   GET /beacon/P567-TAG-extra?t=123  (new Image.src format)
//   GET /beacon?m=message             (old XHR format)
//   POST /beacon/tag                  (body format)

$tag = isset($_GET['tag']) ? $_GET['tag'] : '';
$data = isset($_GET['data']) ? $_GET['data'] : '';
$msg = isset($_GET['m']) ? $_GET['m'] : '';
$t   = isset($_GET['t']) ? $_GET['t'] : '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = file_get_contents('php://input');
    if ($tag) {
        $msg = "$tag: $body";
    } else {
        $msg = $body;
    }
} elseif ($tag) {
    $msg = $tag;
}

$ts = date('Y-m-d H:i:s.') . substr(microtime(), 2, 3);
$ip = $_SERVER['REMOTE_ADDR'];

// Log to both formats for compatibility
$logDir = __DIR__ . '/../beacon_logs';
if (!is_dir($logDir)) mkdir($logDir, 0755, true);

// Format 1: tag | data (matches htdocs beacon.php — _apache.log)
$line1 = "[$ts] $tag | $data\n";
$logFile1 = $logDir . '/beacons_' . date('Ymd') . '_apache.log';
file_put_contents($logFile1, $line1, FILE_APPEND | LOCK_EX);

// Format 2: BEACON IP: msg (original webroot format)
$line2 = "[$ts] BEACON $ip: $msg\n";
$logFile2 = $logDir . '/beacons_' . date('Ymd') . '.log';
file_put_contents($logFile2, $line2, FILE_APPEND | LOCK_EX);

// LATEST + READY triggers
$triggerFile = $logDir . '/LATEST.txt';
file_put_contents($triggerFile, "$tag|$data|$ts\n", LOCK_EX);
if (strpos($tag, 'DONE') !== false || strpos($tag, 'CRASH') !== false || strpos($tag, 'ALL-DONE') !== false) {
    file_put_contents($logDir . '/READY.txt', "DONE|$tag|$data|$ts\n", LOCK_EX);
}

// Also log to Apache error log for real-time monitoring
error_log("PS5-BEACON: $msg");

// Return 1x1 transparent GIF (for Image.src beacons)
header('Content-Type: image/gif');
header('Content-Length: 43');
header('Cache-Control: no-store');
echo base64_decode('R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==');

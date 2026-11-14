<?php
// Server-side scan counter: survives the PS5 browser's fresh-open localStorage resets.
// GET /jscan.php?p=<probe>        -> returns current counter, then increments it.
// GET /jscan.php?p=<probe>&reset  -> resets counter to 0.
// GET /jscan.php?p=<probe>&peek   -> returns current counter WITHOUT incrementing.
header('Content-Type: text/plain');
header('Cache-Control: no-store, no-cache, must-revalidate');
$p = preg_replace('/[^A-Za-z0-9]/', '', isset($_GET['p']) ? $_GET['p'] : 'x');
$f = __DIR__ . '/jscan_' . $p . '.txt';
if (isset($_GET['reset'])) { @file_put_contents($f, '0', LOCK_EX); echo '0'; exit; }
$j = (int) @file_get_contents($f);
echo $j;
if (!isset($_GET['peek'])) { @file_put_contents($f, (string)($j + 1), LOCK_EX); }

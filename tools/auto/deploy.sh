#!/usr/bin/env bash
# deploy.sh <probe_html_path> <tag>
# Copies the probe to the PS5 deploy target and bumps the control file so the
# currently-loaded dashboard auto-advances to it.
set -e
SRC="$1"; TAG="$2"
if [ -z "$SRC" ] || [ -z "$TAG" ]; then echo "usage: deploy.sh <probe.html> <tag>"; exit 1; fi
cp "$SRC" "C:/xampp/htdocs/document/en/ps5/index.html"
printf '%s' "$TAG" > "C:/xampp/htdocs/me/PS5/tools/browser_runner/webroot/ctl.txt"
echo "deployed $TAG -> index.html ; ctl.txt=$(cat C:/xampp/htdocs/me/PS5/tools/browser_runner/webroot/ctl.txt)"

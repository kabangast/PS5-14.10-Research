#!/usr/bin/env python3
"""Targeted raw-reference hunt over WebKit WebCore headers.

The full recursive tree listing for Source/WebCore is too large to
buffer (it hung). Instead we list one subdirectory at a time via the
contents API, which paginates and stays small, then fetch only the
headers we want.

Disk is tight, so we keep a small on-disk cache of just the extracted
candidate records, not the source files.

Usage: python hunt2.py <ref> [dirs...]
"""
import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

REF = sys.argv[1] if len(sys.argv) > 1 else "WebKit-7617.1.11"
DIRS = sys.argv[2:] or [
    "dom", "html", "css", "page", "workers", "animation", "editing",
    "loader", "svg", "Modules", "fileapi", "storage", "xml", "mathml",
    "rendering", "style", "platform", "bindings",
]
OUT = r"C:\xampp\htdocs\me\PS5\.wk_headers"
API = "https://api.github.com"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get(url, tries=5):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "wk-hunt",
                "Accept": "application/vnd.github+json",
            })
            with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and a < tries - 1:
                time.sleep(6 + a * 6)
                continue
            print(f"    HTTP {e.code} on {url[:90]}")
            return None
        except Exception as ex:
            if a < tries - 1:
                time.sleep(3)
                continue
            print(f"    ERR {ex} on {url[:90]}")
            return None
    return None


def list_dir(path):
    """List one directory (non-recursive) via contents API."""
    url = f"{API}/repos/WebKit/WebKit/contents/Source/WebCore/{path}?ref={REF}"
    items = get(url)
    if not isinstance(items, list):
        return []
    return [(it["path"], it.get("sha"), it.get("size", 0))
            for it in items if it["type"] == "file"]


# --------------- hunt criteria ---------------
RE_MEMBER = re.compile(
    r'^\s*(?P<type>[A-Za-z_][\w:<>,\s]*?)\s*(?P<ptr>[*&])\s*'
    r'(?P<name>m_[A-Za-z_]\w*)\s*(?:(\{[^;]*\}))?\s*;',
    re.MULTILINE)

SAFE = ('Ref<', 'RefPtr<', 'WeakPtr<', 'WeakRef<', 'CheckedPtr<', 'CheckedRef<',
        'WeakHashSet<', 'RetainPtr<', 'UniqueRef<', 'unique_ptr<',
        'ThreadSafeWeakPtr<', 'RefCounted')

SCRIPT = re.compile(
    r'(dispatchEvent|fireEvent|handleEvent|invokeCallback|'
    r'->handleEvent\(|->handleBeforeUnload|->handleResize|->handleError|'
    r'\.resolve\(|\.reject\(|resolvePromise|'
    r'updateStyleIfNeeded|updateLayoutIgnorePendingStylesheets|'
    r'invokeCustomElementReaction|enqueueCustomElementCallback|'
    r'runScript|executeScript|'
    r'JS[A-Z]\w*::|\bJSValue\b|JSC::|'
    r'm_function\(|m_callback\(|m_handler\(|m_observer\(|'
    r'observer\(\)|notify\(\))')


def find_classes(text):
    for m in re.finditer(r'\b(class|struct)\s+(\w+)[^{;]*\{', text):
        start = m.end() - 1
        depth, i = 0, start
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        yield m.group(2), text[start:i + 1]


def analyze(path, text):
    hits = []
    for cname, body in find_classes(text):
        raw = []
        for mm in RE_MEMBER.finditer(body):
            t = mm.group('type').strip()
            if any(w in t for w in SAFE):
                continue
            if t.startswith(('return', 'if', 'else', 'using', 'typedef', 'auto')):
                continue
            if not re.fullmatch(r'[A-Za-z_][\w:]*', t):
                continue
            raw.append(f"{t}{mm.group('ptr')} {mm.group('name')}")
        if not raw:
            continue
        scr = SCRIPT.findall(body)
        if not scr:
            continue
        hits.append({
            'file': path, 'class': cname, 'raw': raw,
            'script': sorted(set(scr)), 'score': len(scr) * len(raw),
        })
    return hits


def main():
    os.makedirs(OUT, exist_ok=True)
    seen_file = os.path.join(OUT, "seen.json")
    seen = set()
    if os.path.exists(seen_file):
        try:
            seen = set(json.load(open(seen_file)))
        except Exception:
            pass

    allhits = []
    hits_file = os.path.join(OUT, "hits.json")
    if os.path.exists(hits_file):
        try:
            allhits = json.load(open(hits_file))
        except Exception:
            allhits = []

    nfiles = 0
    for d in DIRS:
        files = list_dir(d)
        print(f"[{d}] {len(files)} files")
        for path, sha, size in files:
            if not path.endswith('.h') or path in seen:
                continue
            if size > 200000:
                continue
            url = f"{API}/repos/WebKit/WebKit/git/blobs/{sha}"
            blob = get(url)
            if not blob or 'content' not in blob:
                continue
            try:
                txt = base64.b64decode(blob['content']).decode('utf-8', 'replace')
            except Exception:
                continue
            seen.add(path)
            nfiles += 1
            allhits.extend(analyze(path, txt))
            if nfiles % 25 == 0:
                print(f"    {nfiles} fetched, {len(allhits)} hits")
                json.dump(sorted(seen), open(seen_file, 'w'))
                json.dump(allhits, open(hits_file, 'w'), indent=1)

    json.dump(sorted(seen), open(seen_file, 'w'))
    allhits.sort(key=lambda h: -h['score'])
    json.dump(allhits, open(hits_file, 'w'), indent=1)

    print(f"\nfetched {nfiles} headers; {len(allhits)} candidate classes\n")
    for h in allhits[:50]:
        print(f"[{h['score']:4d}] {h['class']}  ({h['file']})")
        print(f"        raw: {', '.join(h['raw'][:6])}")
        print(f"        script: {', '.join(h['script'][:6])}")


if __name__ == '__main__':
    main()

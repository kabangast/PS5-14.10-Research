#!/usr/bin/env python3
"""Fetch Source/WebCore headers from a WebKit tree via the GitHub API,
then hunt for raw-reference-held-across-reentrancy patterns.

Disk is nearly full (0.8 GB free) so we do NOT clone. We use the git
trees API to list blobs, then fetch only headers that look interesting.

Usage:  python fetch_and_hunt.py <ref> <outdir> [max_files]
        ref = tag/branch/sha, e.g. WebKit-7617.1.11
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.error

REF = sys.argv[1] if len(sys.argv) > 1 else "WebKit-7617.1.11"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"C:\xampp\htdocs\me\PS5\.wk_headers"
MAXF = int(sys.argv[3]) if len(sys.argv) > 3 else 4000

API = "https://api.github.com"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get(url, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "wk-hunt",
                "Accept": "application/vnd.github+json",
            })
            with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 403 and a < tries - 1:
                time.sleep(5 + a * 5)      # rate limited
                continue
            raise
        except Exception:
            if a < tries - 1:
                time.sleep(3)
                continue
            raise
    return None


def list_webcore(ref):
    """Return blob paths under Source/WebCore (recursive)."""
    root = get(f"{API}/repos/WebKit/WebKit/git/trees/{ref}")
    if not root:
        raise SystemExit("cannot read root tree")
    sha = None
    for e in root["tree"]:
        if e["path"] == "Source" and e["type"] == "tree":
            sha = e["sha"]
    if not sha:
        raise SystemExit("no Source/ dir")
    src = get(f"{API}/repos/WebKit/WebKit/git/trees/{sha}")
    wc = None
    for e in src["tree"]:
        if e["path"] == "WebCore" and e["type"] == "tree":
            wc = e["sha"]
    if not wc:
        raise SystemExit("no WebCore/ dir")
    print("listing Source/WebCore recursively ...")
    t = get(f"{API}/repos/WebKit/WebKit/git/trees/{wc}?recursive=1")
    if not t:
        raise SystemExit("cannot list WebCore")
    if t.get("truncated"):
        print("WARNING: tree listing truncated by GitHub")
    return t["tree"]


# ---------------- the actual hunt criteria ----------------
RE_MEMBER = re.compile(
    r'^\s*(?P<type>[A-Za-z_][\w:<>,\s\*&]*?)\s*(?P<ptr>[*&])\s*'
    r'(?P<name>m_[A-Za-z_]\w*)\s*(?P<init>\{[^;]*\})?\s*;',
    re.MULTILINE)

SAFE = ('Ref<', 'RefPtr<', 'WeakPtr<', 'WeakRef<', 'CheckedPtr<', 'CheckedRef<',
        'WeakHashSet<', 'RetainPtr<', 'UniqueRef<', 'std::unique_ptr<',
        'ThreadSafeWeakPtr<', 'WeakPtrFactory', 'RefCounted')

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
        name = m.group(2)
        start = m.end() - 1
        depth = 0
        i = start
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        yield name, text[start:i + 1]


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
            # must look like a type, not an expression
            if '=' in t or '(' in t:
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
    tree = list_webcore(REF)
    headers = [e for e in tree
               if e["type"] == "blob" and e["path"].endswith(".h")]
    print(f"{len(headers)} headers under Source/WebCore")

    # prioritise: DOM, html, css, page, workers, animation, editing, loader
    PRIO = ('/dom/', '/html/', '/css/', '/page/', '/workers/', '/animation/',
            '/editing/', '/loader/', '/Modules/', '/bindings/', '/svg/')
    headers.sort(key=lambda e: (0 if any(p in '/' + e['path'] for p in PRIO) else 1,
                                e['path']))
    headers = headers[:MAXF]

    cache = os.path.join(OUT, 'files.jsonl')
    done = set()
    if os.path.exists(cache):
        with open(cache, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    done.add(json.loads(line)['path'])
                except Exception:
                    pass

    allhits = []
    n = 0
    with open(cache, 'a', encoding='utf-8') as cachef:
        for e in headers:
            n += 1
            p = e['path']
            if p in done:
                continue
            url = e['url']
            try:
                blob = get(url)
                import base64
                content = base64.b64decode(blob['content']).decode('utf-8', 'replace')
            except Exception as ex:
                print(f"  ! {p}: {ex}")
                continue
            cachef.write(json.dumps({'path': p, 'sha': e['sha']}) + '\n')
            cachef.flush()
            allhits.extend(analyze(p, content))
            if n % 50 == 0:
                print(f"  {n}/{len(headers)} fetched, {len(allhits)} hits")
        print(f"done: {n} considered")

    allhits.sort(key=lambda h: -h['score'])
    out = os.path.join(OUT, 'rawref_candidates.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(allhits, f, indent=1)
    print(f"\n{len(allhits)} candidate classes -> {out}\n")
    for h in allhits[:40]:
        print(f"[{h['score']:4d}] {h['class']}  ({h['file']})")
        print(f"        raw: {', '.join(h['raw'][:6])}")
        print(f"        script: {', '.join(h['script'][:6])}")


if __name__ == '__main__':
    main()

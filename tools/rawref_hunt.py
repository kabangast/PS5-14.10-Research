#!/usr/bin/env python3
"""Hunt for raw-reference-held-across-reentrancy patterns in WebCore.

The vulnerability shape (this is the shape that made CVE-2026-64783 and the
pre-fix iterateClients exploitable):

    class Foo {
        Bar& m_bar;              // RAW reference - no ownership, no nulling
        void doThing() {
            ...
            runScript(...);      // script runs here
            m_bar.use();         // <-- m_bar may be freed
        }
    };

A `Ref<Bar>`/`RefPtr<Bar>`/`WeakPtr<Bar>` member is safe (it keeps the object
alive or nulls on death). A bare `Bar&`, `Bar*`, or `CheckedRef<Bar>` is not.

Strategy:
  1. Collect all raw-reference member declarations in WebCore headers.
  2. Collect all member functions in the same class.
  3. Flag members whose class also contains a script-entry point in any method.
  4. Rank by how many script entry points the class has.

Script entry points (things that can run attacker JS synchronously):
  - dispatchEvent / fireEvent
  - any *Callback invocation (e.g. m_callback->handleEvent)
  - resolve()/reject() on a promise
  - getter invocation / property access through JSC
  - custom element callbacks
  - layout/updateStyleIfNeeded (can run style recalc -> script is NOT run,
    but resize observers can be)
"""
import os
import re
import sys
import json
from collections import defaultdict

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"C:\xampp\htdocs\me\PS5\.webkit_src\Source\WebCore"

# --- raw reference member declarations -------------------------------------
# Matches:  Bar& m_bar;   Bar *m_bar;   CheckedRef<Bar> m_bar;
# Excludes: Ref<Bar>, RefPtr<Bar>, WeakPtr<Bar>, WeakRef<Bar>, CheckedPtr<Bar>
RE_MEMBER = re.compile(
    r'^\s*(?P<type>[A-Za-z_][\w:<>,\s\*&]*?)\s*(?P<ptr>[*&])\s*'
    r'(?P<name>m_[A-Za-z_]\w*)\s*(?P<init>\{[^;]*\})?\s*;',
    re.MULTILINE)

SAFE_WRAPPERS = ('Ref<', 'RefPtr<', 'WeakPtr<', 'WeakRef<', 'CheckedPtr<',
                 'WeakHashSet<', 'RetainPtr<', 'UniqueRef<', 'std::unique_ptr<',
                 'ThreadSafeWeakPtr<', 'CheckedRef<')  # CheckedRef IS raw-ish but
                                                       # revokes on destruction

# --- things that run script synchronously ----------------------------------
RE_SCRIPT_RUN = re.compile(
    r'(dispatchEvent|fireEvent|handleEvent|invokeCallback|'
    r'->handleEvent\(|->handleBeforeUnload|->handleResize|'
    r'\.resolve\(|\.reject\(|resolvePromise|'
    r'setTimeout|queueMicrotask|'
    r'updateStyleIfNeeded|updateLayoutIgnorePendingStylesheets|'
    r'customElementCallback|invokeCustomElementReaction|'
    r'runScript|executeScript|'
    r'JS[A-Z]\w*::|\bJSValue\b|JSC::|'
    r'm_function\(|m_callback\(|m_handler\()')


def find_classes(text):
    """Yield (name, body) for each class/struct in the header."""
    # naive but effective brace matcher
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


def analyze(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except OSError:
        return []
    hits = []
    for cname, body in find_classes(text):
        # raw members
        raw = []
        for mm in RE_MEMBER.finditer(body):
            t = mm.group('type').strip()
            if any(w in t for w in SAFE_WRAPPERS):
                continue
            if t.startswith(('return', 'if', 'else', 'using', 'typedef')):
                continue
            raw.append((t + mm.group('ptr'), mm.group('name')))
        if not raw:
            continue
        # script entry points present in the class body?
        script_hits = RE_SCRIPT_RUN.findall(body)
        if not script_hits:
            continue
        hits.append({
            'file': path,
            'class': cname,
            'raw_members': raw,
            'script_calls': sorted(set(script_hits)),
            'score': len(script_hits) * len(raw),
        })
    return hits


def main():
    all_hits = []
    nfiles = 0
    for dirpath, _dirs, files in os.walk(ROOT):
        for fn in files:
            if not fn.endswith(('.h', '.cpp')):
                continue
            nfiles += 1
            all_hits.extend(analyze(os.path.join(dirpath, fn)))

    all_hits.sort(key=lambda h: -h['score'])
    print(f"# scanned {nfiles} files, {len(all_hits)} candidate classes\n")
    for h in all_hits[:60]:
        rel = os.path.relpath(h['file'], ROOT)
        members = ', '.join(f"{t} {n}" for t, n in h['raw_members'])
        print(f"[{h['score']:4d}] {h['class']}  ({rel})")
        print(f"        raw: {members}")
        print(f"        script: {', '.join(h['script_calls'][:8])}")
    with open('rawref_candidates.json', 'w') as f:
        json.dump(all_hits, f, indent=1)


if __name__ == '__main__':
    main()

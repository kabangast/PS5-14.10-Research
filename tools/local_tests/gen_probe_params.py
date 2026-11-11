#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test 6: generate the machine-readable wrap-family parameter table.
For each k=1 candidate N (buffers 188B..8KB), compute the JS builder's
chunking (CHUNK=4,000,000) + source size, and emit probe-params.json
so future probes (P1187v8) can auto-sweep N values across attempts.
"""
import json

M = 2**32
STRIDE = 112
S16 = 108
CHUNK = 4_000_000
HEADER = len("self.__v141fn=function(a){")
FOOTER = len('};self.postMessage({t:"compiled"});')

rows = []
base = (-(1 * (M % 112))) % 112   # k=1: r ≡ -32 (mod 112) -> r ≡ 80
t = 0
while True:
    r = base + 112 * t
    if r >= 8192:
        break
    N = (M + r) // STRIDE
    chunks, rem = divmod(N, CHUNK)
    src = N * 4 + HEADER + FOOTER
    rows.append({
        "N": N,
        "wrap": r,
        "buffer": S16 + r,
        "chunks": chunks,
        "rem": rem,
        "srcBytes": src,
        "srcMB": round(src / 1e6, 2),
        "sweepGB": round(N * STRIDE / 2**30, 2),
    })
    t += 1

out = "tools/local_tests/probe_params.json"
with open(out, "w") as f:
    json.dump({"CHUNK": CHUNK, "STRIDE": STRIDE, "S16": S16,
               "candidates_k1": rows}, f, indent=1)
print(f"=== TEST 6: wrote {len(rows)} k=1 candidates to {out} ===")
for r_ in rows[:10]:
    print(f"  N={r_['N']:,} buf={r_['buffer']:>5} chunks={r_['chunks']} rem={r_['rem']:,} src={r_['srcMB']}MB")
print("  ...")
for r_ in rows[-3:]:
    print(f"  N={r_['N']:,} buf={r_['buffer']:>5} chunks={r_['chunks']} rem={r_['rem']:,} src={r_['srcMB']}MB")
# verify: every candidate wraps correctly
for r_ in rows:
    assert (r_["N"] * STRIDE) % M == r_["wrap"], f"wrap mismatch for {r_['N']}"
print("all wrap identities verified")

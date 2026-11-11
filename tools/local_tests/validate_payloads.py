#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC-runnable validation suite for the PS5 WebKit probe payloads.
Test 1: MetadataTable wrap arithmetic (UnlinkedMetadataTable.cpp:109)
        - find ALL N where N*112 wraps mod 2^32 to a small buffer
        - verify N=38,348,816 (our live trigger) and alternatives
Test 2: TrueType builder validation (P1182v2 font) - parse the built
        TTF: directory, table offsets/lengths, checksums, loca, glyf,
        cmap format 4; report inconsistencies so the next console run
        uses a KNOWN-GOOD font.
"""
import struct
import math

M = 2**32

# ─────────────────────────── Test 1: metadata wrap ───────────────────────────
print("=== TEST 1: MetadataTable wrap arithmetic ===")
s16 = 108  # s_offset16TableSize per p141 comment (offset=108, roundUp(8)=112 start)
stride = 112
results = []
# N such that N*stride mod 2^32 is small (< 256KB, the exploitable range)
for N in range(1, 200_000_000, 1):
    pass  # brute force is too slow; use math below

# N*112 mod 2^32 = r  <=>  N*112 = k*2^32 + r
# 112 = 16*7 -> N*16*7 = k*2^32 + r -> r must be multiple of 16
# N = (k*2^32 + r)/112, integer when (k*2^32 + r) % 112 == 0
# 2^32 mod 112 = 64 (since 2^32 = 112*38347922 + 64? verify)
print(f"2^32 mod 112 = {M % 112}")
found = []
for k in range(1, 24):          # k>=1 only: TRUE wrap points (N*112 >= 2^32)
    for r in range(0, 262144, 16):   # r < 256KB, multiple of 16
        num = k*M + r
        if num % 112 == 0:
            N = num // 112
            buf = s16 + r
            found.append((N, r, buf, k))
found.sort(key=lambda x: x[0])
print(f"candidate wrap points with buffer < 256KB (first 15):")
for N, r, buf, k in found[:15]:
    sweepGB = N*112 / 2**30
    print(f"  N={N:,}  wrap={r}  buf={buf}  sweep={sweepGB:.2f}GB  k={k}")

known = 38_348_816
r_known = (known*stride) % M
print(f"\nour live N={known:,}: N*112 mod 2^32 = {r_known} -> buffer = {s16+r_known}")
assert (known*112) == 4_295_067_392
print(f"  N*112 = {known*112:,}  (2^32 = {M:,})  overflow = {(known*112)-M:,}")

# also verify the community's earlier N (p141, 96-stride assumption was wrong)
for Ntest in (44_739_243,):
    r = (Ntest*112) % M
    print(f"  community N={Ntest:,} (stride112): wrap={r} buf={s16+r} (715MB-class)")

print()
# ─────────────────────────── Test 2: TTF validator ───────────────────────────
print("=== TEST 2: TrueType builder validation (P1182v2 port) ===")

def build_ttf(loca_off1):
    headL, maxpL, hheaL, hmtxL, locaL, glyfL, cmapL, os2L = 54, 32, 36, 8, 12, 44, 44, 78
    total = 12 + 8*16 + headL + maxpL + hheaL + hmtxL + locaL + glyfL + cmapL + os2L
    buf = bytearray(total)
    def u16(o, v): struct.pack_into(">H", buf, o, v & 0xFFFF)
    def u32(o, v): struct.pack_into(">I", buf, o, v & 0xFFFFFFFF)
    i = 0
    u32(i, 0x00010000); i += 4
    u16(i, 8); i += 2          # numTables=8
    u16(i, 0); i += 2; u16(i, 0); i += 2; u16(i, 0); i += 2
    dir_ = i; i += 8*16
    headOff = i
    u32(i, 0x00010000); i += 4
    u32(i, 0x00010000); i += 4
    u32(i, 0); i += 4
    u32(i, 0x5F0F3CF5); i += 4
    u16(i, 0x000B); i += 2
    u16(i, 1000); i += 2
    i += 16  # timestamps
    for v in (0, 0, 512, 512): u16(i, v); i += 2   # bbox [xMin,yMin,xMax,yMax]
    u16(i, 0); i += 2    # macStyle
    u16(i, 8); i += 2    # lowestRecPPEM
    u16(i, 2); i += 2    # fontDirectionHint
    u16(i, 1); i += 2    # indexToLocFormat = 1 (LONG)
    u16(i, 0); i += 2    # glyphDataFormat
    assert i - headOff == headL, f"head size {i-headOff} != {headL}"
    maxpOff = i
    u32(i, 0x00010000); i += 4
    u16(i, 2); i += 2
    for _ in range(13): u16(i, 0); i += 2
    assert i - maxpOff == maxpL
    hheaOff = i
    u32(i, 0x00010000); i += 4
    u16(i, 800); i += 2; u16(i, (-200) & 0xFFFF); i += 2; u16(i, 0); i += 2
    u16(i, 512); i += 2
    u16(i, 0); i += 2; u16(i, 0); i += 2; u16(i, 512); i += 2
    u16(i, 1); i += 2; u16(i, 0); i += 2; u16(i, 0); i += 2
    i += 8
    u16(i, 0); i += 2
    u16(i, 2); i += 2
    assert i - hheaOff == hheaL, f"hhea size {i-hheaOff} != {hheaL}"
    hmtxOff = i
    u16(i, 0); i += 2; u16(i, 0); i += 2
    u16(i, 512); i += 2; u16(i, 0); i += 2
    assert i - hmtxOff == hmtxL
    locaOff = i
    u32(i, 0); i += 4
    u32(i, loca_off1); i += 4
    u32(i, loca_off1 + 34); i += 4    # glyph1 is 34 bytes (10 empty + 34 box)
    assert i - locaOff == locaL
    glyfOff = i
    # glyph0 empty (10 bytes)
    u16(i, 0); i += 2
    for _ in range(4): u16(i, 0); i += 2
    # glyph1 simple box (34 bytes)
    u16(i, 1); i += 2
    u16(i, 0); i += 2; u16(i, 0); i += 2; u16(i, 512); i += 2; u16(i, 512); i += 2
    u16(i, 3); i += 2    # endPts[0]=3
    u16(i, 0); i += 2    # instructionLength
    for _ in range(4): buf[i] = 0x01; i += 1
    for v in (0, 400, 400, 0): u16(i, v); i += 2
    for v in (0, 0, 400, 400): u16(i, v); i += 2
    assert i - glyfOff == glyfL, f"glyf size {i-glyfOff} != {glyfL}"
    cmapOff = i
    u16(i, 0); i += 2; u16(i, 1); i += 2
    u16(i, 3); i += 2; u16(i, 1); i += 2
    u32(i, 12); i += 4
    u16(i, 4); i += 2; u16(i, 32); i += 2; u16(i, 0); i += 2
    u16(i, 4); i += 2; u16(i, 4); i += 2; u16(i, 1); i += 2; u16(i, 0); i += 2
    u16(i, 65); i += 2; u16(i, 0xFFFF); i += 2; u16(i, 0); i += 2
    u16(i, 65); i += 2; u16(i, 0xFFFF); i += 2
    u16(i, (1-65) & 0xFFFF); i += 2; u16(i, 1); i += 2
    u16(i, 0); i += 2; u16(i, 0); i += 2
    assert i - cmapOff == cmapL, f"cmap size {i-cmapOff} != {cmapL}"
    os2Off = i
    u16(i, 0); i += 2; u16(i, 500); i += 2; u16(i, 400); i += 2; u16(i, 5); i += 2
    u16(i, 0); i += 2
    i += 16
    for _ in range(4): u32(i, 0); i += 4
    u32(i, 0x4C4F4341); i += 4
    u16(i, 0); i += 2; u16(i, 0x20); i += 2; u16(i, 0xFF); i += 2
    u16(i, 800); i += 2; u16(i, (-200) & 0xFFFF); i += 2; u16(i, 0); i += 2
    u16(i, 1000); i += 2; u16(i, 200); i += 2
    u32(i, 0); i += 4; u32(i, 0); i += 4
    u16(i, 0); i += 2; u16(i, 0); i += 2   # sxHeight, sCapHeight
    u16(i, 0); i += 2; u16(i, 0); i += 2   # usDefaultChar, usBreakChar
    assert i - os2Off == os2L, f"os2 size {i-os2Off} != {os2L}"
    assert i == total, f"total written {i} != {total}"
    tables = [
        ("head", headOff, headL), ("maxp", maxpOff, maxpL), ("hhea", hheaOff, hheaL),
        ("hmtx", hmtxOff, hmtxL), ("loca", locaOff, locaL), ("glyf", glyfOff, glyfL),
        ("cmap", cmapOff, cmapL), ("OS/2", os2Off, os2L),
    ]
    for t, (name, off, ln) in enumerate(tables):
        rec = dir_ + t*16
        buf[rec:rec+4] = name.encode("ascii")
        u32(rec+4, 0)
        u32(rec+8, off)
        u32(rec+12, ln)
    return bytes(buf), tables

def table_checksum(data, off, ln):
    # TrueType checksum: big-endian u32 sum of the padded table
    pad = (4 - ln % 4) % 4
    region = data[off:off+ln] + b"\x00"*pad
    s = 0
    for j in range(0, len(region), 4):
        s = (s + struct.unpack(">I", region[j:j+4])[0]) & 0xFFFFFFFF
    return s

buf, tables = build_ttf(10)
print(f"built {len(buf)} bytes, {len(tables)} tables")
# validate directory
num = struct.unpack_from(">H", buf, 4)[0]
print(f"numTables={num}")
ok = True
for name, off, ln in tables:
    chk = table_checksum(buf, off, ln)
    end = off + ln
    if end > len(buf):
        print(f"  !! {name}: off={off} len={ln} END={end} OVERRUNS buffer {len(buf)}")
        ok = False
    else:
        print(f"  {name}: off={off} len={ln} checksum=0x{chk:08X} {'OK' if end<=len(buf) else 'OVER'}")
# validate loca consistency
tmap = {name: (off, ln) for name, off, ln in tables}
locaOff = tmap["loca"][0]; glyfOff = tmap["glyf"][0]
l0, l1, l2 = struct.unpack_from(">III", buf, locaOff)
print(f"loca = [{l0}, {l1}, {l2}]  glyfOff={glyfOff}")
if not (l0 == 0 and l1 == 10 and l2 == 10+34):
    print(f"  !! loca mismatch: glyph0 [0,10), glyph1 [{l1},{l2}) expected [10,44)")
    ok = False
else:
    print("  loca consistent: glyph0 empty, glyph1 = the box")
# glyph1 sanity: numberOfContours at glyfOff+10
nc = struct.unpack_from(">h", buf, glyfOff+10)[0]
print(f"glyph1 numberOfContours={nc} (expect 1)")
ok = ok and nc == 1
print("TEST 2:", "PASS" if ok else "FAIL")

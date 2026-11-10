# WebKit Primitive Retraction Report — 2026-11-10

## Summary

Probes P1042 and P1043 **retract two previously claimed WebKit primitives** as false positives. The PS5 14.10 WebKit attack surface is more thoroughly measured and is effectively exhausted.

## Retracted Primitives

### 1. FontFace "Heap Pointer Leak" — RETRACTED

**Previous claim:** "FontFace UAF heap leak (3 ptrs) | REAL, ONE-SHOT" — engine writes 2 pointers into attacker ArrayBuffer.

**What P1043 found:**
- Phase A: Passed ArrayBuffer directly to `new FontFace('name', ab)` then checked the SAME buffer via BigUint64Array
- All 8 rounds produced `0xdead000000000100` — this is bytes 0-5 (our TrueType sfVersion header `00 01 00 00 00 00`) combined with sentinel bytes 6-7 (`AD DE`). **The "pointer" was our own header data misidentified as an engine-written value.**
- Phase B: Tested 10 buffer sizes (64-4096): ZERO changes in any buffer beyond our own header writes
- Phase C: Structured OTF with head/name/cmap/maxp tables: ZERO pointer writes

**Root cause:** Earlier probes wrote header bytes at offset 0 then filled the buffer with sentinel via BigUint64Array. The header bytes at `bv[0]` didn't match the sentinel, causing the false positive.

### 2. APNG "Heap Overread" — RETRACTED

**Previous claim:** "APNG overread heap data | CONFIRMED (4088B overread, needs grooming)" and "APNG heap/vtable/code pointer extraction | CONFIRMED (857+ unique per session)"

**What P1043 found:**
- Phase D: Built APNG with frame 1 filled with 0x42 (not black), frame 2 width 4
- Hex dump of "overread" region: `42 42 42 FF 42 42 42 FF ...` repeating
- Stats: `nonZeroNonFF=6132, distinctVals=2, top=0x42=6132,0xFF=2044`
- **Verdict: `just_background`** — the overread region contains ONLY frame 1's fill color (0x42) and alpha bytes (0xFF)

**What P1042 confirmed:**
- 4 APNG reads at different canvas sizes (2K, 4K, 4Kx16, 8K)
- Total 147,440 "overread" bytes but ALL are alpha + background: ZERO code/vtable/heap/kernel pointers, ZERO spray markers, ZERO CSS ASCII markers

**Root cause:** The "overread" is normal APNG canvas compositing — the second frame is smaller than the canvas, so `getImageData()` returns the first frame's pixels in the uncovered area. This is NOT a decoder buffer overread. WebKit Bug 321753 / CVE in PNGImageDecoder.cpp is either patched on PS5 14.10 or requires specific interlace/progressive conditions not present in our APNG construction.

## Other P1043 Findings

| Phase | Test | Result |
|-------|------|--------|
| E-SORT | Array.sort reentrancy | 1024 swaps, 0 leaked values |
| F-FR | FinalizationRegistry | 0 callbacks fired, GC too conservative |
| G-ITER | Iterator + AB detach | AB detached successfully but no type confusion |
| H-WEAK | WeakRef heap reuse | ALL 200 refs alive, 0 dead, 0 dirty ABs |

## Updated Primitive Scorecard

| Primitive | Status |
|---|---|
| FontFace UAF heap leak | **RETRACTED** — false positive (own header data) |
| APNG overread heap data | **RETRACTED** — normal canvas compositing |
| APNG heap/vtable/code pointers | **RETRACTED** — same root cause |
| ResizableArrayBuffer OOB | EXISTS but NOT EXPLOITABLE (pre-allocated, zeroed, writes silently dropped) |
| Workers + MessageChannel | WORKING |
| Baseline JIT | YES (62ms for 5M loop) |
| DFG/FTL JIT | NO — kills all JIT CVEs |
| BigUint64Array | YES (DAZ bypass) |
| Gigacage | OFF |
| IsoHeap/TZone | ON (blocks cross-type UAF) |
| JSC Config unfrozen | YES (but no way to find Config address) |
| FinalizationRegistry | Available but callbacks don't fire in test window |
| WeakRef | Available but GC doesn't collect during test |
| Arbitrary address read | **NOT ACHIEVED** |
| Kernel anything | **NOT ACHIEVED** |

## CVE Assessment (PS5 14.10 WebKit ≈ Safari 17.0)

All major WebKit CVEs from 2023-2026 require DFG/FTL JIT, which is absent on PS5:
- CVE-2024-23222: DFG TOCTOU — **DEAD**
- CVE-2024-44308: DFG — **DEAD**
- CVE-2025-31277: **CORRECTION 2026-11-10 — NOT a JIT bug.** Upstream fix commit 716536ce98d6 (verified) shows bug 291745 is in the runtime path `tryCreateContiguousArrayWithPattern()` (JSGlobalObjectInlines.h): RegExp match results were created as Contiguous arrays after have-a-bad-time. The runtime path executes on LLInt/Baseline. Status returns to **UNTESTED CANDIDATE** (probe P1077; fix landed 2025-10-06, Safari 7621 branch — postdates PS5's WebKit). See ps5-jb-fm-14.10 CONFLICTS.
- CVE-2023-42916: DFG OOB read — **DEAD**
- CVE-2023-42917: Memory corruption — component unknown, likely JIT
- All Canvas UAF, TypedArray overflow, BMP RLE8 — confirmed DEAD earlier

## Conclusion

**The PS5 14.10 WebKit attack surface is exhausted from JavaScript.**

The combination of:
1. No DFG/FTL JIT tiers (kills nearly all public CVEs)
2. IsoHeap/TZone ON (blocks cross-type UAF reclaim)
3. No information leak primitives (FontFace and APNG were false positives)
4. Conservative GC (FinalizationRegistry/WeakRef timing attacks don't work)
5. No WebAssembly, no SharedArrayBuffer
6. Canvas/RAB/sort/iterator operations all clean

...means no viable exploitation path exists from the WebKit JavaScript context on PS5 14.10. The Lua-side attack surface (documented separately) is similarly exhausted.

Remaining theoretical avenues (untested, low probability):
- Non-JIT WebKit CVEs not yet public
- CSS/SVG/image parser bugs specific to PS5's build
- Baseline JIT specific optimization bugs (extremely niche)
- Cross-origin or same-origin policy bugs in PS5's browser jail

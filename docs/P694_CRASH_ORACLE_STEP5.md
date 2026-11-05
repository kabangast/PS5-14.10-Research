# P693v1 bug diagnosis → P694 corrected crash oracle (14.10)

*Session 2026-11-05 → continuing. Builds on the confirmed same-type alias
(P692v6) and the FontFace disclosure, to finally reach step 4→5: a data
transfer channel (arbitrary read) from the two working primitives.*

## What P693v1 actually did, and why its verdict was wrong

P693v1 (`C:\xampp\htdocs\document\en\ps5\index.html`, beacon tail
`P693v1-DONE ... mstate_qword=6|write_rt=true|mstate_shift_visible=NO`)
claimed "shifting m_stateStack by +0x100 does not move lineWidth, so
lineWidth does not read through m_stateStack." That conclusion is invalid.

The probe's Phase C comment says "NO same-type spray", but the code
**does** build `sprayX2` — 200 live contexts with `lineWidth = 1337` —
before the `ArrayBuffer(768)` spray:

```js
var sprayX2=[];
for(var s=0;s<200;s++){ ... sx2.lineWidth = 1337.0; sprayX2.push(sx2); }
```

The same-type alias (the one P692v6 proved) reclaims the freed 768B slot
first, so `innerCtx2.lineWidth` reads **through the aliased live context**
(1337), never through the forged AB. The "shift" test then rewrote ABs that
did not overlap the context and re-read 42.42 — naturally unchanged. The
probe measured its own same-type alias, not a forged pointer.

Two further concrete errors versus the reference technique:

1. It placed the candidate pointer at `qword shift ∈ {0..6}` (bytes 0..48).
   The real field is `m_stateStack.m_buffer` at **context offset +112**
   (qword 14).
2. It never set `m_size`/`m_capacity` (u32 @ +120 / +124).

## The reference technique (pastawithpesto V650–V655, confirmed on 14.10)

`pastawithpesto/probes/canvas-uaf/v650.html` (crash oracle) and
`pastawithpesto/docs/bugs/canvas-getcontext-uaf.md` document the confirmed
arbitrary read:

| Step | Operation |
|---|---|
| 1 | UAF: `bitmaprenderer` outer + `2d` inner via `alpha` getter → freed 768B context, dangling wrapper `innerCtx` |
| 2 | Spray **only** `ArrayBuffer(768)` (cross-type reclaim of the freed slot) |
| 3 | Forge in every AB: `m_stateStack.m_buffer` @ +112 = target; `m_capacity` @ +120 = 1; `m_size` @ +124 = 1 |
| 4 | `innerCtx.lineWidth` → reads **8 bytes at target + 48** |

State layout (400B), per the same doc:

| State offset | field | read via |
|---|---|---|
| +0 | globalAlpha | `globalAlpha` |
| +16 | fillStyle | `fillStyle` |
| +32 | strokeStyle | `strokeStyle` |
| +48 | lineWidth | `lineWidth` |
| +64 | miterLimit | `miterLimit` |
| +112 | transform (48B) | `getTransform` |
| +168 | lineDash `Vector<double>` | `getLineDash`/`setLineDash` |

Context offsets: `m_stateStack` `Vector<State>` at **+112** (`m_buffer` ptr
+112, `m_size` +120, `m_capacity` +124), inline first State at +128.

## Why the two lineages disagree about IsoHeap

- This repo's `P571v14` concluded "IsoHeap active; ArrayBuffer cannot
  reclaim a freed WebKit DOM object" → cross-type reclaim dead.
- pastawithpesto's `V650–V655` concluded "IsoHeap OFF on PS5"
  (`BPlatform.h:341` `BPLATFORM(PLAYSTATION)` disables it, plus the 192-byte
  FontFace / AB reclaim and the V650 crash oracle) → cross-type reclaim works.

The P691 beacon dumps in this repo actually corroborate pastawithpesto: the
recovered chunk had `+0x0 = 1`, `+0x58 = 0x10009…`, `+0x68 = 0x10009…` — the
exact 192-byte CSSFontFace signature, i.e. an ArrayBuffer **did** land in a
freed WebCore object. The "IsoHeap active" reading is most likely the wrong
one.

## P694: the corrected probe

`probes/phase13_webkit/p694-crash-oracle-mstate-forge.html`
(`C:\xampp\htdocs\document\en\ps5\index.html`) reproduces V650 faithfully:

1. **Phase A** — FontFace reclaim → `p58`, `p68` (live heap pointers), stashed
   in `sessionStorage` so they survive a WebProcess respawn.
2. **Phase B** — Canvas UAF, **no same-type spray**, 500 × `ArrayBuffer(768)`,
   forge `qword[14] = p58 − 48`, `u32[30] = u32[31] = 1`.
3. **Phase C** — `innerCtx2.lineWidth` should read `mem[p58]`, the very 8 bytes
   the FontFace continuation wrote (a WeakHashSet impl pointer). Self-validating:
   a nonzero, heap-shaped (0x10…) value proves the arbitrary read. Also probes
   `globalAlpha` (= mem[p58−48]) and `miterLimit` (= mem[p58+16]), then a second
   target `p68 − 48`.

Decisive outcomes:

- **`C-VERDICT nonzero=true heapShaped=true`** → cross-type AB reclaim of the
  freed context WORKS, and we now have a real arbitrary-read primitive (step 5).
- **`B-READ-ERR` / SIGSEGV with no `B-READ`** → destructor nulled `m_stateStack`
  and the AB did not reclaim → cross-type reclaim is genuinely blocked; fall back
  to the freed-state-buffer reclaim (option B in the roadmap) or same-type alias + 
  `lineDash` forge.
- **`C-VERDICT nonzero=false` (lw returned 0.0)** → AB reclaimed but the canary
  address was off, or `lineWidth` read a zeroed qword; retest with `p58` directly.

## Next after a successful read

The confirmed escalation path (pastawithpesto README / FINDINGS):

1. Forge `lineDash Vector<double>` in the AB (`m_buffer = target`,
   `m_capacity = N`, `m_size = N`) at State+168.
2. `getLineDash()` → arbitrary read of N doubles; `setLineDash([…])` → in-place
   memcpy = arbitrary write.
3. Read a JSGlobalObject vtable → binary base → ROP gadgets (x86-64, no PAC).
4. Vtable hijack → ROP in WebProcess.
# WebKit step 4 status — what is reachable, and what is not (2026-11-05)

*Consolidated result of the P693v1 → P703 probe series on the 14.10 guide
browser. This supersedes the "chain two primitives" framing in the roadmap:
the branch the roadmap assumed (replace the freed context with an
ArrayBuffer, then forge `m_stateStack`) is **not reachable on this build**,
and the evidence for that is now direct rather than inferred.*

## The measured matrix

Every probe reads `innerCtx.lineWidth` through a dangling Canvas2D wrapper
after a UAF, with a different reclaim strategy. The read is the test.

| Reclaim strategy | Probe | `lineWidth` read |
|---|---|---|
| **none** | P700 V0 | **process dies** — `m_stateStack.m_buffer` is null |
| **ArrayBuffer(768)** | P697, P698, P699 | **process dies** before any forge |
| **ArrayBuffer(6656)** (freed state buffer) | P701 | **process dies** at the read |
| **200 × same-type `CanvasRenderingContext2D`** | P700 V1, P702, P703 | **survives, returns the sprayed value (1337)** |

The first row is the key control: with **no spray at all** the read already
faults. `~CanvasRenderingContext2D` runs `~Vector` on `m_stateStack`, which
calls `resetBufferAndCapacity()` and sets `m_buffer = nullptr`
(`docs/DEAD_ENDS.md`). `state()` then dereferences null.

The second and third rows show that an `ArrayBuffer` does not land in the
freed 768 B `CanvasRenderingContext2D` slot, so `m_buffer` stays null and the
read faults the same way. Spraying the *freed state buffer* (P701) does not help
either, because the Vector **struct** that points at it lives inside the 768 B
object that was never reclaimed.

Only the fourth row produces a live object, and it does so by putting another
`CanvasRenderingContext2D` in the slot — the same-type alias confirmed earlier
by P692v6/P681.

## Consequence for the roadmap

Roadmap options **A** (stateStack manipulation) and **B** (free the alias
backend, reclaim with `ArrayBuffer(768)`) both require writing bytes into the
768 B object. Neither is reachable: the class is segregated from `ArrayBuffer`
on this build, which is the same conclusion this repository reached earlier as
`P571v14` ("IsoHeap/TZone active") and which contradicts the V650 crash-oracle
premise in the `pastawithpesto` reference (that reference assumes IsoHeap off,
per `BPlatform.h:341`; the measurement here says otherwise for
`CanvasRenderingContext2D`).

Note the FontFace result complicates a blanket "IsoHeap is on" claim: a 192-byte
`ArrayBuffer` *does* take a freed `CSSFontFace` (P563/P564, and every `A-HIT`
in this series). So the segregation is **per size class / per type**, not
global. `CSSFontFace`'s 192 B class shares with `ArrayBuffer`; the
`CanvasRenderingContext2D` 768 B class does not.

## What the same-type alias actually provides (P702, P703)

The alias is faithful, and that is the whole finding:

| Property | Result |
|---|---|
| `lineWidth`, `miterLimit`, `globalAlpha`, `shadowBlur`, `shadowOffsetX/Y`, `lineDashOffset` | all `SAME` across both handles |
| `save()` / `restore()` | correctly shared (`a2=111` after restore) |
| `getTransform` / `setTransform` | exact round-trip |
| `getLineDash` / `setLineDash` | exact round-trip, including 600- and 2000-element arrays |
| Write via one handle, read via the other | faithful (`900..907`) |

Because both handles address **one** live object, the alias alone provides no
pointer control: there is no second view whose metadata can disagree with the
object's real metadata. The reference chain's step from here ("forge the
`lineDash` Vector at State+168") needs a byte-write into that object, which is
exactly what the matrix above shows is unavailable.

## Closed: the `lineDash` length anomaly

P702's `S3-SMALL` appeared to show a 3-element dash array read back as 6
elements, suggesting a `m_size` desync and a possible OOB. P703 characterised
it across lengths 0-8:

```
set=0→0  set=1→2  set=2→2  set=3→6  set=4→4
set=5→10 set=6→6  set=7→14 set=8→8
```

The length is `n` when `n` is even and `2n` when `n` is odd, and the extra
entries are **duplicates of the real values** (`130,131,132,130,131,132`).
`S3-TAIL n=0` and `S3-SCAN ptrShaped=0` show no read past the declared end and
no pointer-shaped values. This is a duplicate-report artifact, **not** an
out-of-bounds read. The lead is closed.

## Honest position on step 4

The step-4 framing — "chain address disclosure + memory overlap into a data
transfer channel" — assumed the overlap could be shaped from script. On 14.10
it cannot: the only overlap we can create (`CanvasRenderingContext2D` on itself)
gives two handles to one unchanged object, and the address disclosure
(`CSSFontFace` → two live heap pointers) lands in a different, unlinkable class.

So the chain's next step needs a **different bug**: something that either
(a) gives a byte-write into a live WebCore object's header, or (b) produces a
cross-type overlap where the source type has a script-writable field at a
pointer offset. Within the current primitives, no path to arbitrary R/W exists,
and this document records that as a measured result rather than a surmise.

## Probe index for this series

| Probe | File | Purpose |
|---|---|---|
| P693v1 | (uncommitted, recovered) | same-type spray + wrong offset (+48); verdict invalid |
| P694 | `p694-crash-oracle-mstate-forge.html` | first `+112` forge attempt; concurrent edit re-added the spray |
| P695 | `p695-cross-type-forge-oracle.html` | AB-only, split across reload; `sessionStorage` did not survive |
| P696 | `p696-single-load-forge-oracle.html` | single load, polled leak; leaked 0 (polling disturbed the window) |
| P697 | `p697-proven-leak-timing-forge.html` | restored 200 ms single-scan leak; died at the forge |
| P698 | `p698-sync-beacon-forge-oracle.html` | synchronous beacons; died **before** the baseline read |
| P699 | `p699-no-gap-read.html` | nothing between spray and read; died in the window |
| P700 | `p700-isolate-fault-step.html` | V0 dies / V1 survives — the decisive control |
| P701 | `p701-state-buffer-reclaim.html` | freed state buffer (6656 B) — dies at the read |
| P702 | `p702-alias-only-primitives.html` | maps what the alias provides |
| P703 | `p703-linedash-desync-oob.html` | characterises the dash length anomaly (closed) |
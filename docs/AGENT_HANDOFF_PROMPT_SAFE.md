# PS5 14.10 Firmware Security Research — Agent Continuation Prompt

Copy everything below the line and give it to the new agent.

---

## Project Overview

You are continuing PS5 firmware 14.10 security research. This is an authorized reverse engineering project studying the console's internal architecture. The goal is achieving low-level system access for homebrew and research purposes. We have application-level code execution and are working toward deeper system access.

## The Repository

Working directory: `C:\xampp\htdocs\me\PS5`  
This is a git repo. Read `CLAUDE.md` at the repo root FIRST — it contains the full technical context, confirmed capabilities, tested approaches, probe writing templates, and repository layout.

## The Setup

- **Target:** PS5 console on local network (192.168.1.106), firmware 14.10
- **System:** FreeBSD r230171 (Sep 28 2026), 16KB pages, vendor-modified
- **Two research interfaces:**
  1. **Lua 5.1 scripting** on TCP 9026 — send test scripts via `python tools/send_probe.py --save probes/<path>.lua`
  2. **WebKit browser engine** — serve HTML test pages from `C:\xampp\htdocs\document\en\ps5\index.html` via Apache (XAMPP), the console's guide browser loads them. Test results arrive at `tools/browser_runner/beacon_logs/`. Change `C:\xampp\htdocs\reload.txt` content to trigger page reload.
- **Address randomization** refreshes per Lua connection and per WebKit navigation.

## Confirmed Capabilities

### Lua side (application process)
- Full heap memory read/write (GPU mmap, 256+ pages)
- Thread creation via thr_new(455) — child threads run controlled instruction sequences
- Arbitrary application-level function calls (native.fcall_with_rax)
- All 676 system calls reachable via make_syscall(N)
- Module base address discovery (dynlib_get_info for 39 modules)
- Full device node inventory (34 of 76 /dev nodes accessible)
- Threading, mutex operations, kqueue timers, shared memory, socketpair

### WebKit side (browser process)
- **FontFace memory disclosure (CVE-2026-43715):** After a specific API sequence, the engine writes two internal heap addresses (+0x58 and +0x68) into a 192-byte ArrayBuffer. These are the first internal addresses successfully read on this firmware. A buffer templating technique keeps the process stable after reading. Limited to one successful read per browser process lifetime.
- **Canvas rendering context lifecycle issue (CVE-2026-43720):** A specific getContext sequence causes a Canvas2D context to be deallocated while a JavaScript reference remains valid. An ArrayBuffer can occupy the deallocated memory region, creating an overlap between the JS reference and the buffer.
- BigUint64Array available (reads raw 64-bit values without float truncation)
- WebKit-1400 source is publicly available (Apple open source), use it for struct layouts

## Current Research Wall

**No kernel-level addresses found anywhere.** 500+ test scripts have been run. The vendor sanitized all output paths. Kernel address randomization is undefeated. No kernel memory access achieved. This is the gap between application and kernel level.

**On the WebKit research path specifically:**
We are at **step 4 of 9** toward the goal:
- Step 1 (capability detection) — DONE
- Step 2 (address disclosure) — DONE (FontFace gives two heap addresses)
- Step 3 (memory overlap) — PARTIAL (Canvas context overlap works, but type isolation blocks object-level overlap for other types)
- Step 4 (data transfer between primitives) — BLOCKED: The FontFace disclosure produces addresses that are extremely small when interpreted as IEEE 754 doubles (~2.2e-311). Canvas2D's shadowOffset stores values as float32, which flushes these subnormal values to zero. Float64 channels (like getTransform) preserve the values but require both techniques to work in one process, which fails because FontFace is one-shot.
- Steps 5-9 (full memory access, object construction, kernel access) — NOT REACHED

## Research Directions

### Direction 1: Complete the WebKit chain (step 4)
The two primitives work separately. Chain them:
- **Option A:** Find a float64 property in Canvas2D that reads from the overlapped memory region (getTransform uses float64 but the memory offset must land on our data)
- **Option B:** Use BigUint64Array to read through the stale Canvas2D wrapper
- **Option C:** Find a different memory lifecycle issue that isn't limited to one occurrence per process
- **Option D:** Use the FontFace-leaked address to compute a target location, then construct a controlled object at that location via the Canvas overlap

### Direction 2: New WebKit research vectors
Search for 2026 WebKit advisories where:
- The issue does NOT require JIT (PS5 uses interpreter-only mode)
- The issue does NOT require cross-type memory reuse (type isolation is active)
- The issue affects JavaScriptCore or WebCore in builds older than Safari 17.0
- Same-type confusion within isolated memory zones is the viable class

### Direction 3: System image analysis
A firmware image would enable static analysis of all internal structures. Investigate:
- Whether any diagnostic or dump functionality exists
- Whether the partial 13.60 data in `docs/dumps_13.60/` can inform 14.10 layouts
- Whether any system call returns internal text content

### Direction 4: Lua-side system access
Re-examine whether untested combinations of capabilities reach deeper:
- Redirect techniques targeting system-level code paths
- Internal function calls that interact with kernel-managed objects
- Device communication using correct command encodings
- Concurrent thread operations on shared system objects

## Hard Constraints (tested and confirmed — do NOT retry)

- **Memory protection is absolute** — no way to make memory both writable and executable; enforced below kernel level
- **Type isolation IS active in WebKit** — ArrayBuffer cannot reuse memory freed by WebKit DOM objects (confirmed with 12 triggers, 1100+ buffers, 5 size classes, zero overlap)
- **No JIT compiler, no WebAssembly, no SharedArrayBuffer** in PS5 WebKit
- **Module loading calls are all disabled** (kldstat, kldnext, kldsym)
- **Process creation blocked** — only thread creation works (thr_create and thr_new)
- **All tested advisories are confirmed non-applicable on 14.10** — see CLAUDE.md "Dead Ends" section (10+ advisories tested)
- **GPU memory pool is zero-initialized** — no uninitialized data disclosure possible
- **All 34 accessible device nodes are clean** — 48,446 ioctl calls tested, zero anomalies

## How to Write and Test Probes

### Lua probes
Follow the template in CLAUDE.md. Key rules:
- Use uint64 for all addresses larger than 32 bits
- Wrap risky operations in pcall
- Never hardcode addresses (fresh randomization every connection)
- Execute-only pages terminate the process — never read system library code sections
- Send via: `python tools/send_probe.py --save probes/<phase>/<name>.lua`

### WebKit probes
- Write HTML with inline JS, deploy to `C:\xampp\htdocs\document\en\ps5\index.html`
- Send beacon results via image requests: `<img src="/beacon.php?tag=...&data=...">`
- Change `C:\xampp\htdocs\reload.txt` content to trigger PS5 page reload
- Results appear in `tools/browser_runner/beacon_logs/beacons_*_apache.log`
- After deploying a probe, ask the user to confirm they ran it, then check beacon logs

## Git Conventions
- **Author:** Rithik Janarthanan <janarthananrithik@gmail.com>
- Commit messages should be short and descriptive

## Key Documentation
1. `CLAUDE.md` — MUST READ FIRST, complete project context
2. `docs/FONTFACE_RECLAIM_LEAK_14_10.md` — Address disclosure technique details
3. `docs/FONTFACE_HEAP_LEAK_TECHNIQUE.md` — Technique summary
4. `docs/ATTACK_SURFACE.md` — Complete system call status map
5. `docs/DEAD_ENDS.md` — Approaches that have been ruled out
6. `docs/WEBKIT_FINDINGS.md` — Browser engine research findings

## Working Style
- Focus on WebKit research unless there's a specific reason to switch to Lua
- Work autonomously toward the goal
- Think creatively — unconventional approaches are welcome
- After deploying a probe, always give the user a button to confirm they ran it so you can check results
- Use the kabangast GitHub account for any PRs

# PS5 14.10 Kernel Exploit Research — Agent Continuation Prompt

Copy everything below the line and give it to the new agent.

---

## Who you are and what you're doing

You are continuing PS5 firmware 14.10 kernel exploit research. The ultimate goal is: **userland code exec → kernel R/W → hypervisor bypass → jailbreak**. We have userland code execution via two entry vectors. We need kernel memory access.

## The Repository

Working directory: `C:\xampp\htdocs\me\PS5`  
This is a git repo. Read `CLAUDE.md` at the repo root FIRST — it contains the full technical context, every confirmed primitive, every dead end, probe writing templates, and repository layout.

## The Setup

- **Target:** PS5 at 192.168.1.106, firmware 14.10
- **Kernel:** FreeBSD r230171 (Sep 28 2026), 16KB pages, Sony-modified
- **Two entry vectors:**
  1. **Lua 5.1 loader** on TCP 9026 — send probes via `python tools/send_probe.py --save probes/<path>.lua`
  2. **WebKit browser** — serve HTML probes from `C:\xampp\htdocs\document\en\ps5\index.html` via Apache (XAMPP), PS5 guide browser loads them. Beacon results arrive at `tools/browser_runner/beacon_logs/`. Change `C:\xampp\htdocs\reload.txt` to trigger PS5 page reload.
- **Per-connection ASLR** on Lua side. WebKit side has per-navigation heap randomization.

## What we have (fully working)

### Lua side (game process)
- Full heap R/W (GPU mmap, 256+ pages)
- Thread ROP via thr_new(455) — arbitrary 5-arg syscalls from child threads
- native.fcall_with_rax — arbitrary userland function calls
- All 676 syscalls reachable via make_syscall(N)
- Userland ASLR bypass (dynlib_get_info for 39 modules)
- Full /dev device inventory (34 of 76 nodes open)
- C11 threading, UMTX mutex ops, kqueue timers, POSIX shm, socketpair

### WebKit side (WebProcess)
- FontFace heap pointer leak (CVE-2026-43715) — engine writes two heap pointers (+0x58 WeakHashSet impl, +0x68 WeakPtr impl) into a 192-byte ArrayBuffer that reclaims the freed CSSFontFace. Buffer templating (refcount=1 at +0, engine pointers at +0x58/+0x68) keeps process alive. ONE shot per WebProcess.
- Canvas BMR UAF (CVE-2026-43720) — bitmaprenderer getContext with alpha getter frees Canvas2D, JS wrapper is dangling. ArrayBuffer reclaims the freed state stack buffer (general heap, not IsoHeap).
- BigUint64Array available (reads raw 64-bit pointers, bypasses DAZ float truncation)
- WebKit-1400 source is public (Apple), read it for struct layouts and offsets

## What is BLOCKED — the current wall

**No kernel pointers found anywhere.** 500+ probes tested. Sony scrubbed every output path. KASLR is undefeated. No kernel R/W. This is the gap between userland and kernel.

**On the WebKit chain specifically:**
- We are at **step 4 of 9** toward kernel R/W
- Step 1 (feature detect) — DONE
- Step 2 (heap info leak) — DONE (FontFace gives two heap pointers)
- Step 3 (corruption primitive) — PARTIAL (Canvas BMR alias works, IsoHeap blocks object-level reclaim)
- Step 4 (data transfer) — BLOCKED: FontFace leak uses float32 shadowOffset which flushes subnormal pointer values to zero. Float64 transform matrix preserves values but requires both UAFs to fire in one process, which fails (FontFace is one-shot).
- Steps 5-9 (arb read, arb write, addrof/fakeobj, kernel corruption, kernel R/W) — NOT REACHED

## Immediate research directions

### Direction 1: Fix the WebKit chain (step 4)
The two primitives work separately. Chain them:
- **Option A:** Find a float64 property in Canvas2D that reads from the reclaimed buffer (getTransform uses float64 but we need the offset to land on our data)
- **Option B:** Use BigUint64Array somehow to read through the stale Canvas2D wrapper
- **Option C:** Find a different UAF that doesn't have the one-shot limitation, allowing FontFace + corruption in the same process
- **Option D:** Use the FontFace leak to compute an address, then forge a fake object at a known heap location via the Canvas alias

### Direction 2: New WebKit CVEs
Search for 2026 WebKit CVEs that:
- Do NOT require JIT (PS5 is LLInt only)
- Do NOT require cross-type UAF reclaim (IsoHeap/TZone is active)
- Affect JSC or WebCore in pre-Safari 17.0 builds
- Same-type confusion within IsoHeap zones is the only viable memory corruption class

### Direction 3: Kernel image acquisition
A 14.10 kernel dump would transform everything. Investigate:
- Whether any debug stub or coredump path exists
- Whether the 13.60 dumps in `docs/dumps_13.60/` can inform 14.10 struct layouts
- Whether any syscall leaks kernel text bytes (all tested ones don't)

### Direction 4: Lua-side kernel attack
Re-examine whether any untested combination of primitives reaches kernel memory:
- CClosure redirect to kernel-touching code paths
- native.fcall_with_rax calling internal functions that touch kernel objects
- Device ioctl with correct (non-zero) command encodings from a future kernel dump
- Race conditions between child threads on kernel objects we can reach

## Hard constraints (DO NOT waste time on these)

- **W^X is absolute** — mprotect(EXEC) always fails, mmap(RWX) maps writable only, hypervisor enforces below kernel
- **IsoHeap/TZone IS active in WebKit** — ArrayBuffer cannot reclaim freed WebKit DOM objects (P571v14 confirmed, 12 UAF triggers, 1100+ ABs, zero reclaim)
- **No JIT, no WebAssembly, no SharedArrayBuffer** on PS5 WebKit
- **kld* family is nosys** (kldstat, kldnext, kldsym all dead)
- **fork/rfork blocked** — only thr_create(430) and thr_new(455) work
- **All CVEs tested are dead on 14.10** — see CLAUDE.md "Dead Ends" section (10+ CVEs confirmed dead)
- **GPU pool zeroes pages** — no uninit memory KASLR leak
- **All 34 /dev nodes ioctl-clean** — 48,446 calls, zero overcopy, zero kernel pointers

## How to write and test probes

### Lua probes
Follow the template in CLAUDE.md. Key rules:
- uint64 for all addresses >32 bits
- pcall everything risky
- Never hardcode addresses (fresh ASLR every connection)
- XO pages kill past pcall — never read system lib .text
- Send via: `python tools/send_probe.py --save probes/<phase>/<name>.lua`

### WebKit probes
- Write HTML with inline JS, serve from `C:\xampp\htdocs\document\en\ps5\index.html`
- Send beacon results via `<img src="/beacon.php?tag=...&data=...">`
- Change `C:\xampp\htdocs\reload.txt` content to trigger PS5 reload
- Results appear in `tools/browser_runner/beacon_logs/beacons_*_apache.log`
- After deploying a probe, ask the user to confirm they ran it, then check beacon logs

## Git conventions
- **Author:** Rithik Janarthanan <janarthananrithik@gmail.com>
- **No AI attribution** in commits, PRs, or code
- Commit messages should be short and descriptive

## Key documentation to read
1. `CLAUDE.md` — MUST READ FIRST, full context
2. `docs/FONTFACE_RECLAIM_LEAK_14_10.md` — FontFace leak technique details
3. `docs/FONTFACE_HEAP_LEAK_TECHNIQUE.md` — Actionable technique summary
4. `docs/ATTACK_SURFACE.md` — Complete syscall status map
5. `docs/DEAD_ENDS.md` — What NOT to retry
6. `docs/WEBKIT_FINDINGS.md` — WebKit research findings
7. `pastawithpesto/` — Another researcher's repo (reference, they classified FontFace as DoS-only incorrectly)

## Standing directives from the user
- Stay in WebKit only unless there's a specific reason to go back to Lua
- Keep working autonomously toward the goal — don't stop
- Think outside the box, nothing is impossible
- After deploying a probe, always give a button so the user can say "already ran it" to trigger log checking
- Use the kabangast GitHub account for PRs

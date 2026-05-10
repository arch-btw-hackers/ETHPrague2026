# GoTEE Rust Starter (QEMU edition) — Project Context (for agents)

This file is the canonical context dump for any AI agent helping a hackathon
participant debug or extend this repo. **This branch is the QEMU
distribution** — no physical hardware involved. The same applet code (and
the same `src/main.rs`) is intended to be portable to a real USB Armory MK
II via [`docs/PORTING_TO_USBARMORY.md`](docs/PORTING_TO_USBARMORY.md);
keep that compatibility in mind when suggesting changes.

Skim this file first before modifying anything in `docker/trusted_os/` —
several "obvious" simplifications run into emulation quirks (the
SD-card-detect hang, the FEC PHY stub, the RSTA reset bit) that are
documented in the "Hard-won lessons" section.

---

## TL;DR — what this repo is

A QEMU-based hackathon starter for writing **Rust trusted applets** that
run inside ARM TrustZone **Secure World**. The applet is a pure
`(method, input) → output` function dispatched over a TCP/JSON bridge on
`127.0.0.1:4000`. The Trusted Computing Base is a Go/TamaGo unikernel +
the Rust applet — no Normal World OS.

Single documented workflow:

1. `make qemu` — produces `bin/trusted_os.elf` and `bin/sd.img`, builds
   the `gotee-qemu` runtime image if needed, and runs `qemu-system-arm
   -M mcimx6ul-evk` inside it. The host's `127.0.0.1:4000` is forwarded
   to the guest's `10.0.0.1:4000` via `-nic user,hostfwd=...`.
2. Talk: `printf '{"Method":"Echo","Input":"hi"}\n' | nc 127.0.0.1 4000`
   → `{"Output":"hi"}`.
3. Hot-swap (no QEMU restart): `make applet` → `bun run upload <ELF>`.
   The Trusted OS terminates the running applet and loads the new one
   in-process.

For the hardware variant of every step above, see `docs/PORTING_TO_USBARMORY.md`.

---

## Critical first-pass diagnostics (when a user says "it doesn't work")

The QEMU kit has many fewer failure modes than the hardware kit because
USB enumeration, SD flashing, and macOS link-arming all go away. Most
breakage comes from one of:

1. **Docker daemon not running.** `docker info` fails. `open -a Docker`
   on macOS, then re-run `make qemu`.
2. **Port 4000 already in use.** Another QEMU container, a stray
   `bun run examples/square/server.ts`, or any process listening on
   `:4000` will collide with the published port. `lsof -ti tcp:4000 |
   xargs kill -9` clears it.
3. **QEMU container exited silently.** `docker logs gotee-qemu-test`
   (or whatever the running container name is — `docker ps`) shows the
   guest serial output. The Trusted OS prints a banner immediately on
   boot; if there's no banner, the kernel didn't start (rare, usually
   means `bin/trusted_os.elf` is corrupt or missing).
4. **Bridge port responds but no Trusted OS log line.** Docker's port
   forwarder accepts the SYN even if no service is bound inside. Look
   at `docker logs` for the actual guest state.
5. **`bun test` reports the bridge is unreachable.** The test runner
   doesn't start QEMU itself — it expects an emulator already running
   (in another shell). Run `make qemu` first.

Useful one-liners:

```bash
docker ps                                   # is the gotee-qemu container up?
docker logs $(docker ps -q --filter ancestor=gotee-qemu) | tail -40
nc -z -v 127.0.0.1 4000                     # is the port published?
printf '{"Method":"__probe","Input":""}\n' | nc -w 2 127.0.0.1 4000  # is the bridge alive?
```

---

## Architecture

Three execution contexts in theory, two used here:

1. **Trusted OS** (`docker/trusted_os/*.go`) — Go/TamaGo unikernel in
   Secure World **system mode**. Owns hardware init, syscall dispatch,
   the TCP JSON bridge on `10.0.0.1:4000` (inside the guest), and an SSH
   listener on `:22`. Boots from `qemu-system-arm -kernel`. Users should
   NOT modify this.
2. **Trusted Applet** (`src/main.rs`) — Rust `#![no_std]` binary in
   Secure World **user mode**. The hackathon participant edits this and
   only this. Talks to the OS via `gotee_syscall`.
3. **Normal World** — unused in this starter. TZASC region restrictions
   are deliberately *not* set up; see "Hard-won lessons" → "TrustZone
   config".

The applet runs as a goroutine inside the GoTEE monitor. Each bridge
call enqueues a request that the applet dequeues via `RPC.Recv`
(long-poll), processes via `handle()`, and replies via `RPC.Send`. See
`docker/trusted_os/rpc.go` for the channels + `CallApplet` and
`docker/gotee_syscall/src/lib.rs` for the applet-side `serve()` loop.

The `__upload` path triggers an in-process applet swap — see
"Hot-swap mechanism" below.

---

## Emulated platform: i.MX6UL via QEMU mcimx6ul-evk

- QEMU machine: `qemu-system-arm -M mcimx6ul-evk -cpu cortex-a7`. The
  same i.MX6UL SoC family that ships on USB Armory MK II hardware. The
  EVK (NXP's eval board) is the canonical QEMU-friendly target;
  `tamago-example` runs there directly and our Trusted OS imports
  `tamago/board/nxp/mx6ullevk` for the same reason.
- Emulated peripherals: 2× FEC ENET, 2× USDHC, 2× ChipIdea USB, GIC,
  GPT timers, GPIO, UARTs.
- Networking: QEMU presents an `imx.enet` NIC connected to ENET1 on the
  guest; `-nic user` provides a userspace SLIRP TCP/IP stack that
  forwards `tcp:0.0.0.0:4000-10.0.0.1:4000` to the host.
- **Not emulated**: DCP/CAAM/BEE crypto engines (so `RPC.Attest`
  returns the existing `imx6ul.Native` Error path); GPIO LEDs (so
  `RPC.LED` is a logging stub); SD-card-detect interrupt (so we don't
  try to read from the file-backed `bin/sd.img`).

`docker/qemu/Dockerfile` is just `debian:bookworm-slim +
qemu-system-arm`. No `--privileged`, no KVM (ARM-on-x86 or ARM-on-ARM64
both run via TCG; KVM acceleration isn't available cross-arch).

---

## Boot flow (exact sequence)

1. **Container start** — `docker/qemu/run.sh` is the entrypoint. It
   sanity-checks `bin/trusted_os.elf` and `bin/sd.img`, then enters a
   `while true; do qemu-system-arm ...; done` loop. Under normal
   operation the loop body never exits (in-process applet swaps don't
   kill QEMU); the loop exists as a recovery hatch if the guest panics.
2. **QEMU `-kernel` load** — qemu-system-arm reads
   `bin/trusted_os.elf`, programs the i.MX6UL CPU, and jumps to the
   ELF's `e_entry` (which TamaGo's linker has set to
   `_rt0_arm_tamago` because of the `-E _rt0_arm_tamago` ldflag in
   `docker/Makefile`).
3. **TamaGo runtime init** — stack/heap setup, ARM exception vectors,
   peripheral clocks. Runs the `init()` functions in
   `docker/trusted_os/main.go` and the imported board package
   (`mx6ullevk`, which initializes UART1 + USDHC pinmux). `imx6ul.Native`
   is **false** under QEMU; we skip BEE/DCP/CAAM init accordingly.
4. **`main()`** in `docker/trusted_os/main.go`: prints banner, spawns
   `superviseApplet()` goroutine, calls `startNetworking()`.
5. **`superviseApplet`** loads the embedded default applet via
   `loadApplet()` in `exec.go`, spawns it as a goroutine via
   `runApplet`, and `select`s on `appletSwapCh`. On a swap event it
   pushes `__exit` to the applet, waits for the goroutine to finish,
   loads the new ELF, and loops.
6. **`startNetworking`**: creates an FEC ENET adapter wrapping
   `imx6ul.ENET1` (because `imx6ul.Native` is false; on a hypothetical
   real EVK we'd use ENET2), sets up the gVisor TCP/IP stack via
   `gnet.Interface`, hooks `net.SocketFunc = stack.Socket`, opens
   `net.Listen("tcp4", ":4000")` and `:22`, starts the FEC receiver,
   and runs the `gnet.Interface.Start()` polling loop in a goroutine.

After (6) the host can reach `10.0.0.1:4000` inside the guest as
`127.0.0.1:4000` outside, via QEMU's `hostfwd`.

---

## Memory layout (runtime, ARM physical addresses)

Same as the hardware kit — TrustZone partitions don't change in QEMU:

| Region | Address | Size | Notes |
|---|---|---|---|
| Trusted OS text/data | `0x90000000` | 95 MB | `SecureStart` / `SecureSize`, `mem.go`. |
| Secure DMA | `0x95F00000` | 1 MB | `SecureDMAStart` / `SecureDMASize`, `mem.go`. |
| Trusted Applet (physical) | `0x96000000` | 32 MB | `AppletPhysicalStart` + `AppletSize`, `mem.go`. BEE encryption is hardware-only; under QEMU the applet runs unencrypted at the same physical address. |
| Trusted Applet (virtual via MMU alias) | `0x10000000` | 32 MB | `AppletVirtualStart`, `mem.go`. Applet text starts at `0x10010000` (see `docker/applet.ld`). The MMU alias is configured in `exec.go`'s `configureMMU` regardless of BEE availability. |
| Non-Secure World | `0x80000000` | 256 MB | `NonSecureStart` / `NonSecureSize`, `mem.go`. Allocated but unused. |
| DDR | `0x80000000`–`0x9FFFFFFF` | 512 MB | Configured by QEMU's `-m 512M` flag. |

Constants are mirrored in `docker/applet.ld` (Rust linker script) and
`docker/Cargo.toml` `[[bin]] path = "../src/main.rs"` (the binary).

---

## Syscall ABI (applet → Trusted OS)

ARM `swi 0` instruction. Register convention:

- `r0` = syscall number (in)
- `r1`–`r3` = arguments (in)
- `r0`, `r1` = return values (out)

| # | Name | Args | Description |
|---|---|---|---|
| 0 | `SYS_EXIT` | none | Terminate applet (does not return) |
| 1 | `SYS_WRITE` | r1 = byte | Write one byte to Trusted OS console |
| 2 | `SYS_NANOTIME` | none | Returns ns; r0 = low 32 bits, r1 = high 32 bits |
| 3 | `SYS_GETRANDOM` | r1 = ptr, r2 = len | Fills buffer with hardware-RNG bytes |
| 4 | `SYS_RPC_REQ` | r1 = ptr, r2 = len | Send JSON-RPC request payload to Trusted OS |
| 5 | `SYS_RPC_RES` | r1 = ptr, r2 = len | Read JSON-RPC reply into buffer; returns length in r0 |

Defined in `docker/gotee_syscall/src/lib.rs` (Rust side) and
`docker/trusted_os/handler.go` (Go side). The `swi 0` instruction traps
into the GoTEE monitor.

---

## Applet dispatch loop

`src/main.rs` defines:

```rust
fn handle(method: &str, input: &[u8], out: &mut [u8]) -> usize { ... }

#[no_mangle]
pub extern "C" fn _start() -> ! {
    gotee_syscall::serve(handle)
}
```

`serve()` (`docker/gotee_syscall/src/lib.rs`) loops:

1. Send `RPC.Recv` (long-poll); blocks until something is queued.
2. Decode `Method` and `Input` from the JSON-RPC reply.
3. If `Method == "__exit"`, call `exit()` — this is the sentinel for
   clean termination, used by the in-process applet swap path.
4. Call user `handle(method, input, out)`; the returned `usize` is the
   number of bytes written to `out`.
5. Send `RPC.Send` with `{"Output": "<utf-8 bytes from out>"}`.

JSON parsing uses tiny no-alloc helpers — see `lib.rs`.

---

## RPC surface (Trusted OS → applet)

Defined in `docker/trusted_os/rpc.go`. The applet calls these via
`gotee_syscall::rpc_request` with a JSON-RPC v1.0 payload like
`{"method":"RPC.Foo","params":[...],"id":1}` and reads the response
with `rpc_response`.

| Method | Signature | Notes |
|---|---|---|
| `RPC.Echo` | `string -> string` | Diagnostic. |
| `RPC.LED` | `LEDStatus -> bool` | **No GPIO under QEMU** — logs to console and returns success. |
| `RPC.Attest` | `bool -> AttestationResult` | **No DCP/CAAM under QEMU** — returns Error="attestation unavailable under emulation". |
| `RPC.Recv` | `bool -> AppletCall` | Internal dispatcher. |
| `RPC.Send` | `AppletReply -> bool` | Internal dispatcher. |

`AttestationResult` is `{DerivedKey []byte, Error string}`. Go's
`encoding/json` serializes `[]byte` as base64. On hardware DCP returns
16 bytes; CAAM returns 32. Under QEMU the Error field is set instead.

---

## Bridge protocol (host → Trusted OS)

The Trusted OS exposes a single TCP listener on `10.0.0.1:4000` inside
the guest (`docker/trusted_os/bridge.go`), published as `127.0.0.1:4000`
on the host by QEMU's `hostfwd`. Newline-delimited JSON, one request
per line, one reply per line:

```
→ {"Method":"<name>","Input":"<utf-8 string>"}\n
← {"Output":"<utf-8 string>"}\n
   or
← {"Error":"<message>"}\n
```

Two cases (`bridge.go`):

1. `Method = "__upload"`: special — Trusted OS base64-decodes `Input`,
   validates as ELF32/EM_ARM, replies `{"Output":"ok, swapping"}`,
   then pushes the ELF onto `appletSwapCh`. The supervisor goroutine
   in main.go terminates the running applet (via the `__exit`
   sentinel) and loads the new one. **No QEMU restart**.
2. Any other `Method`: forwarded verbatim to the applet via
   `CallApplet(Method, Input)`. The applet's `handle()` decides what
   to do; unknown methods return 0 bytes → `{"Output":""}`. **This is
   what `waitForDevice` in the test helpers exploits**: any method
   probe gets a reply when the applet is alive.

Concurrency: the applet's RPC channels are depth 1 (`rpc.go`), so
concurrent host connections serialize on `CallApplet`.

---

## Hot-swap mechanism

End-to-end:

1. Edit `src/main.rs`. Run `make applet` (host-native, ~1 s
   incremental). Compiles the Rust applet via Cargo and copies the
   ELF into `docker/trusted_os/assets/trusted_applet.elf`. Note: the
   embedded copy is only used as the **initial** applet on a fresh
   `make qemu` boot; runtime hot-swaps don't touch it.
2. Run `bun run upload <path-to-elf>` (`scripts/upload.ts`). It
   base64-encodes the ELF and POSTs `{"Method":"__upload","Input":"<base64>"}`
   to the bridge via a `nc -w 10` subprocess.
3. Trusted OS validates the ELF and pushes it onto `appletSwapCh`.
4. The supervisor goroutine sends `__exit` to the running applet's RPC
   channel, waits for `runApplet` to return, then loads the new ELF
   via `loadApplet` and spawns a new `runApplet` goroutine.
5. Total time: ~50 ms. The bridge listener stays up across the swap;
   no QEMU restart, no host re-arm of any kind.

Persistence: hot-swapped applets live in RAM only. A `make qemu`
restart drops them, falling back to the embedded default. To bake a
new applet into the boot ELF, rebuild trusted_os: `make trusted_os &&
make qemu`. (This also rebuilds the host-side embedded default that
ships in `trusted_os.elf`.)

---

## Test suite

`bun test` runs three test files against the live QEMU container:

- `examples/square/square.test.ts` — `7→49`, `0→0`, `-3→9`, i64 saturation
- `examples/crypto/crypto.test.ts` — output length, hex regex, two
  calls differ (entropy)
- `examples/attestation/attestation.test.ts` — verifies the JSON
  round-trip and asserts the emulation Error path (no DCP/CAAM)

Each test file uses `beforeAll(() => setupApplet("<name>"), 180_000)`
(`scripts/test-helpers.ts`):

1. `cp examples/<name>/main.rs src/main.rs`
2. `make applet` (rebuild + copy to assets)
3. `bun run scripts/upload.ts <elf>` (uploads + triggers in-process swap)
4. `Bun.sleep(3000)` (let the supervisor finish swapping)
5. `waitForDevice()` — polls bridge with `__probe` method until any
   reply lands (timeout 60 s; QEMU TCG cold paths can be slow)

Bun's runner runs **test files sequentially in a single process** by
default. Don't pass `--concurrency 1` or any equivalent flag — Bun
treats it as a positional filter and skips your tests.

`preflight()` (run inside each test file's `beforeAll`) verifies the
bridge is reachable. There's no sudo dance — that was a hardware-only
concern.

---

## Common user issues + fixes

### Symptom → likely cause table

| Symptom | Most likely cause |
|---|---|
| `make qemu` fails with "docker: command not found" | Install Docker Desktop / Engine. |
| `make qemu` hangs at "Building $(BUILDER_IMAGE)" | First-time TamaGo compile (~5 min). Subsequent runs reuse the image. |
| `nc 127.0.0.1 4000` returns immediately with empty output | Container exited or never bound. `docker ps` + `docker logs <id>`. |
| `bun test` times out in beforeAll | QEMU not running (`make qemu` in another shell). `bun test` doesn't start it. |
| `bun run upload` prints `upload failed: ...refused...` | Same as above — emulator not running. |
| Hot-swap "lost" after `make qemu` restart | Expected: applets live in RAM only. Bake a new default with `make trusted_os && make qemu`. |
| Tests pass but `Attest` returns Error | Expected on QEMU. The attestation test asserts that path. |
| QEMU prints "warning: nic imx.enet.1 has no peer" | Expected and harmless. The mcimx6ul-evk machine has 2 ENETs; we only attach one. |
| Trusted OS prints banner then nothing | Stuck somewhere in main.go. Check `docker logs`; look for the next expected line ("SM loading applet (NNN bytes)"). |

### macOS / Linux differences

The QEMU edition is **identical on macOS and Linux** — no
platform-specific scripts, no `sudo`. Both hosts run the same
`docker run` invocation. This is the main UX win over the hardware path.

---

## Hard-won lessons

This section captures debugging journeys so an agent doesn't repeat them.
Each lesson is QEMU-specific unless marked otherwise.

### 1. mcimx6ul-evk USB device-mode CDC-ECM doesn't work in QEMU.

The hardware kit uses USB-CDC-ECM (`usbarmory.USB1` + `imx-usbnet`) for
its bridge. QEMU's `mcimx6ul-evk` machine emulates ChipIdea USB
controllers but not USB device-mode CDC-ECM gadget enumeration in a way
that's reachable from the host. Pivot: route the bridge through the
emulated FEC ENET NIC + QEMU `-nic user,model=imx.enet,hostfwd=...`
instead. Same `10.0.0.1:4000` listener inside the guest, just attached
to a different NIC. Pattern reference: `tamago-example/network/imx6.go`.

### 2. The mcimx6ul-evk USDHC emulation never clears the RSTA reset bit.

TamaGo's `usdhc.Detect()` does:
```go
reg.Set(hw.sys_ctrl, SYS_CTRL_RSTA)
reg.Wait(hw.sys_ctrl, SYS_CTRL_RSTA, 1, 0)  // hangs forever in QEMU
```
QEMU's `sdhci_reset_write()` performs the reset operation but doesn't
auto-clear the RSTA bit (real hardware does). The poll spins forever and
boot hangs after "SM loading applet" with no further output.

We sidestep this by **not using SD-backed persistence** under QEMU.
Hot-swapped applets live in RAM only (see "Hot-swap mechanism" above).
The hardware kit on `main` keeps the SD path because real hardware
clears the bit correctly.

### 3. mx6ullevk's UART1 is the console — first `-serial` flag is the one that matters.

QEMU's `mcimx6ul-evk` maps `serial_hd(0)` to UART1, which is what
`mx6ullevk.go`'s package init initializes. Our run.sh uses `-serial
stdio` (single arg) to wire UART1 to the container's stdout. An earlier
draft used `-serial null -serial stdio`, which mapped UART1 to /dev/null
and UART2 to stdout — every Trusted OS log line vanished and the
emulator looked silent.

### 4. The FEC PHY emulation in mcimx6ul-evk is a stub.

QEMU emulates a LAN911x PHY rather than the real Micrel KSZ8081RNB. The
`tamago/board/nxp/mx6ullevk` driver works around this; the stack
auto-links and we don't need to call `mx6ullevk.EnablePHY()`
explicitly. There's a harmless boot warning
`qemu-system-arm: warning: nic imx.enet.1 has no peer` because we only
attach a NIC to ENET1 (selected via the `imx6ul.Native==false` branch
in `startNetworking`).

### 5. ENET driver no longer implements gnet.NetworkDevice directly.

Older `tamago-example` code shows `*enet.ENET` being passed straight to
`gnet.Interface{NetworkDevice: eth}`. The current ENET API exposes
`Rx()` and `Tx(buf)` (DMA-managed) instead of the
`Receive(buf) (int, error)` / `Transmit(buf) error` shape gnet expects.
We define a tiny `fecAdapter` in `main.go` that bridges them.

### 6. RX driving via polling beats interrupts under QEMU's mcimx6ul-evk.

`tamago-example/network/imx6.go` runs FEC RX via the GIC + an ISR. That
needs `arm.ServiceInterrupts`, which conflicts with the GoTEE monitor's
exception handler ownership. Going through gnet's polling
`iface.Start()` in a goroutine instead is simpler, doesn't require GIC
init, and works fine under QEMU — packet rates are tiny (a hackathon
bridge, not Gigabit Ethernet).

### 7. Don't run main() to completion.

`startNetworking` ends with `select {}` so main() never returns.
Returning from main causes the Go runtime to unwind, killing the
bridge/SSH/applet supervisor goroutines. (This was already the case in
the hardware kit via `usbarmory.USB1.Start` blocking; the QEMU path
needs an explicit equivalent.)

### 8. Importing mx6ullevk for its package init() is required.

`mx6ullevk`'s package `init()` runs UART1 setup, USDHC pinmux, and a
`runtime/goos.Hwinit1` linkname hook. Just importing the package —
even if you don't reference any of its variables — runs that init.
We force the import via `var _ = mx6ullevk.SD1` at the bottom of
main.go so the linker doesn't optimize it away.

### 9. The applet's RPC.Recv long-poll blocks forever if the applet isn't running.

After a `make qemu` (or after a hot-swap) there's a brief window
(seconds) where the bridge is up but the applet hasn't reached its
`serve()` loop. `CallApplet` in the bridge will block. `waitForDevice`
in `scripts/test-helpers.ts` polls with a 2-second `nc -w 2` timeout
to avoid getting stuck.

### 10. Hot-swap timing and __exit semantics.

The supervisor sends `__exit` to the applet via the RPC channel, NOT
via `CallApplet` — `CallApplet` would also wait for an `appletReplyCh`
that the exiting applet never sends. We push to `appletRequestCh`
directly. Worst case: an in-flight `CallApplet` from a separate
bridge connection hangs across the swap. For a hackathon kit that's
acceptable; if it bites, add a timeout to `CallApplet`.

### 11. (Hardware-only, kept for the porting guide context)

The `.imx` image won't boot without a DCD; mkimage's `-e` flag is
literal, not symbolic; the `objcopy -j` list must include `.go.module`
and exclude `.note.*`. None of these apply under QEMU because
`qemu-system-arm -kernel` skips the BootROM/IVT/DCD path entirely. They
matter only when porting back to hardware — see
`docs/PORTING_TO_USBARMORY.md`.

---

## File inventory (with key references)

### Files users edit
- `src/main.rs` — Trusted Applet entry point.

### Files users may read but shouldn't edit
- `docker/gotee_syscall/src/lib.rs` — Syscall wrappers, `serve()`
  loop, no-alloc JSON helpers, panic handler, formatting macros.
- `docker/applet.ld` — Linker script. Sets text base to `0x10010000`.
- `docker/.cargo/config.toml` — Cargo target/linker config.
- `Makefile` — Thin delegator to `docker/Makefile`.
- `docker/Makefile` — Real build recipes: `applet`, `trusted_os`,
  `qemu`, `clean`. The Trusted OS build runs inside the
  `gotee-starter-builder` Docker image.
- `docker/Dockerfile` — Builder image (TamaGo + binutils + Go).
- `docker/qemu/Dockerfile` — Runtime image (debian + qemu-system-arm).
- `docker/qemu/run.sh` — In-container auto-restart wrapper.
- `scripts/qemu.sh` — Host-side launcher (docker run + port-publish).
- `scripts/make-sd-img.sh` — Creates `bin/sd.img` (currently unused
  by the trusted_os, kept for parity with the porting guide).
- `scripts/upload.ts` — Bun applet uploader; defaults to 127.0.0.1:4000.
- `scripts/test-helpers.ts` — Test helpers; defaults to 127.0.0.1:4000.

### Files users should not touch
- `docker/trusted_os/main.go` — Hardware init, applet supervisor, FEC
  networking, SSH server.
- `docker/trusted_os/handler.go` — Syscall dispatch (the `swi 0` trap
  target).
- `docker/trusted_os/exec.go` — Applet ELF loader.
- `docker/trusted_os/rpc.go` — RPC method definitions exposed to the
  applet.
- `docker/trusted_os/bridge.go` — TCP/JSON bridge listener on `:4000`.
- `docker/trusted_os/mem.go` — Memory layout constants.
- `docker/trusted_os/go.mod`, `go.sum` — Go module pinning.

### Examples (edit/copy at will)
- `examples/blinky/main.rs` — `RPC.Blink(N)` "toggles" blue LED N times.
  Under QEMU just logs to the Trusted OS console.
- `examples/crypto/main.rs` — `Random(N)` returns N hardware-RNG bytes
  hex-encoded.
- `examples/attestation/main.rs` — `Attest()` returns the JSON-RPC
  reply from `RPC.Attest` raw. Under QEMU the reply contains the
  emulation Error field instead of a DerivedKey.
- `examples/square/main.rs` — `Square(x)` returns x² (saturating i64).
  Has a Bun HTTP shim in `server.ts` and its own `README.md`.
- `examples/<name>/<name>.test.ts` — Bun test files for square / crypto /
  attestation.

---

## Hardware port

For instructions on running this kit on a real USB Armory MK II — same
applet code, same examples, same tests — see
[`docs/PORTING_TO_USBARMORY.md`](docs/PORTING_TO_USBARMORY.md). That
file walks through what changes (USB-CDC-ECM transport, WDOG reset, SD
persistence, on-chip crypto, mkimage/IVT/DCD packaging) and links to
the canonical upstream sources for each piece.

---

## External references

### TamaGo (bare-metal Go for ARM)
- Main repo: <https://github.com/usbarmory/tamago>
- mx6ullevk board package: <https://github.com/usbarmory/tamago/tree/master/board/nxp/mx6ullevk>
- tamago-example (FEC + 10.0.0.1 hostfwd recipe we cribbed): <https://github.com/usbarmory/tamago-example>

### GoTEE
- Framework: <https://github.com/usbarmory/GoTEE>
- Reference example: <https://github.com/usbarmory/GoTEE-example>

### gVisor TCP/IP via go-net
- <https://github.com/usbarmory/go-net>

### QEMU
- mcimx6ul-evk machine: <https://www.qemu.org/docs/master/system/arm/mcimx6ul-evk.html>
- User-mode networking + hostfwd: <https://www.qemu.org/docs/master/system/devices/net.html#user-mode-networking>

### Host-side dev stack
- Bun: <https://bun.sh>
- BSD nc man page: `man nc`

## Project status / version snapshots (2026-05)

- TamaGo: `latest` branch (commit varies). Requires Go 1.24.6+ to
  bootstrap → we pin go1.25.1 in the builder Dockerfile.
- go-net: latest, gvisor v0.0.0-20250911...
- Bun: tested with v1.3.9.
- Rust: `rust-toolchain.toml` pins nightly with `armv7a-none-eabi` +
  `rust-src`.
- Tested host: macOS Apple Silicon (M3 Max) with Docker Desktop.
- Linux amd64 paths exist in the Dockerfile but haven't been
  exercised by the maintainers on this branch. The QEMU container
  runs identically on both — no ifs in run.sh.

//! Safe Rust wrappers around GoTEE syscalls.
//!
//! This crate provides the interface between a Rust Trusted Applet and the
//! GoTEE Trusted OS running in ARM TrustZone Secure World system mode.
//!
//! Syscalls are issued via the ARM `swi 0` (software interrupt) instruction.
//! The syscall number is passed in `r0`, with arguments in `r1`–`r3`.

#![no_std]

use core::arch::asm;
use core::fmt::{self, Write};
use core::panic::PanicInfo;
use core::time::Duration;

// ---------------------------------------------------------------------------
// Syscall numbers (must match GoTEE monitor/syscall constants)
// ---------------------------------------------------------------------------

const SYS_EXIT: u32 = 0;
const SYS_WRITE: u32 = 1;
const SYS_NANOTIME: u32 = 2;
const SYS_GETRANDOM: u32 = 3;
const SYS_RPC_REQ: u32 = 4;
const SYS_RPC_RES: u32 = 5;

// ---------------------------------------------------------------------------
// Core syscall wrappers
// ---------------------------------------------------------------------------

/// Terminates the Trusted Applet. This does not return.
pub fn exit() -> ! {
    unsafe {
        asm!(
            "swi 0",
            in("r0") SYS_EXIT,
            options(noreturn),
        );
    }
}

/// Writes a single byte to the Trusted OS console output.
pub fn write_byte(b: u8) {
    unsafe {
        asm!(
            "swi 0",
            in("r0") SYS_WRITE,
            in("r1") b as u32,
        );
    }
}

/// Writes a string to the Trusted OS console output.
pub fn print(s: &str) {
    for b in s.bytes() {
        write_byte(b);
    }
}

/// Returns the current system time in nanoseconds.
pub fn nanotime() -> u64 {
    let ns_low: u32;
    let ns_high: u32;

    unsafe {
        asm!(
            "swi 0",
            in("r0") SYS_NANOTIME,
        );

        asm!(
            "",
            out("r0") ns_low,
            out("r1") ns_high,
        );
    }

    ((ns_high as u64) << 32) | (ns_low as u64)
}

/// Fills `buf` with cryptographically secure random bytes from the hardware RNG.
pub fn getrandom(buf: &mut [u8]) {
    unsafe {
        asm!(
            "swi 0",
            in("r0") SYS_GETRANDOM,
            in("r1") buf.as_ptr(),
            in("r2") buf.len(),
        );
    }
}

/// Sends an RPC request payload to the Trusted OS.
///
/// The Trusted OS will dispatch this to registered RPC handlers.
/// Call [`rpc_response`] afterward to read the reply.
pub fn rpc_request(data: &[u8]) {
    unsafe {
        asm!(
            "swi 0",
            in("r0") SYS_RPC_REQ,
            in("r1") data.as_ptr(),
            in("r2") data.len(),
        );
    }
}

/// Reads an RPC response from the Trusted OS into `buf`.
///
/// Returns the number of bytes written into `buf`.
pub fn rpc_response(buf: &mut [u8]) -> usize {
    let n: u32;

    unsafe {
        asm!(
            "swi 0",
            in("r0") SYS_RPC_RES,
            in("r1") buf.as_mut_ptr(),
            in("r2") buf.len(),
        );

        asm!(
            "",
            out("r0") n,
        );
    }

    n as usize
}

// ---------------------------------------------------------------------------
// Applet dispatch loop
// ---------------------------------------------------------------------------

/// Signature for a trusted-function handler.
///
/// - `method` — the method name the caller asked for
/// - `input`  — request payload (UTF-8 bytes, JSON-unescaped)
/// - `out`    — response buffer the handler writes into
///
/// Returns the number of bytes written to `out`.
pub type Handler = fn(method: &str, input: &[u8], out: &mut [u8]) -> usize;

// Dispatch buffer sizes are large to accommodate post-quantum key material.
// Static allocation avoids stack overflow; the applet is single-threaded.
// PQC worst case: ML-DSA-87 keygen output ≈ 10 KB; send envelope adds ~60 B.
const BUF_SIZE: usize = 16384;
const SEND_SIZE: usize = 20480;

/// Runs the applet dispatch loop. Never returns.
///
/// Each iteration asks the Trusted OS for the next queued request via
/// `RPC.Recv`, invokes `handler`, and ships the reply via `RPC.Send`.
///
/// A request with method `"__exit"` causes the applet to call [`exit`]
/// cleanly — the sentinel used by the Trusted OS to end the session.
///
/// The `input` slice passed to `handler` is JSON-unescaped: callers receive
/// the literal string (e.g. `{"level":"768"}`) regardless of how it was
/// encoded in the outer bridge JSON.
pub fn serve(handler: Handler) -> ! {
    // SAFETY: the applet is single-threaded and serve() runs exactly once.
    static mut RPC_BUF:   [u8; BUF_SIZE]  = [0u8; BUF_SIZE];
    static mut INPUT_BUF: [u8; BUF_SIZE]  = [0u8; BUF_SIZE];
    static mut OUT_BUF:   [u8; BUF_SIZE]  = [0u8; BUF_SIZE];
    static mut SEND_BUF:  [u8; SEND_SIZE] = [0u8; SEND_SIZE];

    loop {
        let (rpc_buf, input_buf, out_buf, send_buf) = unsafe {
            (&mut RPC_BUF, &mut INPUT_BUF, &mut OUT_BUF, &mut SEND_BUF)
        };

        // 1. Long-poll for the next request.
        rpc_request(br#"{"method":"RPC.Recv","params":[false],"id":1}"#);
        let n = rpc_response(rpc_buf);

        let json = core::str::from_utf8(&rpc_buf[..n]).unwrap_or("");
        let method = extract_json_string(json, "\"Method\":");
        let raw_input = extract_json_string(json, "\"Input\":");

        if method == "__exit" {
            exit();
        }

        // 2. Unescape the Input field (bridge JSON-encodes the inner payload).
        let input_len = unescape_json_str(raw_input.as_bytes(), input_buf);

        // 3. Dispatch to the user's handler.
        let n_out = handler(method, &input_buf[..input_len], out_buf);
        let output = core::str::from_utf8(&out_buf[..n_out]).unwrap_or("");

        // 4. Build the RPC.Send envelope directly into send_buf.
        let mut pos = 0;
        let prefix = br#"{"method":"RPC.Send","params":[{"Output":"#;
        if pos + prefix.len() <= send_buf.len() {
            send_buf[pos..pos + prefix.len()].copy_from_slice(prefix);
            pos += prefix.len();
        }
        pos += write_json_str_into(output, &mut send_buf[pos..]);
        let suffix = br#"}],"id":2}"#;
        if pos + suffix.len() <= send_buf.len() {
            send_buf[pos..pos + suffix.len()].copy_from_slice(suffix);
            pos += suffix.len();
        }

        rpc_request(&send_buf[..pos]);
        // Discard ack.
        rpc_response(rpc_buf);
    }
}

// ---------------------------------------------------------------------------
// JSON helpers
// ---------------------------------------------------------------------------

/// Unescape JSON string escape sequences from `src` into `dst`.
/// Returns the number of bytes written to `dst`.
fn unescape_json_str(src: &[u8], dst: &mut [u8]) -> usize {
    let mut si = 0;
    let mut di = 0;
    while si < src.len() && di < dst.len() {
        if src[si] == b'\\' && si + 1 < src.len() {
            si += 1;
            dst[di] = match src[si] {
                b'"'  => b'"',
                b'\\' => b'\\',
                b'n'  => b'\n',
                b'r'  => b'\r',
                b't'  => b'\t',
                other => other,
            };
            si += 1;
            di += 1;
        } else {
            dst[di] = src[si];
            si += 1;
            di += 1;
        }
    }
    di
}

/// Write a JSON-escaped string (with surrounding `"`) into `buf`.
/// Returns the number of bytes written.
fn write_json_str_into(s: &str, buf: &mut [u8]) -> usize {
    let mut pos = 0;

    macro_rules! emit1 {
        ($b:expr) => {
            if pos < buf.len() {
                buf[pos] = $b;
                pos += 1;
            }
        };
    }
    macro_rules! emit2 {
        ($b1:expr, $b2:expr) => {
            if pos + 1 < buf.len() {
                buf[pos]     = $b1;
                buf[pos + 1] = $b2;
                pos += 2;
            }
        };
    }

    emit1!(b'"');
    for b in s.bytes() {
        match b {
            b'"'        => emit2!(b'\\', b'"'),
            b'\\'       => emit2!(b'\\', b'\\'),
            b'\n'       => emit2!(b'\\', b'n'),
            b'\r'       => emit2!(b'\\', b'r'),
            b'\t'       => emit2!(b'\\', b't'),
            0x00..=0x1f => {
                if pos + 5 < buf.len() {
                    let hex = b"0123456789abcdef";
                    buf[pos]     = b'\\';
                    buf[pos + 1] = b'u';
                    buf[pos + 2] = b'0';
                    buf[pos + 3] = b'0';
                    buf[pos + 4] = hex[(b >> 4) as usize];
                    buf[pos + 5] = hex[(b & 0xf) as usize];
                    pos += 6;
                }
            }
            other => emit1!(other),
        }
    }
    emit1!(b'"');
    pos
}

/// Returns the raw (still-escaped) slice of a JSON string value following the
/// given key. Good enough for ASCII payloads; callers needing binary should
/// use their own encoding.
fn extract_json_string<'a>(json: &'a str, key: &str) -> &'a str {
    let Some(key_pos) = json.find(key) else {
        return "";
    };
    let after_key = &json[key_pos + key.len()..];
    let Some(quote_start) = after_key.find('"') else {
        return "";
    };
    let content = &after_key[quote_start + 1..];
    let bytes = content.as_bytes();
    let mut end = 0;
    while end < bytes.len() {
        if bytes[end] == b'\\' {
            end += 2;
        } else if bytes[end] == b'"' {
            return &content[..end];
        } else {
            end += 1;
        }
    }
    ""
}

// ---------------------------------------------------------------------------
// Stdout adapter (enables write! / writeln! macros)
// ---------------------------------------------------------------------------

/// A zero-size type implementing `core::fmt::Write` via the `SYS_WRITE` syscall.
pub struct Stdout;

impl Write for Stdout {
    fn write_str(&mut self, s: &str) -> fmt::Result {
        for b in s.bytes() {
            write_byte(b);
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Convenience macros
// ---------------------------------------------------------------------------

/// Prints formatted text to the Trusted OS console.
#[macro_export]
macro_rules! print {
    ($($arg:tt)*) => {
        {
            use core::fmt::Write;
            write!(&mut $crate::Stdout, $($arg)*).ok();
        }
    };
}

/// Prints formatted text followed by a newline (`\r\n`) to the Trusted OS console.
#[macro_export]
macro_rules! println {
    () => {
        $crate::print!("\r\n")
    };
    ($($arg:tt)*) => {
        {
            use core::fmt::Write;
            write!(&mut $crate::Stdout, $($arg)*).ok();
            $crate::print!("\r\n");
        }
    };
}

/// Prints a timestamped log line to the Trusted OS console.
///
/// Format: `HH:MM:SS <message>\r\n`
#[macro_export]
macro_rules! log {
    ($($arg:tt)*) => {
        {
            $crate::print_walltime($crate::nanotime());
            $crate::println!($($arg)*);
        }
    };
}

/// Prints a wall-clock timestamp prefix (HH:MM:SS) derived from nanotime.
#[doc(hidden)]
pub fn print_walltime(ns: u64) {
    let epoch = Duration::from_nanos(ns).as_secs();
    let ss = epoch % 60;
    let mm = (epoch / 60) % 60;
    let hh = (epoch / 3600) % 24;
    print!("{:02}:{:02}:{:02} ", hh, mm, ss);
}

// ---------------------------------------------------------------------------
// Panic handler
// ---------------------------------------------------------------------------

/// Global panic handler. Logs the panic info and exits the applet.
#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    print_walltime(nanotime());
    print!("PANIC: ");
    if let Some(msg) = info.message().as_str() {
        print(msg);
    } else {
        use core::fmt::Write;
        write!(&mut Stdout, "{}", info).ok();
    }
    print("\r\n");
    exit();
}

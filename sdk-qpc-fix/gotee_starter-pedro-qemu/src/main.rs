//! PQC example applet — ML-KEM and ML-DSA over the GoTEE bridge.
//!
//! Copy this file to src/main.rs, rebuild, and upload:
//!
//!   cp examples/pqc/main.rs src/main.rs
//!   make applet
//!   bun run upload target/armv7a-none-eabi/release/trusted_applet
//!
//! Then probe with nc (see examples below). The Input value is a
//! JSON object encoded as a JSON string, so inner quotes are escaped.
//!
//! # ML-KEM (key encapsulation, default level ML-KEM-768)
//!
//!   # Keygen
//!   printf '{"Method":"MLKEM.Keygen","Input":"{\"level\":\"768\"}"}\n' \
//!     | nc 127.0.0.1 4000
//!
//!   # Encapsulate (replace <pk> with public_key_b64 from Keygen)
//!   printf '{"Method":"MLKEM.Encapsulate","Input":"{\"level\":\"768\",\"public_key_b64\":\"<pk>\"}"}\n' \
//!     | nc 127.0.0.1 4000
//!
//!   # Decapsulate (replace <sk> and <ct> with values from above)
//!   printf '{"Method":"MLKEM.Decapsulate","Input":"{\"level\":\"768\",\"secret_key_b64\":\"<sk>\",\"ciphertext_b64\":\"<ct>\"}"}\n' \
//!     | nc 127.0.0.1 4000
//!
//! # ML-DSA (digital signatures, default level ML-DSA-65)
//!
//!   # Keygen
//!   printf '{"Method":"MLDSA.Keygen","Input":"{\"level\":\"65\"}"}\n' \
//!     | nc 127.0.0.1 4000
//!
//!   # Sign (message_b64 = base64("hello"))
//!   printf '{"Method":"MLDSA.Sign","Input":"{\"level\":\"65\",\"secret_key_b64\":\"<sk>\",\"message_b64\":\"aGVsbG8=\"}"}\n' \
//!     | nc 127.0.0.1 4000
//!
//!   # Verify
//!   printf '{"Method":"MLDSA.Verify","Input":"{\"level\":\"65\",\"public_key_b64\":\"<pk>\",\"message_b64\":\"aGVsbG8=\",\"signature_b64\":\"<sig>\"}"}\n' \
//!     | nc 127.0.0.1 4000
//!
//! # Security notes
//!
//! DEMO ONLY: secret keys are returned over the bridge for testing convenience.
//! In production, generate and retain keys inside the TEE; never export them.
//!
//! This implementation is NOT a FIPS validation claim. It uses the RustCrypto
//! ml-kem and ml-dsa crates which implement FIPS 203 and FIPS 204 respectively.

#![no_std]
#![no_main]

mod pqc;

use gotee_syscall::{self, log};

fn handle(method: &str, input: &[u8], out: &mut [u8]) -> usize {
    match method {
        // ML-KEM (FIPS 203, formerly CRYSTALS-Kyber) — key encapsulation.
        // Levels: "512" | "768" (default) | "1024"
        "MLKEM.Keygen"      => pqc::mlkem::keygen(input, out),
        "MLKEM.Encapsulate" => pqc::mlkem::encapsulate(input, out),
        "MLKEM.Decapsulate" => pqc::mlkem::decapsulate(input, out),

        // ML-DSA (FIPS 204, formerly CRYSTALS-Dilithium) — digital signatures.
        // Levels: "44" | "65" (default) | "87"
        "MLDSA.Keygen" => pqc::mldsa::keygen(input, out),
        "MLDSA.Sign"   => pqc::mldsa::sign(input, out),
        "MLDSA.Verify" => pqc::mldsa::verify(input, out),

        _ => 0,
    }
}

#[no_mangle]
pub extern "C" fn _start() -> ! {
    log!("PQC example ready — ML-KEM-768 / ML-DSA-65 defaults");
    gotee_syscall::serve(handle)
}

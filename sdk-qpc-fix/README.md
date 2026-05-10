# GoTEE PQC — Post-Quantum Cryptography for Trusted Applets

This module adds **NIST-standardized post-quantum cryptography** to the [GoTEE](https://github.com/usbarmory/GoTEE) trusted applet framework. Rust applets running in ARM TrustZone Secure World can perform quantum-resistant key encapsulation and digital signatures, exposed to the Normal World via a JSON/TCP bridge.

## Algorithms

Two FIPS-standardized post-quantum algorithms are implemented:

### ML-KEM (FIPS 203) — Key Encapsulation

Formerly CRYSTALS-Kyber. Used for quantum-resistant key agreement.

| Level | Public Key | Ciphertext | Shared Secret | NIST Category |
|-------|-----------|------------|---------------|---------------|
| ML-KEM-512 | 800 B | 768 B | 32 B | 1 |
| **ML-KEM-768** | 1184 B | 1088 B | 32 B | **3 (default)** |
| ML-KEM-1024 | 1568 B | 1568 B | 32 B | 5 |

### ML-DSA (FIPS 204) — Digital Signatures

Formerly CRYSTALS-Dilithium. Used for quantum-resistant signatures.

| Level | Public Key | Signature | NIST Category |
|-------|-----------|-----------|---------------|
| ML-DSA-44 | 1312 B | 2420 B | 1 |
| **ML-DSA-65** | 1952 B | 3309 B | **3 (default)** |
| ML-DSA-87 | 2592 B | 4627 B | 5 |

## Architecture

The PQC module runs as a **Rust trusted applet** in ARM TrustZone Secure World (EL0S). The Normal World communicates with it through the Trusted OS RPC mechanism, exposed as a TCP/JSON bridge on `127.0.0.1:4000` (QEMU: `10.0.0.1:4000`).

```
Normal World                   Secure World
─────────────────              ─────────────────────────────
Client (bun/node)  ──JSON/TCP──▶  GoTEE Trusted OS
                                       │
                                  RPC dispatch
                                       │
                              ┌────────▼────────┐
                              │  Rust Applet    │
                              │  ┌───────────┐  │
                              │  │  ML-KEM   │  │
                              │  │  ML-DSA   │  │
                              │  └───────────┘  │
                              │  Hardware RNG   │
                              └─────────────────┘
```

All secret key material lives exclusively in Secure World. Binary data crosses the bridge as base64-encoded JSON strings.

## Wire Protocol

Requests follow the GoTEE RPC format:

```json
{"Method": "<algorithm>.<operation>", "Input": "<json-string>"}
```

### ML-KEM

**Keygen**
```json
// request
{"Method":"MLKEM.Keygen","Input":"{\"level\":\"768\"}"}
// response
{"Output":"{\"public_key_b64\":\"...\",\"secret_key_b64\":\"...\"}"}
```

**Encapsulate**
```json
// request
{"Method":"MLKEM.Encapsulate","Input":"{\"level\":\"768\",\"public_key_b64\":\"...\"}"}
// response
{"Output":"{\"ciphertext_b64\":\"...\",\"shared_secret_b64\":\"...\"}"}
```

**Decapsulate**
```json
// request
{"Method":"MLKEM.Decapsulate","Input":"{\"level\":\"768\",\"secret_key_b64\":\"...\",\"ciphertext_b64\":\"...\"}"}
// response
{"Output":"{\"shared_secret_b64\":\"...\"}"}
```

### ML-DSA

**Keygen**
```json
// request
{"Method":"MLDSA.Keygen","Input":"{\"level\":\"65\"}"}
// response
{"Output":"{\"public_key_b64\":\"...\",\"secret_key_b64\":\"...\"}"}
```

**Sign**
```json
// request
{"Method":"MLDSA.Sign","Input":"{\"level\":\"65\",\"secret_key_b64\":\"...\",\"message_b64\":\"...\"}"}
// response
{"Output":"{\"signature_b64\":\"...\"}"}
```

**Verify**
```json
// request
{"Method":"MLDSA.Verify","Input":"{\"level\":\"65\",\"public_key_b64\":\"...\",\"message_b64\":\"...\",\"signature_b64\":\"...\"}"}
// response
{"Output":"{\"valid\":true}"}
```

## Implementation Details

**Source layout:**
```
sdk-qpc-fix/gotee_starter-pedro-qemu/
├── src/
│   ├── main.rs           # applet entry point, RPC dispatch
│   └── pqc/
│       ├── mod.rs        # JSON helpers, base64 encode/decode
│       ├── mlkem.rs      # ML-KEM key encapsulation
│       └── mldsa.rs      # ML-DSA digital signatures
├── examples/pqc/
│   ├── main.rs           # standalone PQC applet
│   └── pqc.test.ts       # Bun integration test suite
└── docker/
    ├── Cargo.toml        # Rust dependencies
    └── gotee_syscall/    # ARM swi 0 syscall wrappers
```

**Design constraints:**

- `no_std` — no heap allocation; all buffers are stack-allocated with compile-time-known maximum sizes
- Keys stored as minimal fixed-size seeds: 64 B for ML-KEM, 32 B for ML-DSA
- Hardware RNG accessed via `SYS_GETRANDOM` syscall into the Trusted OS
- Sensitive key material is zeroed after use (constant-time cleanup)
- On invalid input the applet returns a JSON error response; no panics

**Rust dependencies:**
```toml
ml-kem   = { version = "0.3",         default-features = false }
ml-dsa   = { version = "0.1.0-pre.4", default-features = false }
base64ct = { version = "1",           default-features = false }
```

Both RustCrypto crates have formal verification of memory-safety and constant-time properties.

## Running

### QEMU

```bash
# build and launch QEMU with the PQC applet
cd sdk-qpc-fix/gotee_starter-pedro-qemu
make qemu-pqc
```

### Tests

```bash
# run integration tests against the live QEMU bridge
bun test examples/pqc/pqc.test.ts
```

The test suite covers keygen, encapsulate/decapsulate round-trips, sign/verify round-trips, tampered-message rejection, and invalid-parameter error handling for both algorithms.

## Security Notes

- Secret keys never leave Secure World; only public keys and ciphertexts cross the bridge
- ML-KEM-768 and ML-DSA-65 (NIST category 3) are the defaults, balancing security and performance
- The underlying C reference implementations (`pqc-module/`) include CBMC proofs of memory safety and HOL-Light proofs of assembly timing resistance

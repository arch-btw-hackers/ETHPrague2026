# pqc-module — Post-Quantum Crypto for ESP32

ESP-IDF component that wraps **ML-KEM-512** (FIPS 203) and **ML-DSA-44** (FIPS 204) for an ESP32 cold-chain tracker. The device signs telemetry batches and establishes encrypted sessions with a backend server using post-quantum algorithms from the [PQ Code Package](https://github.com/pq-code-package).

---

## Quick start

```bash
# 1. Clone the library submodules
make submodule-mlkem   # → components/mlkem/mlkem-native
make submodule-mldsa   # → components/mldsa/mldsa-native

# 2. Build firmware (Docker used automatically if idf.py is not installed)
make build

# 3. Run host tests (no ESP32 needed)
make test              # Python tests via liboqs — works immediately
make test-host         # Native C tests — requires submodules above
```

---

## Prerequisites

| Tool | Required for | Install |
|---|---|---|
| `git` | submodules | pre-installed on macOS |
| `docker` | firmware build (if no ESP-IDF) | [docker.com](https://www.docker.com) |
| `idf.py` (ESP-IDF v5.4) | firmware build (native) | `~/esp/esp-idf/install.sh esp32` |
| `python3` + `liboqs` | `make test` / `make backend-keygen` | `pip install liboqs` |
| `gcc` / `clang` | `make test-host` | Xcode Command Line Tools |

The Makefile auto-detects `idf.py`. If it is not in `PATH`, `make build` and `make clean` fall back to the official `espressif/idf:v5.4` Docker image — no manual setup required.

### liboqs-python (local checkout)

If `liboqs` is a local checkout rather than a pip package, set `LIBOQS_PYTHON`:

```bash
make test LIBOQS_PYTHON=/path/to/liboqs-python
# or export it permanently
export LIBOQS_PYTHON=~/Programming/utilits/liboqs-python
```

---

## Directory layout

```
pqc-module/
├── Makefile
├── CMakeLists.txt              # top-level ESP-IDF project
├── sdkconfig.defaults          # stack + flash-encryption defaults
├── partitions.csv              # NVS partition for key storage
├── components/
│   ├── pqc/                    # ← main library component
│   │   ├── include/pqc.h       # public C API
│   │   └── pqc.cpp             # implementation
│   ├── mlkem/                  # ML-KEM-512 (mlkem-native submodule)
│   │   ├── CMakeLists.txt
│   │   └── mlkem-native/       # cloned by make submodule-mlkem
│   └── mldsa/                  # ML-DSA-44 (mldsa-native submodule)
│       ├── CMakeLists.txt
│       ├── randombytes.h
│       ├── randombytes_esp32.cpp
│       └── mldsa-native/       # cloned by make submodule-mldsa
├── main/
│   ├── CMakeLists.txt
│   └── main.cpp                # device application entry point
└── tests/
    ├── test_pqc.py             # Python tests (liboqs) — run with make test
    ├── test_host.c             # C tests (PQCP libs) — run with make test-host
    └── randombytes_host.c      # /dev/urandom shim for host builds
```

---

## C API

Include `pqc.h` and link the `pqc` ESP-IDF component.

```c
#include "pqc.h"
```

### Data types

```c
typedef struct {
    /* ── Secrets — wiped by pqc_zeroize() ──────────────────────── */
    uint8_t dsa_sk_device [PQC_DSA_SK_BYTES];     // 2560 B — ML-DSA-44 signing key
    uint8_t session_key   [PQC_SESSION_KEY_BYTES]; //   32 B — AES-256-GCM key

    /* ── Non-secrets ────────────────────────────────────────────── */
    uint8_t kem_pk_backend[PQC_KEM_PK_BYTES];     //  800 B — backend KEM public key
    uint8_t dsa_pk_device [PQC_DSA_PK_BYTES];     // 1312 B — device DSA public key
    uint8_t kem_ct        [PQC_KEM_CT_BYTES];     //  768 B — KEM ciphertext → backend
    uint8_t signature     [PQC_DSA_SIG_BYTES];    // 2420 B — batch signature output
    size_t  sig_len;
} pqc_context_t;
```

### Size constants

```c
/* ML-KEM-512 (FIPS 203) */
#define PQC_KEM_PK_BYTES   800
#define PQC_KEM_CT_BYTES   768
#define PQC_KEM_SS_BYTES    32

/* ML-DSA-44 (FIPS 204) */
#define PQC_DSA_PK_BYTES  1312
#define PQC_DSA_SK_BYTES  2560
#define PQC_DSA_SIG_BYTES 2420

/* AES-256-GCM */
#define PQC_SESSION_KEY_BYTES  32
#define PQC_NONCE_BYTES        12
#define PQC_TAG_BYTES          16
```

### Functions

#### `pqc_init`
```c
esp_err_t pqc_init(pqc_context_t *ctx);
```
Zeros the context and loads keys from NVS. Call once at startup, after `nvs_flash_init()`.  
Returns `ESP_ERR_NVS_NOT_FOUND` if the device has never been provisioned — call `pqc_generate_keys()` in that case.

---

#### `pqc_generate_keys`
```c
esp_err_t pqc_generate_keys(pqc_context_t *ctx);
```
Generates a fresh ML-DSA-44 keypair and persists it to the NVS encrypted partition. Call **once** during device provisioning. After this, send `ctx->dsa_pk_device` to the backend so it can verify signatures later.

> Requires Wi-Fi radio to be started before calling (ESP32 hardware RNG needs the radio for entropy).

---

#### `pqc_load_keys`
```c
esp_err_t pqc_load_keys(pqc_context_t *ctx);
```
Loads an existing keypair from NVS into `ctx`. Called internally by `pqc_init()`.

---

#### `pqc_establish_session`
```c
esp_err_t pqc_establish_session(pqc_context_t *ctx);
```
Encapsulates to the backend's ML-KEM-512 public key (`ctx->kem_pk_backend`). Fills:
- `ctx->kem_ct` — send this to the backend
- `ctx->session_key` — use for `pqc_encrypt_telemetry()`; **kept secret**

Call before each upload. Call `pqc_zeroize()` after the upload is complete.

---

#### `pqc_sign_batch`
```c
esp_err_t pqc_sign_batch(pqc_context_t *ctx,
                          const uint8_t *batch, size_t batch_len);
```
SHA-256 hashes `batch` and signs the hash with ML-DSA-44. Fills `ctx->signature` and `ctx->sig_len`. Signing is deterministic — no extra randomness is consumed.

> Stack peak: ~7.5 KB. The PQC task stack must be at least 12 KB (see `sdkconfig.defaults`).

---

#### `pqc_encrypt_telemetry`
```c
esp_err_t pqc_encrypt_telemetry(
    const pqc_context_t *ctx,
    const uint8_t *aad,  size_t aad_len,   // authenticated but not encrypted
    const uint8_t *pt,   size_t pt_len,    // plaintext batch JSON
    uint8_t *nonce_out,                    // caller allocates PQC_NONCE_BYTES
    uint8_t *ct_out,                       // caller allocates >= pt_len bytes
    uint8_t *tag_out                       // caller allocates PQC_TAG_BYTES
);
```
AES-256-GCM encrypts `pt` with a fresh random nonce. The nonce is written into `nonce_out`.

---

#### `pqc_zeroize`
```c
void pqc_zeroize(pqc_context_t *ctx);
```
Securely wipes `dsa_sk_device` and `session_key` (uses `mbedtls_platform_zeroize` — compiler cannot elide it). Call after every upload session.

---

## Usage example

### 1. Provisioning (run once)

```cpp
#include "pqc.h"
#include "nvs_flash.h"

static pqc_context_t pqc;

void provision_device(void)
{
    nvs_flash_init();

    esp_err_t err = pqc_init(&pqc);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        // First boot — generate keys and store in NVS
        ESP_ERROR_CHECK(pqc_generate_keys(&pqc));
        ESP_LOGI("app", "Provisioned. Send dsa_pk_device to backend.");
        // Transmit pqc.dsa_pk_device (1312 bytes) to backend over a secure channel.
        // Receive kem_pk_backend (800 bytes) from backend and store in NVS.
    }
}
```

### 2. Upload session (runs every batch)

```cpp
void upload_batch(const char *batch_json, size_t batch_len,
                  const char *aad_json,   size_t aad_len)
{
    // a) Establish ephemeral session
    ESP_ERROR_CHECK(pqc_establish_session(&pqc));
    // pqc.kem_ct is now filled — include it in the upload packet.

    // b) Sign the batch
    ESP_ERROR_CHECK(pqc_sign_batch(&pqc,
        (const uint8_t *)batch_json, batch_len));
    // pqc.signature / pqc.sig_len are filled.

    // c) Encrypt the batch
    static uint8_t nonce[PQC_NONCE_BYTES];
    static uint8_t ct   [PQC_BATCH_JSON_MAX];
    static uint8_t tag  [PQC_TAG_BYTES];

    ESP_ERROR_CHECK(pqc_encrypt_telemetry(&pqc,
        (const uint8_t *)aad_json, aad_len,
        (const uint8_t *)batch_json, batch_len,
        nonce, ct, tag));

    // d) Build and send the upload packet (JSON / CBOR / HTTP POST)
    send_packet(pqc.kem_ct, nonce, ct, batch_len, tag,
                pqc.signature, pqc.sig_len,
                (const uint8_t *)aad_json, aad_len);

    // e) Wipe secrets — always call after upload
    pqc_zeroize(&pqc);
}
```

---

## Build

### With ESP-IDF installed

```bash
. ~/esp/esp-idf/export.sh    # source once per terminal
make submodules
make build
make flash monitor
```

### With Docker (no ESP-IDF install needed)

```bash
make submodules
make build          # pulls espressif/idf:v5.4 automatically
# Flash still needs native idf.py — Docker cannot access USB
```

Pre-pull the image to avoid build-time delay:

```bash
make docker-pull
```

---

## Tests

### Python tests (no submodules needed)

Tests the same algorithms (ML-KEM-512, ML-DSA-44) via liboqs and validates all size constants against `pqc.h`.

```bash
make test
```

Expected output:

```
ML-KEM-512 — round-trip
  [PASS] pk size == 800 B
  [PASS] ct size == 768 B
  [PASS] ss size == 32 B
  [PASS] encap/decap shared secrets match

ML-KEM-512 — wrong ciphertext (CCA security)
  [PASS] decap with flipped ct yields different secret
...
Results: 15/15 checks passed
```

### Native C tests (requires submodules)

Compiles mlkem-native and mldsa-native for the host and calls the same `mlkem512_*` / `mldsa44_*` symbols as the ESP32 firmware.

```bash
make submodules
make test-host
```

Expected output:

```
ML-KEM-512 — round-trip
  [PASS] keypair ok
  [PASS] pk size == 800 B
  [PASS] ct size == 768 B
  [PASS] ss size == 32 B
  [PASS] enc ok
  [PASS] dec ok
  [PASS] enc/dec ss match

ML-KEM-512 — deterministic encapsulation (_derand)
  [PASS] enc_derand ok
  [PASS] dec ok
  [PASS] ss match

ML-KEM-512 — wrong ciphertext (CCA)
  [PASS] flipped ct → different ss

ML-DSA-44 — sign / verify
  [PASS] pk size == 1312 B
  [PASS] sk size == 2560 B
  [PASS] keypair ok
  [PASS] sign ok
  [PASS] sig <= 2420 B
  [PASS] verify ok

ML-DSA-44 — reject tampered message
  [PASS] tampered msg fails verify

ML-DSA-44 — reject wrong public key
  [PASS] sig from key1 rejected by key2

==========================================
Results: 19/19 checks passed
```

---

## Backend keygen

Generate the backend ML-KEM-512 keypair (run on the server, not the device):

```bash
make backend-keygen
# → backend_kem_pk.bin  (800 bytes — flash or send to devices)
# → backend_kem_sk.bin  (1632 bytes — keep secret on server)
```

---

## Architecture

```
┌──────────────────────── ESP32 Device ──────────────────────────┐
│  Sensors → batch_json → SHA-256 → ML-DSA-44.Sign → signature  │
│  kem_pk_backend → ML-KEM-512.Encaps → (kem_ct, shared_secret) │
│  HKDF-SHA256(shared_secret, "cold-chain-v1") → session_key    │
│  AES-256-GCM.Encrypt(session_key, batch_json) → ciphertext    │
│                                                                │
│  Upload: { kem_ct, nonce, aad, ciphertext, tag, signature }   │
└────────────────────────────────┬───────────────────────────────┘
                                 │ HTTPS
┌──────────────────────── Backend ────────────────────────────────┐
│  ML-KEM-512.Decaps(kem_ct, kem_sk_backend) → shared_secret    │
│  HKDF-SHA256(shared_secret, "cold-chain-v1") → session_key    │
│  AES-256-GCM.Decrypt → batch_json                             │
│  ML-DSA-44.Verify(SHA-256(batch_json), signature, dsa_pk)     │
│  → contract.submitTrackerState(shipmentId, isGood)            │
└─────────────────────────────────────────────────────────────────┘
```

**Design decisions:**
- Backend holds the KEM private key; device only holds the KEM public key → no private KEM key ever leaves the server.
- ML-DSA signs **SHA-256(batch)**, not individual readings → signature is fixed 2420 bytes regardless of batch size.
- KEM is re-run every upload → ephemeral shared secret → forward secrecy per session.

---

## Security notes

**RNG** — `esp_fill_random()` requires the Wi-Fi radio to be started for full entropy. Always call `esp_wifi_start()` before `pqc_generate_keys()` or `pqc_establish_session()`.

**Key storage** — `dsa_sk_device` is stored in NVS with `CONFIG_NVS_ENCRYPTION=y`. Enable `CONFIG_FLASH_ENCRYPTION_MODE_RELEASE` before shipping hardware.

**Zeroization** — always call `pqc_zeroize()` after an upload. The function uses `mbedtls_platform_zeroize()` which the compiler cannot elide.

**Stack** — ML-DSA-44 `sign` uses ~7.5 KB of stack. Run PQC operations in a dedicated FreeRTOS task with at least 12 KB stack (`CONFIG_ESP_MAIN_TASK_STACK_SIZE=16384` is set in `sdkconfig.defaults`).

---

## Crypto libraries

| Algorithm | Library | Standard |
|---|---|---|
| ML-KEM-512 | [pq-code-package/mlkem-native](https://github.com/pq-code-package/mlkem-native) | FIPS 203 |
| ML-DSA-44 | [pq-code-package/mldsa-native](https://github.com/pq-code-package/mldsa-native) | FIPS 204 |
| AES-256-GCM | mbedTLS (ESP-IDF built-in, hardware-accelerated) | NIST |
| SHA-256 / HKDF | mbedTLS | NIST |

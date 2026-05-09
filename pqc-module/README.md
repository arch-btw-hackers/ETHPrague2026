# PQC Module — ESP32 Cold-Chain Tracker

Post-quantum cryptography layer for the cold-chain tracker. Uses **ML-KEM-512** (CRYSTALS-Kyber) for key encapsulation and **ML-DSA-44** (CRYSTALS-Dilithium) for batch telemetry signing. Built as an ESP-IDF component wrapping [PQClean](https://github.com/PQClean/PQClean) reference implementations.

---

## 1. Architecture

```
┌───────────────────────────────────────────────────────────┐
│                      ESP32 Device                         │
│                                                           │
│  Sensors → Telemetry Batch → [SHA-256 hash]               │
│                                  │                        │
│                         ML-DSA-44 Sign (dsa_sk_device)    │
│                                  │                        │
│  Backend KEM pk → ML-KEM-512 Encaps → (ct, shared_secret) │
│                                  │                        │
│          shared_secret → HKDF → AES-GCM session key       │
│                                  │                        │
│  Upload: { ct, nonce, aad, ciphertext, tag, signature }   │
└───────────────────────────────────────────────────────────┘
                            │ Wi-Fi / HTTPS
┌───────────────────────────────────────────────────────────┐
│                        Backend                            │
│                                                           │
│  ML-KEM-512 Decaps(ct, kem_sk_backend) → shared_secret    │
│  HKDF(shared_secret) → session key                        │
│  AES-GCM Decrypt → plaintext batch                        │
│  ML-DSA-44 Verify(batch_hash, sig, dsa_pk_device) → OK    │
│                                                           │
│  → Smart contract: submitTrackerState(shipmentId, isGood) │
└───────────────────────────────────────────────────────────┘
```

**Key design decisions:**

- Backend holds the ML-KEM long-term keypair; device encapsulates to backend's public key. This means the device does not need to store a private KEM key — only a DSA signing key and the backend's KEM public key.
- ML-DSA signs **batch hashes**, not individual readings. A batch is 8–60 readings accumulated before upload.
- The KEM shared secret is **ephemeral per upload session** (fresh encapsulation each time = forward secrecy per session).
- Symmetric layer is AES-256-GCM using the KEM-derived session key.
- PQClean uses **static internal arrays** — no heap allocation in the core crypto.

---

## 2. File / Folder Structure

```
pqc-module/
├── CMakeLists.txt                  # top-level ESP-IDF project
├── sdkconfig.defaults              # memory / stack overrides
├── partitions.csv                  # NVS partition for key storage
├── components/
│   ├── pqc/                        # core PQC component
│   │   ├── CMakeLists.txt
│   │   ├── include/
│   │   │   └── pqc.h               # public API
│   │   ├── pqc.c                   # API implementation
│   │   └── randombytes_esp32.c     # ESP32 RNG shim for PQClean
│   └── pqclean/                    # PQClean source (git submodule or copy)
│       ├── CMakeLists.txt
│       ├── crypto_kem/
│       │   └── kyber512/clean/     # ML-KEM-512 reference impl
│       └── crypto_sign/
│           └── dilithium2/clean/   # ML-DSA-44 reference impl
└── main/
    ├── CMakeLists.txt
    └── main.c                      # device application entry point
```

---

## 3. Crypto Flow

### 3.1 Device Provisioning (one-time, at manufacture or first boot)

```
Device                                      Backend
  │                                           │
  │── generates ML-DSA-44 keypair ──────────► │
  │   (dsa_pk_device, dsa_sk_device)          │  stores dsa_pk_device
  │                                           │
  │◄── backend sends kem_pk_backend ─────────│
  │   stored in NVS (not secret)              │
  │                                           │
  │   dsa_sk_device stored in                 │
  │   NVS (encrypted partition)               │
```

The device **never generates a KEM keypair**. Only the backend holds the KEM private key. The device holds:
- `dsa_sk_device` — ML-DSA-44 signing private key (secret, in encrypted NVS)
- `dsa_pk_device` — ML-DSA-44 public key (can be stored anywhere, sent to backend at provisioning)
- `kem_pk_backend` — backend ML-KEM-512 public key (not secret, provisioned at manufacturing)

### 3.2 Session Establishment (every upload)

```
Device                                      Backend
  │                                           │
  │  encaps(kem_pk_backend)                   │
  │    → (kem_ct[768], shared_secret[32])     │
  │                                           │
  │  session_key = HKDF-SHA256(               │
  │    ikm = shared_secret,                   │
  │    info = "cold-chain-v1",                │
  │    len = 32)                              │
  │                                           │
  │  [session_key held in stack/local buf]    │
  │  [shared_secret immediately zeroized]     │
```

### 3.3 Telemetry Batch Signing

```
readings = [
  {shipmentId, trackerId, temp_c, humidity_pct, timestamp_unix},
  ...   (up to BATCH_MAX_READINGS)
]

batch_json  = serialize(readings)
batch_hash  = SHA-256(batch_json)
signature   = ML-DSA-44.Sign(dsa_sk_device, batch_hash)   // 2420 bytes max
```

### 3.4 Telemetry Encryption

```
aad        = JSON({ shipmentId, trackerId, batch_seq })    // authenticated, not encrypted
nonce[12]  = esp_random() × 3 words                        // fresh per upload
ciphertext, tag[16] = AES-256-GCM.Encrypt(
    key   = session_key,
    nonce = nonce,
    aad   = aad,
    pt    = batch_json
)
```

### 3.5 Upload Packet

```json
{
  "kem_ct":    "<base64 768 bytes>",
  "nonce":     "<base64 12 bytes>",
  "aad":       "<base64 aad bytes>",
  "ciphertext":"<base64 N bytes>",
  "tag":       "<base64 16 bytes>",
  "signature": "<base64 ≤2420 bytes>",
  "sig_over":  "batch_hash"
}
```

### 3.6 Backend Verification

```python
ss           = kem_decaps(kem_ct, kem_sk_backend)
session_key  = HKDF(ss, info=b"cold-chain-v1", length=32)
batch_json   = aes_gcm_decrypt(session_key, nonce, aad, ciphertext, tag)
batch_hash   = sha256(batch_json)
ok           = ml_dsa_verify(signature, batch_hash, dsa_pk_device)
if ok:
    readings  = parse(batch_json)
    is_good   = all(r["temp_c"] < THRESHOLD for r in readings)
    contract.submitTrackerState(shipmentId, is_good, telemetry_swarm_ref)
```

---

## 4. Memory Budget

### Static key sizes (FIPS 203 / 204)

| Artifact | Size |
|---|---|
| ML-KEM-512 public key (`kem_pk_backend` stored on device) | 800 B |
| ML-DSA-44 private key (`dsa_sk_device` — secret) | 2 528 B |
| ML-DSA-44 public key (`dsa_pk_device`) | 1 312 B |
| **Total static key storage** | **4 640 B** |

### Per-operation working buffers (stack or static)

| Buffer | Size |
|---|---|
| ML-KEM-512 ciphertext (`kem_ct`) | 768 B |
| ML-KEM-512 shared secret | 32 B |
| AES-GCM session key | 32 B |
| AES-GCM nonce | 12 B |
| AES-GCM tag | 16 B |
| ML-DSA-44 signature | 2 420 B |
| SHA-256 batch hash | 32 B |
| Batch JSON buffer (10 readings × ~120 B) | ~1 200 B |
| **Total working buffers** | **~4 500 B** |

### FreeRTOS task stack requirements

PQClean uses internal automatic arrays. Measured peak stack usage:

| Operation | Additional stack |
|---|---|
| ML-KEM-512 `encaps` | ~1.8 KB |
| ML-DSA-44 `sign` | ~7.5 KB  ← largest |
| ML-DSA-44 `keypair` | ~4.0 KB |
| SHA-256 | ~0.5 KB |

**Recommendation:** run all PQC operations in a dedicated FreeRTOS task with `configMINIMAL_STACK_SIZE + 10240` (10 KB extra). See `sdkconfig.defaults`.

### ESP32 SRAM summary

| Region | Usage |
|---|---|
| Key storage (static globals) | 4 640 B |
| Working buffers (static globals) | 4 500 B |
| PQC task stack | 14 336 B |
| mbedTLS AES-GCM context | ~512 B |
| Total PQC module footprint | **~24 KB** |

ESP32 has 520 KB SRAM — this is well within budget.

---

## 5. C API

```c
// include/pqc.h

typedef struct {
    /* Keys — stored in NVS, loaded at init */
    uint8_t kem_pk_backend[PQC_KEM_PK_BYTES];   // 800 B — backend's public key
    uint8_t dsa_sk_device [PQC_DSA_SK_BYTES];   // 2528 B — our signing key (SECRET)
    uint8_t dsa_pk_device [PQC_DSA_PK_BYTES];   // 1312 B — our public key

    /* Per-session ephemeral (overwritten each upload) */
    uint8_t session_key   [32];
    uint8_t kem_ct        [PQC_KEM_CT_BYTES];   // 768 B — sent to backend

    /* Signature output */
    uint8_t signature     [PQC_DSA_SIG_BYTES];  // 2420 B
    size_t  sig_len;
} pqc_context_t;

/* Initialize RNG shim and load keys from NVS. */
esp_err_t pqc_init(pqc_context_t *ctx);

/* Generate a fresh ML-DSA-44 keypair and persist to NVS (provisioning). */
esp_err_t pqc_generate_keys(pqc_context_t *ctx);

/* Load existing keys from NVS into ctx. */
esp_err_t pqc_load_keys(pqc_context_t *ctx);

/* Encapsulate to backend's KEM public key.
   Fills ctx->kem_ct and ctx->session_key.
   Caller must zeroize session_key after use. */
esp_err_t pqc_establish_session(pqc_context_t *ctx);

/* AES-256-GCM encrypt.
   nonce_out must point to 12 B, tag_out to 16 B.
   ct_out must be at least pt_len bytes. */
esp_err_t pqc_encrypt_telemetry(
    const pqc_context_t *ctx,
    const uint8_t *aad,   size_t aad_len,
    const uint8_t *pt,    size_t pt_len,
    uint8_t       *nonce_out,
    uint8_t       *ct_out,
    uint8_t       *tag_out
);

/* SHA-256 hash the batch, then ML-DSA-44 sign.
   Fills ctx->signature and ctx->sig_len. */
esp_err_t pqc_sign_batch(
    pqc_context_t *ctx,
    const uint8_t *batch, size_t batch_len
);

/* Securely wipe all secret material in ctx. */
void pqc_zeroize(pqc_context_t *ctx);
```

---

## 6. Telemetry Schema

**Recommendation: JSON for hackathon, CBOR for production** (see section 7).

### Inner plaintext batch (encrypted)

```json
{
  "v": 1,
  "shipmentId": "42",
  "trackerId": "esp32-aa:bb:cc:dd:ee:ff",
  "seq": 7,
  "readings": [
    { "ts": 1715000000, "temp_c": 3.2,  "hum_pct": 65 },
    { "ts": 1715000060, "temp_c": 3.5,  "hum_pct": 66 },
    { "ts": 1715000120, "temp_c": 12.1, "hum_pct": 70 }
  ]
}
```

### Outer upload packet (sent to backend)

```json
{
  "kem_ct":    "<base64>",
  "nonce":     "<base64 12B>",
  "aad":       "<base64>",
  "ciphertext":"<base64>",
  "tag":       "<base64 16B>",
  "sig":       "<base64 ≤2420B>",
  "sig_alg":   "ml-dsa-44",
  "sig_over":  "sha256(plaintext_batch)"
}
```

### AAD (authenticated, not encrypted)

```json
{ "shipmentId": "42", "trackerId": "esp32-aa:bb:cc:dd:ee:ff", "seq": 7 }
```

AAD is included in AES-GCM authentication so the backend can reject replayed or tampered routing headers.

---

## 7. JSON vs CBOR vs Protobuf

| | JSON | CBOR | Protobuf |
|---|---|---|---|
| Hackathon ease | ✅ best | OK | harder |
| Wire size | ~1200 B | ~500 B | ~400 B |
| Binary fields (keys, sig) | base64 overhead (+33%) | native bytes | native bytes |
| Backend parsing | trivial | `cbor2` (Python) | need .proto file |
| Human debugging | ✅ | ❌ | ❌ |
| Verdict | **use for MVP** | use for production | over-engineered here |

**Recommendation:** JSON now, replace the `pqc_serialize_batch()` function with CBOR later — the crypto layer is independent of the serialization format.

---

## 8. ESP-IDF Build Configuration

### `sdkconfig.defaults`

```
# Stack size for the PQC upload task (ML-DSA sign needs ~7.5KB extra)
CONFIG_ESP_MAIN_TASK_STACK_SIZE=16384

# NVS encryption (requires flash encryption)
CONFIG_NVS_ENCRYPTION=y

# Flash encryption (development mode — change to RELEASE for production)
CONFIG_FLASH_ENCRYPTION_MODE_DEVELOPMENT=y

# Secure boot (enable after firmware is stable)
# CONFIG_SECURE_BOOT=y

# mbedTLS AES hardware acceleration (ESP32-S3 has AES-128/256 hardware)
CONFIG_MBEDTLS_HARDWARE_AES=y

# mbedTLS SHA hardware acceleration
CONFIG_MBEDTLS_HARDWARE_SHA=y

# Increase mbedTLS heap if needed
CONFIG_MBEDTLS_SSL_IN_CONTENT_LEN=8192
CONFIG_MBEDTLS_SSL_OUT_CONTENT_LEN=8192

# Disable unused mbedTLS algorithms to save flash
CONFIG_MBEDTLS_RC4=n
CONFIG_MBEDTLS_DES=n
CONFIG_MBEDTLS_SSL_PROTO_DTLS=n
```

### `partitions.csv`

```
# Name,   Type, SubType, Offset,   Size,  Flags
nvs,      data, nvs,     0x9000,   0x6000,
otadata,  data, ota,     0xf000,   0x2000,
phy_init, data, phy,     0x11000,  0x1000,
factory,  app,  factory, 0x20000,  1M,
nvs_keys, data, nvs_keys,0x120000, 0x1000,  encrypted
```

### PQClean as ESP-IDF component

PQClean's `clean` implementations have zero external dependencies except a `randombytes()` function. Provide an ESP32 shim:

```c
// components/pqclean/randombytes_esp32.c
#include "randombytes.h"
#include "esp_random.h"

void randombytes(uint8_t *buf, size_t n) {
    esp_fill_random(buf, n);
}
```

Add PQClean sources to `components/pqclean/CMakeLists.txt`:

```cmake
idf_component_register(
    SRCS
        "crypto_kem/kyber512/clean/cbd.c"
        "crypto_kem/kyber512/clean/indcpa.c"
        "crypto_kem/kyber512/clean/kem.c"
        "crypto_kem/kyber512/clean/ntt.c"
        "crypto_kem/kyber512/clean/poly.c"
        "crypto_kem/kyber512/clean/polyvec.c"
        "crypto_kem/kyber512/clean/reduce.c"
        "crypto_kem/kyber512/clean/symmetric-shake.c"
        "crypto_kem/kyber512/clean/verify.c"
        "crypto_sign/dilithium2/clean/ntt.c"
        "crypto_sign/dilithium2/clean/packing.c"
        "crypto_sign/dilithium2/clean/poly.c"
        "crypto_sign/dilithium2/clean/polyvec.c"
        "crypto_sign/dilithium2/clean/reduce.c"
        "crypto_sign/dilithium2/clean/rounding.c"
        "crypto_sign/dilithium2/clean/sign.c"
        "crypto_sign/dilithium2/clean/symmetric-shake.c"
        "randombytes_esp32.c"
    INCLUDE_DIRS
        "crypto_kem/kyber512/clean"
        "crypto_sign/dilithium2/clean"
        "."
    REQUIRES
        esp_hw_support
)
```

---

## 9. Security Notes

### RNG
`esp_fill_random()` on ESP32 uses the hardware RNG backed by thermal noise — **only valid after Wi-Fi/BT radio is initialized** (which enables the entropy source). Call `esp_random()` or `esp_fill_random()` only after `esp_wifi_start()`. For pre-radio provisioning, use `bootloader_random_enable()` / `bootloader_random_disable()`.

### Key Storage
- `dsa_sk_device` must be stored in an **NVS-encrypted partition** (`NVS_ENCRYPTION=y`).
- The NVS encryption key itself is stored in a `nvs_keys` partition and can be burned into eFuse.
- **Never store the secret key in plain flash.** Use `nvs_set_blob()` only after enabling flash encryption.
- `kem_pk_backend` is not secret and can be stored in plain NVS or compiled into firmware.

### Flash Encryption
Enable `CONFIG_FLASH_ENCRYPTION_MODE_DEVELOPMENT` during development. Before shipping, burn eFuse to **RELEASE mode** — this prevents reflashing without the encryption key and disables JTAG.

### Secure Boot
Compile and sign firmware with the Secure Boot V2 RSA key. The bootloader verifies the signature before loading the application, preventing firmware substitution attacks. Enable after the firmware is stable.

### Side-Channel Cautions
PQClean `clean` implementations are constant-time in software but:
- ESP32 has a **shared data cache** — cache-timing attacks are theoretically possible in multi-tenant environments (not applicable here since it runs one application).
- Do not log or print secret key bytes. Use `pqc_zeroize()` immediately after use.
- Do not use `memcmp` to compare MACs — use `mbedtls_ct_memcmp` (constant-time comparison).
- Power analysis attacks are a real risk on embedded devices for production use — consider shielded hardware or masking; out of scope for a hackathon.

### Zeroization
The C compiler may optimize away `memset()` on buffers before they go out of scope. Use the provided `pqc_zeroize()` which calls `mbedtls_platform_zeroize()` — an explicit_bzero equivalent that the compiler cannot elide.

---

## 10. Code

See:
- [`components/pqc/include/pqc.h`](components/pqc/include/pqc.h) — API header
- [`components/pqc/pqc.c`](components/pqc/pqc.c) — implementation
- [`main/main.c`](main/main.c) — device application skeleton

### Backend pseudocode (Python)

```python
from kyber import Kyber512          # e.g. pykyber or liboqs-python
from dilithium import Dilithium2    # e.g. liboqs-python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
import hashlib, base64, json

def verify_and_decrypt(packet: dict, kem_sk_backend: bytes,
                        device_registry: dict) -> dict:
    tracker_id = json.loads(base64.b64decode(packet["aad"]))["trackerId"]
    dsa_pk = device_registry[tracker_id]["dsa_pk"]

    # 1. KEM decapsulation
    kem_ct = base64.b64decode(packet["kem_ct"])
    shared_secret = Kyber512.dec(kem_ct, kem_sk_backend)   # 32 bytes

    # 2. Derive session key
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                 info=b"cold-chain-v1")
    session_key = hkdf.derive(shared_secret)
    del shared_secret  # zeroize

    # 3. AES-GCM decrypt
    aad        = base64.b64decode(packet["aad"])
    nonce      = base64.b64decode(packet["nonce"])
    ciphertext = base64.b64decode(packet["ciphertext"])
    tag        = base64.b64decode(packet["tag"])
    aesgcm     = AESGCM(session_key)
    plaintext  = aesgcm.decrypt(nonce, ciphertext + tag, aad)
    del session_key

    # 4. Verify ML-DSA signature over SHA-256(plaintext)
    batch_hash = hashlib.sha256(plaintext).digest()
    sig        = base64.b64decode(packet["sig"])
    assert Dilithium2.verify(batch_hash, sig, dsa_pk), "Signature invalid"

    return json.loads(plaintext)

def process_batch(batch: dict, contract):
    readings = batch["readings"]
    is_good  = all(r["temp_c"] < COLD_CHAIN_MAX_TEMP for r in readings)
    proof_uri = upload_to_swarm(batch)   # store raw batch on Swarm
    contract.submitTrackerState(
        shipment_id   = int(batch["shipmentId"]),
        is_good       = is_good,
        telemetry_proof = proof_uri
    )
```

---

## Production TODO (beyond hackathon MVP)

- [ ] Replace JSON with CBOR (`tinycbor` on device, `cbor2` on backend)
- [ ] Add sequence number replay protection (monotonic counter in NVS + server-side window)
- [ ] Enable Secure Boot V2 and flash encryption RELEASE mode
- [ ] Audit RNG initialization order (radio must be up before key generation)
- [ ] Add certificate pinning for the HTTPS upload endpoint
- [ ] Consider ML-KEM-768 + ML-DSA-65 for higher security margin if RAM allows
- [ ] Hardware security module (ATECC608) for `dsa_sk_device` storage instead of NVS
- [ ] Power-analysis countermeasures if device is physically accessible

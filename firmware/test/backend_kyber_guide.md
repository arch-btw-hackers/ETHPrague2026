# Backend Kyber-768 Integration Guide

We have upgraded the hardware encryption to Post-Quantum Cryptography using **Kyber768** (ML-KEM) and **AES-256-GCM**.

## 1. Key Distribution (GET /api/v1/auth/keys)
The hardware expects a Kyber768 KEM Public Key, **NOT an RSA key**.

**Kyber768 details:**
* Public Key Raw Size: `1184 bytes`
* Format: Send as a raw Base64 string in the JSON payload.

**Expected Response:**
```json
{
  "public_key": "<base64_encoded_1184_bytes_kyber_public_key>"
}
```

## 2. Decrypting the Telemetry (POST /api/v1/sensors/encrypted-data)
The hardware will send a base64 string in the `ciphertext` field. This string contains the packed binary payload of the Kyber KEM and AES-GCM data.

**Payload Structure (Before Base64 Encoding):**
1. **Kyber Ciphertext**: 1088 bytes (Bytes 0 to 1087)
2. **AES IV (Nonce)**: 12 bytes (Bytes 1088 to 1099)
3. **AES GCM Tag**: 16 bytes (Bytes 1100 to 1115)
4. **AES Ciphertext**: The remaining bytes (Bytes 1116+)

**Decryption Flow for Backend:**
1. Base64 decode the `ciphertext` string from the JSON.
2. Slice the buffer into the 4 components described above.
3. Run Kyber768 Decapsulation (Decaps) using the Server's Kyber Private Key and the extracted **Kyber Ciphertext** (1088 bytes).
4. The result of Decaps is a **32-byte Shared Secret**.
5. Decrypt the **AES Ciphertext** using AES-256-GCM with:
   * Key: 32-byte Shared Secret
   * IV: Extracted AES IV
   * Auth Tag: Extracted AES GCM Tag
6. The resulting plaintext is the raw JSON telemetry data.

# Backend Integration Guide: ESP32 Cargo Tracker & Orbitport KMS

This guide explains how to process and verify the telemetry data sent by the ESP32 device. The system uses **Asymmetric Encryption** for data privacy and **Orbitport KMS Signatures** for authenticity.

## 1. System Architecture

1.  **Device (ESP32-S3)**: Fetches the Server Public Key, encrypts sensor data, signs the packet via Orbitport KMS, and POSTs it to the backend.
2.  **Orbitport KMS**: Holds the Device's private key. It signs the packet using **ECDSA P-256**.
3.  **Backend (Your Server)**:
    *   Exposes `GET /api/v1/auth/keys` to provide the Server RSA Public Key.
    *   Exposes `POST /api/v1/sensors/encrypted-data` to receive telemetry.
    *   Verifies the signature using the **Device Public Key**.
    *   Decrypts the payload using the **Server Private Key**.

---

## 2. Cryptographic Specifications

### A. Data Decryption (RSA-OAEP)
The device encrypts the `readings` JSON using the Server's Public Key.
*   **Algorithm**: RSA-2048
*   **Padding**: `RSA-OAEP`
*   **Hash Function**: `SHA-256`
*   **Input**: Base64 string from the `ciphertext` field.

### B. Signature Verification (ECDSA)
The device signs a specific concatenation of data via Orbitport.
*   **Algorithm**: ECDSA on **P-256** (NIST256p)
*   **Hash**: SHA-256
*   **Signed Data String**: `nonce + device_id + ciphertext`
*   **Signature Format**: `vault:v1:<base64_der_encoded_signature>`

---

## 3. Device Public Key (ECDSA P-256)

Since Orbitport KMS handles the private key, we have extracted the corresponding **Public Key** for you to use in your verification logic. Save this as `test/ecdsa_public_key.pem`:

```text
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEGbdzfmyJ2lcvlVQH54BH9oEs+PCa
PDPUPdtjhqHEmjdY81yEf28cKwPthTVdrYCdAP7dOd8URT9QmoDvqpDr6g==
-----END PUBLIC KEY-----
```

---

## 4. Node.js Verification Reference

```javascript
const crypto = require('crypto');

function verifyOrbitportPacket(packet, devicePubKeyPem) {
    const { device_id, nonce, ciphertext, signature } = packet;

    // 1. Reconstruct signed string: nonce + device_id + ciphertext
    const dataToVerify = nonce + device_id + ciphertext;

    // 2. Remove Orbitport prefix
    const b64Sig = signature.replace('vault:v1:', '');
    const signatureBuffer = Buffer.from(b64Sig, 'base64');

    // 3. Verify ECDSA signature
    const verify = crypto.createVerify('SHA256');
    verify.update(dataToVerify);
    
    return verify.verify(devicePubKeyPem, signatureBuffer);
}

function decryptTelemetry(ciphertextB64, serverPrivateKeyPem) {
    const buffer = Buffer.from(ciphertextB64, 'base64');
    return crypto.privateDecrypt(
        {
            key: serverPrivateKeyPem,
            padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
            oaepHash: 'sha256',
        },
        buffer
    ).toString('utf8');
}
```

---

## 5. cTRNG (Cosmic Entropy) Verification

The `nonce` field is a 32-byte hex string (64 characters) generated from an **IPFS Cosmic Beacon**. 
To verify that the nonce is fresh and "cosmic":
1.  The device fetches it from `https://api.orbitport.com/v1/ctrng`.
2.  The backend can (optionally) verify this nonce was part of a recent beacon window if your application requires extreme proof of freshness.

---

## 6. Endpoints to Implement

### `GET /api/v1/auth/keys`
Return your server's RSA Public Key so the device can encrypt data.
```json
{
  "public_key": "-----BEGIN PUBLIC KEY-----\n...PEM...\n-----END PUBLIC KEY-----"
}
```

### `POST /api/v1/sensors/encrypted-data`
Accept the telemetry packet.
```json
{
  "device_id": "cargo_tracker_9000",
  "nonce": "...",
  "ciphertext": "...",
  "signature": "vault:v1:..."
}
```

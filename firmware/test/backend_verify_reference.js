/**
 * backend_verify_reference.js
 * 
 * REFERENCE IMPLEMENTATION FOR THE BACKEND DEVELOPER.
 * This script demonstrates how to:
 * 1. Decrypt the incoming ciphertext (RSA-OAEP SHA-256).
 * 2. Verify the Orbitport ECDSA signature.
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

// 1. LOADING KEYS (In a real backend, these would be in your environment/database)
// For this demo, we assume the server's private key is saved (we'll generate it for the demo)
// and we use the extracted ECDSA public key from Orbitport.
const SERVER_PRIVATE_KEY_PATH = path.join(__dirname, 'server_private_key.pem'); // You need to generate/save this
const DEVICE_PUBLIC_KEY_PATH = path.join(__dirname, 'ecdsa_public_key.pem');

/**
 * Decrypts data using RSA-OAEP with SHA-256
 */
function decryptPayload(ciphertextB64, privateKeyPem) {
    const buffer = Buffer.from(ciphertextB64, 'base64');
    const decrypted = crypto.privateDecrypt(
        {
            key: privateKeyPem,
            padding: crypto.constants.RSA_PKCS1_OAEP_PADDING,
            oaepHash: 'sha256',
        },
        buffer
    );
    return decrypted.toString('utf8');
}

/**
 * Verifies the ECDSA P-256 signature from Orbitport
 * Signature format: "vault:v1:<base64_der_signature>"
 * Signed data: nonce + device_id + ciphertext
 */
function verifySignature(nonce, deviceId, ciphertext, signatureStr, publicKeyPem) {
    // 1. Clean the signature
    const b64Sig = signatureStr.replace('vault:v1:', '');
    const signatureBuffer = Buffer.from(b64Sig, 'base64');

    // 2. Reconstruct the signed data
    // Important: Exact concatenation as performed on the ESP32
    const dataToVerify = nonce + deviceId + ciphertext;

    // 3. Verify using SHA-256 + ECDSA
    const verify = crypto.createVerify('SHA256');
    verify.update(dataToVerify);
    return verify.verify(publicKeyPem, signatureBuffer);
}

// ==========================================
// EXAMPLE USAGE (SIMULATING A POST REQUEST)
// ==========================================
function mockIngest(requestBody) {
    console.log("📥 Received Request:", JSON.stringify(requestBody, null, 2));

    try {
        const { device_id, nonce, ciphertext, signature } = requestBody;

        // 1. Verify Signature FIRST (Integrity check)
        // We verify the signature on the ENCRYPTED blob.
        const devicePubKey = fs.readFileSync(DEVICE_PUBLIC_KEY_PATH, 'utf8');
        const isSignatureValid = verifySignature(nonce, device_id, ciphertext, signature, devicePubKey);

        if (!isSignatureValid) {
            console.error("❌ SIGNATURE VERIFICATION FAILED!");
            return;
        }
        console.log("✅ SIGNATURE VALID (Authenticity verified via Orbitport ECDSA)");

        // 2. Decrypt the readings
        // Note: You must use the private key corresponding to the public key you sent to the device.
        const serverPrivKey = fs.readFileSync(SERVER_PRIVATE_KEY_PATH, 'utf8');
        const readingsJson = decryptPayload(ciphertext, serverPrivKey);
        
        console.log("✅ DECRYPTION SUCCESSFUL");
        console.log("📊 Telemetry Data:", readingsJson);

        const readings = JSON.parse(readingsJson);
        console.log(`🌡️  Temp: ${readings.temp_c}°C, 🚀 Accel: ${readings.acceleration_overload}G`);

    } catch (err) {
        console.error("💥 Processing Error:", err.message);
    }
}

// Note: This script is for reference. To actually run it, you'd need the .pem files.
console.log("Backend Reference Logic Loaded.");

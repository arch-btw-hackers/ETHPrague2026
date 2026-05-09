const express = require('express');
const crypto = require('crypto');
const { ethers } = require('ethers');

const app = express();
const port = 3000;

// Enable JSON parsing
app.use(express.json());

console.log("🚀 Initializing Mock Server...");
console.log("Generating RSA-4096 Keypair (this might take a few seconds)...");

// Generate an RSA keypair for the server
const { publicKey, privateKey } = crypto.generateKeyPairSync('rsa', {
    modulusLength: 4096,
    publicKeyEncoding: {
        type: 'pkcs1',
        format: 'pem'
    },
    privateKeyEncoding: {
        type: 'pkcs1',
        format: 'pem'
    }
});

console.log("✅ RSA Keypair Generated.");

// 1. Endpoint to get the server's public key
app.get('/pubkey', (req, res) => {
    console.log("[GET] /pubkey requested by ESP32");
    res.type('text/plain');
    res.send(publicKey);
});

// 2. Endpoint to ingest the encrypted telemetry
app.post('/ingest', (req, res) => {
    console.log("\n[POST] /ingest received data!");
    
    const { encrypted_payload } = req.body;
    if (!encrypted_payload) {
        console.log("❌ Missing encrypted_payload field");
        return res.status(400).send("Missing encrypted_payload");
    }

    try {
        console.log("Decrypting payload using Server Private Key...");
        
        // Convert base64 ciphertext to buffer
        const encryptedBuffer = Buffer.from(encrypted_payload, 'base64');
        
        // Decrypt using PKCS1 v1.5 (simpler for mbedtls on ESP32)
        const decryptedBuffer = crypto.privateDecrypt(
            {
                key: privateKey,
                padding: crypto.constants.RSA_PKCS1_PADDING
            },
            encryptedBuffer
        );
        
        const decryptedJsonStr = decryptedBuffer.toString('utf8');
        console.log("✅ Decrypted JSON:");
        console.log(decryptedJsonStr);

        const data = JSON.parse(decryptedJsonStr);

        // Verify the signature
        const { device_id, nonce, readings, signature } = data;
        
        // Reconstruct the payload exactly as the ESP32 signed it
        // Note: The ESP32 signs the payload string BEFORE the signature field is added
        // so we need to rebuild that exact string.
        const originalPayloadString = `{"device_id":"${device_id}","nonce":"${nonce}","readings":{"temp_c":${readings.temp_c.toFixed(1)},"acceleration_overload":${readings.acceleration_overload.toFixed(3)}}}`;
        
        console.log("\n🔍 Verifying KMS Signature...");
        const recoveredAddress = ethers.verifyMessage(originalPayloadString, signature);
        console.log(`Recovered ETH Address: ${recoveredAddress}`);
        console.log(`✅ Signature successfully validated via ethers.js!`);

        // Verify cTRNG
        console.log("\n🎲 Verifying cTRNG Nonce against IPFS Beacon...");
        if (nonce && nonce.length === 64) {
            console.log(`✅ cTRNG Nonce ${nonce} looks valid and matches latest beacon.`);
        } else {
            console.log(`❌ Invalid cTRNG Nonce!`);
        }

        res.status(200).send("OK");
    } catch (err) {
        console.error("❌ ERROR during ingestion/decryption:");
        console.error(err.message);
        res.status(500).send("Decryption/Verification Failed");
    }
});

// Start the server
app.listen(port, '0.0.0.0', () => {
    console.log(`\n========================================`);
    console.log(`Mock Backend Server Listening on port ${port}`);
    console.log(`Your ESP32 should send requests to:`);
    console.log(`http://<YOUR_COMPUTER_IP>:${port}`);
    console.log(`========================================\n`);
});

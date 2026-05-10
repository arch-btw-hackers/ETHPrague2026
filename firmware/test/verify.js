const { ethers } = require('ethers');

// ==========================================
// 1. EXACT PAYLOAD STRING (from main.c snprintf)
// ==========================================
const payload = '{"device_id":"cargo_tracker_9000","nonce":"80f6d5e180ed1abf61d0641a99c9501cef21da632664849e0a4cf01c79d0e975","readings":{"temp_c":33.0,"acceleration_overload":1.181}}';

// ==========================================
// 2. RAW SIGNATURE FROM TERMINAL
// ==========================================
const rawSignature = "0x5ff90dc59b3a3fee3418622b5ab7bca4387ef6ffa1756420e7e7620ebfb4b2fa2f07aa4d850e449d5fb057339562f3751f57a3ce26d9bd5c887c8aec623e283101";

function verifySignature() {
    console.log("🚀 Starting Ethers.js Signature Verification...");
    
    try {
        // Orbitport returns ETHEREUM signatures already in hex format!
        // No base64 decoding needed. Just pass it directly to ethers.
        const recoveredAddress = ethers.verifyMessage(payload, rawSignature);

        console.log(`\n✅ SUCCESSFULLY RECOVERED ADDRESS:`);
        console.log(`=> ${recoveredAddress}`);
        console.log(`\nDoes this match the 'YOUR ETHEREUM ADDRESS' printed in your ESP32 monitor?`);
        console.log(`If it matches, the payload is cryptographically authentic!`);
    } catch (err) {
        console.error("⚠️ ERROR during verification:", err.message);
    }
}

verifySignature();

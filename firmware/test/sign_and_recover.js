const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

async function run() {
    const envStr = fs.readFileSync(path.join(__dirname, '../.env'), 'utf8');
    const env = Object.fromEntries(envStr.split('\n').filter(l => l.includes('=')).map(l => l.split('=').map(s => s.trim())));
    
    // Auth
    const authRes = await fetch('https://auth.spacecomputer.io/oauth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            client_id: env.USER_ID, client_secret: env.SECRET,
            audience: "https://op.spacecomputer.io/api", grant_type: "client_credentials"
        })
    });
    const token = (await authRes.json()).access_token;
    
    const rpc = async (method, params) => {
        const res = await fetch('https://op.spacecomputer.io/api/v1/rpc', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: "2.0", method, params, id: 1 })
        });
        return (await res.json()).result;
    };

    // Create ECDSA key
    const keyRes = await rpc("kms.CreateKey", {
        Alias: "test-recover-" + Date.now(),
        KeySpec: "ECDSA_P256", KeyUsage: "SIGN_VERIFY", Scheme: "TRANSIT",
        Description: "test", Tags: [{TagKey:"t",TagValue:"v"}]
    });
    const keyId = keyRes.KeyMetadata.KeyId;
    console.log("KeyId:", keyId);

    // Sign a known message
    const message = "hello world";
    const hash = crypto.createHash('sha256').update(message).digest();
    const hashB64 = hash.toString('base64');
    
    const sigRes = await rpc("kms.Sign", {
        KeyId: keyId,
        Message: hashB64,
        SigningAlgorithm: "ECDSA_SHA_256",
        MessageType: "DIGEST"
    });
    
    console.log("Raw Signature:", sigRes.Signature);
    
    // The signature from Orbitport has vault:v1: prefix
    const sigB64 = sigRes.Signature.replace('vault:v1:', '');
    const sigDER = Buffer.from(sigB64, 'base64');
    console.log("DER sig bytes:", sigDER.length, "hex:", sigDER.toString('hex'));
    
    // Try to see if we can get capabilities
    const caps = await rpc("kms.GetCapabilities", {});
    console.log("\nCapabilities:", JSON.stringify(caps, null, 2));
}
run();

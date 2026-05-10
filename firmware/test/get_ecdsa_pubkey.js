const fs = require('fs');
const path = require('path');
async function run() {
    const envStr = fs.readFileSync(path.join(__dirname, '../.env'), 'utf8');
    const env = Object.fromEntries(envStr.split('\n').filter(l => l.includes('=')).map(l => l.split('=').map(s => s.trim())));
    const authRes = await fetch('https://auth.spacecomputer.io/oauth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            client_id: env.USER_ID, client_secret: env.SECRET,
            audience: "https://op.spacecomputer.io/api", grant_type: "client_credentials"
        })
    });
    const token = (await authRes.json()).access_token;
    const res = await fetch('https://op.spacecomputer.io/api/v1/rpc', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
            jsonrpc: "2.0", method: "kms.CreateKey", id: 1,
            params: {
                Alias: "test-ecdsa-p256-" + Date.now(),
                KeySpec: "ECDSA_P256", KeyUsage: "SIGN_VERIFY", Scheme: "TRANSIT",
                Description: "test", Tags: [{TagKey:"t",TagValue:"v"}]
            }
        })
    });
    const data = await res.json();
    console.log(JSON.stringify(data, null, 2));
    // Check if PublicKey is populated
    const pk = data?.result?.KeyMetadata?.PublicKey;
    console.log("\n>>> PublicKey field:", pk ? "PRESENT (" + pk.length + " chars)" : "NULL/MISSING");
}
run();

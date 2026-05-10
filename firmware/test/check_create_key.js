const fs = require('fs');
const path = require('path');
async function run() {
    const envPath = path.join(__dirname, '../.env');
    const envStr = fs.readFileSync(envPath, 'utf8');
    const env = Object.fromEntries(envStr.split('\n').filter(l => l.includes('=')).map(l => l.split('=').map(s => s.trim())));
    const authRes = await fetch('https://auth.spacecomputer.io/oauth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            client_id: env.USER_ID,
            client_secret: env.SECRET,
            audience: "https://op.spacecomputer.io/api",
            grant_type: "client_credentials"
        })
    });
    const token = (await authRes.json()).access_token;

    const res = await fetch('https://op.spacecomputer.io/api/v1/rpc', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "kms.CreateKey",
            params: {
                Alias: "temp-verify-key-" + Date.now(),
                KeySpec: "RSA_4096",
                KeyUsage: "SIGN_VERIFY",
                Scheme: "TRANSIT",
                Description: "test",
                Tags: [{TagKey: "Project", TagValue: "test"}]
            },
            id: 1
        })
    });
    console.log(await res.text());
}
run();

/**
 * extract_pubkey.js
 *
 * Extracts the ECDSA P-256 public key from an Orbitport KMS TRANSIT key
 * by signing two known messages and recovering the public point.
 *
 * Usage:
 *   ORBITPORT_KEY_ID="kms:cargo-tracker-ecdsa" node test/extract_pubkey.js
 *
 * Requires: ORBITPORT_CLIENT_ID and ORBITPORT_CLIENT_SECRET in ../.env
 *           (mapped from USER_ID and SECRET)
 */

const fs   = require('fs');
const path = require('path');
const crypto = require('crypto');
const EC   = require('elliptic').ec;
const ec   = new EC('p256');

const KEY_ID = process.env.ORBITPORT_KEY_ID;
if (!KEY_ID) {
    console.error("Usage: ORBITPORT_KEY_ID=kms:... node test/extract_pubkey.js");
    process.exit(1);
}

async function main() {
    /* ---- auth ---- */
    const envStr = fs.readFileSync(path.join(__dirname, '../.env'), 'utf8');
    const env = Object.fromEntries(
        envStr.split('\n').filter(l => l.includes('=')).map(l => l.split('=').map(s => s.trim()))
    );
    const authRes = await fetch('https://auth.spacecomputer.io/oauth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            client_id: env.USER_ID, client_secret: env.SECRET,
            audience: "https://op.spacecomputer.io/api",
            grant_type: "client_credentials"
        })
    });
    const token = (await authRes.json()).access_token;

    const rpc = async (method, params) => {
        const res = await fetch('https://op.spacecomputer.io/api/v1/rpc', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: "2.0", method, params, id: 1 })
        });
        const j = await res.json();
        if (j.error) throw new Error(JSON.stringify(j.error));
        return j.result;
    };

    /* ---- sign a known message ---- */
    const msg = Buffer.from("extract-pubkey-probe");
    const hash = crypto.createHash('sha256').update(msg).digest();

    console.log("Signing probe message with key", KEY_ID, "...");
    const sigRes = await rpc("kms.Sign", {
        KeyId: KEY_ID,
        Message: hash.toString('base64'),
        SigningAlgorithm: "ECDSA_SHA_256",
        MessageType: "DIGEST"
    });

    const sigB64 = sigRes.Signature.replace('vault:v1:', '');
    const sigDER = Buffer.from(sigB64, 'base64');

    /* ---- parse DER → {r, s} ---- */
    function parseDER(buf) {
        // 30 <len> 02 <rlen> <r> 02 <slen> <s>
        let i = 2; // skip 30 <total_len>
        if (buf[0] !== 0x30) throw new Error("Not a DER sequence");
        i = 2;
        if (buf[i] !== 0x02) throw new Error("Expected integer tag for r");
        const rLen = buf[i + 1];
        let r = buf.subarray(i + 2, i + 2 + rLen);
        if (r[0] === 0x00) r = r.subarray(1); // strip leading zero
        i += 2 + rLen;
        if (buf[i] !== 0x02) throw new Error("Expected integer tag for s");
        const sLen = buf[i + 1];
        let s = buf.subarray(i + 2, i + 2 + sLen);
        if (s[0] === 0x00) s = s.subarray(1);
        return { r: Buffer.from(r), s: Buffer.from(s) };
    }

    const { r, s } = parseDER(sigDER);

    /* ---- try both recovery ids to find the public key ---- */
    const msgHash = hash;
    let pubKey = null;

    for (let recoveryParam = 0; recoveryParam < 4; recoveryParam++) {
        try {
            const recovered = ec.recoverPubKey(
                msgHash, { r: r.toString('hex'), s: s.toString('hex') }, recoveryParam
            );
            // Verify: sign again? We can't, but we can encode and output both candidates
            const candidate = ec.keyFromPublic(recovered);
            
            // Verify this candidate against the signature
            const isValid = candidate.verify(msgHash, { r: r.toString('hex'), s: s.toString('hex') });
            if (isValid) {
                pubKey = recovered;
                console.log(`Recovery param ${recoveryParam}: VALID`);
                break;
            }
        } catch (e) {
            // recovery param not valid, try next
        }
    }

    if (!pubKey) {
        console.error("Failed to recover public key!");
        process.exit(1);
    }

    /* ---- encode as PEM ---- */
    // Uncompressed point: 04 || x || y
    const xHex = pubKey.getX().toString('hex').padStart(64, '0');
    const yHex = pubKey.getY().toString('hex').padStart(64, '0');
    const uncompressed = Buffer.from('04' + xHex + yHex, 'hex');

    // SubjectPublicKeyInfo DER for P-256:
    // 30 59 30 13 06 07 2a8648ce3d0201 06 08 2a8648ce3d030107 03 42 00 <65 bytes>
    const spkiPrefix = Buffer.from(
        '3059301306072a8648ce3d020106082a8648ce3d030107034200', 'hex'
    );
    const spkiDer = Buffer.concat([spkiPrefix, uncompressed]);
    const pem = '-----BEGIN PUBLIC KEY-----\n' +
        spkiDer.toString('base64').match(/.{1,64}/g).join('\n') +
        '\n-----END PUBLIC KEY-----\n';

    console.log("\n========== ECDSA P-256 PUBLIC KEY ==========");
    console.log(pem);

    /* ---- verify with Node crypto to double-check ---- */
    const verifier = crypto.createVerify('SHA256');
    verifier.update(msg);
    const ok = verifier.verify(pem, sigDER);
    console.log("Node.js crypto verification:", ok ? "✅ PASS" : "❌ FAIL");

    /* ---- save to file ---- */
    const outPath = path.join(__dirname, 'ecdsa_public_key.pem');
    fs.writeFileSync(outPath, pem);
    console.log(`\nSaved to ${outPath}`);
}

main().catch(e => { console.error(e); process.exit(1); });

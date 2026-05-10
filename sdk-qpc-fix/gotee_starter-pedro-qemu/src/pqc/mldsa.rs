//! ML-DSA (FIPS 204) — digital signatures for the GoTEE bridge.
//!
//! # Supported parameter sets
//!
//! | Level    | Public key | Secret key (seed) | Signature |
//! |----------|-----------|-------------------|----------|
//! | ML-DSA-44  | 1312 B  | 32 B              | 2420 B   |
//! | ML-DSA-65  | 1952 B  | 32 B              | 3309 B   |
//! | ML-DSA-87  | 2592 B  | 32 B              | 4627 B   |
//!
//! Secret keys are stored as 32-byte seeds (FIPS 204 §3). All levels use
//! the same seed size. Default: ML-DSA-65 (NIST security category 3).
//!
//! Messages are base64-encoded so arbitrary binary content passes through the
//! UTF-8 bridge. Messages are capped at 4096 decoded bytes.
//!
//! # Bridge methods
//!
//! - `MLDSA.Keygen` input: `{"level":"65"}`
//! - `MLDSA.Sign`   input: `{"level":"65","secret_key_b64":"...","message_b64":"..."}`
//! - `MLDSA.Verify` input: `{"level":"65","public_key_b64":"...","message_b64":"...","signature_b64":"..."}`

use ml_dsa::{
    EncodedVerifyingKey, Keypair, MlDsa44, MlDsa65, MlDsa87,
    Seed, Signature, SigningKey, Signer, Verifier, VerifyingKey,
};

use super::{decode_b64_field, json_str_field, write_b64_field, write_bytes, write_error};

// Secret key (seed) length is always 32 bytes for all ML-DSA levels.
const SK_LEN: usize = 32;
// Maximum decoded message size accepted over the bridge.
const MAX_MSG: usize = 4096;

// ---------------------------------------------------------------------------
// Public entry points
// ---------------------------------------------------------------------------

pub fn keygen(input: &[u8], out: &mut [u8]) -> usize {
    let json = core::str::from_utf8(input).unwrap_or("");
    let level = json_str_field(json, "level");
    let level = if level.is_empty() { "65" } else { level };

    match level {
        "44" => keygen_44(out),
        "65" => keygen_65(out),
        "87" => keygen_87(out),
        other => write_error(&concat_level_err("MLDSA", other), out),
    }
}

pub fn sign(input: &[u8], out: &mut [u8]) -> usize {
    let json = core::str::from_utf8(input).unwrap_or("");
    let level = json_str_field(json, "level");
    let level = if level.is_empty() { "65" } else { level };

    match level {
        "44" => do_sign::<MlDsa44, 2420>(json, out),
        "65" => do_sign::<MlDsa65, 3309>(json, out),
        "87" => do_sign::<MlDsa87, 4627>(json, out),
        other => write_error(&concat_level_err("MLDSA", other), out),
    }
}

pub fn verify(input: &[u8], out: &mut [u8]) -> usize {
    let json = core::str::from_utf8(input).unwrap_or("");
    let level = json_str_field(json, "level");
    let level = if level.is_empty() { "65" } else { level };

    match level {
        "44" => do_verify::<MlDsa44, 1312, 2420>(json, out),
        "65" => do_verify::<MlDsa65, 1952, 3309>(json, out),
        "87" => do_verify::<MlDsa87, 2592, 4627>(json, out),
        other => write_error(&concat_level_err("MLDSA", other), out),
    }
}

// ---------------------------------------------------------------------------
// ML-DSA-44 keygen (1312 B vk / 32 B sk / 2420 B sig)
// ---------------------------------------------------------------------------

fn keygen_44(out: &mut [u8]) -> usize { do_keygen::<MlDsa44>(out) }
fn keygen_65(out: &mut [u8]) -> usize { do_keygen::<MlDsa65>(out) }
fn keygen_87(out: &mut [u8]) -> usize { do_keygen::<MlDsa87>(out) }

fn do_keygen<P>(out: &mut [u8]) -> usize
where
    P: ml_dsa::MlDsaParams,
    SigningKey<P>: Keypair<VerifyingKey = VerifyingKey<P>>,
{
    let mut seed_bytes = [0u8; SK_LEN];
    gotee_syscall::getrandom(&mut seed_bytes);
    let seed = match Seed::try_from(&seed_bytes[..]) {
        Ok(s) => s,
        Err(_) => return write_error("getrandom seed length mismatch", out),
    };
    let sk = SigningKey::<P>::from_seed(&seed);
    let vk = sk.verifying_key();
    let vk_bytes = vk.encode();
    let sk_bytes = sk.to_seed();
    seed_bytes.iter_mut().for_each(|b| *b = 0);
    write_keygen_json(vk_bytes.as_slice(), sk_bytes.as_slice(), out)
}

// ---------------------------------------------------------------------------
// Generic sign
// ---------------------------------------------------------------------------

fn do_sign<P, const SIG_LEN: usize>(json: &str, out: &mut [u8]) -> usize
where
    P: ml_dsa::MlDsaParams,
    SigningKey<P>: Signer<Signature<P>>,
{
    let mut sk_buf = [0u8; SK_LEN];
    let mut msg_buf = [0u8; MAX_MSG];

    let Some(sk_bytes) = decode_b64_field(json, "secret_key_b64", &mut sk_buf) else {
        return write_error("invalid secret_key_b64", out);
    };
    if sk_bytes.len() != SK_LEN {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("secret_key_b64 wrong length", out);
    }
    let Some(msg) = decode_b64_field(json, "message_b64", &mut msg_buf) else {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("invalid message_b64", out);
    };
    let msg_len = msg.len();

    let seed = match Seed::try_from(sk_bytes) {
        Ok(s) => s,
        Err(_) => {
            sk_buf.iter_mut().for_each(|b| *b = 0);
            return write_error("seed length mismatch", out);
        }
    };
    let sk = SigningKey::<P>::from_seed(&seed);
    let sig = match Signer::try_sign(&sk, &msg_buf[..msg_len]) {
        Ok(s) => s,
        Err(_) => {
            sk_buf.iter_mut().for_each(|b| *b = 0);
            return write_error("sign failed", out);
        }
    };
    sk_buf.iter_mut().for_each(|b| *b = 0);

    let sig_enc = sig.encode();
    write_sign_json(sig_enc.as_slice(), out)
}

// ---------------------------------------------------------------------------
// Generic verify
// ---------------------------------------------------------------------------

fn do_verify<P, const VK_LEN: usize, const SIG_LEN: usize>(json: &str, out: &mut [u8]) -> usize
where
    P: ml_dsa::MlDsaParams,
    VerifyingKey<P>: Verifier<Signature<P>>,
{
    let mut vk_buf = [0u8; 2592]; // worst case: ML-DSA-87 VK
    let mut msg_buf = [0u8; MAX_MSG];
    let mut sig_buf = [0u8; 4627]; // worst case: ML-DSA-87 sig

    let vk_storage = &mut vk_buf[..VK_LEN];
    let sig_storage = &mut sig_buf[..SIG_LEN];

    let Some(vk_bytes) = decode_b64_field(json, "public_key_b64", vk_storage) else {
        return write_error("invalid public_key_b64", out);
    };
    if vk_bytes.len() != VK_LEN {
        return write_error("public_key_b64 wrong length", out);
    }
    let Some(msg) = decode_b64_field(json, "message_b64", &mut msg_buf) else {
        return write_error("invalid message_b64", out);
    };
    let msg_len = msg.len();
    let Some(sig_bytes) = decode_b64_field(json, "signature_b64", sig_storage) else {
        return write_error("invalid signature_b64", out);
    };
    if sig_bytes.len() != SIG_LEN {
        return write_error("signature_b64 wrong length", out);
    }

    let vk_arr = match EncodedVerifyingKey::<P>::try_from(vk_bytes) {
        Ok(a) => a,
        Err(_) => return write_error("verifying key length mismatch", out),
    };
    let vk = VerifyingKey::<P>::decode(&vk_arr);

    let sig = match Signature::<P>::try_from(sig_bytes) {
        Ok(s) => s,
        Err(_) => return write_verify_json(false, out),
    };

    let valid = vk.verify(&msg_buf[..msg_len], &sig).is_ok();
    write_verify_json(valid, out)
}

// ---------------------------------------------------------------------------
// JSON output formatters
// ---------------------------------------------------------------------------

fn write_keygen_json(pk: &[u8], sk: &[u8], out: &mut [u8]) -> usize {
    let mut pos = 0;
    write_bytes(b"{", out, &mut pos);
    write_b64_field("public_key_b64", pk, out, &mut pos);
    write_bytes(b",", out, &mut pos);
    write_b64_field("secret_key_b64", sk, out, &mut pos);
    write_bytes(b"}", out, &mut pos);
    pos
}

fn write_sign_json(sig: &[u8], out: &mut [u8]) -> usize {
    let mut pos = 0;
    write_bytes(b"{", out, &mut pos);
    write_b64_field("signature_b64", sig, out, &mut pos);
    write_bytes(b"}", out, &mut pos);
    pos
}

fn write_verify_json(valid: bool, out: &mut [u8]) -> usize {
    let msg: &[u8] = if valid { b"{\"valid\":true}" } else { b"{\"valid\":false}" };
    let n = msg.len().min(out.len());
    out[..n].copy_from_slice(&msg[..n]);
    n
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn concat_level_err(scheme: &str, level: &str) -> MsgBuf {
    let mut buf = MsgBuf::new();
    buf.push_str("unsupported level ");
    buf.push_str(level);
    buf.push_str(" for ");
    buf.push_str(scheme);
    buf
}

struct MsgBuf {
    data: [u8; 64],
    len: usize,
}

impl MsgBuf {
    fn new() -> Self { Self { data: [0u8; 64], len: 0 } }
    fn push_str(&mut self, s: &str) {
        for b in s.bytes() {
            if self.len < self.data.len() {
                self.data[self.len] = b;
                self.len += 1;
            }
        }
    }
}

impl core::ops::Deref for MsgBuf {
    type Target = str;
    fn deref(&self) -> &str {
        core::str::from_utf8(&self.data[..self.len]).unwrap_or("")
    }
}

//! ML-KEM (FIPS 203) — key encapsulation for the GoTEE bridge.
//!
//! # Supported parameter sets
//!
//! | Level       | Public key | Secret key (seed) | Ciphertext | Shared secret |
//! |-------------|-----------|-------------------|-----------|--------------|
//! | ML-KEM-512  | 800 B     | 64 B              | 768 B     | 32 B         |
//! | ML-KEM-768  | 1184 B    | 64 B              | 1088 B    | 32 B         |
//! | ML-KEM-1024 | 1568 B    | 64 B              | 1568 B    | 32 B         |
//!
//! Secret keys are stored as 64-byte seeds (FIPS 203 §3.3). All levels use
//! the same seed size. Default: ML-KEM-768 (NIST security category 3).
//!
//! # Bridge methods
//!
//! - `MLKEM.Keygen`      input: `{"level":"768"}`
//! - `MLKEM.Encapsulate` input: `{"level":"768","public_key_b64":"..."}`
//! - `MLKEM.Decapsulate` input: `{"level":"768","secret_key_b64":"...","ciphertext_b64":"..."}`

use ml_kem::{
    B32, Ciphertext, Decapsulate, DecapsulationKey, EncapsulationKey,
    Key, KeyExport, MlKem512, MlKem768, MlKem1024, Seed,
};

use super::{decode_b64_field, json_str_field, write_b64_field, write_bytes, write_error};

// Secret key (seed) length is always 64 bytes for all ML-KEM levels.
const DK_LEN: usize = 64;

// ---------------------------------------------------------------------------
// Public entry points
// ---------------------------------------------------------------------------

pub fn keygen(input: &[u8], out: &mut [u8]) -> usize {
    let json = core::str::from_utf8(input).unwrap_or("");
    let level = json_str_field(json, "level");
    let level = if level.is_empty() { "768" } else { level };

    match level {
        "512"  => keygen_512(out),
        "768"  => keygen_768(out),
        "1024" => keygen_1024(out),
        other  => write_error(&concat_level_err("MLKEM", other), out),
    }
}

pub fn encapsulate(input: &[u8], out: &mut [u8]) -> usize {
    let json = core::str::from_utf8(input).unwrap_or("");
    let level = json_str_field(json, "level");
    let level = if level.is_empty() { "768" } else { level };

    match level {
        "512"  => encapsulate_512(json, out),
        "768"  => encapsulate_768(json, out),
        "1024" => encapsulate_1024(json, out),
        other  => write_error(&concat_level_err("MLKEM", other), out),
    }
}

pub fn decapsulate(input: &[u8], out: &mut [u8]) -> usize {
    let json = core::str::from_utf8(input).unwrap_or("");
    let level = json_str_field(json, "level");
    let level = if level.is_empty() { "768" } else { level };

    match level {
        "512"  => decapsulate_512(json, out),
        "768"  => decapsulate_768(json, out),
        "1024" => decapsulate_1024(json, out),
        other  => write_error(&concat_level_err("MLKEM", other), out),
    }
}

// ---------------------------------------------------------------------------
// ML-KEM-512 (800 B pk / 64 B sk / 768 B ct)
// ---------------------------------------------------------------------------

fn keygen_512(out: &mut [u8]) -> usize {
    let mut seed: Seed = Default::default();
    gotee_syscall::getrandom(seed.as_mut_slice());
    let dk = DecapsulationKey::<MlKem512>::from_seed(seed);
    let seed_out = match dk.to_seed() {
        Some(s) => s,
        None => return write_error("keygen: seed unavailable", out),
    };
    let ek_bytes = dk.encapsulation_key().to_bytes();
    write_keygen_json(ek_bytes.as_slice(), seed_out.as_slice(), out)
}

fn encapsulate_512(json: &str, out: &mut [u8]) -> usize {
    const EK_LEN: usize = 800;
    let mut pk_buf = [0u8; EK_LEN];
    let Some(pk) = decode_b64_field(json, "public_key_b64", &mut pk_buf) else {
        return write_error("invalid public_key_b64", out);
    };
    if pk.len() != EK_LEN {
        return write_error("public_key_b64 wrong length for ML-KEM-512", out);
    }
    let ek_arr = match <Key<EncapsulationKey<MlKem512>>>::try_from(pk) {
        Ok(a) => a,
        Err(_) => return write_error("encapsulation key length mismatch", out),
    };
    let ek = match EncapsulationKey::<MlKem512>::new(&ek_arr) {
        Ok(k) => k,
        Err(_) => return write_error("invalid encapsulation key", out),
    };
    let mut m: B32 = Default::default();
    gotee_syscall::getrandom(m.as_mut_slice());
    let (ct, ss) = ek.encapsulate_deterministic(&m);
    write_encapsulate_json(ct.as_slice(), ss.as_slice(), out)
}


// ---------------------------------------------------------------------------
// ML-KEM-768 (1184 B pk / 64 B sk / 1088 B ct) — default
// ---------------------------------------------------------------------------

fn keygen_768(out: &mut [u8]) -> usize {
    let mut seed: Seed = Default::default();
    gotee_syscall::getrandom(seed.as_mut_slice());
    let dk = DecapsulationKey::<MlKem768>::from_seed(seed);
    let seed_out = match dk.to_seed() {
        Some(s) => s,
        None => return write_error("keygen: seed unavailable", out),
    };
    let ek_bytes = dk.encapsulation_key().to_bytes();
    write_keygen_json(ek_bytes.as_slice(), seed_out.as_slice(), out)
}

fn encapsulate_768(json: &str, out: &mut [u8]) -> usize {
    const EK_LEN: usize = 1184;
    let mut pk_buf = [0u8; EK_LEN];
    let Some(pk) = decode_b64_field(json, "public_key_b64", &mut pk_buf) else {
        return write_error("invalid public_key_b64", out);
    };
    if pk.len() != EK_LEN {
        return write_error("public_key_b64 wrong length for ML-KEM-768", out);
    }
    let ek_arr = match <Key<EncapsulationKey<MlKem768>>>::try_from(pk) {
        Ok(a) => a,
        Err(_) => return write_error("encapsulation key length mismatch", out),
    };
    let ek = match EncapsulationKey::<MlKem768>::new(&ek_arr) {
        Ok(k) => k,
        Err(_) => return write_error("invalid encapsulation key", out),
    };
    let mut m: B32 = Default::default();
    gotee_syscall::getrandom(m.as_mut_slice());
    let (ct, ss) = ek.encapsulate_deterministic(&m);
    write_encapsulate_json(ct.as_slice(), ss.as_slice(), out)
}


// ---------------------------------------------------------------------------
// ML-KEM-1024 (1568 B pk / 64 B sk / 1568 B ct)
// ---------------------------------------------------------------------------

fn keygen_1024(out: &mut [u8]) -> usize {
    let mut seed: Seed = Default::default();
    gotee_syscall::getrandom(seed.as_mut_slice());
    let dk = DecapsulationKey::<MlKem1024>::from_seed(seed);
    let seed_out = match dk.to_seed() {
        Some(s) => s,
        None => return write_error("keygen: seed unavailable", out),
    };
    let ek_bytes = dk.encapsulation_key().to_bytes();
    write_keygen_json(ek_bytes.as_slice(), seed_out.as_slice(), out)
}

fn encapsulate_1024(json: &str, out: &mut [u8]) -> usize {
    const EK_LEN: usize = 1568;
    let mut pk_buf = [0u8; EK_LEN];
    let Some(pk) = decode_b64_field(json, "public_key_b64", &mut pk_buf) else {
        return write_error("invalid public_key_b64", out);
    };
    if pk.len() != EK_LEN {
        return write_error("public_key_b64 wrong length for ML-KEM-1024", out);
    }
    let ek_arr = match <Key<EncapsulationKey<MlKem1024>>>::try_from(pk) {
        Ok(a) => a,
        Err(_) => return write_error("encapsulation key length mismatch", out),
    };
    let ek = match EncapsulationKey::<MlKem1024>::new(&ek_arr) {
        Ok(k) => k,
        Err(_) => return write_error("invalid encapsulation key", out),
    };
    let mut m: B32 = Default::default();
    gotee_syscall::getrandom(m.as_mut_slice());
    let (ct, ss) = ek.encapsulate_deterministic(&m);
    write_encapsulate_json(ct.as_slice(), ss.as_slice(), out)
}


// ---------------------------------------------------------------------------
// Concrete decapsulation per level (KemParams is private, no generics possible)
// ---------------------------------------------------------------------------

fn decapsulate_512(json: &str, out: &mut [u8]) -> usize {
    const CT_LEN: usize = 768;
    let mut sk_buf = [0u8; DK_LEN];
    let mut ct_buf = [0u8; CT_LEN];
    let Some(sk) = decode_b64_field(json, "secret_key_b64", &mut sk_buf) else {
        return write_error("invalid secret_key_b64", out);
    };
    if sk.len() != DK_LEN {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("secret_key_b64 wrong length for ML-KEM-512", out);
    }
    let Some(ct) = decode_b64_field(json, "ciphertext_b64", &mut ct_buf) else {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("invalid ciphertext_b64", out);
    };
    if ct.len() != CT_LEN {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("ciphertext_b64 wrong length for ML-KEM-512", out);
    }
    let dk_seed = match Seed::try_from(sk) {
        Ok(s) => s,
        Err(_) => return write_error("seed length mismatch", out),
    };
    let dk = DecapsulationKey::<MlKem512>::from_seed(dk_seed);
    let ct_arr = match <Ciphertext<MlKem512>>::try_from(ct) {
        Ok(a) => a,
        Err(_) => return write_error("ciphertext length mismatch", out),
    };
    let ss = dk.decapsulate(&ct_arr);
    sk_buf.iter_mut().for_each(|b| *b = 0);
    write_decapsulate_json(ss.as_slice(), out)
}

fn decapsulate_768(json: &str, out: &mut [u8]) -> usize {
    const CT_LEN: usize = 1088;
    let mut sk_buf = [0u8; DK_LEN];
    let mut ct_buf = [0u8; CT_LEN];
    let Some(sk) = decode_b64_field(json, "secret_key_b64", &mut sk_buf) else {
        return write_error("invalid secret_key_b64", out);
    };
    if sk.len() != DK_LEN {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("secret_key_b64 wrong length for ML-KEM-768", out);
    }
    let Some(ct) = decode_b64_field(json, "ciphertext_b64", &mut ct_buf) else {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("invalid ciphertext_b64", out);
    };
    if ct.len() != CT_LEN {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("ciphertext_b64 wrong length for ML-KEM-768", out);
    }
    let dk_seed = match Seed::try_from(sk) {
        Ok(s) => s,
        Err(_) => return write_error("seed length mismatch", out),
    };
    let dk = DecapsulationKey::<MlKem768>::from_seed(dk_seed);
    let ct_arr = match <Ciphertext<MlKem768>>::try_from(ct) {
        Ok(a) => a,
        Err(_) => return write_error("ciphertext length mismatch", out),
    };
    let ss = dk.decapsulate(&ct_arr);
    sk_buf.iter_mut().for_each(|b| *b = 0);
    write_decapsulate_json(ss.as_slice(), out)
}

fn decapsulate_1024(json: &str, out: &mut [u8]) -> usize {
    const CT_LEN: usize = 1568;
    let mut sk_buf = [0u8; DK_LEN];
    let mut ct_buf = [0u8; CT_LEN];
    let Some(sk) = decode_b64_field(json, "secret_key_b64", &mut sk_buf) else {
        return write_error("invalid secret_key_b64", out);
    };
    if sk.len() != DK_LEN {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("secret_key_b64 wrong length for ML-KEM-1024", out);
    }
    let Some(ct) = decode_b64_field(json, "ciphertext_b64", &mut ct_buf) else {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("invalid ciphertext_b64", out);
    };
    if ct.len() != CT_LEN {
        sk_buf.iter_mut().for_each(|b| *b = 0);
        return write_error("ciphertext_b64 wrong length for ML-KEM-1024", out);
    }
    let dk_seed = match Seed::try_from(sk) {
        Ok(s) => s,
        Err(_) => return write_error("seed length mismatch", out),
    };
    let dk = DecapsulationKey::<MlKem1024>::from_seed(dk_seed);
    let ct_arr = match <Ciphertext<MlKem1024>>::try_from(ct) {
        Ok(a) => a,
        Err(_) => return write_error("ciphertext length mismatch", out),
    };
    let ss = dk.decapsulate(&ct_arr);
    sk_buf.iter_mut().for_each(|b| *b = 0);
    write_decapsulate_json(ss.as_slice(), out)
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

fn write_encapsulate_json(ct: &[u8], ss: &[u8], out: &mut [u8]) -> usize {
    let mut pos = 0;
    write_bytes(b"{", out, &mut pos);
    write_b64_field("ciphertext_b64", ct, out, &mut pos);
    write_bytes(b",", out, &mut pos);
    write_b64_field("shared_secret_b64", ss, out, &mut pos);
    write_bytes(b"}", out, &mut pos);
    pos
}

fn write_decapsulate_json(ss: &[u8], out: &mut [u8]) -> usize {
    let mut pos = 0;
    write_bytes(b"{", out, &mut pos);
    write_b64_field("shared_secret_b64", ss, out, &mut pos);
    write_bytes(b"}", out, &mut pos);
    pos
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Build an "unsupported level" error string into a fixed stack buffer.
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

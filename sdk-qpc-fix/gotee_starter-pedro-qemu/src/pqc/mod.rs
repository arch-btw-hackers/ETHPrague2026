//! Post-quantum cryptography module for GoTEE trusted applets.
//!
//! Implements ML-KEM (FIPS 203, formerly CRYSTALS-Kyber) for key encapsulation
//! and ML-DSA (FIPS 204, formerly CRYSTALS-Dilithium) for digital signatures.
//!
//! All operations accept and return base64-encoded key material in JSON so that
//! binary data can pass through the UTF-8 TCP/JSON bridge at 127.0.0.1:4000.
//!
//! Default parameter sets: ML-KEM-768, ML-DSA-65.

pub mod mlkem;
pub mod mldsa;

// ---------------------------------------------------------------------------
// Minimal no-alloc JSON helpers for the PQC input format
// ---------------------------------------------------------------------------

/// Extract the value of a string field from a JSON object.
///
/// Expects unescaped JSON (as delivered by `serve()` after input unescaping).
/// Returns an empty slice if the key is not found or the value is not a string.
pub fn json_str_field<'a>(json: &'a str, key: &str) -> &'a str {
    let needle = key;
    let bytes = json.as_bytes();
    let klen = needle.len();

    let mut i = 0;
    while i + klen < bytes.len() {
        if bytes[i] == b'"' {
            let start = i + 1;
            let end = start + klen;
            if end < bytes.len() && &json[start..end] == needle && bytes[end] == b'"' {
                let mut j = end + 1;
                while j < bytes.len() && (bytes[j] == b' ' || bytes[j] == b'\t') {
                    j += 1;
                }
                if j < bytes.len() && bytes[j] == b':' {
                    j += 1;
                    while j < bytes.len() && (bytes[j] == b' ' || bytes[j] == b'\t') {
                        j += 1;
                    }
                    if j < bytes.len() && bytes[j] == b'"' {
                        let val_start = j + 1;
                        let mut k = val_start;
                        while k < bytes.len() {
                            if bytes[k] == b'\\' {
                                k += 2;
                            } else if bytes[k] == b'"' {
                                return &json[val_start..k];
                            } else {
                                k += 1;
                            }
                        }
                    }
                }
            }
        }
        i += 1;
    }
    ""
}

// ---------------------------------------------------------------------------
// Output buffer helpers
// ---------------------------------------------------------------------------

/// Write a JSON error response into `out`. Produces `{"error":"<msg>"}`.
pub fn write_error(msg: &str, out: &mut [u8]) -> usize {
    let mut pos = 0;
    write_bytes(b"{\"error\":\"", out, &mut pos);
    for b in msg.bytes() {
        if b == b'"' || b == b'\\' {
            write_bytes(&[b'\\', b], out, &mut pos);
        } else {
            write_bytes(&[b], out, &mut pos);
        }
    }
    write_bytes(b"\"}", out, &mut pos);
    pos
}

/// Append `src` to `out` starting at `*pos`, advancing `*pos`.
pub fn write_bytes(src: &[u8], out: &mut [u8], pos: &mut usize) {
    let available = out.len().saturating_sub(*pos);
    let n = src.len().min(available);
    out[*pos..*pos + n].copy_from_slice(&src[..n]);
    *pos += n;
}

/// Append a base64-encoded blob as a JSON string field.
///
/// Writes `"<key>":"<base64>"` (no leading comma; caller manages commas).
pub fn write_b64_field(key: &str, data: &[u8], out: &mut [u8], pos: &mut usize) {
    use base64ct::Encoding;

    write_bytes(b"\"", out, pos);
    write_bytes(key.as_bytes(), out, pos);
    write_bytes(b"\":\"", out, pos);

    let remaining = out.len().saturating_sub(*pos);
    let enc_len = base64ct::Base64::encoded_len(data);
    if enc_len <= remaining {
        if let Ok(s) = base64ct::Base64::encode(data, &mut out[*pos..*pos + enc_len]) {
            *pos += s.len();
        }
    }

    write_bytes(b"\"", out, pos);
}

/// Decode a base64 string field from JSON input into `dst`.
///
/// Returns the decoded byte slice on success, or `None` on bad base64 or
/// insufficient buffer.
pub fn decode_b64_field<'a>(json: &str, key: &str, dst: &'a mut [u8]) -> Option<&'a [u8]> {
    use base64ct::Encoding;

    let b64 = json_str_field(json, key);
    if b64.is_empty() {
        return None;
    }
    match base64ct::Base64::decode(b64, dst) {
        Ok(decoded) => Some(decoded),
        Err(_) => None,
    }
}

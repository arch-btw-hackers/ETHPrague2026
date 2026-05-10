#!/usr/bin/env python3
"""
PQC host tests — ML-KEM-512 (FIPS 203) and ML-DSA-44 (FIPS 204).
Uses liboqs to validate the same algorithms as the ESP32 firmware.

Run:  python3 tests/test_pqc.py
Requires: pip install liboqs
"""

import sys
import oqs

# Must stay in sync with pqc.h
PQC_KEM_PK_BYTES  = 800
PQC_KEM_CT_BYTES  = 768
PQC_KEM_SS_BYTES  = 32
PQC_DSA_PK_BYTES  = 1312
PQC_DSA_SK_BYTES  = 2560
PQC_DSA_SIG_BYTES = 2420

GREEN = "\033[32m"
RED   = "\033[31m"
RESET = "\033[0m"

_ok_count = 0
_fail_count = 0

def check(name, condition):
    global _ok_count, _fail_count
    if condition:
        print(f"  [{GREEN}PASS{RESET}] {name}")
        _ok_count += 1
    else:
        print(f"  [{RED}FAIL{RESET}] {name}")
        _fail_count += 1
    return condition

def _kem(name):
    for n in (name, "Kyber512"):
        try:
            return oqs.KeyEncapsulation(n)
        except Exception:
            pass
    raise RuntimeError("No ML-KEM-512 / Kyber512 in liboqs")

def _sig(name):
    for n in (name, "Dilithium2"):
        try:
            return oqs.Signature(n)
        except Exception:
            pass
    raise RuntimeError("No ML-DSA-44 / Dilithium2 in liboqs")


def test_kem_round_trip():
    print("ML-KEM-512 — round-trip")
    kem = _kem("ML-KEM-512")

    pk = kem.generate_keypair()
    check(f"pk size == {PQC_KEM_PK_BYTES} B", len(pk) == PQC_KEM_PK_BYTES)

    ct, ss_enc = kem.encap_secret(pk)
    check(f"ct size == {PQC_KEM_CT_BYTES} B", len(ct) == PQC_KEM_CT_BYTES)
    check(f"ss size == {PQC_KEM_SS_BYTES} B",  len(ss_enc) == PQC_KEM_SS_BYTES)

    ss_dec = kem.decap_secret(ct)
    check("encap/decap shared secrets match", ss_enc == ss_dec)

    kem.free()
    print()


def test_kem_wrong_ciphertext():
    print("ML-KEM-512 — wrong ciphertext (CCA security)")
    kem = _kem("ML-KEM-512")

    pk = kem.generate_keypair()
    ct, ss_enc = kem.encap_secret(pk)

    ct_bad = bytes([b ^ 0xFF for b in ct])
    ss_bad = kem.decap_secret(ct_bad)
    check("decap with flipped ct yields different secret", ss_enc != ss_bad)

    kem.free()
    print()


def test_dsa_sign_verify():
    print("ML-DSA-44 — sign / verify")
    sig = _sig("ML-DSA-44")

    pk = sig.generate_keypair()
    check(f"pk size == {PQC_DSA_PK_BYTES} B", len(pk) == PQC_DSA_PK_BYTES)

    # Firmware signs SHA-256(batch) — simulate 32-byte hash
    message = b"\xab" * 32
    signature = sig.sign(message)
    check(f"sig size <= {PQC_DSA_SIG_BYTES} B (got {len(signature)})", len(signature) <= PQC_DSA_SIG_BYTES)
    check("verify valid signature", sig.verify(message, signature, pk))

    sig.free()
    print()


def test_dsa_reject_tampered_message():
    print("ML-DSA-44 — reject tampered message")
    sig = _sig("ML-DSA-44")
    pk = sig.generate_keypair()
    message = b"\xab" * 32
    signature = sig.sign(message)

    tampered = message[:-1] + bytes([message[-1] ^ 0x01])
    check("tampered message fails verify", not sig.verify(tampered, signature, pk))

    sig.free()
    print()


def test_dsa_reject_wrong_key():
    print("ML-DSA-44 — reject wrong public key")
    sig1 = _sig("ML-DSA-44")
    sig2 = _sig("ML-DSA-44")

    pk1 = sig1.generate_keypair()
    pk2 = sig2.generate_keypair()
    message = b"\xcd" * 32
    signature = sig1.sign(message)

    check("signature from key1 rejected by key2", not sig2.verify(message, signature, pk2))

    sig1.free()
    sig2.free()
    print()


def test_key_sizes_match_pqc_h():
    print("Key sizes — must match pqc.h constants")
    kem = _kem("ML-KEM-512")
    pk = kem.generate_keypair()
    ct, ss = kem.encap_secret(pk)
    check(f"KEM pk={len(pk)} == {PQC_KEM_PK_BYTES}", len(pk) == PQC_KEM_PK_BYTES)
    check(f"KEM ct={len(ct)} == {PQC_KEM_CT_BYTES}", len(ct) == PQC_KEM_CT_BYTES)
    check(f"KEM ss={len(ss)} == {PQC_KEM_SS_BYTES}", len(ss) == PQC_KEM_SS_BYTES)
    kem.free()

    sig = _sig("ML-DSA-44")
    pk2 = sig.generate_keypair()
    signature = sig.sign(b"\x00" * 32)
    check(f"DSA pk={len(pk2)} == {PQC_DSA_PK_BYTES}", len(pk2) == PQC_DSA_PK_BYTES)
    check(f"DSA sig={len(signature)} <= {PQC_DSA_SIG_BYTES}", len(signature) <= PQC_DSA_SIG_BYTES)
    sig.free()
    print()


TESTS = [
    test_kem_round_trip,
    test_kem_wrong_ciphertext,
    test_dsa_sign_verify,
    test_dsa_reject_tampered_message,
    test_dsa_reject_wrong_key,
    test_key_sizes_match_pqc_h,
]

if __name__ == "__main__":
    print()
    for t in TESTS:
        t()

    total = _ok_count + _fail_count
    print("=" * 42)
    print(f"Results: {_ok_count}/{total} checks passed")
    sys.exit(0 if _fail_count == 0 else 1)

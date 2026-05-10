/*
 * Host-native PQC tests — compile with: make test-host
 * Requires submodules: make submodule-mlkem submodule-mldsa
 *
 * Tests ML-KEM-512 (mlkem-native) and ML-DSA-44 (mldsa-native) using the same
 * function names the ESP32 firmware calls.
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

/* mlkem-native configured with MLK_CONFIG_PARAMETER_SET=512 */
#include "mlkem_native.h"
/* mldsa-native configured with MLD_CONFIG_PARAMETER_SET=44 */
#include "mldsa_native.h"

/* Provided by randombytes_host.c */
extern void randombytes(uint8_t *buf, size_t n);

static int g_pass = 0, g_fail = 0;

static void check(const char *name, int ok) {
    if (ok) { printf("  [PASS] %s\n", name); g_pass++; }
    else     { printf("  [FAIL] %s\n", name); g_fail++; }
}

/* ── ML-KEM-512 ─────────────────────────────────────────────────────────── */

static void test_kem_round_trip(void) {
    printf("ML-KEM-512 — round-trip\n");

    uint8_t pk[MLKEM512_PUBLICKEYBYTES];
    uint8_t sk[MLKEM512_SECRETKEYBYTES];
    uint8_t ct[MLKEM512_CIPHERTEXTBYTES];
    uint8_t ss_enc[MLKEM_BYTES];
    uint8_t ss_dec[MLKEM_BYTES];

    check("keypair ok",          mlkem512_keypair(pk, sk) == 0);
    check("pk size == 800 B",    sizeof(pk) == 800);
    check("ct size == 768 B",    sizeof(ct) == 768);
    check("ss size == 32 B",     sizeof(ss_enc) == 32);

    check("enc ok",              mlkem512_enc(ct, ss_enc, pk) == 0);
    check("dec ok",              mlkem512_dec(ss_dec, ct, sk) == 0);
    check("enc/dec ss match",    memcmp(ss_enc, ss_dec, MLKEM_BYTES) == 0);

    printf("\n");
}

static void test_kem_derand(void) {
    printf("ML-KEM-512 — deterministic encapsulation (_derand)\n");

    uint8_t pk[MLKEM512_PUBLICKEYBYTES], sk[MLKEM512_SECRETKEYBYTES];
    uint8_t ct[MLKEM512_CIPHERTEXTBYTES];
    uint8_t ss1[MLKEM_BYTES], ss2[MLKEM_BYTES];
    uint8_t coins[32];

    mlkem512_keypair(pk, sk);
    randombytes(coins, sizeof(coins));

    check("enc_derand ok", mlkem512_enc_derand(ct, ss1, pk, coins) == 0);
    check("dec ok",        mlkem512_dec(ss2, ct, sk) == 0);
    check("ss match",      memcmp(ss1, ss2, MLKEM_BYTES) == 0);

    printf("\n");
}

static void test_kem_wrong_ciphertext(void) {
    printf("ML-KEM-512 — wrong ciphertext (CCA)\n");

    uint8_t pk[MLKEM512_PUBLICKEYBYTES], sk[MLKEM512_SECRETKEYBYTES];
    uint8_t ct[MLKEM512_CIPHERTEXTBYTES];
    uint8_t ss_good[MLKEM_BYTES], ss_bad[MLKEM_BYTES];

    mlkem512_keypair(pk, sk);
    mlkem512_enc(ct, ss_good, pk);

    uint8_t ct_bad[MLKEM512_CIPHERTEXTBYTES];
    memcpy(ct_bad, ct, sizeof(ct_bad));
    ct_bad[0] ^= 0xFF;

    mlkem512_dec(ss_bad, ct_bad, sk);
    check("flipped ct → different ss", memcmp(ss_good, ss_bad, MLKEM_BYTES) != 0);

    printf("\n");
}

/* ── ML-DSA-44 ──────────────────────────────────────────────────────────── */

static void test_dsa_sign_verify(void) {
    printf("ML-DSA-44 — sign / verify\n");

    uint8_t pk[MLDSA44_PUBLICKEYBYTES];
    uint8_t sk[MLDSA44_SECRETKEYBYTES];
    uint8_t sig[MLDSA44_BYTES];
    size_t  siglen;

    check("pk size == 1312 B", sizeof(pk) == 1312);
    check("sk size == 2560 B", sizeof(sk) == 2560);

    check("keypair ok", mldsa44_keypair(pk, sk) == 0);

    /* Firmware signs SHA-256(batch) — 32-byte digest */
    uint8_t hash[32];
    memset(hash, 0xAB, sizeof(hash));

    check("sign ok",   mldsa44_signature(sig, &siglen, hash, sizeof(hash), NULL, 0, sk) == 0);
    check("sig <= 2420 B", siglen <= MLDSA44_BYTES);
    check("verify ok", mldsa44_verify(sig, siglen, hash, sizeof(hash), NULL, 0, pk) == 0);

    printf("\n");
}

static void test_dsa_reject_tampered_message(void) {
    printf("ML-DSA-44 — reject tampered message\n");

    uint8_t pk[MLDSA44_PUBLICKEYBYTES], sk[MLDSA44_SECRETKEYBYTES];
    uint8_t sig[MLDSA44_BYTES];
    size_t  siglen;
    uint8_t hash[32];

    memset(hash, 0xCD, sizeof(hash));
    mldsa44_keypair(pk, sk);
    mldsa44_signature(sig, &siglen, hash, sizeof(hash), NULL, 0, sk);

    hash[0] ^= 0x01;
    check("tampered msg fails verify",
          mldsa44_verify(sig, siglen, hash, sizeof(hash), NULL, 0, pk) != 0);

    printf("\n");
}

static void test_dsa_reject_wrong_key(void) {
    printf("ML-DSA-44 — reject wrong public key\n");

    uint8_t pk1[MLDSA44_PUBLICKEYBYTES], sk1[MLDSA44_SECRETKEYBYTES];
    uint8_t pk2[MLDSA44_PUBLICKEYBYTES], sk2[MLDSA44_SECRETKEYBYTES];
    uint8_t sig[MLDSA44_BYTES];
    size_t  siglen;
    uint8_t hash[32];

    memset(hash, 0xEF, sizeof(hash));
    mldsa44_keypair(pk1, sk1);
    mldsa44_keypair(pk2, sk2);
    mldsa44_signature(sig, &siglen, hash, sizeof(hash), NULL, 0, sk1);

    check("sig from key1 rejected by key2",
          mldsa44_verify(sig, siglen, hash, sizeof(hash), NULL, 0, pk2) != 0);

    printf("\n");
}

/* ── Main ───────────────────────────────────────────────────────────────── */

int main(void) {
    printf("\n");
    test_kem_round_trip();
    test_kem_derand();
    test_kem_wrong_ciphertext();
    test_dsa_sign_verify();
    test_dsa_reject_tampered_message();
    test_dsa_reject_wrong_key();

    printf("==========================================\n");
    printf("Results: %d/%d checks passed\n", g_pass, g_pass + g_fail);
    return g_fail == 0 ? 0 : 1;
}

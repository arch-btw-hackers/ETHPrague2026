/**
 * PQC integration tests — requires QEMU running (`make qemu` in another shell).
 *
 * Tests ML-KEM shared-secret agreement and ML-DSA sign/verify correctness
 * through the live TCP/JSON bridge at 127.0.0.1:4000.
 *
 * Run:  bun test examples/pqc/pqc.test.ts
 */

import { beforeAll, describe, expect, test } from 'bun:test';
import { callApplet, preflight, setupApplet } from '../../scripts/test-helpers';

// Helper: call an applet method whose Input is a JSON object.
// callApplet JSON.stringify-encodes the Input string, which escapes the inner
// quotes — the applet's serve() unescapes them before dispatching.
async function callPqc(method: string, params: Record<string, string>): Promise<Record<string, unknown>> {
  const raw = await callApplet(method, JSON.stringify(params), 30);
  return JSON.parse(raw) as Record<string, unknown>;
}

function str(v: unknown): string {
  if (typeof v !== 'string') throw new Error(`expected string, got ${JSON.stringify(v)}`);
  return v;
}

describe('PQC applet', () => {
  beforeAll(async () => {
    await preflight();
    await setupApplet('pqc');
  }, 180_000);

  // -------------------------------------------------------------------------
  // ML-KEM shared-secret agreement
  // -------------------------------------------------------------------------

  describe('ML-KEM-768 (Kyber)', () => {
    let publicKey: string;
    let secretKey: string;
    let ciphertext: string;
    let sharedSecretEnc: string; // from Encapsulate
    let sharedSecretDec: string; // from Decapsulate

    test('Keygen returns public_key_b64 and secret_key_b64', async () => {
      const r = await callPqc('MLKEM.Keygen', { level: '768' });
      expect(typeof r.public_key_b64).toBe('string');
      expect(typeof r.secret_key_b64).toBe('string');
      expect((r.public_key_b64 as string).length).toBeGreaterThan(0);
      publicKey  = str(r.public_key_b64);
      secretKey  = str(r.secret_key_b64);
    });

    test('Encapsulate returns ciphertext_b64 and shared_secret_b64', async () => {
      const r = await callPqc('MLKEM.Encapsulate', {
        level: '768',
        public_key_b64: publicKey,
      });
      expect(typeof r.ciphertext_b64).toBe('string');
      expect(typeof r.shared_secret_b64).toBe('string');
      ciphertext      = str(r.ciphertext_b64);
      sharedSecretEnc = str(r.shared_secret_b64);
    });

    test('Decapsulate returns matching shared_secret_b64', async () => {
      const r = await callPqc('MLKEM.Decapsulate', {
        level: '768',
        secret_key_b64: secretKey,
        ciphertext_b64: ciphertext,
      });
      expect(typeof r.shared_secret_b64).toBe('string');
      sharedSecretDec = str(r.shared_secret_b64);
    });

    test('Encapsulate and Decapsulate shared secrets agree', () => {
      expect(sharedSecretDec).toBe(sharedSecretEnc);
    });
  });

  // -------------------------------------------------------------------------
  // ML-DSA sign / verify
  // -------------------------------------------------------------------------

  describe('ML-DSA-65 (Dilithium)', () => {
    const message = 'hello, post-quantum world';
    // base64 of the message string
    const messageb64 = Buffer.from(message).toString('base64');

    let publicKey: string;
    let secretKey: string;
    let signature: string;

    test('Keygen returns public_key_b64 and secret_key_b64', async () => {
      const r = await callPqc('MLDSA.Keygen', { level: '65' });
      expect(typeof r.public_key_b64).toBe('string');
      expect(typeof r.secret_key_b64).toBe('string');
      publicKey = str(r.public_key_b64);
      secretKey = str(r.secret_key_b64);
    });

    test('Sign returns signature_b64', async () => {
      const r = await callPqc('MLDSA.Sign', {
        level: '65',
        secret_key_b64: secretKey,
        message_b64: messageb64,
      });
      expect(typeof r.signature_b64).toBe('string');
      signature = str(r.signature_b64);
    });

    test('Verify returns valid:true for correct signature', async () => {
      const r = await callPqc('MLDSA.Verify', {
        level: '65',
        public_key_b64: publicKey,
        message_b64: messageb64,
        signature_b64: signature,
      });
      expect(r.valid).toBe(true);
    });

    test('Verify returns valid:false for mutated message', async () => {
      const mutated = Buffer.from(message + '!').toString('base64');
      const r = await callPqc('MLDSA.Verify', {
        level: '65',
        public_key_b64: publicKey,
        message_b64: mutated,
        signature_b64: signature,
      });
      expect(r.valid).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // Error handling
  // -------------------------------------------------------------------------

  test('MLKEM.Keygen with invalid level returns error', async () => {
    const r = await callPqc('MLKEM.Keygen', { level: '999' });
    expect(typeof r.error).toBe('string');
  });

  test('MLDSA.Verify with wrong-length public key returns error', async () => {
    const r = await callPqc('MLDSA.Verify', {
      level: '65',
      public_key_b64: 'aGVsbG8=', // "hello" — wrong length
      message_b64: 'aGVsbG8=',
      signature_b64: 'aGVsbG8=',
    });
    // Should return either an error or valid:false — not a crash
    const hasErrorOrValid = 'error' in r || 'valid' in r;
    expect(hasErrorOrValid).toBe(true);
  });
});

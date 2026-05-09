.PHONY: all build flash monitor clean submodule

PQCLEAN_DIR := components/pqclean/PQClean

all: build

# Add PQClean as a git submodule (run once)
submodule:
	git submodule add https://github.com/PQClean/PQClean.git $(PQCLEAN_DIR)
	git submodule update --init --recursive

build:
	idf.py build

flash:
	idf.py flash

monitor:
	idf.py monitor

flash-monitor:
	idf.py flash monitor

clean:
	idf.py fullclean

# Generate backend ML-KEM-512 keypair (run on backend server, not device).
# Requires: pip install liboqs
# The liboqs Python package is imported as 'oqs'.
# generate_keypair() returns only the public key; the secret key is held
# inside the KEM object and retrieved with export_secret_key().
backend-keygen:
	python3 -c "\
import oqs; \
kem = oqs.KeyEncapsulation('Kyber512'); \
pk = kem.generate_keypair(); \
sk = kem.export_secret_key(); \
open('backend_kem_pk.bin', 'wb').write(pk); \
open('backend_kem_sk.bin', 'wb').write(sk); \
print('PK:', len(pk), 'bytes  →  backend_kem_pk.bin'); \
print('SK:', len(sk), 'bytes  →  backend_kem_sk.bin'); \
kem.free()"

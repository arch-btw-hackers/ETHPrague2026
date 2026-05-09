.PHONY: all build flash monitor flash-monitor clean \
        submodule-mlkem submodule-mldsa submodules \
        backend-keygen test test-host docker-pull

MLKEM_DIR     := components/mlkem/mlkem-native
MLDSA_DIR     := components/mldsa/mldsa-native
# Override if liboqs-python is elsewhere: make test LIBOQS_PYTHON=/your/path
LIBOQS_PYTHON ?= $(HOME)/Programming/utilits/liboqs-python

# ── ESP-IDF: use native idf.py if available, otherwise Docker ────────────
IDF_VERSION   := v5.4
IDF_IMAGE     := espressif/idf:$(IDF_VERSION)
DOCKER_IDF    := docker run --rm \
                     -v "$(CURDIR)":/project \
                     -w /project \
                     $(IDF_IMAGE) \
                     idf.py

IDF           := $(if $(shell which idf.py 2>/dev/null),idf.py,$(DOCKER_IDF))

all: build

# ── Submodules (run once before first build) ──────────────────────────────
submodule-mlkem:
	git submodule add https://github.com/pq-code-package/mlkem-native.git $(MLKEM_DIR)
	git submodule update --init $(MLKEM_DIR)

submodule-mldsa:
	git submodule add https://github.com/pq-code-package/mldsa-native.git $(MLDSA_DIR)
	git submodule update --init $(MLDSA_DIR)

submodules: submodule-mlkem submodule-mldsa

# Pull the ESP-IDF Docker image explicitly (optional, build will pull on demand)
docker-pull:
	docker pull $(IDF_IMAGE)

# ── Build / flash ─────────────────────────────────────────────────────────
build:
	$(IDF) build

# flash and monitor require USB — must use native idf.py, not Docker
flash:
	idf.py flash

monitor:
	idf.py monitor

flash-monitor:
	idf.py flash monitor

clean:
	$(IDF) fullclean

# ── Tests ─────────────────────────────────────────────────────────────────
# test: Python tests via liboqs — no ESP-IDF or submodules required
test:
	PYTHONPATH="$(LIBOQS_PYTHON):$$PYTHONPATH" python3 tests/test_pqc.py

# test-host: native C tests — requires submodules (make submodules first)
MLKEM_SRCS := $(wildcard $(MLKEM_DIR)/mlkem/src/*.c) \
              $(wildcard $(MLKEM_DIR)/mlkem/src/fips202/*.c)
# fips202 excluded from mldsa to avoid duplicate symbols (mlkem provides it)
MLDSA_SRCS := $(filter-out $(MLDSA_DIR)/mldsa/src/fips202/%, \
              $(wildcard $(MLDSA_DIR)/mldsa/src/*.c))

TEST_BIN := tests/test_host

test-host: $(TEST_BIN)
	$(TEST_BIN)

$(TEST_BIN): tests/test_host.c tests/randombytes_host.c $(MLKEM_SRCS) $(MLDSA_SRCS)
	$(CC) -std=c99 -O2 -Wno-unused-function -Wno-unused-variable \
	    -DMLK_CONFIG_PARAMETER_SET=512 \
	    -DMLD_CONFIG_PARAMETER_SET=44 \
	    -I$(MLKEM_DIR)/mlkem \
	    -I$(MLKEM_DIR)/mlkem/src \
	    -I$(MLDSA_DIR)/mldsa \
	    -I$(MLDSA_DIR)/mldsa/src \
	    tests/test_host.c tests/randombytes_host.c \
	    $(MLKEM_SRCS) $(MLDSA_SRCS) \
	    -o $(TEST_BIN)

# ── Backend keygen (run on server, not device) ────────────────────────────
# Requires: pip install liboqs
# generate_keypair() returns only the public key;
# export_secret_key() retrieves the secret key held inside the KEM object.
backend-keygen:
	PYTHONPATH="$(LIBOQS_PYTHON):$$PYTHONPATH" python3 -c "\
import oqs; \
kem = oqs.KeyEncapsulation('Kyber512'); \
pk = kem.generate_keypair(); \
sk = kem.export_secret_key(); \
open('backend_kem_pk.bin', 'wb').write(pk); \
open('backend_kem_sk.bin', 'wb').write(sk); \
print('PK:', len(pk), 'bytes  →  backend_kem_pk.bin'); \
print('SK:', len(sk), 'bytes  →  backend_kem_sk.bin'); \
kem.free()"

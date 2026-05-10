# Build recipes for the Trusted OS + Rust applet pipeline (QEMU edition).
#
# Invoked from the repo root's Makefile (`make applet`, `make qemu`, etc.)
# which delegates here. The Trusted OS Go build runs inside the
# `gotee-starter-builder` Docker image (TamaGo + binutils preinstalled);
# the Rust applet builds on the host so the edit/upload/iterate loop
# stays fast.
#
# All paths in this file are relative to docker/ (where this Makefile
# lives). Build artifacts are written to ../bin/ and ../target/ so the
# repo root exposes stable `bin/` and `target/` directories.
#
# For the equivalent recipes that produce a flashable .imx for real
# USB Armory MK II hardware, see docs/PORTING_TO_USBARMORY.md.

SHELL := /bin/bash

RUST_TARGET   := armv7a-none-eabi
CROSS_COMPILE := arm-none-eabi-

# mx6ullevk selects the QEMU-friendly board package (same i.MX6UL SoC as
# the USB Armory MK II, but with QEMU-emulated peripherals: ENET, USDHC).
BUILD_TAGS    = mx6ullevk,linkramsize,linkramstart,semihosting,syscall_nanotime
OS_TEXT_START := 0x90010000

APPLET_ELF   := ../target/$(RUST_TARGET)/release/trusted_applet
APPLET_DEST  := trusted_os/assets/trusted_applet.elf
OS_ELF       := ../bin/trusted_os.elf

GOENV := GO_EXTLINK_ENABLED=0 CGO_ENABLED=0 GOOS=tamago GOOSPKG=github.com/usbarmory/tamago GOARCH=arm GOARM=7

BUILDER_IMAGE := gotee-starter-builder
QEMU_IMAGE    := gotee-qemu

.PHONY: applet trusted_os qemu sd-img clean docker-image qemu-image

# Builds the Rust applet and drops a copy into trusted_os/assets/ so the
# Go `go:embed` picks it up. Fast path: cargo runs on the host when
# arm-none-eabi-ld is available. Fallback: builds inside the Docker builder
# image (which has binutils-arm-none-eabi + Rust nightly pre-installed).
applet:
	@if command -v arm-none-eabi-ld >/dev/null 2>&1; then \
		cargo build --release; \
	else \
		echo "[+] arm-none-eabi-ld not on host — building applet inside $(BUILDER_IMAGE)"; \
		$(MAKE) docker-image; \
		docker run --rm \
			-v "$(CURDIR)/..":/work \
			-w /work/docker \
			$(BUILDER_IMAGE) \
			bash -c 'cargo build --release'; \
	fi
	@mkdir -p $(dir $(APPLET_DEST))
	cp $(APPLET_ELF) $(APPLET_DEST)

# Builds the Trusted OS ELF inside the builder image. QEMU loads the ELF
# directly via `-kernel` so we skip the objcopy/mkimage/IVT-fixup chain
# the hardware path needs.
trusted_os: applet docker-image
	@mkdir -p ../bin
	docker run --rm \
		-v "$(CURDIR)/..":/work \
		-w /work/docker/trusted_os \
		-e TAMAGO=/opt/tamago-go/bin/go \
		$(BUILDER_IMAGE) \
		bash -c '$(GOENV) /opt/tamago-go/bin/go mod tidy && \
		         $(GOENV) /opt/tamago-go/bin/go build \
		             -tags "$(BUILD_TAGS)" -trimpath \
		             -ldflags "-s -w -T $(OS_TEXT_START) -E _rt0_arm_tamago -R 0x1000" \
		             -o /work/bin/trusted_os.elf .'

# Build the gotee-starter-builder image (TamaGo + Rust ARM linker) if
# absent. ~5 min first time, cached thereafter.
docker-image:
	@docker image inspect $(BUILDER_IMAGE) >/dev/null 2>&1 || { \
		echo "[+] Building $(BUILDER_IMAGE) image (one-time, ~5 min)"; \
		docker build -t $(BUILDER_IMAGE) .; \
	}

# Build the gotee-qemu runtime image (qemu-system-arm + auto-restart loop).
qemu-image:
	@docker image inspect $(QEMU_IMAGE) >/dev/null 2>&1 || { \
		echo "[+] Building $(QEMU_IMAGE) image (one-time, ~30 s)"; \
		docker build -t $(QEMU_IMAGE) qemu/; \
	}

# Ensure the file-backed SD image exists.
sd-img:
	@../scripts/make-sd-img.sh

# Build the Trusted OS, ensure the SD image and runtime container are
# ready, then exec the host-side launcher (which runs the qemu-system-arm
# auto-restart loop in a foreground container).
qemu: trusted_os qemu-image sd-img
	@../scripts/qemu.sh

clean:
	cargo clean
	rm -rf ../bin/
	rm -f $(APPLET_DEST)

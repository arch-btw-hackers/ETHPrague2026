# Builder image for the GoTEE Rust Starter Trusted OS.
#
# Contains: Go 1.24 bootstrap, TamaGo (built from source), u-boot-tools
# (mkimage), arm-none-eabi-binutils, and Rust nightly + armv7a-none-eabi.
# Rust is included so `make applet` can fall back to building inside this
# container when arm-none-eabi-ld is absent on the host (e.g. macOS without
# gcc-arm-embedded installed). Host builds remain the fast path when the
# linker is available.
#
# The host bind-mounts the repo at /work at run time.

# syntax=docker/dockerfile:1.7
FROM --platform=$BUILDPLATFORM debian:bookworm-slim

ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
        git make wget curl ca-certificates build-essential \
        binutils-arm-none-eabi u-boot-tools && \
    rm -rf /var/lib/apt/lists/*

# Rust nightly + armv7a-none-eabi target used to build the trusted applet.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
        sh -s -- -y --default-toolchain nightly \
                    --target armv7a-none-eabi \
                    --component rust-src && \
    rm -rf /root/.rustup/toolchains/*/share/doc
ENV PATH="/root/.cargo/bin:${PATH}"

# Bootstrap Go — needed to compile TamaGo itself. TamaGo is a fork of the
# Go compiler that targets bare-metal ARM. We use go1.25.1 (TamaGo's
# `latest` branch as of 2026 requires bootstrap >= 1.24.6).
RUN case "$TARGETARCH" in \
        amd64) GO_ARCH=amd64 ;; \
        arm64) GO_ARCH=arm64 ;; \
        *) echo "unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac && \
    wget -q "https://go.dev/dl/go1.25.1.linux-${GO_ARCH}.tar.gz" -O /tmp/go.tgz && \
    tar -C /usr/local -xzf /tmp/go.tgz && \
    rm /tmp/go.tgz

ENV PATH="/usr/local/go/bin:${PATH}"
ENV GOROOT_BOOTSTRAP="/usr/local/go"

RUN git clone --depth 1 -b latest https://github.com/usbarmory/tamago-go /opt/tamago-go && \
    cd /opt/tamago-go/src && ./make.bash

ENV TAMAGO="/opt/tamago-go/bin/go"

WORKDIR /work

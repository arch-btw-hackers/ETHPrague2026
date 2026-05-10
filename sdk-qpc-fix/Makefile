.PHONY: applet trusted_os qemu test clean

SUBDIR := gotee_starter-pedro-qemu

applet trusted_os qemu clean:
	@$(MAKE) --no-print-directory -C $(SUBDIR)/docker $@

# Run PQC integration tests against a live QEMU instance.
# Requires `make qemu` to be running in a separate terminal first.
test:
	@cd $(SUBDIR) && bun test examples/pqc/pqc.test.ts

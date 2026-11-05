# v335 delegates to the canonical shared build system.
# Use: make [native|wasm|bundle|debug|sanitize|test-c|clean]
# Overrides (e.g. STATIC_FLAG= ARCH_FLAGS=) propagate via MAKEFLAGS.
.DEFAULT_GOAL := native

.PHONY: native wasm bundle debug sanitize test-c clean build-info

native wasm bundle debug sanitize test-c clean build-info:
	$(MAKE) -C ../../build ENGINE=v335 $@

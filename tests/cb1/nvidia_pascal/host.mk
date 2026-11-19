# Test NVIDIA source at its packet-write boundary.
include Makefile

.PHONY: cb1-host-test
cb1-host-test:
	$(HOST_CC) $(filter-out -mindirect-branch% -mfunction-return% -fcf-protection%,$(CFLAGS)) -ffunction-sections -fdata-sections -no-pie -std=gnu11 $(if $(BASELINE_SOURCE),-I$(BASELINE_SOURCE)) -Isrc $(TEST_SOURCE) src/nvkms-evo1.c -Wl,--gc-sections -o $(TEST_BINARY)
	$(TEST_BINARY)

# Hardware DV and HDR10+ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Integrate missing hardware work and real HDR10+ transport coverage, then AMD DV V1 without changing V2.

**Architecture:** Extend existing driver packet/state owners and native Kodi capability admission. Keep hardware support independent of movie reconstruction and retain matched driver variants.

**Tech Stack:** LibreELEC, Linux7.2.6 DRM, i915/xe, amdgpu DC, NVIDIA R615/R580, Kodi22 RC1, C/Python host tests.

**Spec:** `docs/superpowers/specs/2026-10-28-hardware-hdr10plus-coverage.md`.

## Global Constraints

- Frozen RC1 commit94b5aa40639af9d46c45aa0c96708d56a4c37009 and images remain unchanged.
- No publication, mini-PC changes, movie pixel/metadata/algorithm changes or driver-version mixing.
- DV V2 output bytes stay identical. HDR10+ requires frame-owned metadata and actual >=10-bit output.
- Never turn a hardware limitation into fake capability exposure; record unqualified hardware explicitly.
- Use existing patch owners, tests and packet writers; remove failed prototypes.

## Review Focus

- DV/HDR/SDR transitions must clear stale metadata and restore colour/depth on failure.
- Legacy V1, V0, modern V2 and LLDV-only EDID must not share the wrong VSIF.
- Native and converted HDR10+ must negotiate receiver version and actual wire depth.
- Framebuffer-only, metadata-only and rejected atomic commits must not advance the wrong packet.
- Default R615, opt-in R580, existing DCN and ordinary playback remain isolated.

### Task 1: Restore existing hardware work

**Files:** `packages/linux/package.mk`, `packages/graphics/nvidia/package.mk`, new Pascal package/patch, `projects/Generic/patches/linux/linux-9925-vegam-dv-transport.patch`, hardware documentation and original PR tests.
**Interfaces:** Existing PR refs and source locks; retain default R615 and opt-in `CB1_NVIDIA_PASCAL=yes`.

- [ ] Import the PR firmware/family/package tests first and run on unchanged production sources: missing xe, DCE11.22 and Pascal selection must fail for the expected reasons.
- [ ] Port production changes from #40/#43/#57, preserve #44 documentation, recompute current receipts instead of copying old locks.
- [ ] Replay kernel/NVIDIA patches in private source fixtures and compile affected owners. Run focused tests, native/DCN/default-driver controls and full integration suite. Expected: no failures, skips explicit.
- [ ] Commit the bounded hardware integration and record evidence.

### Task 2: Close native and converted HDR10+ admission gaps

**Files:** Existing Linux HDR10/HDR10+ patches, Kodi `WinSystemGbmGLESContext.cpp` owner, CB1 HDR10+ metadata helpers, receiver/version tests.
**Interfaces:** Existing `HDR10PLUS_METADATA`, `DVBRIDGE_HDR10_DEEP_COLOR`, `SupportsHDR10Conversion()`, `RefreshDVOutputCapabilities()`.

- [ ] Add failing controls for receiverV0, admissible native deep output and rejection of sub-10-bit/unsupported hardware.
- [ ] Reuse real precision validation rather than CPU-generation shortcuts. Implement supported version semantics with unchanged movie pixels. If a driver cannot prove the contract, retain rejection and ledger the physical limitation.
- [ ] Test metadata version/quantization, ordinary output, transitions and full integration; compile changed owners. Expected: valid contracts pass, unsupported routes remain explicit.
- [ ] Commit and record the resulting compatibility matrix.

### Task 3: NVIDIA HDR10+ selected-frame transport

**Files:** Current R615 and opt-in R580 source patches, existing Kodi atomic staging only if required, packet/lifetime tests.
**Interfaces:** Generic `HDR10PLUS_METADATA` blob, native NVKMS VSIF payload/primary transaction and actual deep-colour state.

- [ ] Exercise production source with valid/invalid packets, missing primary frame, metadata-only update, conflicts, 8/10-bit and clear/retry. Confirm current missing support fails.
- [ ] Add the minimum native DRM/NVKMS connection, preserving the DV property. Resolve shared HDR/VSIF slot and update timing from actual HAL contracts; never acknowledge an unsent or unsynchronized packet.
- [ ] Compile matching modules, run packet/atomic/restore controls and full suite. Document any physically unsupported stack instead of emulating it unsafely.
- [ ] Commit and submit the complete hardware range to Astra for implementation review; fix demonstrated important findings with RED/GREEN controls.

### Task 4: AMD DV V1 and precise rejection diagnostics

**Files:** Existing `linux-9920-amd-dcn-native-dv.patch`, shared packet/EDID helpers where reusable, targeted driver-policy tests.
**Interfaces:** `amdgpu_dm_dv_configure_stream()`, scanout validation, `dvbridge_parse_edid()` and native AVI/VSIF builders.

- [ ] Add actual-source V1 short/long, legacyV0, V2, LLDV-only and malformed-EDID controls. Assert frozen V2 packet bytes/checksum and ordinary/DCN state.
- [ ] Replace both V2-only exclusions with coherent packet-family admission, not an unconditional bypass. Preserve RGB8, neutral LUT/CSC, EDID, topology and timing checks.
- [ ] Preserve/report the original rejection before generic stream-creation failure. Test unsupported cases and no repeated log flooding.
- [ ] Replay and compile kernel owners; run full integration and exact V2 controls. Expected: correct legacy packets, V2 identical, invalid routes refused.
- [ ] Commit and ask Astra for the final V1/V2 and whole-range validation.

### Task 5: Final candidate verification and handoff

- [ ] Verify source locks, stage check, patch replay, dependency source/licence consistency and clean diff.
- [ ] Run the complete matched integration suite; record physical test availability and every unverified route.
- [ ] Review the whole candidate with Astra xhigh, resolve critical/important findings with regression tests.
- [ ] Preserve frozen RC1 and leave tested local commits only; no release or device installation without a separate request.

# HDR Transport Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Close proven HDR output gaps across the supported driver stacks and audit every native/converted output combination.

**Architecture:** Reuse native driver selectors, packet writers and Kodi's frame-owned atomic transaction. No rendering algorithm changes or per-GPU player backend.

**Tech Stack:** Linux 7.2.6 DRM, i915/xe, amdgpu DC, matched NVIDIA R615/R580, Kodi 22 RC1, C/C++ host tests.

**Spec:** `docs/superpowers/specs/2026-10-28-hdr-transport-completion.md`.

## Global Constraints

- Base f8a03017a9. Frozen RC1, mini-PCs and public repositories unchanged.
- No new Hades code or GPLv3 dependency; independent implementation from candidate and native interfaces.
- Movie pixels and Dolby metadata unchanged. DV V2 packet bytes unchanged.
- HDR10+ retains actual >=10-bit PQ output, frame ownership and explicit failure handling.
- Unsupported hardware is refused with a reason, not advertised as working.

## Review Focus

- Depth changes must restore after rejected setup, stop and DV/HDR transitions.
- Metadata-only, TEST_ONLY and overlapping pending presentations must not advance a packet independently of its frame.
- Packet slot/VRR conflicts and packet-writer failure must preserve existing output state.
- Native HDR10+ and DV-converted HDR10+ use the same output admission and accepted-state report.
- Independent source provenance, matched NVIDIA stacks and absent physical qualification must stay explicit.

### Task 1: Intel depth and native HDR audit

**Files:** existing Intel HDR conversion patch, Kodi output owner, `tests/cb1/test_hdr10_transport.py`, depth transaction controls.

- [x] Extend actual-source tests with Display10 RGB/420 12-bpc, insufficient EDID/depth/bandwidth and Display9 rejection; observe RED.
- [x] Admit the demonstrated Display10 route and request its native maximum transactionally, without changing existing framebuffer precision or ordinary Kodi HDR.
- [x] Run selector/restore tests, replay patches and compile owners; record the remaining Display9 limit.

### Task 2: NVIDIA native HDR and dynamic transport

**Files:** independent R615/R580 transport patches and matching host controls, existing Kodi atomic/capability owners.

- [x] Add RED controls for real depth reporting, valid/invalid shared packets, frame ownership, TEST_ONLY, conflicts, pending flips and native writer failure.
- [x] Implement current-depth reporting from the original NVKMS attribute and independently connect the supported packet routes to the existing 31-byte property contract.
- [x] Reject unproved routes or precision rather than borrowing DV RGB8 or silently accepting stale metadata. Retain native slot/VRR/bandwidth constraints.
- [x] Compile matching source cores/modules, test fallback/clear/recovery and run the complete suite.

### Task 3: Whole matrix, receipts and Astra review

**Files:** `docs/cb1/DRIVER-COVERAGE.md`, source receipts and focused matrix tests.

- [x] Enumerate driver/display/link/version/depth and source/output combinations; qualify native HDR10/HLG separately from conversion.
- [x] Run V1/V2 goldens, native and generated HDR10+ receiver-version tests, all circuit/admission regressions and source-lock checks.
- [x] Ask a fresh Astra xhigh reviewer to inspect the complete range, provenance and every unsupported matrix cell.
- [x] Resolve demonstrated blocking findings with RED/GREEN tests, rerun verification and retain the local candidate. No publication or device changes.

## Final verification

Source lock: `0a0d230a3ad6b871de4d904acfe339a7fa1b403b10416b60614774062e67901c`.
Matched integration suite: 254 passed, no skips; independent Astra controls: 56 passed.
Windows normal-product inventory: 1 passed. Engine: 224 passed, 15 GPU-required skips.
Six kernel and four Kodi owners compile; both matched NVIDIA native cores/modules compile.
Astra accepts the explicitly limited experimental source candidate with no open Critical/Important finding on admitted routes. Native NVIDIA HDMI-VIC/VSI conflicts remain excluded, not claimed cleanly rejected for ordinary HDR. No full image/physical HDMI validation, device modification or publication was performed.

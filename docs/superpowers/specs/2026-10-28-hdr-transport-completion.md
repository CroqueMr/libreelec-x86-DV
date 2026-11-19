# HDR transport coverage completion

Base: `f8a03017a9`, branch `candidate/rc1-hardware-coverage`.
The delivered RC1, mini-PCs and public repositories remain unchanged.

## Intent

Audit native HDR10/HLG, native HDR10+, Dolby Vision V1/V2 and every CB1
output circuit across the admitted Intel, AMD and NVIDIA driver stacks.
Close demonstrated software gaps without claiming that unavailable hardware
or unsupported links have passed physical qualification.

## Approach

Extend the existing native output owners and shared metadata transaction.
Keep reconstruction, shaders, movie pixels and Dolby metadata unchanged.
Do not create separate player backends per GPU or change vanilla resolution
selection. Capability admission follows the selected connector and driver,
not the CPU name or EDID alone.

Hades is a feasibility reference only. No new Hades code, patch, helper,
comment, test or public ABI is imported. New work is written against the
existing candidate and original Linux/NVIDIA interfaces, with explicit
provenance and GPLv2-compatible source boundaries. The pre-existing max-bpc
patch remains baseline provenance, not a new import.

The alternatives rejected are optimistic property exposure without packet
delivery, a userspace packet loop, and importing the Hades implementation.

## Gaps and owners

| Gap | Owner and proposed correction |
| --- | --- |
| Display10 converted HDR refuses its native 12-bit route | Intel HDMI native depth/format selector plus Kodi transactional maximum-depth request; preserve EDID and bandwidth checks |
| NVIDIA link depth is unknown to Kodi | Existing NVKMS current-depth attribute, exposed read-only after accepted configuration; buffer precision is not link precision |
| R615 HDR10+ absent | Independent shared 31-byte metadata binding, native packet slots, selected-frame transaction and explicit failure propagation |
| R580 HDR10+ absent | Investigate original R580 packet, precision and flip interfaces; do not infer support from its static DV VSIF modeset path |
| Display9 native HDMI static HDR absent | Investigate native packet capabilities; do not relabel Dolby RGB8 transport as HDR10 support |
| Circuit menu and supported-format reporting differ | Use existing selected-connector capability source for native and converted HDR10+, preserving valid HDR10 fallback |

## Invariants

- DV V1 legacy/modern packets follow parsed EDID. Existing V2 packet goldens
  remain identical on Intel, AMD and both NVIDIA stacks.
- HDR10+ keeps static PQ/BT.2020 signaling and actual output at least 10 bits.
- Complete packet validation, receiver application version, enabled primary
  framebuffer, conflicting DV/3D state and asynchronous-flip exclusion are
  checked before accepting dynamic metadata.
- TEST_ONLY and rejected requests cannot program packets or mutate accepted
  state. Packet slots are not marked owned on failed writes or disables.
- NVIDIA packet writes coupled to a flip are not represented as a proven
  hardware-FID latch. Native outstanding-frame ordering and failure behavior
  must be established before enabling a route.
- Stop, failed start, hotplug and HDR10+/HDR10/DV/SDR transitions clear stale
  state and retain the ordinary Kodi path.
- No new GPLv3 code, dependency, copied Hades source or opaque vendor-binary
  modification. R580 and R615 remain separately matched images.

## Validation

Execute native-source selectors, packet builders and transaction owners with
failure injection. Replay shipped patches on pinned sources, compile changed
owners and run the full integration suite. Final Astra review covers every
matrix cell and circuit, not only the new patches. Unsupported and physically
unqualified cells remain explicit, with the reason and next evidence needed.

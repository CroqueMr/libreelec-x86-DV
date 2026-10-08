# Creative mapping integration

Dependencies remain exactly those pinned in `config/dependencies.json`.
No kernel, driver, display query, player UI, audio or scheduling patch is included.

## Caller contract

- Rebuild adapters: `DVBRIDGE_HDR10_POLICY_API` is 4 and `DVBRIDGE_DV_POLICY_API` is 5.
  The embedded creative snapshot now includes CM4 targets and field-presence
  masks. These layouts are not binary compatible with earlier adapters.
- `DVBRIDGE_ENHANCEMENT_SIGNATURE` is value 1. `INTENSE` is a deprecated numeric
  alias. Display Natural and Signature for DV Enhanced, without changing stored values.
- Authored-DV Enhanced prepare normally returns `READY` immediately after GPU submission.
  This is a prepared candidate, not GPU completion or scanout confirmation.
  Continue supporting `BUSY`, failure and asynchronous resource retirement.
- Preserve the existing prepare/resolve/present/commit transaction. Capture the
  resolve serial actually submitted; do not reread a later serial in callbacks.
- Keep caller-owned decoder imports and display targets alive through their real
  GPU/display use. Keep the retirement owner's GPU context current until destroy succeeds.
- Read `creative.status`, `backend`, `reason`, `applied_levels` and
  `preserved_levels` from the prepared or committed snapshot. The two masks may
  overlap when some fields of a level are used while others are preserved.
- Read `creative_edit.status`, `reason` and edited/preserved masks for the actual
  metadata edit. `creative.status` alone does not describe the committed edit.
  An unsupported edit preserves the whole source family, not a partial result.
- `cm4_targets` describes structural target resolution, not rendering readiness.
  `cm4_lower`/`cm4_upper` own value snapshots; `cm4_weight` is PQ distance only.
  Never report L8 controls as applied from these fields alone.
- Check `min_pq_present` before using a target black level. Preset and manual
  targets have no qualified black-level value; zero is not a measurement.
- Authored-DV Enhanced measured-statistics fields are zero, with `measured=false` and
  `output_generation=DVBRIDGE_SOURCE_METADATA`. Never display them as measurements.

## Processing scope

HDR10 Expert uses the independent `cb1-cm4-v1` scalar/spatial operator.
DV Enhanced uses `cb1-dve-v6`. Fixed linear-nits goals derive from the unedited
authored response. A bounded fit adjusts existing primary controls within
512 codes of their source, preserving secondary controls and target descriptions.
Black/near-black values, source detail, PQ error, chroma and hue remain guarded.
No extra controls or target metadata are synthesized.
The treatment reference is at least 1000 nits; the actual manual TV profile is
unchanged. A matching reference can make Natural neutral. The TV still performs
its TV-Led display mapping. This is not the licensed Dolby display mapper.

L8 primary and present optional fields are checked against preserved raw RPU
bytes. L10 PQ limits and present custom primaries are checked independently.
Unknown target/primary IDs remain unsupported, without a default 100-nit target.
Expert rejects unknown L9 mastering IDs and inconsistent custom raw/parsed
coordinates. Standard and Basic retain their existing admission. Expert consumes
L1/L3 maximum and average values; minimum is validated and preserved, not applied.
Same-peak different-gamut targets remain distinct; only gamut matches at the
metadata's signed 16-bit coordinate precision participate in the anchor snapshot.
Known incompatible EOTFs are excluded. L10 has no EOTF field; its transfer stays
unknown. Resolved custom targets support the absolute-linear control reference
without inventing a display transfer. Source mastering is not changed.

Authored-DV Enhanced uses reconstruction, an intermediate image, packing and
resource-retirement fences, without an image-analysis pass.

HDR10 AI Enhanced retains the existing asynchronous analysis path and its
stricter GPU requirements. Adapters must query
`dvbridge_renderer_supports_hdr10_ai` for AI output and
`dvbridge_renderer_supports_mode` for authored-DV output.

Automated checks cover metadata, numerical behavior and resource lifetimes.
Hardware performance and HDMI interoperability require device-specific checks.

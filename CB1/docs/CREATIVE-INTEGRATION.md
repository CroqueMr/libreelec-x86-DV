# Creative mapping integration

Dependencies remain exactly those pinned in `config/dependencies.json`.
No kernel, driver, display query, player UI, audio or scheduling patch is included.

## Caller contract

- Rebuild adapters: `DVBRIDGE_HDR10_POLICY_API` is 4 and `DVBRIDGE_DV_POLICY_API` is 7.
- DV READY may retain a source-sized intermediate. Resolve scales and packs it directly. RGB consumers call `dvbridge_render_dv_policy_rgb` to materialize and cache output-sized PQ without changing the metadata or presentation state.
  The embedded creative snapshot now includes CM4 targets and field-presence
  masks. These layouts are not binary compatible with earlier adapters.
- Adaptive exposes one policy, without a preset field or Natural/Signature selector.
- Authored-Dolby Vision Adaptive HDR Mapping RGB and packed prepare may return `PENDING` for dense
  content analysis. Poll to `READY` before resolve, without presenting an
  unready surface. Continue supporting `BUSY`, failure and resource retirement.
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
- Generation 3 records the historical dense LMS/PQ model and newly generated
  L1/L5. Identity retains generation 2 and zero measured-statistics fields.
  Read `pixel_algorithm`, `analysis_model` and `expansion_reason` from the
  matching committed snapshot. These are not physical display measurements.

## Processing scope

HDR10 Expert uses the independent `cb1-cm4-v1` scalar/spatial operator.
Dolby Vision Adaptive HDR Mapping uses `cb1-dve-pixel-v1`: trim-guided expansion after reconstruction,
protected shadows, common RGB gain and fresh output metadata. Added light is
bounded by the display reference; existing brighter samples are not reduced.
Original metadata stays immutable. See
[equations and domains](ALGORITHMS.md#authored-dolby-vision-adaptive-hdr-mapping).
The TV retains its final TV-Led mapping; a configured peak is not an achieved
panel measurement.

L8 primary and present optional fields are checked against preserved raw RPU
bytes. L10 PQ limits and present custom primaries are checked independently.
Unknown target/primary IDs remain unsupported, without a default 100-nit target.
Expert rejects unknown L9 mastering IDs and inconsistent custom raw/parsed
coordinates. Standard and Basic retain their existing admission. Expert consumes
L1/L3 maximum and average values; minimum is validated and preserved, not applied.
Same-peak different-gamut L8 targets remain distinct; only gamut matches at the
metadata's signed 16-bit coordinate precision participate in the anchor snapshot.
L2 has no authored gamut; Adaptive HDR Mapping retains its scalar guidance for every display
gamut, evaluated in the established BT.2020 domain.
Known incompatible EOTFs are excluded. L10 has no EOTF field; its transfer stays
unknown. Resolved custom targets support the absolute-linear control reference
without inventing a display transfer. Source mastering is not changed.

Authored-Dolby Vision Adaptive HDR Mapping retains canonical native reconstruction
for identity and uses direct packed preparation when eligible. Dense GPU
reductions validate output bounds; scene descriptors follow the mapped source
analysis rather than frame-extrema noise. GUI/subtitles are composed after
analysis, reusing the existing composition scratch.

HDR10 AI Adaptive HDR Mapping retains the existing asynchronous analysis path and its
stricter GPU requirements. Adapters must query
`dvbridge_renderer_supports_hdr10_ai` for AI output and
`dvbridge_renderer_supports_mode` for authored-DV output.

Automated checks cover metadata, numerical behavior and resource lifetimes.
Hardware performance and HDMI interoperability require device-specific checks.

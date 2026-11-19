# Adaptive HDR Mapping rev B: offline prototype

## Scope and freeze

- RC1 V1 source checkpoint: `checkpoint/rc1-v1-20261027`, commit `5a457f67f97d5aa3e61ea8f93802e175c0f48d1c`.
- RC1 V2 prototype branch: `candidate/rc1-v2-adaptive-revb`.
- Previously built RC1 image remains unchanged, based on `f5002ad86080082a4eb989729419dba389c682df`. The later SDR fixes in the V1 source checkpoint are not claimed to be in that image.
- New offline circuit title: `Dolby Vision Adaptive HDR Mapping rev B`.
- Dolby Vision input only. Existing Adaptive, Standard, Master, AI and HDR10 paths remain unchanged. No Kodi menu changes, device access, full image build or publication in this prototype.

## Approved approach

Use the existing Adaptive plan, GPU shader, reconstruction and output transaction. A separate opt-in CPU builder produces rev B plans; no production caller switches to it. Its qualification executable substitutes this builder at the existing authored-DV preparation boundary only.

The original effective L1 (with L3 folded once), HDR trim guidance, common RGB gain, protected low lights, soft component ceiling and temporal slew remain the basis. Rev B selectively attenuates added light below the upper part of the authored scene range. Scene high/mid describe a tonal balance, not highlight occupancy or object identity. No image histogram drives the current frame, no local masks, and no new GPU pass.

Exclude six-vector SDR secondary hue/saturation controls from rev B HDR guidance, retaining the input and output metadata bytes. Retain HDR primary guidance. Do not recalibrate L2/L8 or add a second trim application.

L1 output keeps the current neutral-axis projection and is explicitly an approximation, not Dolby analysis. Offline qualification compares this projection against measured output distributions, including the distinct linear and PQ statistics paths. No experimental L1 correction is activated.

## Alternatives

- Analytical L1 correction alone: inexpensive but cannot solve color-dependent distribution errors.
- Full analysis/histogram or automatic trim refit: extra cost, timing and unknown TV mapper; excluded.
- Selected: metadata-guided CPU curve refinement plus existing GPU processing, with offline measurement of remaining errors.

## Acceptance and limitations

- Rev B changes are opt-in and have the title above; old circuit pixels/metadata stay exact against V1.
- Source metadata immutable; output L3 folded once; original L2/L8 preserved; output metadata and curve use the same frame/revision.
- No added light for luminance <=10 nits, no darkening, finite bounded output, monotone neutral ramp and common RGB gain.
- Separate baseline/rev B temporal histories; test fluctuations, cuts/reset, fades, seek, pause and transitions.
- Metadata-guidance sensitivity tested with/without trims; SDR secondary changes cannot affect rev B pixels.
- Quantify native-to-Adaptive and old-Adaptive-to-rev-B differences separately. Synthetic stress fixtures do not establish subjective improvement on films.
- GPU timing must name the actual local backend. WSL software timings are not hardware GPU timings. Local GPU timings are not N100/3200U or HDMI cadence results.
- Additional p95 GPU cost <=0.5 ms is an experimental target, not an established bound. No mini-PC testing is allowed.
- Astra final read-only challenge before handoff; disclose unqualified items.

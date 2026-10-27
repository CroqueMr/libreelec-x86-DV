# RC1 V2: signed Adaptive rev B on N100

Private complete image: `DV-R1.0.0-RC1-V2`, source `dd997af3299a3091508a687f0ca8523fc5f76238`.
No publication. Frozen RC1 V1 archive retained with SHA-256
`73d8b825b87e5c69550ad834e946e7f3bf49cbadeac2693bf381014462429056`.

## Integration

- Qualified signed builder promoted from tests to CB1, without changing its
  numerical operations. One implementation, no duplicated runtime prototype.
- `Dolby Vision Adaptive HDR Mapping rev B` is output preference6, accepted
  telemetry8, circuit `CB1-DVDVAB.0.1`. Current Adaptive remains available.
- Native Kodi settings, O menu, admission, Player information and existing
  telemetry expose the variant. No skin code added.
- Rev B only accepts authored-DV Adaptive FP16 policy. AI clears/rejects the
  flag; temporal interpolation does not mix the two Adaptive histories.
- Fallback policies clear the flag. Capability probes normalize fields not
  applicable to their probed mode. Other pixel shaders/filters are unchanged.
- Eleven affected Kodi files replay exactly through their existing owning
  patches. Matched engine/package staging and source receipts pass.

Independent Astra xhigh review found two important guard defects: invalid
flagged FP32 policy accepted through the neutral-base builder; flag retained
after fallback to HDR10/Standard. Both were reproduced by failing checks and
corrected with passing checks. No remaining review minor. Review did not
approve hardware performance, rollback execution or subjective quality.

## Verification

- Final engine suite: 242 registered, 227 passed, 15 unsupported skips, zero
  failures, 121.85 s. Native integration: 212/212 passed, 226.50 s.
- Complete image build exit0. TAR and disk payloads, embedded kernel early
  userspace, delivered library ABI, stripped linked binaries, AI model/license,
  source dependencies and normal-build boundaries pass the reused image gate.
- Delivered Kodi binary contains the signed algorithm and circuit identity;
  delivered settings contain rev B and preserve default output0.
- N100 positively identified before changes. Native LibreELEC updater used;
  reboot identity changed, V2 release and all delivered component hashes match.
- Configuration snapshot retained privately; rollback RC1 tar staged outside
  `.update`. Update directory empty afterward. No SSD formatting or media edits.
- Avatar 4K: rev B then current Adaptive each stayed on the expected accepted
  mode for a 10-second observation and stopped successfully. Kodi stayed active.
  Original output preference4 (Master Reference) restored, HDMI still connected.
  No TV power or source-control operation was performed.

The native drop-counter label was empty in these probes. No zero-drop, FPS,
headroom, whole-film pumping or subjective-quality claim is made. No AMD test.
Rollback archive and settings are retained, but rollback was not executed.
The previously measured analytic GPU overhead and approximate L1 projection
remain limitations of this experimental circuit, not deployment failures.

User comparison: O opens Player information, O again opens the playback menu;
choose `Dolby Vision Adaptive HDR Mapping rev B` or the existing Adaptive.
Current TV calibration was preserved. No automatic selection of rev B.

Raw evidence is local: WSL `DVBuild`, `/home/dvbuild/adaptive-revb-runtime-20261027`,
and the matching project `work/adaptive-revb-runtime-20261027` folder. Recovery
settings are private and intentionally excluded from repository documentation.
[Image and N100 receipt](adaptive-revb-runtime-20261027.json).

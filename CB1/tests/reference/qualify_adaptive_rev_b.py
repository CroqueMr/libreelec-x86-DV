# SPDX-License-Identifier: GPL-2.0-or-later
"""Summarize offline observations; never infer TV luminance or mini-PC cadence."""
import argparse
import json
import math
from pathlib import Path
from statistics import median


def rows(root, name):
    return [json.loads(line) for line in (root / name).read_text().splitlines()
            if line.startswith('{')]


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize(root):
    timing = []
    for path in sorted(root.glob('timing-idle-*.jsonl')):
        timing.extend(dict(row, run=path.stem) for row in rows(root, path.name))
    identity = next(row for row in timing if row['kind'] == 'identity')
    assert identity['title'].endswith('rev B')
    assert 'llvmpipe' not in identity['renderer'].lower(), 'Not a hardware GPU benchmark'
    result = {'renderer': identity['renderer'],
              'timing_scope': 'expansion, statistics, fused carrier prepack and auxiliary PQ write; no final resolve',
              'mini_pc_or_hdmi_tested': False, 'timings': [], 'pixels': [], 'clips': {}, 'curves': []}
    for analytic in (0, 1):
        samples = [r for r in timing if r['kind'] == 'timing' and r['analytic'] == analytic]
        assert len(samples) >= 48 and len(samples) % 48 == 0
        assert all(r['gpu_timer'] and not r['disjoint'] for r in samples)
        assert all(r.get('prepack') is True and r.get('auxiliary_write') is True
                   and r.get('input_bits') == 32 for r in samples), 'Effective timed configuration must be recorded'
        sets = [[r['gpu_ms'] for r in samples if r['mode'] == m] for m in (0, 1)]
        pairs = {(r['run'], r['trial']): {} for r in samples}
        for row in samples:
            pairs[row['run'], row['trial']][row['mode']] = row['gpu_ms']
        delta = [pair[1] - pair[0] for pair in pairs.values()]
        result['timings'].append({'analytic': analytic, 'samples_per_mode': len(sets[0]),
                                  'median_ms': [median(s) for s in sets],
                                  'p95_ms': [percentile(s, .95) for s in sets],
                                  'paired_delta_median_ms': median(delta),
                                  'paired_delta_p95_ms': percentile(delta, .95)})
    pixels = rows(root, 'pixels-local-gpu.jsonl')
    for row in pixels:
        if row['kind'] != 'pixels':
            continue
        assert row['max_error_code12'] <= 1 and row['black_error_nits'] <= .002
        # This comparison uses a deliberately matched arithmetic proxy, not Dolby analysis.
        row['projected_avg_minus_measured_proxy_code12'] = row['projected_L1'][2] - row['measured_pq'][2] * 4095
        result['pixels'].append(row)
    assert len(result['pixels']) == 4
    for name in ('avatar', 'dragon'):
        clip = rows(root, name + '.jsonl')
        metadata = [r for r in clip if r['kind'] == 'pipeline']
        pictures = [r for r in clip if r['kind'] == 'clip_pixels_sampled']
        assert len(metadata) == len(pictures) == 12
        assert all(r['same_picture'] and r['source_immutable'] and r['trims_preserved'] for r in metadata)
        result['clips'][name] = {'frames_per_mode': 6,
            'sampled_components_per_mode': sum(r['sampled_components'] for r in pictures if r['mode'] == 1),
            'protected_roundtrip_max_nits': max(r['protected_roundtrip_nits'] for r in pictures),
            'rev_b_vs_baseline_max_difference_code12': max(r['max_difference_code12'] for r in pictures),
            'rev_b_vs_baseline_mean_difference_code12':
                sum(r['mean_difference_code12'] for r in pictures if r['mode'] == 1) / 6,
            'metadata': metadata}
    scalar = rows(root, 'scalar.jsonl')
    result['curves'] = [r for r in scalar if r['kind'] == 'curve']
    result['temporal'] = [r for r in scalar if r['kind'] == 'temporal']
    result['cpu_plan_median_us'] = [median(r['mean_us'] for r in scalar
        if r['kind'] == 'cpu_plan' and r['mode'] == m) for m in (0, 1)]
    assert len(result['temporal']) == 2 and all(r['frames'] == 240 for r in result['temporal'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.evidence), indent=2))

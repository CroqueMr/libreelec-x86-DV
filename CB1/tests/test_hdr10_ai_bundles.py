# SPDX-License-Identifier: MIT
"""Run native rejection tests against copies of the bundled model."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(binary, bundle):
    def reject(path):
        subprocess.run([str(binary), str(path), 'reject'], check=True)
    cases = 0
    with tempfile.TemporaryDirectory(prefix='cb1-bundle-test-') as directory:
        root = Path(directory)
        for name in ('field-0.txt', 'field-5.txt', 'normalization.f32', 'cb1_l1l3_schema.h', 'manifest.json'):
            path = root/('corrupt-'+name)
            shutil.copytree(bundle, path)
            data = bytearray((path/name).read_bytes())
            data[len(data)//2] ^= 1
            (path/name).write_bytes(data)
            reject(path)
            cases += 1
            path = root/('missing-'+name)
            shutil.copytree(bundle, path)
            (path/name).unlink()
            reject(path)
            cases += 1
        for field, value in (('feature_count', 221), ('backend_version', '4.6.0'),
                             ('feature_names', ['incorrect-order'])):
            path = root/field
            shutil.copytree(bundle, path)
            manifest = json.loads((path/'manifest.json').read_text())
            manifest[field] = value
            (path/'manifest.json').write_text(json.dumps(manifest))
            reject(path)
            cases += 1
        path = root/'symlinked-weight'
        shutil.copytree(bundle, path)
        (path/'field-0.txt').unlink()
        (path/'field-0.txt').symlink_to(bundle/'field-0.txt')
        reject(path)
        cases += 1
    print(f'Native malformed-bundle rejection: {cases} cases')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--bundle', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'models/l1l3/data')
    args = parser.parse_args()
    run(args.binary.resolve(), args.bundle.resolve())

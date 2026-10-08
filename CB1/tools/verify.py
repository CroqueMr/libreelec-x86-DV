# SPDX-License-Identifier: MIT
"""Check exact extraction inputs, licenses and accidental private data."""
import hashlib
import argparse
import json
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def checked(root, name):
    if (not isinstance(name, str) or not name or '\\' in name
            or any(char in name for char in '<>:"|?*')
            or any(ord(char) < 32 for char in name)
            or PureWindowsPath(name).drive
            or any(part in ('', '.', '..', '.git') or part.endswith((' ', '.'))
                   or re.fullmatch(r'(?i)(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])',
                                   part.split('.')[0].rstrip(' ')) for part in name.split('/'))):
        raise ValueError('Unsafe source name: ' + repr(name))
    path = root / name
    component = root
    for part in ('', *name.split('/')):
        component = component / part
        if component.is_symlink() or (hasattr(component, 'is_junction') and component.is_junction()):
            raise ValueError('Symlink or junction in source path: ' + name)
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)) or not path.is_file():
        raise ValueError('Unsafe or missing file: ' + name)
    return path

def source_files(root, for_export=False):
    """Validate export authority separately from an ordinary private-data scan."""
    if (root / '.git').exists():
        command = ['git', '-C', str(root), 'ls-files', '-z', '--cached']
        if not for_export:
            command += ['--others', '--exclude-standard']
        result = subprocess.run(
            command, capture_output=True, check=True)
        names = result.stdout.decode('utf-8').split('\0')[:-1]
    elif (root / 'SOURCE-INVENTORY.json').exists() or (root / 'SOURCE-INVENTORY.json').is_symlink():
        inventory = json.loads(checked(root, 'SOURCE-INVENTORY.json').read_text(encoding='utf-8'))
        if (not isinstance(inventory, dict) or type(inventory.get('version')) is not int
                or inventory['version'] != 1 or not isinstance(inventory.get('files'), list)):
            raise ValueError('Invalid version-1 source inventory')
        names = inventory['files']
    elif for_export:
        raise ValueError('No-Git export requires SOURCE-INVENTORY.json')
    else:
        ignored = {'.git', '.superpowers', '__pycache__', 'host-tests', 'build-output', '.venv', 'venv'}
        names = [p.relative_to(root).as_posix() for p in root.rglob('*')
                 if (p.is_file() or p.is_symlink())
                 and not ignored.intersection(p.relative_to(root).parts) and p.suffix != '.pyc']
    files = {}
    portable_names = set()
    for name in names:
        path = checked(root, name)
        if name.casefold() in portable_names:
            raise ValueError('Duplicate or case-colliding source name: ' + name)
        portable_names.add(name.casefold())
        files[name] = path
    return files

def verify(root, dependency_roots=None, prefix=None):
    files = source_files(root)
    origins = json.loads(checked(root, 'config/extraction-origins.json').read_text())
    dependencies = json.loads(checked(root, 'config/dependencies.json').read_text())
    if len(origins['files']) != 22:
        raise ValueError('Expected all 22 corrected common paths')
    # Historical extraction attribution is immutable; owned additions use current digests.
    owned = json.loads(checked(root, 'config/owned-sources.json').read_text())
    if set(owned) != {'src/CMakeLists.txt', 'src/dvbridge_policy.c', 'src/dvbridge_policy.h',
                      'src/dvbridge_placebo.c', 'src/dvbridge_placebo.h',
                      'src/dvbridge_render.c', 'src/dvbridge_render.h', 'src/dvbridge_gl_pack.c',
                      'src/dvbridge_core.c', 'src/dvbridge_core.h',
                      'src/dvbridge_metadata.h', 'src/dvbridge_pack_sources.h.in',
                      'src/dvbridge_creative.c', 'src/dvbridge_creative.h',
                      'src/cb1_circuit.c', 'src/cb1_circuit.h',
                      'src/cb1_l1l3_model.c', 'src/cb1_l1l3_model.h',
                      'src/cb1_hdr10_features.c', 'src/cb1_hdr10_features.h',
                      'src/cb1_hdr10_extrema.c', 'src/cb1_hdr10_extrema.h',
                      'src/cb1_hdr10_quantiles.c', 'src/cb1_hdr10_quantiles.h',
                      'src/cb1_hdr10_ingress.c', 'src/cb1_hdr10_ingress.h',
                      'src/cb1_hdr10_statistics.c', 'src/cb1_hdr10_statistics.h',
                      'src/cb1_hdr10_filter.c', 'src/cb1_hdr10_filter.h',
                      'src/cb1_hdr10_spatial.c', 'src/cb1_hdr10_spatial.h',
                      'src/cb1_hdr10_temporal.c', 'src/cb1_hdr10_temporal.h',
                      'src/cb1_hdr10_ai.c', 'src/cb1_hdr10_ai.h'}:
        raise ValueError('Unexpected owned source identity')
    expected = {name: record['sha256'] for name, record in origins['files'].items()}
    expected.update(owned)
    expected.update(dependencies['patches'])
    expected.update(json.loads(checked(root, 'config/license-origins.json').read_text())['files'])
    expected.update(json.loads(checked(root, 'config/hdr10-ai-dependencies.json').read_text())['model']['files'])
    for name, digest in expected.items():
        if sha(checked(root, name)) != digest:
            raise ValueError('Extraction checksum mismatch: ' + name)
    if dependency_roots:
        for name, digest in dependencies['modified_sources'].items():
            component, relative = name.split('/', 1)
            if sha(checked(dependency_roots[component], relative)) != digest:
                raise ValueError('Modified dependency source mismatch: ' + name)
    if prefix:
        if sha(checked(prefix, 'include/libavutil/dovi_meta.h')) != dependencies['modified_sources']['ffmpeg/libavutil/dovi_meta.h']:
            raise ValueError('Installed metadata header does not match producer source')
        if sha(checked(prefix, 'include/libplacebo/renderer.h')) != dependencies['modified_sources']['libplacebo/src/include/libplacebo/renderer.h']:
            raise ValueError('Installed rendering header does not match pinned policy ABI')
        if sha(checked(prefix, 'include/libplacebo/shaders/colorspace.h')) != dependencies['modified_sources']['libplacebo/src/include/libplacebo/shaders/colorspace.h']:
            raise ValueError('Installed color mapping header does not match pinned policy ABI')
        for name in ('shaders.h', 'dispatch.h', 'shaders/sampling.h'):
            if sha(checked(prefix, 'include/libplacebo/' + name)) != dependencies['modified_sources']['libplacebo/src/include/libplacebo/' + name]:
                raise ValueError('Installed shader/dispatch header does not match pinned policy ABI')
    actual_sources = {p.relative_to(root).as_posix() for p in (root / 'src').rglob('*') if p.is_file()}
    if actual_sources != origins['files'].keys() | owned.keys():
        raise ValueError('Unexpected or missing runtime source')
    patches = {p.relative_to(root).as_posix() for p in (root / 'patches').rglob('*.patch')}
    if patches != dependencies['patches'].keys() or len(patches) != 18:
        raise ValueError('Unexpected or missing dependency patch')
    receipt = json.loads(checked(root, 'src/PROVENANCE.json').read_text())
    for name, digest in receipt['files'].items():
        path='src/' + name
        origin=origins['files'].get(path)
        if not origin or origin['sha256'] != digest:
            raise ValueError('Inherited helper provenance/origin mismatch: ' + name)
        if sha(checked(root, path)) != owned.get(path,digest):
            raise ValueError('Inherited helper provenance mismatch')
    patterns = [r'(?i)-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',
                r'(?i)\b(?:ghp|github_pat)_[a-z0-9_]{20,}',
                r'(?i)(?:api[_-]?key|password|token)\s*[=:]\s*["\'][a-z0-9_-]{16,}',
                r'(?i)(?:/home/|[a-z]:[\\/]+Users[\\/]+)[a-z0-9_.-]+[\\/]',
                r'\b192\.168\.\d{1,3}\.\d{1,3}\b']
    for name, path in files.items():
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # An illustration or other binary is not a malformed source tree.
            # This text scanner is not a binary-release or malware audit.
            continue
        for pattern in patterns:
            if re.search(pattern, text):
                raise ValueError('Private-data pattern found in ' + name)
        if path.suffix == '.patch' and re.search(r'^\+.*(?:DVBRIDGE_CM4_TRACE|glReadPixels|/storage/videos/)', text, re.M):
            raise ValueError('Development capture hook in runtime patch: ' + name)

    return {'source_files': len(files), 'common_paths': len(actual_sources),
            'historical_extraction_paths': 22, 'dependency_patches': len(patches),
            'checks': 'passed', 'hardware_test': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg-source', type=Path)
    parser.add_argument('--libplacebo-source', type=Path)
    parser.add_argument('--prefix', type=Path)
    args = parser.parse_args()
    if bool(args.ffmpeg_source) != bool(args.libplacebo_source):
        parser.error('Provide both modified dependency source roots')
    dependency_roots = ({'ffmpeg': args.ffmpeg_source, 'libplacebo': args.libplacebo_source}
                        if args.ffmpeg_source else None)
    try:
        print(json.dumps(verify(ROOT, dependency_roots, args.prefix), indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'Source check failed: {error}', file=sys.stderr)
        sys.exit(1)

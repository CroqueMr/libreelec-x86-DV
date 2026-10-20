#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Embed one path/profile-independent source identity in both Debug SYSTEMs.

Linux arguments come from the native build's selected package recipe. Source
identities hash canonical repo-relative file/digest maps, including recipes,
patches, CB1 core and matched models, never host paths or profile selection.
Final packaging additionally requires the paired manifest's embedded build
identity to match these current sources; it does not regenerate a SYSTEM.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_identity(root, paths):
    files = {}
    for name in paths:
        path = root / name
        for item in sorted(path.rglob('*')) if path.is_dir() else (path,):
            if item.is_file() and '__pycache__' not in item.parts and item.suffix != '.pyc':
                files[item.relative_to(root).as_posix()] = digest(item)
    if not files:
        raise ValueError('Missing component source inputs')
    return canonical_hash(files)


def build_info(root, build_id, linux_version, linux_source):
    if not re.fullmatch(r'[A-Za-z0-9._-]+-debug', build_id) or linux_version != '7.2.6':
        raise ValueError('Expected Debug build identity and pinned Linux 7.2.6')
    policy = json.loads((root / 'config/cb1-driver-profiles.json').read_text())
    if policy['schema'] != 1 or linux_source != policy['linux_source_sha256']:
        raise ValueError('Selected Linux source disagrees with pinned driver policy')
    ordinary = policy['ordinary_patches']
    if not ordinary:
        raise ValueError('Missing ordinary patch policy')
    for name, expected in ordinary.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Invalid ordinary patch identity')
        if digest(root / path) != expected:
            raise ValueError('Ordinary patch content disagrees with pinned policy: ' + name)
    userspace = {}
    for component, directory in (('kodi', 'mediacenter'), ('mesa', 'graphics')):
        package = f'packages/{directory}/{component}'
        recipe = (root / package / 'package.mk').read_text()
        if not re.search(r'^PKG_SHA256="[0-9a-f]{64}"$', recipe, re.M):
            raise ValueError('Component requires its pinned source recipe: ' + component)
        paths = [package, f'projects/Generic/patches/{component}', f'projects/Generic/packages/{component}']
        if component == 'kodi':
            paths.append('projects/Generic/filesystem/usr/share/kodi')
        userspace[component] = source_identity(root, paths)
    for required in ('CB1/CMakeLists.txt', 'CB1/src', 'CB1/models', 'CB1/config'):
        if not (root / required).exists():
            raise ValueError('Missing CB1 source or matched model input: ' + required)
    userspace['cb1'] = source_identity(root, ('CB1/CMakeLists.txt', 'CB1/src', 'CB1/models', 'CB1/config',
        'projects/Generic/filesystem/usr/bin/cb1-driver-profile',
        'projects/Generic/filesystem/usr/bin/dv-diagnostics',
        'projects/Generic/filesystem/usr/lib/systemd/system/cb1-driver-profile.service'))
    return {'id': build_id, 'linux_version': linux_version, 'linux_source_sha256': linux_source,
            'ordinary_patches_sha256': canonical_hash(ordinary), 'userspace': userspace}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--install', type=Path, required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--linux-version', required=True)
    parser.add_argument('--linux-source-sha256', required=True)
    parser.add_argument('--profiles-dir', default='')
    args = parser.parse_args()
    try:
        build = build_info(args.root, args.build_id, args.linux_version, args.linux_source_sha256)
        if args.profiles_dir:
            paired = json.loads((Path(args.profiles_dir) / 'cb1/driver-profiles.json').read_text())
            if paired['build'] != build:
                raise ValueError('Prepared Debug pair does not match current source identity')
        target = args.install / 'usr/share/cb1/driver-profile-build.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(build, sort_keys=True, indent=2) + '\n')
        marker = args.install / 'etc/cb1-debug'
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Debug build identity refused: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

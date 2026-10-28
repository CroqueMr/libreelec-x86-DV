#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate a stable, explicit boot table from the two pinned vendor inputs."""
import json
from pathlib import Path
import re
import sys


def classifications(document):
    result = {}
    for chip in document['chips']:
        device = chip['devid'].lower().removeprefix('0x')
        if not re.fullmatch('[0-9a-f]{4}', device):
            raise ValueError('Invalid NVIDIA PCI ID')
        branch = chip.get('legacybranch')
        if device in result and result[device] != branch:
            raise ValueError('Conflicting subsystem classifications for '+device)
        result[device] = branch
    return result


def table(current, legacy):
    current, legacy = classifications(current), classifications(legacy)
    result = {}
    for device, branch in current.items():
        if branch is None:
            result[device] = 'r615'
        elif branch == '580.xx':
            if device not in legacy or legacy[device] is not None:
                raise ValueError('R580 input does not support '+device)
            result[device] = 'r580'
    return ''.join(f'{device} {branch}\n' for device, branch in sorted(result.items()))


if __name__ == '__main__':
    current, legacy, output = map(Path, sys.argv[1:])
    output.write_text(table(json.loads(current.read_text()), json.loads(legacy.read_text())), encoding='ascii')

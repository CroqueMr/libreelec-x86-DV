"""Kodi source files created by the integration patches, as the whole stack leaves them.

A file created by one patch and changed by a later one is rebuilt by applying its
sections in patch order, so tests compile the code that ships.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / 'projects/Generic/patches/kodi'


def write_patched_files(relatives, directory):
    """Write each Kodi file of relatives into directory; return False if one is not shipped."""
    directory = Path(directory)
    for relative in relatives:
        sections = []
        for patch in sorted(PATCHES.glob('*.patch')):
            for part in re.split(r'(?=^diff --git )', patch.read_text(), flags=re.M):
                if re.search(r'^\+\+\+ b/' + re.escape(relative) + r'$', part, re.M):
                    sections.append(part)
        if not sections or '--- /dev/null' not in sections[0]:
            return False
        for section in sections:
            subprocess.run(['patch', '-p1', '-s', '-d', str(directory)], input=section,
                           text=True, check=True, capture_output=True)
    return True

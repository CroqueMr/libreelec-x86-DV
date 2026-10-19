"""Read tested implementations independently of their integration-patch location."""
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]

def shipped_code(relative):
    tree=os.environ.get('KODI_NATIVE_SOURCE_TREE')
    if tree and (Path(tree)/relative).is_file():
        return (Path(tree)/relative).read_text()
    sections=[]
    for patch in sorted((ROOT/'projects/Generic/patches/kodi').glob('*.patch')):
        text=patch.read_text()
        for part in re.split(r'(?=^--- (?:a/|/dev/null))',text,flags=re.M):
            if re.search(r'^\+\+\+ b/'+re.escape(relative)+r'$',part,re.M):
                sections.extend(line[1:] for line in part.splitlines()
                                if line.startswith('+') and not line.startswith('+++'))
    return '\n'.join(sections)

"""Replay complete vendor patch stacks from the pinned original archives."""
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('CB1_NVIDIA_ARCHIVES'), 'requires pinned NVIDIA source archives')
class NvidiaPatchReplay(unittest.TestCase):
    def test_both_native_stacks_replay_exactly(self):
        for package,version,source_env in (
            ('nvidia-open-kernel-modules','615.78.08','CB1_NVIDIA_SOURCE'),
            ('nvidia-pascal-modeset','580.178.04','CB1_PASCAL_SOURCE'),
        ):
            folder=ROOT/'packages/graphics'/package
            patches=sorted((folder/'patches').glob('*.patch'))
            archive=Path(os.environ['CB1_NVIDIA_ARCHIVES'])/package/f'{package}-{version}.tar.gz'
            expected=re.search(r'PKG_SHA256="([0-9a-f]+)"',(folder/'package.mk').read_text())[1]
            with self.subTest(stack=package),archive.open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),expected)
            existing=set()
            for patch in patches:
                existing.update(re.findall(r'^--- a/(.+)$',patch.read_text(),re.M))
            with tempfile.TemporaryDirectory() as tmp,tarfile.open(archive) as tar:
                tree=Path(tmp)
                for member in tar:
                    path=PurePosixPath(member.name)
                    relative=str(PurePosixPath(*path.parts[1:]))
                    if relative not in existing:
                        continue
                    self.assertTrue(member.isfile() and '..' not in path.parts)
                    target=tree/relative
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
                for patch in patches:
                    applied=subprocess.run(['patch','-p1','--batch','--fuzz=0','-i',str(patch)],
                        cwd=tree,capture_output=True,text=True)
                    self.assertEqual(applied.returncode,0,str(patch)+'\n'+applied.stdout+applied.stderr)
                # Compare the integration owners, not an independent implementation.
                native=Path(os.environ[source_env])
                index=json.loads((ROOT/'config/cb1-patch-index.json').read_text())
                targets=set()
                for patch in patches:
                    targets.update(index[str(patch.relative_to(ROOT))]['files'])
                for name in sorted(targets):
                    self.assertTrue((tree/name).is_file(),'missing shipped owner '+name)
                # The package separately copies the authoritative KAPI header
                # into kernel-open/common; compare direct owners before staging.
                for name in ('src/nvidia-modeset/src/nvkms-hdmi.c',
                             'src/nvidia-modeset/src/nvkms-evo1.c',
                             'kernel-open/nvidia-drm/nvidia-drm-connector.c',
                             'kernel-open/nvidia-drm/nvidia-drm-connector.h',
                             'kernel-open/nvidia-drm/nvidia-drm-encoder.c',
                             'kernel-open/nvidia-drm/nvidia-drm-encoder.h'):
                    self.assertEqual((tree/name).read_bytes(),(native/name).read_bytes(),name)


if __name__=='__main__': unittest.main()

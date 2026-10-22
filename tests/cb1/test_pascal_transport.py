"""Check the native R580 packet builder and transport bounds off hardware."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent/'nvidia_pascal'


@unittest.skipUnless(os.environ.get('CB1_PASCAL_SOURCE'), 'requires patched pinned R580 sources')
class PascalTransport(unittest.TestCase):
    def test_metadata_bounds(self):
        source = Path(os.environ['CB1_PASCAL_SOURCE'])
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp)/'bounds'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                '-I'+str(source/'src/common/sdk/nvidia/inc'),
                '-I'+str(source/'src/common/inc'),str(HERE/'bounds.c'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)

    def test_exact_dv_packet_and_disable_with_native_pascal_packer(self):
        source = Path(os.environ['CB1_PASCAL_SOURCE'])
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['make','-s','-C',str(source/'src/nvidia-modeset'),
                '-f',str(HERE/'host.mk'),'cb1-host-test','HOST_CC=cc','TARGET_ARCH=x86_64',
                'TEST_SOURCE='+str(HERE/'hdmi.c'),'TEST_BINARY='+str(Path(tmp)/'hdmi')],check=True)


if __name__ == '__main__':
    unittest.main()

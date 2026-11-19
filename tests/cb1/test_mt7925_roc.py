"""Exercise Linux's MT7925 ROC callbacks with a simulated channel grant and timer."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get("CB1_KERNEL_SOURCE"), "requires the replayed kernel")
class Mt7925Roc(unittest.TestCase):
    def test_join_ownership(self):
        directory = Path(os.environ["CB1_KERNEL_SOURCE"]) / "drivers/net/wireless/mediatek/mt76/mt7925"
        driver = (directory / "main.c").read_text()
        channel = driver[driver.index("static void mt7925_roc_iter("):
                         driver.index("static int mt7925_set_link_key(")]
        callbacks = [function(driver, name) for name in
                     ("mt7925_mac_sta_event", "mt7925_mgd_prepare_tx", "mt7925_mgd_complete_tx")]
        mcu = (directory / "mcu.c").read_text()
        source = Path(__file__).with_name("mt7925_roc.c").read_text()
        source = source.replace("/* DRIVER */", "\n".join([channel, *callbacks]))
        source = source.replace("/* GRANT */", function(mcu, "mt7925_mcu_roc_handle_grant"))
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "roc"
            subprocess.run(["cc", "-std=gnu11", "-Werror", "-x", "c", "-", "-o", str(binary)],
                           input=source, text=True, check=True)
            for scenario in ("open", "wpa", "disassoc", "rejected", "tdls", "expired",
                             "busy", "failed", "mlo", "queued", "other-vif", "grant", "offchannel",
                             "reassoc", "removed", "busy-reject"):
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(binary), scenario], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)

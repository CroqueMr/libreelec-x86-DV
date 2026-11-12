"""Compile the shipped GBM owners against a deterministic connector/commit boundary."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


def method(source, name):
    match = re.search(r"^[^\n]*\b" + re.escape(name) + r"\([^;]*?\)\s*(?:const\s*)?\n\{", source, re.M)
    if not match:
        raise AssertionError(f"native owner method missing: {name}")
    end, depth = match.end(), 1
    # These owner bodies contain no braces in quoted messages that affect balance.
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def native_owner_program(root):
    source = (root / "xbmc/windowing/gbm/WinSystemGbm.cpp").read_text()
    header = (root / "xbmc/windowing/gbm/WinSystemGbm.h").read_text()
    names = ["ApplyMaxBpcSetting", "GetEffectiveMaxBpc", "ApplyColorFormatSetting",
             "IsColorFormatOffered", "GetColorFormat", "GetRequestedColorFormat",
             "IsHdmiFrlLink", "ContentNeedsSubsampling", "IsYuvRequested",
             "IsYuvFormatCommitted", "IsYuvFormat", "ApplyColorRangeSetting", "GetColorRange",
             "MigrateLimitedRangeSetting", "DeferConnectorPreferences", "ApplyConnectorProperties",
             "ApplyBroadcastRange", "ApplyMaxBpc", "ApplyColorFormat", "IsRequestRejected",
             "RequeueConnectorProperties", "RetryConnectorProperties", "UpdateDriverLimitedRange",
             "UseLimitedColor", "ApplyColorspace", "SetColorimetry"]
    bodies = "\n".join(method(source, "CWinSystemGbm::" + name) for name in names)
    # The two QueueConnectorProperty overloads are adjacent in the actual owner.
    start = source.index("bool CWinSystemGbm::QueueConnectorProperty(")
    end = source.index("void CWinSystemGbm::ApplyMaxBpc()", start)
    bodies += "\n" + source[start:end]
    constants = source[source.index("constexpr const char* BROADCAST_RGB"):source.index("// These map")]+source[source.index("constexpr auto ColorimetryMap"):source.index("} // namespace")].replace("constexpr auto ColorimetryMap", "const auto ColorimetryMap")
    enums = header[header.index("enum class ColorRange"):header.index("class CWinSystemGbm :")]
    members = header[header.index("  static void ApplyColorRangeSetting"):header.index("  // Claim no 3D")]
    depth = re.search(r"^  uint64_t GetEffectiveMaxBpc.*;", header, re.M)[0]
    members = depth + "\n" + members
    program = (Path(__file__).with_name("gbm_colour_owner.cpp").read_text()
               .replace("// NATIVE_CONSTANTS", constants + enums)
               .replace("// NATIVE_MEMBERS", members)
               .replace("// NATIVE_BODIES", bodies))
    return program

class GbmColourOwner(unittest.TestCase):
    def test_native_connector_policy(self):
        tree = os.environ.get("KODI_NATIVE_SOURCE_TREE")
        if not tree:
            self.skipTest("requires the fully prepared native Kodi tree")
        program = native_owner_program(Path(tree))
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "check"
            build = subprocess.run(["c++", "-std=c++20", "-x", "c++", "-", "-o", str(binary)],
                                   input=program, text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()

"""Driver acceptance must reflect live transport status, not a queued request."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class DriverReceipt(unittest.TestCase):
    def test_output_fault_forces_clear_without_claiming_hdr10plus(self):
        source = (TREE / 'xbmc/windowing/gbm/drm/DRMAtomic.cpp').read_text()
        signature = 'void CDRMAtomic::AcceptHDR10Plus('
        self.assertTrue(signature in source, 'No live driver receipt is checked')
        implementation = body(source, signature)
        program = r'''
#include <cassert>
#include <cstdint>
#include <optional>
#include <string_view>
constexpr int LOGWARNING=1;
struct CLog {template<class... T> static void Log(T...) {}}
;
struct Connector {
 bool driverStatus=true;
 std::optional<uint64_t> status=1,depth=10;
 bool SupportsProperty(const char*)const {return driverStatus;}
 std::optional<uint64_t> ReadPropertyValue(std::string_view name)const {
  return name=="CB1_OUTPUT_BPC"?depth:status;
 }
 std::optional<uint64_t> GetPropertyValue(const char*)const {return 73;}
};
struct CDRMAtomic {
 Connector con,*m_connector=&con;
 bool m_hdr10plusActive{},m_hdr10plusClearRequired{};
 uint64_t m_hdr10plusGeneration=11,m_hdr10plusRejectedGeneration{},m_hdr10plusRejectedEdid{};
 void AcceptHDR10Plus(bool enabled) BODY
};
int main() {
 CDRMAtomic d;
 d.AcceptHDR10Plus(true);assert(d.m_hdr10plusActive && !d.m_hdr10plusClearRequired);
 d.con.status=2;d.AcceptHDR10Plus(true);
 assert(!d.m_hdr10plusActive && d.m_hdr10plusClearRequired);
 assert(d.m_hdr10plusRejectedGeneration==11 && d.m_hdr10plusRejectedEdid==73);
 d.AcceptHDR10Plus(false);assert(d.m_hdr10plusClearRequired);
 d.con.status=0;d.AcceptHDR10Plus(false);
 assert(!d.m_hdr10plusActive && !d.m_hdr10plusClearRequired);
 for(auto depth:{0,8,9}) {
  d.con.status=1;d.con.depth=depth;d.AcceptHDR10Plus(true);
  assert(!d.m_hdr10plusActive && d.m_hdr10plusClearRequired);
 }
 for(auto depth:{10,12}) {
  d.con.depth=depth;d.AcceptHDR10Plus(true);
  assert(d.m_hdr10plusActive && !d.m_hdr10plusClearRequired);
 }
 d.con.status.reset();d.AcceptHDR10Plus(true);assert(!d.m_hdr10plusActive);
 d.con.driverStatus=false;d.AcceptHDR10Plus(true);
 assert(d.m_hdr10plusActive && !d.m_hdr10plusClearRequired);
}
'''.replace('BODY', implementation)
        with tempfile.TemporaryDirectory() as directory:
            code, binary = Path(directory)/'test.cpp', Path(directory)/'test'
            code.write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                    '-fsanitize=address,undefined', str(code), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()

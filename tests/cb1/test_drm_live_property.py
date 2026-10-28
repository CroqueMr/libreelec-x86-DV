"""Immutable driver receipts must be read from DRM, not its startup cache."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class LiveProperty(unittest.TestCase):
    def test_changed_driver_value_and_failed_query(self):
        source = (TREE / 'xbmc/windowing/gbm/drm/DRMObject.cpp').read_text()
        signature = 'std::optional<uint64_t> CDRMObject::ReadPropertyValue('
        self.assertTrue(signature in source, 'Live driver receipt query is missing')
        program = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <optional>
#include <string_view>
struct drmModeObjectProperties {uint32_t count_props=1;uint32_t props[1]={7};uint64_t prop_values[1]={8};};
static drmModeObjectProperties value;
static bool failure=false;
static unsigned reads=0,frees=0;
static drmModeObjectProperties* drmModeObjectGetProperties(int fd,uint32_t id,uint32_t type) {
 assert(fd==3 && id==9 && type==11);++reads;return failure?nullptr:&value;
}
static void drmModeFreeObjectProperties(drmModeObjectProperties*) {++frees;}
struct CDRMObject {
 struct DrmModeObjectPropertiesDeleter {void operator()(drmModeObjectProperties*p){drmModeFreeObjectProperties(p);}};
 int m_fd=3;uint32_t m_id=9,m_type=11;
 uint32_t GetPropertyId(std::string_view name)const {return name=="CB1_OUTPUT_BPC"?7:0;}
 std::optional<uint64_t> ReadPropertyValue(std::string_view name)const BODY
};
int main() {
 CDRMObject object;
 assert(object.ReadPropertyValue("CB1_OUTPUT_BPC")==8);
 value.prop_values[0]=12;assert(object.ReadPropertyValue("CB1_OUTPUT_BPC")==12);
 assert(reads==2 && frees==2);
 assert(!object.ReadPropertyValue("absent") && reads==2);
 failure=true;assert(!object.ReadPropertyValue("CB1_OUTPUT_BPC") && reads==3);
 failure=false;value.props[0]=99;assert(!object.ReadPropertyValue("CB1_OUTPUT_BPC"));
}
'''.replace('BODY', body(source, signature))
        with tempfile.TemporaryDirectory() as directory:
            code, binary = Path(directory)/'test.cpp', Path(directory)/'test'
            code.write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                    str(code), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

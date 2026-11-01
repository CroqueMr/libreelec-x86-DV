"""Exercise accepted native output telemetry and its source/output bindings."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE, body


class OutputFormats(unittest.TestCase):
    def test_accepted_ordinary_output_format(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        code = body(source, 'if (drm->LastPageAccepted() &&')
        program = r'''
#include <cassert>
#include <chrono>
#include "VideoProcessingInfo.h"
namespace KODI::UTILS {enum class Eotf {TRADITIONAL_SDR,TRADITIONAL_HDR,PQ,HLG};}
using KODI::UTILS::Eotf;
Eotf eotf; Eotf GetEotf(){return eotf;}
struct Cache {
 uint64_t generation=0; VideoProcessingInfo info;
 uint64_t GetVideoProcessingGeneration(){return generation;}
 VideoProcessingInfo GetVideoProcessingInfo(){return info;}
 bool SetVideoProcessingInfo(uint64_t, const VideoProcessingInfo& value){info=value;return true;}
} cache;
struct CServiceBroker {static Cache& GetDataCacheCore(){return cache;}};
namespace DVBRIDGE {
struct StreamTelemetry {static int Read(){return 0;}};
VideoProcessingInfo NativeProcessingInfo(int){VideoProcessingInfo info;return info;}
}
struct Drm {bool plus=false;bool HDR10PlusActive(){return plus;}};
void accepted(Drm* drm) BODY
int main(){
 Drm drm;
 for(auto [input,output] : {std::pair{Eotf::TRADITIONAL_SDR,VideoOutputType::SDR},
      {Eotf::PQ,VideoOutputType::HDR10},{Eotf::HLG,VideoOutputType::HLG}}){
   eotf=input;++cache.generation;accepted(&drm);assert(cache.info.outputType==output);
 }
 eotf=Eotf::PQ;drm.plus=true;++cache.generation;accepted(&drm);
 assert(cache.info.outputType==VideoOutputType::HDR10Plus);
 drm.plus=false;accepted(&drm);assert(cache.info.outputType==VideoOutputType::HDR10);
 assert(!cache.info.output.flags);
}
'''.replace('BODY', code)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', '-I' + str(TREE/'xbmc/cores'),
                                    str(root/'test.cpp'), '-o', str(root/'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_panel_keeps_input_and_mode_without_redundant_output_row(self):
        repo = Path(__file__).resolve().parents[2]
        xml = ET.parse(repo/'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        rows = xml.findall(".//include[@name='DVVideoFields']/definition/include[@content='DVInfoRow']")
        rows = [{p.get('name'):p.get('value') for p in row.findall('param')} for row in rows]
        video=xml.find(".//include[@name='DVVideoFields']/definition/include[@content='DVSection']")
        self.assertEqual(video.find("param[@name='label']").get('value'),'VIDEO : $VAR[DVSourceFormat]')
        self.assertFalse(any(row.get('label')=='Output format' for row in rows))
        self.assertIsNone(xml.find("variable[@name='DVOutputFormat']"))
        mode=xml.find("variable[@name='DVPanelMode']")
        self.assertIn('Property(DV.Mode)',ET.tostring(mode,encoding='unicode'))

    def test_settings_category_has_requested_engine_name(self):
        import re
        settings=ET.parse(TREE/'system/settings/settings.xml')
        self.assertIsNotNone(settings.find(".//group[@label='40810']"))
        strings=(TREE/'addons/resource.language.en_gb/resources/strings.po').read_text()
        match=re.search(r'msgctxt "#40810"\s+msgid "([^"]+)"',strings)
        self.assertEqual(match.group(1),'CB1 - Dolby Vision engine')


if __name__ == '__main__':
    unittest.main()

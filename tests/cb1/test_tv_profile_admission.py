"""An unset TV profile must not make its configuration unreachable."""
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class TVProfileAdmissionTests(unittest.TestCase):
    def test_error_catalog_keeps_route_specific_short_causes(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        labels=dict(re.findall(r'msgctxt "#(\d+)"\s+msgid "([^"\n]*)"',
            (tree/'addons/resource.language.en_gb/resources/strings.po').read_text()))
        for number in (40841,40842,40843,40844,40845,40846,40847,40923,41141,41142):
            self.assertLessEqual(len(labels[str(number)]),29)
        self.assertIn('Dolby Vision',labels['40841'])
        self.assertIn('HDR10+',labels['40923'])
        self.assertIn('SDR',labels['41141'])
        self.assertNotIn('HDR',labels['41141'])
        self.assertNotIn('TV',labels['41141'])

    def test_settings_allow_configuration_but_playback_keeps_invalid_modes_disabled(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source=(tree/'xbmc/settings/SettingConditions.cpp').read_text()
        section=source.split('    int reasonId=CDVPlaybackInfo::ReasonLabel(reason);',1)[1].split('\n  }\n}',1)[0]
        program=r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include <cassert>
#include <cmath>
#include <vector>
#include <utility>
struct Option {std::string label="Adaptive",label2;std::vector<std::pair<std::string,bool>> properties;};
Option annotate(DVBRIDGE::OutputReason reason,bool menu,bool hdr10Menu,double peak,int gamut,bool guided=false,bool hlgMenu=false,int requestedMode=4,bool hdr10PlusMenu=false) {
 struct {double peak;int gamut;double expertPeak;int expertGamut;} preferences{peak,gamut,peak,gamut};
 struct Localizer {std::string Get(int id) {return std::to_string(id);}} localizer;
 Option option;int mode=guided?1:requestedMode;
 struct {int lldvUnavailableLabel=41245;} caps;
 int reasonId=CDVPlaybackInfo::ReasonLabel(reason);
 SECTION
 return option;
}
int main() {
 using R=DVBRIDGE::OutputReason;
 auto setup=annotate(R::TVProfileRequired,false,false,0,2);
 assert(!setup.properties.back().second && setup.label2=="40911");
 assert(setup.label=="Adaptive");
 auto gamut=annotate(R::TVProfileRequired,false,false,1000,0);
 assert(!gamut.properties.back().second && gamut.label2=="40912");
 assert(annotate(R::TVProfileRequired,true,false,0,2).properties.back().second);
 assert(annotate(R::TVProfileRequired,false,true,0,2).properties.back().second);
 assert(annotate(R::NoDVTransport,false,false,1000,2).properties.back().second);
 assert(!annotate(R::None,true,false,1000,2).properties.back().second);
 auto sdr=annotate(R::SDRTargetInvalid,false,false,0,0,false,false,7);
 assert(!sdr.properties.back().second && sdr.label2=="41141" && sdr.label=="Adaptive");
 auto validHDR=annotate(R::SDRTargetInvalid,true,false,1000,2,false,false,7);
 assert(validHDR.properties.back().second && validHDR.label2=="41141");
 assert(annotate(R::SDRTargetInvalid,false,false,1000,2,false,false,7,true).properties.back().second);
 static_assert(int(R::NoHDR10PlusTransport)==8 && int(R::SDRTargetInvalid)==9 && int(R::ProcessingPending)==10);
 assert(CDVPlaybackInfo::ReasonLabel(R::TVProfileRequired)==40845);
 struct Output{unsigned flags=CDVPlaybackInfo::SDR;int effective=8;bool fallback=false;};
 const auto detail=CDVPlaybackInfo::Detail("HDR10",Output{});
 assert(detail.find("SDR Rendering")!=std::string::npos && detail.find("metadata")==std::string::npos);
 assert(std::string(CDVPlaybackInfo::Reason(R::SDRTargetInvalid))=="sdr-target-invalid");
 auto lldv=annotate(R::NoPlayerLedTransport,false,false,0,0);
 assert(lldv.properties.back().second && lldv.label2=="41245");
 auto pending=annotate(R::ProcessingPending,true,false,1000,2);
 assert(pending.label=="Adaptive" && pending.label2=="41142" && pending.properties.back().second);
 auto sourceGuided=annotate(R::None,false,true,1000,2,true);
 assert(!sourceGuided.properties.back().second && sourceGuided.label2=="40971");
}
'''.replace('SECTION',section)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(tree/'xbmc'),str(root/'test.cpp'),'-o',str(root/'test')],
                text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],text=True,capture_output=True)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__=='__main__':unittest.main()

"""An unset TV profile must not make its configuration unreachable."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class TVProfileAdmissionTests(unittest.TestCase):
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
Option annotate(DVBRIDGE::OutputReason reason,bool menu,bool hdr10Menu,double peak,int gamut) {
 struct {double peak;int gamut;} preferences{peak,gamut};
 struct Localizer {std::string Get(int id) {return std::to_string(id);}} localizer;
 Option option;int mode=4;
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

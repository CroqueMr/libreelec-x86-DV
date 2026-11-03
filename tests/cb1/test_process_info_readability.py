"""Regression for clipped static metadata captions and grouped pixel dimensions."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE


class ProcessInfoReadability(unittest.TestCase):
    def test_temperature_uses_kodis_regional_label(self):
        path=Path(__file__).resolve().parents[2]/'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml'
        panel=ET.parse(path)
        row=next(row for row in panel.iter('include') if any(
            p.get('name')=='label' and p.get('value')=='Temperature' for p in row.findall('param')))
        value=next(p.get('value') for p in row.findall('param') if p.get('name')=='value')
        self.assertEqual(value,'$INFO[System.CPUTemperature]')

    def test_static_captions_do_not_scroll_and_keep_a_real_value_gap(self):
        path=Path(__file__).resolve().parents[2]/'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml'
        panel=ET.parse(path)
        row=panel.find('./include[@name="DVInfoRow"]')
        dimensions={p.get('name'):p.get('default') for p in row.findall('param')}
        controls=panel.findall('./include[@name="DVInfoRow"]/definition/control/control')
        label,value=controls
        self.assertEqual(label.get('type'),'label')
        self.assertIsNone(label.find('scroll'))
        labelwidth=int(dimensions['labelwidth'])
        valueleft=int(dimensions['valueleft'])
        self.assertEqual(label.findtext('width'),'$PARAM[labelwidth]')
        self.assertEqual(value.findtext('left'),'$PARAM[valueleft]')
        self.assertGreaterEqual(labelwidth,252)
        self.assertGreaterEqual(valueleft-labelwidth,12)
        self.assertGreaterEqual(548-valueleft,280)
        labels={n.get('value') for n in panel.findall('.//include[@content="DVInfoRow"]/param[@name="label"]')}
        self.assertIn('Before AI min/max/avg',labels)
        self.assertIn('AI model',labels)
        self.assertIn('DV L1 min/max/avg',labels)
        self.assertIn('DV L3 min/max/avg',labels)
        self.assertIn('Out L1 min/max/avg',labels)

    def test_native_dimensions_are_plain_integers(self):
        text=(TREE/'xbmc/guilib/guiinfo/PlayerGUIInfo.cpp').read_text()
        start=text.index('    case PLAYER_PROCESS_VIDEOWIDTH:')
        code=text[start:text.index('    case PLAYER_PROCESS_VIDEOSCANTYPE:',start)]
        program=r'''
#include <cassert>
#include <string>
constexpr int PLAYER_PROCESS_VIDEOWIDTH=0,PLAYER_PROCESS_VIDEOHEIGHT=1;
struct StringUtils{static std::string FormatNumber(int x){return x==3840?"3,840":"2,160";}};
struct Cache{int GetVideoWidth(){return 3840;}int GetVideoHeight(){return 2160;}};
struct CServiceBroker{static Cache& GetDataCacheCore(){static Cache c;return c;}};
bool get(int info,std::string& value){switch(info){CASES default:return false;}}
int main(){std::string value;assert(get(0,value)&&value=="3840");assert(get(1,value)&&value=="2160");}
'''.replace('CASES',code)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'check.cpp').write_text(program)
            subprocess.run(['c++','-std=c++20',str(root/'check.cpp'),'-o',str(root/'check')],check=True)
            run=subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

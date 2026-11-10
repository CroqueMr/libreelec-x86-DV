"""Regression for clipped static metadata captions and grouped pixel dimensions."""
from pathlib import Path
import itertools
import json
import os
import re
import subprocess
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE


class ProcessInfoReadability(unittest.TestCase):
    def test_current_block_positions_order_and_row_bindings_are_retained(self):
        panel=ET.parse(Path(__file__).resolve().parents[2]/
            'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        expected=json.loads(Path(__file__).with_name('process_info_structure.json').read_text())
        for name,structure in expected.items():
            include=panel.find('./include[@name="'+name+'"]')
            actual={
                'includes':[{'name':node.get('content') or (node.text or '').strip(),
                    'params':{p.get('name'):p.get('value') for p in node.findall('param')}}
                    for node in include.iter('include')],
                'coordinates':[{'tag':node.tag,'value':node.text}
                    for node in include.iter() if node.tag in
                    {'left','right','top','bottom','width','height'}]}
            self.assertEqual(actual,structure,name)

    def test_current_panel_uses_original_rounded_assets_with_solid_metadata(self):
        panel=ET.parse(Path(__file__).resolve().parents[2]/
            'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        shapes=[('DVProcessLayout','texture','cb1-glass.png','60'),
                ('DVMeters','texture','cb1-card.png','16'),
                ('DVBlockChip','texture','cb1-chip.png','6'),
                ('DVMeterBar','texturebg','cb1-bar.png','2,0,2,0'),
                ('DVMeterBar','midtexture','cb1-bar.png','2,0,2,0')]
        for include,tag,asset,border in shapes:
            node=panel.find('./include[@name="'+include+'"]//'+tag)
            self.assertEqual(node.text,'special://xbmc/media/'+asset)
            self.assertEqual(node.get('border'),border)
        surface=panel.find('./include[@name="DVProcessLayout"]//texture')
        self.assertIsNone(surface.get('colordiffuse'))
        chips=panel.find('./include[@name="DVBlockChips"]')
        for name in ['fill','color']:
            self.assertTrue(chips.find('./param[@name="'+name+'"]').get('default').startswith('FF'))
        used=panel.find('./include[@name="DVUsageChips"]')
        for param in used.findall('.//param[@name="fill"]')+used.findall('.//param[@name="color"]'):
            self.assertTrue(param.get('value').startswith('FF'))
        self.assertNotIn('DV.UnappliedBlocks',ET.tostring(used,encoding='unicode'))

    def test_native_topbar_is_hidden_only_while_process_info_is_visible(self):
        name='addons/skin.estuary/xml/Custom_1109_TopBarOverlay.xml'
        panel=ET.parse(TREE/name).getroot()
        archive=os.environ.get('KODI_UPSTREAM_ARCHIVE')
        if not archive:
            self.skipTest('Set KODI_UPSTREAM_ARCHIVE to the pinned Kodi archive')
        with tarfile.open(archive) as source:
            members=[member for member in source.getmembers() if member.name.endswith('/'+name)]
            self.assertEqual(len(members),1)
            original=ET.fromstring(source.extractfile(members[0]).read())
        conditions=[node.text for node in panel.findall('visible')]
        guard='!Window.IsVisible(playerprocessinfo)'
        added=[node for node in panel.findall('visible') if node.text==guard]
        self.assertEqual(len(added),1)
        panel.remove(added[0])
        # Closing O restores the entire original window: timers, animations,
        # title/clock, actions and every native visibility condition unchanged.
        self.assertEqual(ET.tostring(panel),ET.tostring(original))
        original_conditions=[node.text for node in original.findall('visible')]
        windows=['fullscreenvideo','visualisation','seekbar','pvrosdchannels','pvrchannelguide']

        def evaluate(expression,active,visible):
            expression=re.sub(r'Window.Is(Active|Visible)\(([^)]+)\)',
                lambda match:str(match[2] in (active if match[1]=='Active' else visible)),expression)
            return eval(expression.replace('!',' not ').replace('|',' or ').replace('+',' and '),{'__builtins__':{}},{})

        for flags in itertools.product([False,True],repeat=len(windows)):
            active={window for window,enabled in zip(windows,flags) if enabled}
            native=all(evaluate(condition,active,set()) for condition in original_conditions)
            for info_active,info_visible in itertools.product([False,True],repeat=2):
                context=active|({'playerprocessinfo'} if info_active else set())
                visible={'playerprocessinfo'} if info_visible else set()
                actual=all(evaluate(condition,context,visible) for condition in conditions)
                self.assertEqual(actual,native and not info_visible,
                    (active,info_active,info_visible))

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
        # The caption sits in a zero-height group; the value textbox shares its line and grows.
        label=panel.find('./include[@name="DVInfoRow"]/definition/control/control')
        value=panel.find('./include[@name="DVInfoRow"]/definition/control[@type="label"]')
        self.assertEqual(label.get('type'),'label')
        self.assertIsNone(label.find('scroll'))
        self.assertIsNone(value.find('autoscroll'))
        labelwidth=int(dimensions['labelwidth'])
        valueleft=int(dimensions['valueleft'])
        self.assertEqual(label.findtext('width'),'$PARAM[labelwidth]')
        self.assertEqual(value.findtext('left'),'$PARAM[valueleft]')
        self.assertEqual(labelwidth,252)
        self.assertGreaterEqual(valueleft-labelwidth,12)
        self.assertGreaterEqual(548-valueleft,280)
        for column in panel.findall('.//include[@name="DVProcessLayout"]/definition/control/control[@type="grouplist"]'):
            self.assertEqual(column.findtext('width'),'548')
        self.assertEqual(value.findtext('scroll'),'false')
        self.assertEqual(value.findtext('wrapmultiline'),'false')
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

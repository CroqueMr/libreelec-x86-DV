"""The native label controls retain long values and all processing fields."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


class ProcessInfoWordingTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
    def test_rendering_names_and_committed_ai_details(self):
        import json
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        repo=Path(__file__).resolve().parents[2]
        strings=(tree/'addons/resource.language.en_gb/resources/strings.po').read_text()
        for number in (40867,40970):
            self.assertIn(f'msgctxt "#{number}"\nmsgid "Dolby Vision Rendering"',strings)
        dialog=(tree/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        start=dialog.index('    SetProperty("DV.Reconstruction", "");')
        end=dialog.index('    const auto& localizer=',start)
        # The first localizer belongs inside the generation block.
        end=dialog.index('    const auto& localizer=',end+1)
        code=dialog[start:end]
        program=r'''
#include "cores/VideoProcessingInfo.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include <fmt/format.h>
#include <cassert>
#include <map>
struct StringUtils {template<class... A> static std::string Format(const char* s,A... a){return fmt::format(fmt::runtime(s),a...);}};
struct Localizer {std::string Get(int id)const{return std::to_string(id);}};
struct Resources {Localizer GetLocalizeStrings()const{return {};}};
struct CServiceBroker {static Resources GetResourcesComponent(){return {};}};
int main(){
 VideoProcessingInfo data;auto& output=data.output;
 std::map<std::string,std::string> p;
 auto SetProperty=[&](const char* key,const std::string& value){p[key]=value;};
 auto refresh=[&]{const auto active=output.flags;const bool hdr10=false,metadata=false; CODE };
 output.flags=1;output.hdr10AI=true;output.effective=1;
 output.aiModel="CB1-L1L3 0.1";output.aiBaseline={12,3079,1000};
 output.aiL1L3={15,3100,1100,2048,2050,2049};
 output.emittedL1Known=true;output.emittedL1={15,3100,1100};refresh();
 assert(p["DV.AIModel"]=="CB1-L1L3 0.1" && p["DV.BeforeAI"]=="12 | 3079 | 1000");
 assert(p["DV.AIL1"]=="15 | 3100 | 1100" && p["DV.OutputL1"]=="15 | 3100 | 1100");
 output.aiModel.clear();output.hdr10PlusDV=true;output.guidedSourceFields=6;refresh();
 assert(p["DV.AIModel"].empty() && p["DV.BeforeAI"].empty());
 assert(p["DV.Reconstruction"].find("AI")==std::string::npos);
 assert(p["DV.AIL1"]=="15 | 3100 | 1100");
 output={};refresh();
 for(const auto* key:{"DV.AIModel","DV.BeforeAI","DV.AIL1","DV.AIL3","DV.OutputL1","DV.Reconstruction"})assert(p[key].empty());
}
'''.replace('CODE',code)
        with tempfile.TemporaryDirectory(prefix='cb1-ai-info-') as temp:
            root=Path(temp);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(tree/'xbmc'),str(root/'test.cpp'),
                '-lfmt','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
        header=(repo/'CB1/src/cb1_l1l3_model.h').read_text()
        version=json.loads((repo/'CB1/config/hdr10-ai-dependencies.json').read_text())['model']['version']
        self.assertIn('#define CB1_L1L3_MODEL_VERSION "'+version+'"',header)

    @unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
    def test_renderer_reports_executed_mapping_not_new_preferences(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source=(tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        capture=source[source.index('  const double displayBlack ='):source.index('  const float peak =',source.index('  const double displayBlack ='))]
        start=source.index('  const bool expert=m_effectiveMode==DVBRIDGE_MODE_HDR10_EXPERT;')
        publication=source[start:source.index('  output.fallback =',start)]
        program=r'''
#include "cores/VideoProcessingInfo.h"
#include "dvbridge_policy.h"
#include <cassert>
int main() {
 struct {dvbridge_policy policy;} rendered;
 rendered.policy.tv.gamut=DVBRIDGE_GAMUT_P3_D65;
 rendered.policy.expert_black_nits=0.0042;
 auto* hdrOutput=&rendered;
 CAPTURE
 // Commit releases the pending plan; later settings must not leak into telemetry.
 rendered={};
 struct {int panel=1,gamut=1;double peak=9999;} m_requested;
 struct {unsigned revision=17;} m_pendingIdentity;
 VideoProcessingInfo::Output output;
 const float peak=1234.5;
 auto publish=[&](dvbridge_mode m_effectiveMode) { PUBLICATION };
 publish(DVBRIDGE_MODE_HDR10_EXPERT);
 assert(output.gamut==2 && output.manualPeak==1234.5 && output.displayBlack==0.0042);
 assert(output.revision==17);
 publish(DVBRIDGE_MODE_ENHANCED_DV);
 assert(output.gamut==1 && output.manualPeak==9999 && output.displayBlack==0);
}
'''.replace('CAPTURE',capture).replace('PUBLICATION',publication)
        with tempfile.TemporaryDirectory(prefix='cb1-accepted-mapping-') as temp:
            root=Path(temp);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(tree/'xbmc'),
                '-I'+str(Path(__file__).resolve().parents[2]/'CB1/src'),
                str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    @unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
    def test_display_mapping_tracks_accepted_values_and_clears_for_other_modes(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        dialog = (tree/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        statements = []
        for prop in ('TVProfile', 'DisplayBlack', 'HDR10Target', 'HDR10TargetLabel'):
            start = dialog.index('SetProperty("DV.'+prop+'",')
            statements.append(dialog[start:dialog.index(';', start)+1])
        program = r'''
#include "cores/VideoProcessingInfo.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include <fmt/format.h>
#include <cassert>
#include <map>
struct StringUtils {
 template<class... A> static std::string Format(const char* s,A... a) {
  return fmt::format(fmt::runtime(s),a...);
 }
};
int main() {
 VideoProcessingInfo data;auto& output=data.output;
 std::map<std::string,std::string> properties;
 auto SetProperty=[&](const char* key,const std::string& value){properties[key]=value;};
 auto refresh=[&]{const auto active=output.flags;const bool hdr10=active&CDVPlaybackInfo::HDR10;
  STATEMENTS
 };
 output.flags=CDVPlaybackInfo::HDR10;output.effective=3;
 output.gamut=2;output.target=1234.5;output.manualPeak=9999;output.displayBlack=0.0042;
 refresh();
 assert(properties["DV.TVProfile"]=="P3-D65 / 1234.5 nits");
 assert(properties["DV.DisplayBlack"]=="0.0042 nits");
 assert(properties["DV.HDR10Target"].empty()); // No duplicate peak row.
 output.target=600;output.gamut=1;output.displayBlack=0;
 refresh();
 assert(properties["DV.TVProfile"]=="BT.709 / 600 nits");
 assert(properties["DV.DisplayBlack"]=="0 nits"); // Zero is a valid OLED black.
 output.effective=2;output.fallback=true;output.target=1000;
 refresh();
 assert(properties["DV.TVProfile"].empty() && properties["DV.DisplayBlack"].empty());
 assert(properties["DV.HDR10Target"]=="1000 nits");
 assert(properties["DV.HDR10TargetLabel"]=="Source reference");
 for(int mode:{1,5}) {output.flags=CDVPlaybackInfo::HDMI;output.effective=mode;refresh();
  assert(properties["DV.TVProfile"].empty() && properties["DV.DisplayBlack"].empty());}
 output.effective=4;output.gamut=3;output.manualPeak=2000;refresh();
 assert(properties["DV.TVProfile"]=="BT.2020 / 2000 nits");
 assert(properties["DV.DisplayBlack"].empty());
 output.flags=0;refresh();
 assert(properties["DV.TVProfile"].empty() && properties["DV.DisplayBlack"].empty());
 assert(properties["DV.HDR10Target"].empty());
}
'''.replace('STATEMENTS', '\n'.join(statements))
        with tempfile.TemporaryDirectory(prefix='cb1-display-info-') as temp:
            root=Path(temp);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(tree/'xbmc'),
                str(root/'test.cpp'),'-lfmt','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    @unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
    def test_unused_blocks_exclude_locally_applied_and_forwarded_metadata(self):
        from test_native_video_source import body
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        dialog = (tree/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        statement = re.search(r'^\s*SetProperty\("DV.UnappliedBlocks",[^\n]+', dialog, re.M).group()
        used_statement = re.search(r'^\s*SetProperty\("DV.AppliedBlocks",[^\n]+', dialog, re.M).group()
        header = (tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h').read_text()
        formatter = body(header, 'static std::string Blocks(')
        program = r'''
#include "cores/VideoProcessingInfo.h"
#include <cassert>
struct CDVPlaybackInfo {enum { HDR10PLUS=16 }; static std::string Blocks(const std::bitset<256>& blocks) FORMATTER };
int main() {
  VideoProcessingInfo data;
  bool metadata = true;
  auto displayed = [&](bool used=false) {
    std::string result;
    auto SetProperty = [&](const char*, const std::string& value) { result = value; };
    const auto applied = data.AppliedBlocks();
    const auto active=data.output.flags;
    if(used) { USED_STATEMENT } else { STATEMENT }
    return result;
  };
  // TV-Led Master: L1/L4 are forwarded, L5 is geometry, L6 stays local/unused.
  for (unsigned level : {1u, 4u, 5u, 6u}) data.blocks[level] = true;
  data.appliedBlocks[5] = true;
  for (unsigned level : {1u, 3u, 4u, 5u, 9u, 11u, 254u}) data.transmittedBlocks[level] = true;
  assert(displayed() == "L6" && "Forwarded L1/L4 must not be reported unused");
  // Suppressed L2 remains unused unless a local conversion consumed it.
  data.blocks[2] = true;
  assert(displayed() == "L2 L6");
  data.appliedBlocks[2] = true;
  assert(displayed() == "L6");
  // HDR10 conversion has no DV-forwarding exemption.
  data.blocks[2] = false;
  data.transmittedBlocks.reset();
  data.appliedBlocks[1] = data.appliedBlocks[6] = true;
  assert(displayed() == "L4");
  data.appliedBlocks[4] = true;
  assert(displayed().empty());
  metadata = false;
  data.appliedBlocks.reset();
  assert(displayed().empty());
  metadata=true;data.blocks.reset();data.transmittedBlocks.reset();
  data.blocks[1]=data.blocks[5]=data.blocks[8]=true;data.appliedBlocks[5]=true;
  data.output.flags=CDVPlaybackInfo::HDR10PLUS;data.output.creativeEdited=(1u<<1)|(1u<<8);
  assert(displayed(true)=="L1 L5 L8"); // Metadata translation is use, not pixel application.
  data.output.flags=0;assert(displayed(true)=="L5");
}
'''.replace('FORMATTER', formatter).replace('USED_STATEMENT', used_statement).replace('STATEMENT', statement)
        with tempfile.TemporaryDirectory(prefix='cb1-metadata-use-') as temp:
            root = Path(temp)
            (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-I'+str(tree/'xbmc'),
                                    str(root/'test.cpp'), '-o', str(root/'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_block_details_keep_source_use_and_delivery_visible_together(self):
        panel=ET.parse(Path(__file__).resolve().parents[2]/
            'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        rows=panel.findall('.//include[@content="DVInfoRow"]')
        self.assertIsNone(panel.find('./variable[@name="DVAudioOutput"]'))
        self.assertTrue(any(r.find('./param[@name="value"]').get('value') ==
                            '$INFO[Player.Process(audiooutputtransport)]' for r in rows))
        expected={'DV.ParsedBlocks':'File metadata','DV.AppliedBlocks':'Used by CB1',
                  'DV.TransmittedBlocks':'Sent to TV','DV.MinimumLinkBits':'$LOCALIZE[40848]',
                  'DV.Fallback':'Fallback'}
        for prop,label in expected.items():
            row=next(r for r in rows if r.find('./param[@name="value"]').get('value')==
                     '$INFO[Window(playerprocessinfo).Property('+prop+')]')
            self.assertEqual(row.find('./param[@name="label"]').get('value'),label)
        def row_for(prop):
            return next(r for r in rows if r.find('./param[@name="value"]').get('value')==
                        '$INFO[Window(playerprocessinfo).Property('+prop+')]')
        used=row_for('DV.AppliedBlocks').find('./param[@name="visible"]').get('value')
        sent=row_for('DV.TransmittedBlocks').find('./param[@name="visible"]').get('value')
        self.assertNotIn('DV.TransmittedBlocks',used)
        self.assertIn('!String.IsEmpty(Window(playerprocessinfo).Property(DV.AppliedBlocks))',used)
        self.assertIn('!String.IsEmpty(Window(playerprocessinfo).Property(DV.TransmittedBlocks))',sent)
        values={r.find('./param[@name="value"]').get('value') for r in rows}
        self.assertNotIn('$INFO[Window(playerprocessinfo).Property(DV.UnappliedBlocks)]',values)
        self.assertNotIn('$INFO[Window(playerprocessinfo).Property(DV.PartialBlocks)]',values)
        controls=panel.findall('./include[@name="DVInfoRow"]/definition/control/control')
        self.assertEqual(len(controls),2)
        self.assertEqual(controls[0].get('type'),'label')
        self.assertEqual(controls[1].get('type'),'label')
        self.assertNotEqual(controls[1].findtext('scroll'),'true')
        self.assertEqual(controls[1].findtext('wrapmultiline'),'true')
        self.assertEqual(controls[1].findtext('aligny'),'top')
        for prop in ('DV.Fallback','DV.AdmissionReason','DV.Reconstruction'):
            self.assertGreaterEqual(int(row_for(prop).find('./param[@name="height"]').get('value')),90)
        for prop in ('DV.RequestedPolicy','DV.OutputStage','DV.AtomicResult'):
            height=row_for(prop).find('./param[@name="height"]')
            self.assertGreaterEqual(int(height.get('value')) if height is not None else 30,54,prop)
        default=panel.find('./include[@name="DVInfoRow"]/param[@name="height"]').get('default')
        for prop in ('DV.ParsedBlocks','DV.AppliedBlocks','DV.TransmittedBlocks','DV.L1Nits'):
            height=row_for(prop).find('./param[@name="height"]')
            self.assertEqual(int(height.get('value') if height is not None else default),30,prop)

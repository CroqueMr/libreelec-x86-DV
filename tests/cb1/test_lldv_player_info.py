"""Exercise the Kodi presentation summary for a rendered LLDV picture."""

import os
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from test_native_video_source import TREE, body
from test_process_info_metadata import run


ROOT = Path(__file__).resolve().parents[2]


class PlayerLedInfoTests(unittest.TestCase):
    def test_confirmed_picture_owns_the_panel_facts(self):
        prefix = os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:
            self.skipTest('matched FFmpeg required')
        prefix = Path(prefix)
        dialog = (TREE / 'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        trim_text = body(dialog, 'std::string LldvTrimText(') if 'LldvTrimText(' in dialog else '{}'
        program = r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlayerLedOutput.h"
#include <cassert>

extern "C" bool dvbridge_creative_cm4_coefficients(dvbridge_cm4_coefficients* out,
    const dvbridge_creative_plan* plan)
{
  *out={}; out->sop[0]=1.25; out->sop[2]=1; out->chroma_base=out->saturation_gain=1;
  out->mid_exponent=plan->cm4_weight;
  return true;
}

std::string LldvTrimText(unsigned levels, unsigned groups) TRIM_TEXT

int main()
{
  using namespace DVBRIDGE;
  SourceBinding id{7,2,9};
  LldvConnectorStatus connector{};
  connector.sink.status=DV_EDID_LLDV_ONLY; connector.sink.lldv_422=true;
  connector.driverFormats=LLDV_422; connector.currentTiming=true;
  dvbridge_creative_plan plan{};
  plan.policy.tv={1000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_P3_D65};
  plan.policy.expert_black_nits=0.002;
  plan.status=DVBRIDGE_CREATIVE_READY;
  plan.backend=DVBRIDGE_CREATIVE_CM29_COMPATIBILITY;
  plan.cmv40_status=CB1_CMV40_APPEND;
  plan.applied_levels=(1u<<1)|(1u<<2)|(1u<<9);
  plan.l2_coverage.applied=31;
  for(double& code : plan.codes) code=2048;
  plan.codes[0]=2100; plan.codes[3]=3000; // Chroma is dormant without a saturation trim.
  plan.analysis[1]=3300; plan.analysis[2]=1800;
  assert(!PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true));
  connector.active=LldvFormat::Y422_10;
  assert(!PlayerLedOutput(CB1_MASTER_FAILED,id,id,connector,plan,true));
  assert(!PlayerLedOutput(CB1_MASTER_READY,{},{},connector,plan,true));
  assert(!PlayerLedOutput(CB1_MASTER_READY,id,{7,3,9},connector,plan,true));
  connector.currentTiming=false;
  assert(!PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true));
  connector.currentTiming=true;
  connector.driverFormats=0;
  assert(!PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true));
  connector.forced42210=true; // Advertised capability alone cannot describe the active route.
  assert(!PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true));
  connector.activeForced=true;
  auto forced=PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true);
  assert(forced && forced->bits==10 && forced->minimumLinkBits==12);
  connector.active=LldvFormat::Y422_12;
  assert(!PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true));
  connector.active=LldvFormat::Y422_10;
  connector.forced42210=false;
  assert(!PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true));
  connector.activeForced=false;
  connector.driverFormats=LLDV_422;
  connector.sink.lldv_422=false;
  assert(!PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true));
  connector.sink.lldv_422=true;
  auto output=PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true);
  assert(output && output->lldv && output->bits==10 && output->minimumLinkBits==12);
  assert(output->stream==7 && output->picture==2 && output->revision==9);
  assert((output->flags & CDVPlaybackInfo::FEL) && output->felUpscaling==-1);
  assert(PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,true,true)->felUpscaling==2);
  assert(output->target==1000 && output->displayBlack==0.002 && output->lldv->cm4Appended);
  assert(output->lldv->scenePQ[0]==3300 && output->lldv->scenePQ[1]==1800);
  assert(LldvTrimText(output->creativeApplied,output->lldv->trimGroups)=="L2 · SOP");
  assert(CDVPlaybackInfo::Mode(*output)=="Dolby Vision Player-Led");

  StreamSnapshot source;
  source.profile=7; source.metadata=true; source.l1=true;
  source.blocks.set(1).set(2).set(5).set(8);
  source.output=*output;
  auto info=NativeProcessingInfo(source);
  assert(info.outputType==VideoOutputType::DolbyVision && info.output.lldv);
  assert(info.AppliedBlocks()[2] && !info.AppliedBlocks()[5] && !info.AppliedBlocks()[8]);
  assert(info.TransmittedBlocks().none() && !info.cm4);

  plan.codes[0]=2048;
  output=PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,false);
  assert(output && !(output->creativeApplied & (1u<<2)) && !(output->flags & CDVPlaybackInfo::FEL));
  assert(LldvTrimText(output->creativeApplied,output->lldv->trimGroups).empty());

  plan.backend=DVBRIDGE_CREATIVE_CM4; plan.cmv40_status=CB1_CMV40_EXISTING;
  plan.applied_levels=(1u<<1)|(1u<<3)|(1u<<8);
  plan.l8_coverage.applied=0xdf; plan.l8_coverage.preserved=32; plan.cm4_weight=1.5;
  connector.active=LldvFormat::Y422_12;
  output=PlayerLedOutput(CB1_MASTER_READY,id,id,connector,plan,false);
  assert(output && output->bits==12 && !output->lldv->cm4Appended);
  assert(LldvTrimText(output->creativeApplied,output->lldv->trimGroups)=="L8 · SOP · Mid");
  source.output=*output; source.cm4=true;
  for (unsigned profile : {5u,7u,8u})
  {
    source.profile=profile; source.compatibility=profile==8 ? 4 : 0;
    source.el=profile==7; // MEL on this render, since FEL was not executed.
    info=NativeProcessingInfo(source);
    assert(info.cm4 && info.profile==profile && info.compatibility==source.compatibility);
    assert(info.el==source.el && !(info.output.flags & CDVPlaybackInfo::FEL));
    assert(info.TransmittedBlocks().none());
  }

  // A pending/failed frame has no accepted summary. TV-led and native SDR replace it.
  assert(!PlayerLedOutput(CB1_MASTER_FAILED,{8,1,10},{8,1,10},connector,plan,false));
  assert(source.output.lldv && source.output.stream==id.stream);
  source.output={}; source.output.flags=CDVPlaybackInfo::HDMI;
  info=NativeProcessingInfo(source);
  assert(!info.output.lldv && info.TransmittedBlocks()[2]);
  assert(CDVPlaybackInfo::Mode(info.output)=="Dolby Vision Reference");
  source={}; info=NativeProcessingInfo(source);
  assert(!info.output.lldv && !info.outputType && info.AppliedBlocks().none());
}
'''.replace('TRIM_TEXT', trim_text)
        run(self, {
            'test.cpp': program,
            'ServiceBroker.h': '''#pragma once
#include "cores/DataCacheCore.h"
struct CServiceBroker { static CDataCacheCore& GetDataCacheCore(); };
''',
            'cores/DataCacheCore.h': '''#pragma once
#include "cores/VideoProcessingInfo.h"
struct CDataCacheCore {
  bool SetVideoProcessingInfo(uint64_t, const VideoProcessingInfo&);
  VideoProcessingInfo GetVideoProcessingInfo();
};
''',
        }, ('-I' + str(ROOT / 'CB1/src'), '-I' + str(prefix / 'include')))

    def test_panel_reuses_the_fixed_layout(self):
        path = ROOT / 'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml'
        panel = ET.parse(path)
        output = panel.find('./variable[@name="DVOutputFormat"]/value')
        self.assertEqual(output.text, 'Dolby Vision · Player-Led')
        rows = panel.findall('./include[@name="DVRenderingFields"]//include[@content="DVInfoRow"]')
        self.assertTrue(any(row.find('./param[@name="value"]').get('value').endswith('Property(DV.LocalCM4)]')
                            for row in rows))

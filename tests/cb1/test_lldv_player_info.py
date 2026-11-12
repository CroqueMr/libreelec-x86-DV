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
  connector.connectorId=17; connector.timingCommitted=true;
  LldvTransport packed{17,LldvFormat::Y422_10,false};
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
  const auto outputFor = [&](cb1_master_status status, SourceBinding mapped,
                             SourceBinding presented, bool fel, bool upscaled = false) {
    return PlayerLedOutput(status,mapped,presented,packed,connector,plan,fel,upscaled);
  };
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.active=LldvFormat::Y422_10;
  assert(!outputFor(CB1_MASTER_FAILED,id,id,true));
  assert(!outputFor(CB1_MASTER_READY,{},{},true));
  assert(!outputFor(CB1_MASTER_READY,id,{7,3,9},true));
  connector.timingCommitted=false; // The selected mode has not flipped.
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.timingCommitted=true;
  connector.connectorId=18; // A late receipt from another connector is insufficient.
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.connectorId=17;
  connector.active=LldvFormat::Y422_12;
  assert(!outputFor(CB1_MASTER_READY,id,id,true)); // Carrier packed at 10 bits.
  connector.active=LldvFormat::Y422_10;
  connector.currentTiming=false;
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.currentTiming=true;
  connector.driverFormats=0;
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.forced42210=true; // Advertised capability alone cannot describe the active route.
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.activeForced=true;
  assert(!outputFor(CB1_MASTER_READY,id,id,true)); // Native carrier request, forced readback.
  packed.forced=true;
  auto forced=outputFor(CB1_MASTER_READY,id,id,true);
  assert(forced && forced->bits==10 && forced->minimumLinkBits==12);
  connector.active=LldvFormat::Y422_12;
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.active=LldvFormat::Y422_10;
  connector.forced42210=false;
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.activeForced=false;
  packed.forced=false;
  connector.driverFormats=LLDV_422;
  connector.sink.lldv_422=false;
  assert(!outputFor(CB1_MASTER_READY,id,id,true));
  connector.sink.lldv_422=true;
  auto output=outputFor(CB1_MASTER_READY,id,id,true);
  assert(output && output->lldv && output->bits==10 && output->minimumLinkBits==12);
  assert(!output->ignoreL5);
  assert(output->stream==7 && output->picture==2 && output->revision==9);
  assert((output->flags & CDVPlaybackInfo::FEL) && output->felUpscaling==-1);
  assert(outputFor(CB1_MASTER_READY,id,id,true,true)->felUpscaling==2);
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
  assert(info.AppliedBlocks()[2] && info.AppliedBlocks()[5] && !info.AppliedBlocks()[8]);
  assert(info.TransmittedBlocks().none() && !info.cm4);

  plan.codes[0]=2048;
  output=outputFor(CB1_MASTER_READY,id,id,false);
  assert(output && !(output->creativeApplied & (1u<<2)) && !(output->flags & CDVPlaybackInfo::FEL));
  assert(LldvTrimText(output->creativeApplied,output->lldv->trimGroups).empty());

  plan.backend=DVBRIDGE_CREATIVE_CM4; plan.cmv40_status=CB1_CMV40_EXISTING;
  plan.applied_levels=(1u<<1)|(1u<<3)|(1u<<8);
  plan.l8_coverage.applied=0xdf; plan.l8_coverage.preserved=32; plan.cm4_weight=1.5;
  connector.active=LldvFormat::Y422_12;
  packed.format=LldvFormat::Y422_12;
  output=outputFor(CB1_MASTER_READY,id,id,false);
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
  assert(!outputFor(CB1_MASTER_FAILED,{8,1,10},{8,1,10},false));
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

    def test_seek_retires_only_unsubmitted_carriers(self):
        renderer = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        current = body(renderer, 'bool CDVBridgeGLES::PlayerLedCpuCurrent(')
        window = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        present = body(window, 'bool CWinSystemGbmGLESContext::PresentPlayerLedFrame()')
        start = present.index('  if (m_dvBridge->PlayerLedCpuPending())')
        queue = present[start:present.index('  bool accepted', start)]
        run(self, {'test.cpp': r'''
#include <cassert>
#include <cstdint>
#include <deque>
struct Bridge
{
  struct Frame {struct {uint64_t informationGeneration;} source;} frame{{4}};
  struct Cpu {struct {Frame* frame;} slots[1]; std::deque<unsigned> queue{0};} cpu{{{&frame}}};
  Cpu* m_playerLedCpu{&cpu};
  bool PlayerLedCpuPending() const { return !cpu.queue.empty(); }
  bool PlayerLedCpuCurrent(uint64_t generation) const CURRENT
};
struct CServiceBroker
{
  inline static uint64_t generation=4;
  static CServiceBroker GetDataCacheCore() { return {}; }
  uint64_t GetVideoProcessingGeneration() const { return generation; }
};
struct Window
{
  Bridge bridge;
  Bridge* m_dvBridge{&bridge};
  unsigned queued=0, acceptedByKms=1;
  void DiscardDVBridgeFrame() { bridge.cpu.queue.clear(); }
  void PresentPlayerLedCpu(int) { ++queued; }
  bool present()
  {
    const int transport=2;
    QUEUE
    return false;
  }
};
int main()
{
  Window w;
  assert(w.present() && w.queued==1 && w.acceptedByKms==1);
  CServiceBroker::generation=5;
  assert(w.present() && w.queued==1 && w.acceptedByKms==1 && !w.bridge.PlayerLedCpuPending());
  w.bridge.frame.source.informationGeneration=5;
  w.bridge.cpu.queue.push_back(0);
  assert(w.present() && w.queued==2 && w.acceptedByKms==1);
}
'''.replace('CURRENT', current).replace('QUEUE', queue)})

    def test_panel_reuses_the_fixed_layout(self):
        path = ROOT / 'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml'
        panel = ET.parse(path)
        output = panel.find('./variable[@name="DVOutputFormat"]/value')
        self.assertEqual(output.text, 'Dolby Vision · Player-Led')
        rows = panel.findall('./include[@name="DVRenderingFields"]//include[@content="DVInfoRow"]')
        self.assertTrue(any(row.find('./param[@name="value"]').get('value').endswith('Property(DV.LocalCM4)]')
                            for row in rows))

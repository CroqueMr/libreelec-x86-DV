"""Execute navigation retirement and the real subtitle close/selection code.

The fixture models packet/queue boundaries and overlay ownership, not rendering.
FFmpeg's inherited EnableStream is deliberately a no-op, as in the pinned tree.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class BluraySubtitleRetirement(unittest.TestCase):
    def test_deselected_pg_retires_without_a_new_packet_and_preserves_menus(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text()
        process = body(source, 'void CVideoPlayer::Process()')
        marker = 'const auto closeDeselectedBluraySubtitle = [this]'
        retire = body(process, marker) if marker in process else '{}'
        close = body(source, 'bool CVideoPlayer::CloseStream(')
        enable = body(source, 'void CVideoPlayer::SetEnableStream(')
        better = body(source, 'bool CVideoPlayer::IsBetterStream(')
        sub_source = (TREE / 'xbmc/cores/VideoPlayer/VideoPlayerSubtitle.cpp').read_text()
        sub_close = body(sub_source, 'void CVideoPlayerSubtitle::CloseStream(')
        program = r'''
#include <algorithm>
#include <cassert>
#include <memory>
#include <mutex>
#include <vector>
constexpr int LOGINFO=0, CACHESTATE_DONE=1;
struct CLog { template<class... T>static void Log(T&&...){} };
enum class StreamType { AUDIO, VIDEO, SUBTITLE };
enum class DVDOverlaySource { SUBTITLE, MENU };
enum { DVDSTREAM_TYPE_BLURAY, DVDSTREAM_TYPE_DVD, OTHER_INPUT };
enum { STREAM_SOURCE_NONE, STREAM_SOURCE_DEMUX, STREAM_SOURCE_TEXT,
       STREAM_SOURCE_DEMUX_SUB, STREAM_SOURCE_VIDEOMUX };
#define STREAM_SOURCE_MASK(x) (x)
struct CDVDInputStream {
 struct IMenus { virtual ~IMenus()=default;virtual MenuType GetSupportedMenuType()=0; };
 virtual ~CDVDInputStream()=default;
 int kind=DVDSTREAM_TYPE_BLURAY;
 bool IsStreamType(int t) const { return kind==t; }
};
struct Input : CDVDInputStream, CDVDInputStream::IMenus {
 MenuType type=MenuType::NATIVE;
 MenuType GetSupportedMenuType() override { return type; }
};
struct OverlayContainer {
 std::vector<DVDOverlaySource> values{DVDOverlaySource::SUBTITLE,DVDOverlaySource::MENU};
 void Clear(DVDOverlaySource source) {
  values.erase(std::remove(values.begin(),values.end(),source),values.end());
 }
 bool Has(DVDOverlaySource source) const {
  return std::find(values.begin(),values.end(),source)!=values.end();
 }
};
struct IDVDStreamPlayer {
 static constexpr int SYNC_INSYNC=0;
 virtual ~IDVDStreamPlayer()=default;
 virtual void CloseStream(bool)=0;
};
struct CVideoPlayerSubtitle : IDVDStreamPlayer {
 std::mutex m_section;
 std::unique_ptr<int> m_pSubtitleFileParser=std::make_unique<int>(1);
 std::unique_ptr<int> m_pOverlayCodec=std::make_unique<int>(1);
 struct { void FlushCurrentPacket() {} } m_dvdspus;
 std::shared_ptr<OverlayContainer> m_pOverlayContainer=std::make_shared<OverlayContainer>();
 void CloseStream(bool bWaitForBuffers) override SUB_CLOSE
};
struct CCurrentStream {
 StreamType type=StreamType::SUBTITLE;
 int id=19,source=STREAM_SOURCE_DEMUX,player=1,syncState=0;
 long demuxerId=7;
 void Clear() { id=-1;source=STREAM_SOURCE_NONE; }
};
struct CDemuxStream {
 int dvdNavId=4770,uniqueId=19,source=STREAM_SOURCE_DEMUX;
 long demuxerId=7;
 bool disabled=false;
 StreamType type=StreamType::SUBTITLE;
};
struct Demuxer {
 CDemuxStream full,forced{4771,20};
 CDemuxStream* GetStream(long demux,int id) {
  if (demux!=7) return nullptr;
  return id==19 ? &full : id==20 ? &forced : nullptr;
 }
 void EnableStream(long,int,bool) {} // pinned CDVDDemux implementation
};
struct CVideoPlayer {
 std::shared_ptr<CDVDInputStream> m_pInputStream=std::make_shared<Input>();
 std::shared_ptr<Demuxer> m_pDemuxer=std::make_shared<Demuxer>();
 CCurrentStream m_CurrentSubtitle;
 CVideoPlayerSubtitle subtitle;
 struct { int iSelectedSPUStream=4771,iSelectedAudioStream=-1; } m_dvd;
 struct { bool videoOnly=false; } m_playerOptions;
 struct { bool Contains(StreamType,int,long,int) const { return true; } } m_SelectionStreams;
 bool m_bAbortRequest=false, m_bdjAudioHandoff=false;
 int cachingChanges=0;
 IDVDStreamPlayer* GetStreamPlayer(int) { return &subtitle; }
 void SetCaching(int) { ++cachingChanges; }
 void SetEnableStream(CCurrentStream& current,bool isEnabled) ENABLE
 bool CloseStream(CCurrentStream& current,bool bWaitForBuffers) CLOSE
 bool IsBetterStream(const CCurrentStream& current,CDemuxStream* stream) BETTER
 void Boundary() RETIRE
};
int main() {
 // The old cue and menu are both present. No forced-track packet is needed.
 CVideoPlayer p;p.Boundary();
 assert(p.m_CurrentSubtitle.id==-1 && !p.subtitle.m_pOverlayContainer->Has(DVDOverlaySource::SUBTITLE)
        && "deselected full PG must retire before the first forced packet");
 assert(p.subtitle.m_pOverlayContainer->Has(DVDOverlaySource::MENU));
 assert(!p.subtitle.m_pOverlayCodec && p.cachingChanges==0);
 // Old full packets cannot reselect themselves; the existing selection code
 // accepts the requested forced packet whenever it eventually arrives.
 assert(!p.IsBetterStream(p.m_CurrentSubtitle,&p.m_pDemuxer->full));
 assert(p.IsBetterStream(p.m_CurrentSubtitle,&p.m_pDemuxer->forced));
 // Model that later successful opening, then the reverse author selection.
 p.m_CurrentSubtitle.id=20;p.m_CurrentSubtitle.source=STREAM_SOURCE_DEMUX;
 p.subtitle.m_pOverlayContainer->values.push_back(DVDOverlaySource::SUBTITLE);
 p.m_dvd.iSelectedSPUStream=4770;p.Boundary();
 assert(p.m_CurrentSubtitle.id==-1 && p.subtitle.m_pOverlayContainer->Has(DVDOverlaySource::MENU));
 assert(p.IsBetterStream(p.m_CurrentSubtitle,&p.m_pDemuxer->full));
 // Placement checks below bind this body to both production boundaries,
 // including the paused/full-queue path that never reaches ReadPacket.
 // Do not disturb direct/no-interface, non-disc, external/CC or unknown choices.
 for (int scenario=0;scenario<12;++scenario) {
  CVideoPlayer keep;
  if (scenario==0) std::static_pointer_cast<Input>(keep.m_pInputStream)->type=MenuType::NONE;
  if (scenario==1) keep.m_pInputStream=std::make_shared<CDVDInputStream>();
  if (scenario==2) keep.m_pInputStream->kind=OTHER_INPUT;
  if (scenario==3) keep.m_CurrentSubtitle.source=STREAM_SOURCE_TEXT;
  if (scenario==4) keep.m_CurrentSubtitle.source=STREAM_SOURCE_DEMUX_SUB;
  if (scenario==5) keep.m_CurrentSubtitle.source=STREAM_SOURCE_VIDEOMUX;
  if (scenario==6) keep.m_dvd.iSelectedSPUStream=-1;
  if (scenario==7) keep.m_dvd.iSelectedSPUStream=4770;
  if (scenario==8) keep.m_pDemuxer.reset();
  if (scenario==9) keep.m_CurrentSubtitle.demuxerId=88;
  if (scenario==10) keep.m_pInputStream.reset();
  if (scenario==11) keep.m_CurrentSubtitle.id=-1;
  const int originalId=keep.m_CurrentSubtitle.id;
  keep.Boundary();
  assert(keep.m_CurrentSubtitle.id==originalId && keep.subtitle.m_pOverlayContainer->Has(DVDOverlaySource::SUBTITLE));
  assert(keep.subtitle.m_pOverlayContainer->Has(DVDOverlaySource::MENU));
 }
}
'''
        program = program.replace('struct CDVDInputStream {', 'enum class MenuType {NONE,NATIVE};\nstruct CDVDInputStream {')
        for tag, value in [('SUB_CLOSE', sub_close), ('ENABLE', enable), ('CLOSE', close),
                           ('BETTER', better), ('RETIRE', retire)]:
            program = program.replace(tag, value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(process.count('closeDeselectedBluraySubtitle();'), 2)
        messages = process.index('HandleMessages();')
        first = process.index('closeDeselectedBluraySubtitle();', messages)
        self.assertLess(process.index('if (m_bAbortRequest)', messages), first)
        self.assertLess(first, process.index('HandlePlaySpeed();', messages))
        read = re.search(r'ReadPacket\(pPacket,\s*pStream\)', process).start()
        second = process.index('closeDeselectedBluraySubtitle();', read)
        self.assertLess(second, process.index('if (pPacket && !pStream)', read))
        self.assertLess(second, process.index('if (!pPacket)', read))


if __name__ == '__main__':
    unittest.main()

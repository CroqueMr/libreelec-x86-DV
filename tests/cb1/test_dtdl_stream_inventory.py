"""A late in-band joined BL must reach Kodi's selectable stream inventory.

Runs the shipped demux insertion and player packet-consumption methods. Packet
I/O is replaced with one controlled stream; no decoder, GPU or media is needed.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class DTDLStreamInventory(unittest.TestCase):
    def test_late_joined_base_is_published_before_source_labels_are_read(self):
        demux = (TREE / 'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        player = (TREE / 'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text()
        insert = 'void CDVDDemuxFFmpeg::AddStream(int streamIdx, CDemuxStream* stream)'
        read = 'bool CVideoPlayer::ReadPacket(DemuxPacket*& packet, CDemuxStream*& stream)'
        # This is how the real top-level AddStream initializes a newly admitted
        # BL, after ParsePacket has finally extracted its in-band HEVC headers.
        source_start = demux.index('    stream->source =', demux.index('CDemuxStream* CDVDDemuxFFmpeg::AddStream(int streamIdx)'))
        source_assignment = demux[source_start:demux.index('\n', source_start)]
        program = r'''
#define HAVE_DVBRIDGE 1
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <vector>
enum { STREAM_SOURCE_NONE=0, STREAM_SOURCE_DEMUX=256,
       STREAM_SOURCE_DEMUX_SUB=768, DMX_SPECIALID_STREAMCHANGE=-11, LOGDEBUG=0, LOGERROR=1 };
enum class StreamType { NONE, VIDEO };
struct CDemuxStream {
 int source{}, uniqueId{}, changes{}; int64_t demuxerId{7};
 StreamType type{StreamType::VIDEO};
};
struct DemuxPacket { int iStreamId{}; int64_t demuxerId{7}; };
struct CLog { template<class... T> static void Log(T&&...) {} };
CDemuxStream* newStream() {
 auto* stream=new CDemuxStream;
 SOURCE_ASSIGNMENT
 return stream;
}
class CDVDDemuxFFmpeg {
public:
 std::map<int,CDemuxStream*> m_streams;
 bool m_blurayDovi{true};
 int m_blurayBase{0};
 bool late{};
 void AddStream(int streamIdx,CDemuxStream* stream);
 CDemuxStream* GetStream(int64_t,int id) {return m_streams.at(id);}
 std::vector<CDemuxStream*> GetStreams() {
   std::vector<CDemuxStream*> result;
   for (auto [id,stream]:m_streams) result.push_back(stream);
   return result;
 }
 DemuxPacket* Read() {
   if(late) {
     AddStream(0,newStream()); late=false;
   }
   return new DemuxPacket;
 }
 void GetPrograms(std::vector<int>&) {}
 ~CDVDDemuxFFmpeg() {for(auto [id,stream]:m_streams) delete stream;}
};
struct SelectionStreams {
 std::vector<CDemuxStream*> streams;
 void Clear(StreamType,int) {streams.clear();}
 void Update(void*,CDVDDemuxFFmpeg* demux) {
   streams=demux->GetStreams();
   // CSelectionStreams::Update consumes the native discovery marker.
   for(auto* stream:streams) stream->source=STREAM_SOURCE_DEMUX;
 }
};
struct SubtitlePlayer {bool AcceptsData() {return false;}};
class CVideoPlayer {
public:
 std::shared_ptr<CDVDDemuxFFmpeg> m_pDemuxer=std::make_shared<CDVDDemuxFFmpeg>();
 std::shared_ptr<CDVDDemuxFFmpeg> m_pSubtitleDemuxer;
 std::shared_ptr<SubtitlePlayer> m_VideoPlayerSubtitle=std::make_shared<SubtitlePlayer>();
 void* m_pInputStream{};
 SelectionStreams m_SelectionStreams;
 std::vector<CDemuxStream*> published;
 unsigned publications{};
 std::vector<int> m_programs;
 double m_offset_pts{};
 void UpdateCorrection(DemuxPacket*,double) {}
 void UpdateContent() {published=m_SelectionStreams.streams;++publications;}
 void OpenDefaultStreams(bool) {}
 void UpdateHasVideoAudio() {}
 bool ReadPacket(DemuxPacket*& packet,CDemuxStream*& stream);
};
INSERT_METHOD
READ_METHOD
int main() {
 {
   CDVDDemuxFFmpeg ordinary;
   ordinary.m_blurayDovi=false;
   ordinary.AddStream(0,newStream());
   assert(ordinary.GetStream(7,0)->source==STREAM_SOURCE_DEMUX &&
       "unrelated streams must retain the existing source marker");
 }
 {
   CVideoPlayer eager;
   eager.m_pDemuxer->AddStream(0,newStream());
   eager.m_SelectionStreams.Update(nullptr,eager.m_pDemuxer.get());
   eager.UpdateContent();
   DemuxPacket* packet=nullptr; CDemuxStream* stream=nullptr;
   assert(eager.ReadPacket(packet,stream));
   assert(eager.published.size()==1 && eager.publications==1);
   assert(stream->source==STREAM_SOURCE_DEMUX);
   delete packet;
   // Replacing an existing id is not discovery of a new selectable stream.
   auto* replacement=newStream();
   eager.m_pDemuxer->AddStream(0,replacement);
   assert(replacement->changes==1);
   assert(replacement->source==STREAM_SOURCE_DEMUX);
   assert(eager.ReadPacket(packet,stream) && stream==replacement);
   assert(eager.publications==1);
   delete packet;
 }
 CVideoPlayer player;
 // DT/DL normalization may leave the joined BL without extradata initially.
 // The existing AddStream gate defers it, so the initial public list is empty.
 player.m_pDemuxer->late=true;
 player.m_SelectionStreams.Update(nullptr,player.m_pDemuxer.get());
 player.UpdateContent();
 assert(player.published.empty());
 DemuxPacket* packet=nullptr; CDemuxStream* stream=nullptr;
 assert(player.ReadPacket(packet,stream));
 assert(stream && stream->uniqueId==0); // Decoder can play this late BL.
 assert(player.published.size()==1 && "late joined BL must reach native videostreams");
 assert(player.published[0]==stream);
 assert(stream->source==STREAM_SOURCE_DEMUX);
 assert(player.publications==2); // Initial empty list, then discovered BL.
 delete packet;
 assert(player.ReadPacket(packet,stream));
 assert(player.publications==2 && "discovery marker must not cause a refresh loop");
 delete packet;
}
'''.replace('SOURCE_ASSIGNMENT', source_assignment).replace(
            'INSERT_METHOD', insert + body(demux, insert)).replace(
            'READ_METHOD', read + body(player, read))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'),
                                    '-o', str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()

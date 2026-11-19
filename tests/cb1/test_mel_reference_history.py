"""A verified MEL picture can start the disc without giving up later FEL references."""

from pathlib import Path
import unittest

from test_native_video_source import body
import test_audio_information_wiring as wiring


class MelReferenceHistory(unittest.TestCase):
    run_cpp = wiring.AudioInformationWiring.run_cpp

    def test_exact_mel_picture_preserves_the_current_gop_for_a_later_residual(self):
        source = (Path(__file__).resolve().parents[2] / "CB1/src/dvbridge_fel.c").read_text()
        program = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
constexpr int64_t AV_NOPTS_VALUE=INT64_MIN;
constexpr unsigned QUEUE_MAX=32;
constexpr int AV_LOG_ERROR=0,AV_LOG_DEBUG=1;
template<class... T> void av_log(T...){}
struct AVPacket {const uint8_t* data;int size;};
struct AVFrame {int64_t pts{},best_effort_timestamp{};};
struct AVCodecParameters {const uint8_t* extradata{};int extradata_size{};};
struct AVBSFContext {AVCodecParameters* par_out;};
void av_packet_free(AVPacket** p){delete *p;*p=nullptr;}
constexpr uint8_t idr[]={0,0,1,64,1,7,0,0,1,66,1,7,0,0,1,68,1,7,0,0,1,40,1,7};
constexpr uint8_t bareIdr[]={0,0,1,40,1,7};
constexpr uint8_t inter[]={0,0,1,2,1,7};
struct dvbridge_fel {
 struct Entry {int64_t order,pts;bool presentable;}times[8]{};
 unsigned num_times{},num_packets{};
 size_t packet_bytes{};
 AVPacket* packets[8]{};
 int64_t packet_order[8]{}, source_taken=AV_NOPTS_VALUE, output_order=AV_NOPTS_VALUE;
 bool packet_key[8]{},source_no_rasl=false,synchronizing=false,failed=false;
 bool el_started=false,mel_deferred=false,eof=false,recovering=false;
 int64_t anchor_pts=1,wanted=AV_NOPTS_VALUE;
 void* decoder=nullptr;
 AVBSFContext* split=nullptr;
};
int vcl_type(const AVPacket* packet,const AVCodecParameters* parameters) VCL
bool self_contained_idr(const AVPacket* packet) IDR
void prune_mel_history(dvbridge_fel* f) PRUNE
bool pump(dvbridge_fel* f) {
 assert(f->packets[0] && f->packet_order[0]==4 && f->packet_order[1]==5);
 f->el_started=true; f->wanted=5;return true;
}
int take_ready(dvbridge_fel* f,int64_t pts, AVFrame** frame) {
 if (f->wanted!=pts) return 0;
 *frame=new AVFrame{};return 1;
}
int take_source(dvbridge_fel* f,int64_t pts,AVFrame** frame,bool no_residual) TAKE
template <size_t N> void append(dvbridge_fel& f,int64_t pts,const uint8_t(&data)[N],bool key) {
 f.times[f.num_times++]={pts,pts*1000,true};
 const auto i=f.num_packets++;
 f.packets[i]=new AVPacket{data,static_cast<int>(N)};
 f.packet_order[i]=pts;f.packet_key[i]=key;f.packet_bytes+=N;
}
int main() {
 AVCodecParameters annexB;
 AVBSFContext split{&annexB};
 dvbridge_fel f; AVFrame* frame=nullptr;
 f.split=&split;
 append(f,1,idr,true);append(f,2,inter,false);append(f,3,bareIdr,true);
 append(f,4,idr,true);append(f,5,inter,false);
 assert(take_source(&f,1000,&frame,true)==3 && !frame && !f.el_started);
 assert(take_source(&f,2000,&frame,true)==3 && f.packet_order[0]==1);
 assert(take_source(&f,3000,&frame,true)==3 && f.packet_order[0]==1);
 assert(take_source(&f,4000,&frame,true)==3 && f.packet_order[0]==4 &&
        f.num_packets==2 && f.packet_bytes==sizeof(idr)+sizeof(inter));
 assert(take_source(&f,5000,&frame,false)==1 && frame->pts==5000 && f.el_started);
 delete frame;
 for (unsigned i=0;i<f.num_packets;++i) av_packet_free(&f.packets[i]);
 // Unmatched metadata cannot cause a decoded picture to be substituted.
 frame=nullptr;
 assert(take_source(&f,8000,&frame,true)==-1 && !frame);
}
'''
        for token, signature in (
            (" VCL", "static int vcl_type("),
            (" IDR", "static bool self_contained_idr("),
            (" PRUNE", "static void prune_mel_history("),
            (" TAKE", "static int take_source("),
        ):
            program = program.replace(token, " " + body(source, signature))
        self.run_cpp(program)

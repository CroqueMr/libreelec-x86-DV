"""Native decode/pairing startup facts must log once without changing output."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class DecodeStartupDiagnostics(unittest.TestCase):
    def test_native_events_keep_exact_pairing_and_do_not_log_every_frame(self):
        source = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        signature = 'void CDVDVideoCodecFFmpeg::ReportDVStartup('
        self.assertTrue(signature in source, 'Once-only decoder startup diagnostic owner missing')
        report = body(source, signature)
        picture = body(source, 'CDVDVideoCodec::VCReturn CDVDVideoCodecFFmpeg::GetPicture(')
        begin = source.index('  // Submit once, only after BL accepted the packet')
        submitted = source[begin:source.index('\n#endif', begin)]
        program = r'''
#include <cassert>
#include <cstdint>
#include <deque>
#include <memory>
#include <string>
#include <vector>
#define HAVE_DVBRIDGE 1
constexpr int LOGINFO=1,LOGWARNING=2,DVD_CODEC_CTRL_DRAIN=128;
constexpr int64_t AV_NOPTS_VALUE=INT64_MIN;
struct CLog{template<class...T>static void Log(T...) {}};
namespace DVBRIDGE{
 std::vector<std::string> events;bool enabled=true;
 bool DiagnosticsEnabled(){return enabled;}
 void DiagnosticStartup(uint64_t,const char* stage,bool,size_t){events.emplace_back(stage);}
}
struct AVFrame{int pixels=123;};
void av_frame_free(AVFrame** p){delete *p;*p=nullptr;}
struct AVBufferRef{unsigned char* data{};};
struct AVHWFramesContext{void* device_ref{};};
struct AVCodecContext{AVBufferRef* hw_frames_ctx{};};
struct AVPacket{};
struct Fel{bool ready=false,failed=false,submit=true;int takes=0;};
bool dvbridge_fel_submit(Fel* f,AVPacket*){return f->submit;}
bool dvbridge_fel_failed(Fel* f){return f->failed;}
bool dvbridge_fel_exhausted(Fel*){return false;}
bool dvbridge_fel_device(Fel*,void*){return true;}
bool dvbridge_fel_drain(Fel*){return true;}
int dvbridge_fel_take(Fel* f,int64_t pts,AVFrame** frame){
 if(!f->ready)return 0;assert(pts>=1);++f->takes;*frame=new AVFrame;return 1;
}
struct VideoPicture{
 int64_t doviSourcePts=AV_NOPTS_VALUE;int pixels=123;
 std::shared_ptr<AVFrame> doviEnhancement;int doviEnhancementBinding{};
 struct Metadata{int Binding()const{return 17;}}doviMetadata;
 void Reset(){*this={};}void CopyRef(const VideoPicture& p){*this=p;}
};
struct CDVDVideoCodec{enum VCReturn{VC_NONE,VC_ERROR,VC_BUFFER,VC_EOF,VC_PICTURE};};
struct CDVDVideoCodecFFmpeg:CDVDVideoCodec{
 std::shared_ptr<Fel> m_dvFel;std::deque<std::shared_ptr<VideoPicture>>m_dvPending;
 unsigned m_dvStartupReported{};uint64_t m_dvDiagnosticGeneration=1;
 bool m_dvFailed=false,m_dvNativeOutput=true;
 int m_codecControlFlags{},baseDecoded{};AVCodecContext context;AVCodecContext* m_pCodecContext=&context;
 static constexpr unsigned DVEnhancementPendingPictures=16;
 void ReportDVStartup(unsigned fact,const char* stage)noexcept @REPORT@
 VCReturn GetBasePicture(VideoPicture* p){p->doviSourcePts=++baseDecoded;p->pixels=123;return VC_PICTURE;}
 VCReturn GetPicture(VideoPicture* pVideoPicture)@PICTURE@
 void Submitted(int ret){AVPacket packet;auto* avpkt=&packet;@SUBMITTED@}
};
int main(){
 using namespace DVBRIDGE;
 CDVDVideoCodecFFmpeg c;c.m_dvFel=std::make_shared<Fel>();
 c.Submitted(-11);assert(events.empty());
 c.Submitted(0);c.Submitted(0);assert(events==std::vector<std::string>{"el-submitted"});
 VideoPicture output;
 assert(c.GetPicture(&output)==CDVDVideoCodec::VC_BUFFER && c.m_dvPending.size()==1);
 assert(events.back()=="base-decoded");
 c.m_dvFel->ready=true;
 assert(c.GetPicture(&output)==CDVDVideoCodec::VC_PICTURE && c.m_dvPending.empty());
 assert(output.doviSourcePts==1 && output.pixels==123 && output.doviEnhancement->pixels==123);
 assert(output.doviEnhancementBinding==17);
 assert((events==std::vector<std::string>{"el-submitted","base-decoded","el-decoded","fel-paired"}));
 for(int n=0;n<1000;++n){c.Submitted(0);assert(c.GetPicture(&output)==CDVDVideoCodec::VC_PICTURE);}
 assert(events.size()==4 && c.m_dvFel->takes==1001 && c.baseDecoded==1001);
 CDVDVideoCodecFFmpeg next;assert(next.GetPicture(&output)==CDVDVideoCodec::VC_PICTURE);
 assert(events.size()==5 && events.back()=="base-decoded");
 CDVDVideoCodecFFmpeg vanilla;vanilla.m_dvNativeOutput=false;
 assert(vanilla.GetPicture(&output)==CDVDVideoCodec::VC_PICTURE && events.size()==5);
 enabled=false;CDVDVideoCodecFFmpeg disabled;disabled.GetPicture(&output);assert(events.size()==5);
 enabled=true;c.m_dvFel->submit=false;c.Submitted(0);assert(c.m_dvFailed && events.size()==5);
}
'''.replace('@REPORT@', report).replace('@PICTURE@', picture).replace('@SUBMITTED@', submitted)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(root/'check.cpp'), '-o', str(root/'check')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root/'check')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)

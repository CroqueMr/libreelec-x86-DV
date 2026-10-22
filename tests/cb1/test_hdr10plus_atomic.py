"""Test dynamic metadata ownership at the real atomic-request boundary."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class HDR10PlusAtomicTests(unittest.TestCase):
    def test_import_failure_does_not_leak_metadata_to_next_circuit(self):
        source=(TREE/'xbmc/windowing/gbm/drm/DRMAtomic.cpp').read_text()
        flip=body(source,'void CDRMAtomic::FlipPage(')
        destroy=body(source,'void CDRMAtomic::DestroyDrm(')
        program=r'''
#include <cassert>
#include <array>
#include <optional>
#include <cstdint>
constexpr int LOGERROR=1,LOGDEBUG=2,DRM_MODE_ATOMIC_NONBLOCK=4,DRM_MODE_ATOMIC_ALLOW_MODESET=8;
struct CLog {template<class... A>static void LogF(A...) {}};
struct gbm_bo{};struct drm_fb{int fb_id=42;};
struct CDRMUtils {static drm_fb* DrmFbGetFromBo(gbm_bo*){return nullptr;}static void DestroyDrm(){}};
struct CDRMAtomic {
 bool m_lastPageAccepted=true,m_need_modeset=false,m_hdr10plusActive=true;
 uint64_t m_hdr10plusGeneration=3,m_hdr10plusRejectedGeneration=3,m_hdr10plusRejectedEdid=1;
 std::optional<std::array<uint8_t,31>> m_hdr10plusPacket=std::array<uint8_t,31>{};
 void ResetCB1PresentationTime(){};
 bool DrmAtomicCommit(int,int,bool,bool){assert(false);return false;}
 void FlipPage(gbm_bo* bo,bool rendered,bool videoLayer,bool async) FLIP
 void DestroyDrm() DESTROY
};
int main(){
 CDRMAtomic d;gbm_bo bo;d.FlipPage(&bo,true,false,false);
 assert(!d.m_lastPageAccepted && !d.m_hdr10plusPacket);
 d.m_hdr10plusPacket=std::array<uint8_t,31>{};d.DestroyDrm();
 assert(!d.m_hdr10plusPacket && !d.m_hdr10plusActive);
 assert(!d.m_hdr10plusGeneration && !d.m_hdr10plusRejectedGeneration && !d.m_hdr10plusRejectedEdid);
}
'''.replace('FLIP',flip).replace('DESTROY',destroy)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);code=root/'check.cpp';binary=root/'check'
            code.write_text(program)
            built=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_packet_lifetime_rejected_stream_and_explicit_clear(self):
        source=(TREE/'xbmc/windowing/gbm/drm/DRMAtomic.cpp').read_text()
        signatures=(
            'void CDRMAtomic::StageHDR10Plus(',
            'bool CDRMAtomic::PrepareHDR10Plus(',
            'bool CDRMAtomic::RemoveRejectedHDR10Plus(',
            'int CDRMAtomic::TestAtomicFrame(')
        functions=[]
        for signature in signatures:
            if signature not in source:
                functions.append('')
                continue
            start=source.index(signature);brace=source.index('{',start)
            functions.append(source[start:brace]+body(source,signature))
        program=r'''
#include <cassert>
#include <array>
#include <cstdint>
#include <optional>
#include <utility>
constexpr int DRM_MODE_ATOMIC_ALLOW_MODESET=4,DRM_MODE_ATOMIC_TEST_ONLY=8,LOGWARNING=1;
struct CLog {template<class... A>static void Log(A...) {}};
struct Connector {
 bool supported=true;
 bool SupportsProperty(const char*)const{return supported;}
 std::optional<uint64_t> GetPropertyValue(const char*)const{return 3;}
};
struct CDRMPropertyBlob {
 static inline unsigned alive=0,next=7;
 unsigned id{};
 CDRMPropertyBlob()=default;
 CDRMPropertyBlob(int,const void*,size_t){id=next++;++alive;}
 CDRMPropertyBlob(const CDRMPropertyBlob&)=delete;
 CDRMPropertyBlob& operator=(CDRMPropertyBlob&& o){Reset();id=std::exchange(o.id,0);return *this;}
 ~CDRMPropertyBlob(){Reset();}
 void Reset(){if(id)--alive;id=0;}
 bool IsValid()const{return id!=0;} unsigned Get()const{return id;}
};
struct Request {CDRMPropertyBlob hdr10plusBlob;std::optional<bool> hdr10plus;
 unsigned framebuffer=42,packetId{};Request* Get(){return this;}};
unsigned calls{};bool rejectPacket=false,rejectAll=false;
Request* tested{};
int drmModeAtomicCommit(int,Request* req,int flags,void*) {
 assert(flags&DRM_MODE_ATOMIC_TEST_ONLY);++calls;
 assert(!tested || tested==req);tested=req;assert(req->framebuffer==42);
 assert(!req->packetId || CDRMPropertyBlob::alive);
 return rejectAll || (rejectPacket && req->packetId) ? -1 : 0;
}
struct CDRMAtomic {
 Connector connector,*m_connector=&connector;int m_fd=1;Request request,*m_req=&request;
 bool m_hdr10plusActive=false;
 uint64_t m_hdr10plusGeneration{},m_hdr10plusRejectedGeneration{},m_hdr10plusRejectedEdid{};
 std::optional<std::array<uint8_t,31>> m_hdr10plusPacket;
 unsigned queued=0;bool accept=true;
 bool AddProperty(Connector*,const char*,uint64_t id){queued=id;request.packetId=id;return accept;}
 void StageHDR10Plus(std::optional<std::array<uint8_t,31>>,uint64_t);
 bool PrepareHDR10Plus(int&,bool&);
 bool RemoveRejectedHDR10Plus(int&);
 int TestAtomicFrame(int&,bool);
};
FUNCTIONS
int main(){
 CDRMAtomic d;std::array<uint8_t,31> p{};p[0]=0x81;int flags=0;bool bound=false;
 d.StageHDR10Plus(p,9);assert(d.PrepareHDR10Plus(flags,bound));
 assert(bound && (flags&4) && d.queued==7 && CDRMPropertyBlob::alive==1);
 assert(!d.m_hdr10plusPacket && d.request.hdr10plus==true);
 rejectPacket=true;assert(d.TestAtomicFrame(flags,bound)==0 && calls==2);
 assert(d.queued==0 && d.request.hdr10plus==false && CDRMPropertyBlob::alive==0);
 d.StageHDR10Plus(p,9);flags=0;bound=true;assert(d.PrepareHDR10Plus(flags,bound));
 assert(!bound && !d.m_hdr10plusPacket);
 d.StageHDR10Plus(p,10);assert(d.PrepareHDR10Plus(flags,bound));assert(bound && d.queued==8);
 rejectPacket=false;assert(d.TestAtomicFrame(flags,bound)==0 && calls==3);
 rejectAll=true;assert(d.TestAtomicFrame(flags,bound)<0 && calls==5);rejectAll=false;
 d.m_hdr10plusActive=true;d.request.hdr10plusBlob.Reset();
 d.StageHDR10Plus(std::nullopt,10);flags=0;assert(d.PrepareHDR10Plus(flags,bound));
 assert(bound && d.queued==0 && (flags&4));
 d.m_hdr10plusActive=false;d.connector.supported=false;d.StageHDR10Plus(p,11);
 bound=true;assert(d.PrepareHDR10Plus(flags,bound));assert(!bound);
}
'''
        stubs=[
                'void CDRMAtomic::StageHDR10Plus(std::optional<std::array<uint8_t,31>>,uint64_t){}',
                'bool CDRMAtomic::PrepareHDR10Plus(int&,bool&){return true;}',
                'bool CDRMAtomic::RemoveRejectedHDR10Plus(int&){return false;}',
                'int CDRMAtomic::TestAtomicFrame(int&,bool){return 0;}']
        functions=[function or stub for function,stub in zip(functions,stubs)]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);code=root/'check.cpp';binary=root/'check'
            code.write_text(program.replace('FUNCTIONS','\n'.join(functions)))
            built=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__':
    unittest.main()

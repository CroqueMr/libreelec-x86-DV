"""A failed video-start EDID read cannot erase the last usable display."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class DisplayRefreshTests(unittest.TestCase):
    def test_live_edid_lookup_does_not_force_another_hardware_probe(self):
        source=(TREE/'xbmc/windowing/gbm/drm/DRMConnector.cpp').read_text()
        method=body(source,'std::vector<uint8_t> CDRMConnector::GetEDID(')
        program=r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>
constexpr int LOGDEBUG=0;
struct CLog {template<class... T> static void LogF(T&&...) {}};
struct drmModeConnector {uint32_t connector_id=7;int count_props=2;
 uint32_t props[2]={19,42};uint64_t prop_values[2]={0,22};};
struct Blob {uint32_t length;void* data;};using drmModePropertyBlobPtr=Blob*;
static unsigned probes,queries,freed_connectors,freed_blobs;
static bool kernel_dv=true,query_fails,blob_fails;
static uint32_t blob_length=2;static bool null_data;
static uint8_t old_data[]={1,2},new_data[]={3,4};
static drmModeConnector live;
static Blob blob;
static drmModeConnector* drmModeGetConnector(int,uint32_t){
 ++probes;kernel_dv=false;live.prop_values[1]=0;return &live;
}
static drmModeConnector* drmModeGetConnectorCurrent(int,uint32_t){
 ++queries;return query_fails?nullptr:&live;
}
static void drmModeFreeConnector(drmModeConnector*){++freed_connectors;}
static Blob* drmModeGetPropertyBlob(int,uint64_t id){
 if(blob_fails)return nullptr;
 blob={blob_length,null_data?nullptr:id==11?old_data:new_data};return &blob;
}
static void drmModeFreePropertyBlob(Blob*){++freed_blobs;}
struct CDRMConnector {
 int m_fd=5;std::unique_ptr<drmModeConnector> m_connector=std::make_unique<drmModeConnector>();
 std::optional<uint64_t> GetPropertyValue(const char*) const{return 11;}
 uint32_t GetPropertyId(const char*) const{return 42;}
 std::vector<uint8_t> GetEDID(bool refresh=false)const METHOD
};
int main(){
 CDRMConnector c;
 assert((c.GetEDID()==std::vector<uint8_t>{1,2}));
 assert(!probes && !queries && freed_blobs==1);
 assert((c.GetEDID(true)==std::vector<uint8_t>{3,4}));
 assert(!probes && queries==1 && kernel_dv);
 assert(freed_connectors==1 && freed_blobs==2);
 live.prop_values[1]=0;assert(c.GetEDID(true).empty());
 assert(!probes && freed_connectors==2 && freed_blobs==2);
 live.count_props=0;live.prop_values[1]=22;assert(c.GetEDID(true).empty());
 assert(freed_connectors==3 && freed_blobs==2);
 query_fails=true;assert(c.GetEDID(true).empty());
 assert(freed_connectors==3 && freed_blobs==2);
 query_fails=false;live.count_props=2;blob_fails=true;assert(c.GetEDID(true).empty());
 assert(freed_connectors==4 && freed_blobs==2 && !probes && kernel_dv);
 blob_fails=false;null_data=true;assert(c.GetEDID(true).empty());
 null_data=false;blob_length=0;assert(c.GetEDID(true).empty());
 blob_length=32769;assert(c.GetEDID(true).empty());
 assert(freed_connectors==7 && freed_blobs==5 && !probes && kernel_dv);
 assert(c.m_connector->connector_id==7); // Native connector/mode ownership is untouched.
}
'''.replace('METHOD',method)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined','-no-pie',
                str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_actual_refresh_preserves_valid_information(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text()
        self.assertIn('bool CWinSystemGbm::RefreshDisplayInfoForVideo()', source,
                      'video-start display refresh is missing')
        method = body(source, 'bool CWinSystemGbm::RefreshDisplayInfoForVideo()')
        program = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <mutex>
#include <vector>
constexpr int LOGINFO=0;
namespace DVBRIDGE {
template<class... T> void DiagnosticLog(T&&...) {}
struct LldvDisplay {};
LldvDisplay ReadLldvDisplay(const uint8_t*,size_t) {return {};}
}
namespace UTILS {struct CDisplayInfo {
 int value;
 static std::unique_ptr<CDisplayInfo> Create(const std::vector<uint8_t>& bytes) {
  return bytes.empty() || bytes[0]==255 ? nullptr : std::make_unique<CDisplayInfo>(bytes[0]);
 }
};}
struct Connector {
 std::vector<uint8_t> next; int reads{};
 std::vector<uint8_t> GetEDID(bool refresh) {assert(refresh); ++reads; return next;}
 unsigned GetId() const {return 7;}
 unsigned id=7;
 unsigned* GetConnectorId() {return &id;}
 bool IsConnected() const {return true;}
};
struct DRM {Connector connector; Connector* GetConnector() {return &connector;}};
struct CWinSystemGbm {
 std::unique_ptr<DRM> m_DRM=std::make_unique<DRM>();
 std::unique_ptr<UTILS::CDisplayInfo> m_info=std::make_unique<UTILS::CDisplayInfo>(1);
 std::vector<uint8_t> m_displayEdid{1};
 std::mutex m_lldvEdidMutex;
 std::vector<uint8_t> m_lldvEdid;
 DVBRIDGE::LldvDisplay m_lldvDisplay;
 uint32_t m_lldvEdidConnector{};
 uint64_t m_lldvEdidGeneration{};
 bool RefreshDisplayInfoForVideo() METHOD
};
int main() {
 CWinSystemGbm window;
 auto* original=window.m_info.get();
 assert(window.RefreshDisplayInfoForVideo() && window.m_info.get()==original);
 window.m_DRM->connector.next={255};
 assert(window.RefreshDisplayInfoForVideo() && window.m_info.get()==original);
 window.m_DRM->connector.next={1};
 assert(window.RefreshDisplayInfoForVideo() && window.m_info.get()==original);
 assert(!window.RefreshDisplayInfoForVideo());
 window.m_DRM->connector.next={2};
 assert(window.RefreshDisplayInfoForVideo() && window.m_info->value==2);
 assert(window.m_displayEdid==std::vector<uint8_t>{2});
 window.m_DRM.reset();
 assert(window.RefreshDisplayInfoForVideo() && window.m_info->value==2);
 assert(window.m_lldvEdid.empty() && window.m_lldvEdidGeneration==5);
}
'''.replace('METHOD', method)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()

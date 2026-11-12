#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>
constexpr int LOGINFO=0,LOGWARNING=1,LOGDEBUG=2;
struct CLog {template<class... T> static void LogF(T...) {}};
constexpr const char* SETTING_VIDEOSCREEN_COLORRANGE="videoscreen.colorrange";
constexpr const char* SETTING_VIDEOSCREEN_COLORFORMAT="videoscreen.colorformat";
constexpr const char* SETTING_VIDEOSCREEN_MAXBPC="videoscreen.maxbpc";
struct CSettings {static constexpr const char* SETTING_VIDEOSCREEN_LIMITEDRANGE="legacy";};
namespace KODI::MESSAGING {struct ThreadMessageCallback {void (*callback)(void*);void* owner;};}
struct Setting {bool defaultValue=true;bool IsDefault() const {return defaultValue;}};
struct Settings {
 bool legacy=false;std::map<std::string,int> values;Setting range;
 bool GetBool(const char*) const {return legacy;}int GetInt(const char* id){return values[id];}
 std::shared_ptr<Setting> GetSetting(const char*) {return std::shared_ptr<Setting>(&range,[](auto*){});}
 void SetInt(const char* id,int value) {values[id]=value;range.defaultValue=false;}
 void SetBool(const char*,bool value) {legacy=value;}
 std::shared_ptr<Settings> GetSettings() {return std::shared_ptr<Settings>(this,[](auto*){});}
};
struct Manager {int dirties=0;Manager& GetWindowManager(){return *this;}void MarkDirty(){++dirties;}};
struct CServiceBroker {static Manager* GetGUI(){static Manager gui;return &gui;}static Settings* GetSettingsComponent() {static Settings settings;return &settings;}};
struct Blob {bool IsValid() const {return false;} int Get() const {return 0;}};
struct CDRMConnector {
 std::map<std::string,uint64_t> cache{{"Broadcast RGB",0},{"color format",0},{"max bpc",12}};
 std::map<std::string,std::map<std::string,uint64_t>> enums{
  {"Broadcast RGB",{{"Automatic",0},{"Full",1},{"Limited 16:235",2}}},
  {"color format",{{"AUTO",0},{"RGB",1},{"YUV 4:4:4",2},{"YUV 4:2:2",3},{"YUV 4:2:0",4}}}};
 std::string type="HDMI-A";int frl=0;uint32_t highestClock=594000;bool immutable=false;
 bool SupportsProperty(const char* property) const {return cache.count(property);}
 std::optional<uint64_t> GetPropertyValue(const char* property) const {
  auto it=cache.find(property);if(it==cache.end()) return {};return it->second;}
 std::optional<uint64_t> GetPropertyEnumValue(std::string_view property,std::string_view name) const {
  auto p=enums.find(std::string(property));if(p==enums.end())return {};auto it=p->second.find(std::string(name));
  if(it==p->second.end())return {};return it->second;}
 std::optional<bool> IsPropertyImmutable(const char*) const {return immutable;}
 std::optional<std::pair<uint64_t,uint64_t>> GetRangePropertyLimits(const char*) const {return {{8,12}};}
 std::string GetType() const {return type;}
 int GetMaxFrlRate() const {return frl;}
 bool HasModeAboveClock(uint32_t clock) const {return highestClock>clock;}
};
struct CDRMUtils {
 virtual ~CDRMUtils()=default;CDRMConnector connector;uint32_t clock=594000;
 bool fellBack=false;int modesets=0;
 CDRMConnector* GetConnector() {return &connector;}
 virtual bool LastCommitFellBack() const {return fellBack;}
 virtual void RequestModeset() {++modesets;}
 uint32_t GetModeClock() const {return clock;}
};
struct CDRMAtomic : CDRMUtils {
 std::map<std::string,uint64_t> pending;bool accepted=true,addSuccess=true;
 bool AddProperty(CDRMConnector*,const char* name,uint64_t value) {
  if(!addSuccess)return false;pending[name]=value;return true;}
 bool rangeTransition=false;void SetColorRangeTransition(){rangeTransition=true;}
 bool LastPageAccepted() const {return accepted;} void SetActive(bool) {}
 void Commit(bool accept,bool fallback=false) {
  accepted=accept;fellBack=fallback;
  if(accept&&!fallback)for(auto [name,value]:pending)connector.cache[name]=value;
  pending.clear();rangeTransition=false;}
};
namespace KODI::UTILS {
enum class Colorimetry {DEFAULT,SMPTE_170M_YCC,BT709_YCC,XVYCC_601,XVYCC_709,SYCC_601,OPYCC_601,OPRGB,BT2020_CYCC,BT2020_RGB,BT2020_YCC,DCI_P3_RGB_D65,DCI_P3_RGB_THEATER,BT601_YCC,ST2113_RGB,ICTCP,RGB_WIDE_FIXED,RGB_WIDE_FLOAT};
const char* ColorimetryToString(Colorimetry) {return "colorimetry";}
}
struct VideoPicture {int colorBits=10;KODI::UTILS::Colorimetry color=KODI::UTILS::Colorimetry::BT2020_YCC;};
namespace KODI::UTILS {Colorimetry GetColorimetry(const VideoPicture& picture){return picture.color;}}
template<class K,class V> std::map<K,V> make_map(std::initializer_list<std::pair<const K,V>> values) {return {values};}
// NATIVE_CONSTANTS
struct CWinSystemGbm {
 bool allowed=true;int colorSpaceApplications=0;
 std::shared_ptr<CDRMUtils> m_DRM=std::make_shared<CDRMAtomic>();Blob m_hdrBlob;
 bool ConnectorPreferencesAllowed() const {return allowed;}

 void DeferConnectorPreferences();bool UseLimitedColor();void ApplyColorspace();void SetColorimetry(const VideoPicture*);
 std::optional<uint64_t> m_queuedColorspace;
 KODI::UTILS::Colorimetry m_colorimetry=KODI::UTILS::Colorimetry::DEFAULT;
 std::optional<bool> activeRange;
 std::optional<bool> TransportLimitedColor() const {return activeRange;}
 std::map<std::string,uint64_t> restoreProperties;
 std::optional<uint64_t> RestoredConnectorProperty(const char* name) const {
  auto it=restoreProperties.find(name);if(it==restoreProperties.end())return {};return it->second;}
// NATIVE_MEMBERS
};

// NATIVE_BODIES
int main() {
 CWinSystemGbm w;auto drm=std::dynamic_pointer_cast<CDRMAtomic>(w.m_DRM);
 w.m_defaultMaxBpc=12;
 drm->connector.cache["max bpc"]=8;
 assert(w.GetEffectiveMaxBpc()==8 && w.GetEffectiveMaxBpc(12)==12);
 w.m_maxBpc=1;assert(w.GetEffectiveMaxBpc(12)==8);
 w.m_maxBpc=0;drm->connector.cache["max bpc"]=12;
 drm->connector.cache["Colorspace"]=0;
 drm->connector.enums["Colorspace"]={{"Default",0},{"BT2020_RGB",1},{"BT2020_YCC",2},{"BT709_YCC",3}};
 VideoPicture picture;
 w.m_colorFormat=3;w.ApplyConnectorProperties();w.SetColorimetry(&picture);assert(drm->pending.at("Colorspace")==2);
 w.allowed=false;w.restoreProperties["color format"]=3;
 w.SetColorimetry(&picture);assert(drm->pending.at("Colorspace")==2);
 w.restoreProperties.clear();w.SetColorimetry(&picture);assert(drm->pending.at("Colorspace")==1);
 w.allowed=true;w.m_colorFormat=0;w.ApplyConnectorProperties();w.SetColorimetry(nullptr);assert(drm->pending.at("Colorspace")==0);
 drm->pending.clear();
 w.m_colorRange=2;w.ApplyConnectorProperties();
 assert(drm->pending.at("Broadcast RGB")==2 && !w.UseLimitedColor());
 drm->Commit(true);w.UpdateDriverLimitedRange();w.RetryConnectorProperties();
 assert(!w.UseLimitedColor()); // accepted driver conversion, no second shader compression
 w.m_colorRange=1;w.ApplyConnectorProperties();drm->Commit(false,true);
 w.UpdateDriverLimitedRange();w.RetryConnectorProperties();
 assert(!w.UseLimitedColor() && !drm->pending.empty());
 drm->Commit(true);w.RetryConnectorProperties();assert(!w.UseLimitedColor());
 drm->connector.cache.erase("Broadcast RGB");drm->connector.enums.erase("Broadcast RGB");
 w.m_colorRange=2;w.ApplyConnectorProperties();drm->Commit(true);w.RetryConnectorProperties();
 assert(w.UseLimitedColor()); // missing range property requires shader conversion
 drm->connector.cache["Broadcast RGB"]=1;
 drm->connector.enums["Broadcast RGB"]={{"Automatic",0},{"Full",1},{"Limited 16:235",2}};
 w.m_colorFormat=5;w.m_contentBits=10;w.m_maxBpc=0;
 assert(w.GetRequestedColorFormat()==ColorFormat::YUV422);
 drm->connector.enums["color format"].erase("YUV 4:2:2");
 assert(w.GetRequestedColorFormat()==ColorFormat::YUV420);
 drm->connector.type="DP";assert(w.GetRequestedColorFormat()==ColorFormat::AUTO);
 drm->connector.type="HDMI-A";drm->connector.frl=3;drm->connector.highestClock=2376000;
 assert(w.GetRequestedColorFormat()==ColorFormat::AUTO);
 drm->connector.highestClock=1188000;assert(w.GetRequestedColorFormat()==ColorFormat::YUV420);
 w.m_contentBits=8;assert(w.GetRequestedColorFormat()==ColorFormat::AUTO);
 w.m_contentBits=10;w.m_maxBpc=1;assert(w.GetRequestedColorFormat()==ColorFormat::AUTO);
 w.m_maxBpc=2;drm->connector.cache.erase("color format");
 assert(w.GetRequestedColorFormat()==ColorFormat::AUTO);
 drm->connector.cache["color format"]=0;
 w.m_colorFormat=3;w.m_maxBpc=3;
 drm->connector.enums["color format"]["YUV 4:2:2"]=3;
 w.ApplyConnectorProperties();drm->Commit(false,true);w.RetryConnectorProperties();
 assert(w.m_bpcProbe && w.m_maxBpcFallback && drm->pending.at("max bpc")==12);
 drm->Commit(false,true);w.RetryConnectorProperties();
 assert(!w.m_bpcProbe && !w.m_maxBpcFallback && w.m_colorFormatSkip==1);
 assert(w.GetRequestedColorFormat()==ColorFormat::AUTO);
 drm->pending.clear();w.allowed=false;w.ApplyConnectorProperties();
 assert(drm->pending.empty() && w.m_connectorPreferencesDeferred);
 assert(!w.m_rangeRequest.queued && !w.m_formatRequest.queued && !w.m_bpcRequest.queued);
 assert(w.UseLimitedColor()); // CB1 retains legacy requested limited pixels
 w.restoreProperties={{"Broadcast RGB",2},{"color format",3}};
 assert(!w.UseLimitedColor() && w.IsYuvRequested()); // ordinary target range before its real commit
 w.restoreProperties.clear();
 w.activeRange=true;w.m_colorRange=1;assert(w.UseLimitedColor());
 w.activeRange=false;w.m_colorRange=2;assert(!w.UseLimitedColor());
 w.activeRange.reset();
 w.allowed=true;w.ApplyConnectorProperties();
 assert(!drm->pending.empty() && !w.m_connectorPreferencesDeferred);
 CWinSystemGbm::PropertyRequest request{"max bpc",true,12};
 drm->connector.cache["max bpc"]=12;drm->accepted=false;drm->fellBack=false;
 assert(w.IsRequestRejected(request)); // matching old cache is not an accepted same-mode commit
 drm->accepted=true;drm->fellBack=true;request.queued=true;assert(w.IsRequestRejected(request));
 drm->fellBack=false;request.queued=true;assert(!w.IsRequestRejected(request));
 drm->connector.immutable=true;drm->pending.clear();w.ApplyConnectorProperties();assert(!drm->pending.count("Broadcast RGB") && !drm->pending.count("color format") && !drm->pending.count("max bpc"));
 drm->connector.immutable=false;drm->addSuccess=false;w.m_rangeRequest.queued=false;
 w.ApplyBroadcastRange();assert(!w.m_rangeRequest.queued);
 // Ordinary Full -> Limited uses target-range pixels before the same real commit.
 CWinSystemGbm transition;auto td=std::dynamic_pointer_cast<CDRMAtomic>(transition.m_DRM);
 transition.m_defaultMaxBpc=12;transition.m_colorRange=2;
 transition.ApplyConnectorProperties();assert(td->rangeTransition && !transition.UseLimitedColor());
 td->Commit(false);transition.RetryConnectorProperties();assert(!transition.UseLimitedColor());
 td->Commit(false);transition.RetryConnectorProperties();assert(transition.UseLimitedColor());
 assert(td->connector.cache.at("Broadcast RGB")==0); // durable refusal switches only the shader
 // No Broadcast property: YUV conversion and shader compression are still exclusive.
 CWinSystemGbm yuv;auto yd=std::dynamic_pointer_cast<CDRMAtomic>(yuv.m_DRM);
 yd->connector.cache.erase("Broadcast RGB");yd->connector.enums.erase("Broadcast RGB");
 yuv.m_colorRange=2;yuv.m_colorFormat=3;yuv.ApplyConnectorProperties();
 assert(!yuv.UseLimitedColor() && yd->rangeTransition);
 yd->Commit(false);yuv.RetryConnectorProperties();assert(yuv.GetRequestedColorFormat()==ColorFormat::AUTO);
 assert(yuv.UseLimitedColor());
 yd->Commit(true);yuv.RetryConnectorProperties();assert(yuv.UseLimitedColor());
 // Replay is staged by the first query, before any pixels are drawn, once only.
 yuv.allowed=false;CServiceBroker::GetSettingsComponent()->values[SETTING_VIDEOSCREEN_COLORFORMAT]=3;CWinSystemGbm::ApplyColorFormatSetting(&yuv);yuv.allowed=true;
 yd->pending.clear();assert(!yuv.UseLimitedColor() && yd->pending.at("color format")==3);
 auto modesets=yd->modesets;yuv.UseLimitedColor();assert(yd->modesets==modesets);
 // A refused Auto request leaves accepted YUV authoritative for subsequent tags.
 yuv.m_colorFormat=0;yd->connector.cache["color format"]=3;yuv.m_formatRequest.queued=false;
 yuv.m_colorimetry=KODI::UTILS::Colorimetry::BT2020_YCC;
 yd->connector.cache["Colorspace"]=0;yd->connector.enums["Colorspace"]={{"Default",0},{"BT2020_RGB",1},{"BT2020_YCC",2}};
 yuv.ApplyColorspace();assert(yd->pending.at("Colorspace")==2);
 // An asynchronous desired change cannot alter the shader before its main-thread callback.
 CWinSystemGbm asynchronous;asynchronous.m_colorRange=2;assert(!asynchronous.UseLimitedColor());
 auto settings=CServiceBroker::GetSettingsComponent();settings->legacy=true;
 w.MigrateLimitedRangeSetting();assert(!settings->legacy && settings->values[SETTING_VIDEOSCREEN_COLORRANGE]==2);
 settings->values[SETTING_VIDEOSCREEN_COLORRANGE]=0;w.MigrateLimitedRangeSetting();
 assert(settings->values[SETTING_VIDEOSCREEN_COLORRANGE]==0);
 settings->legacy=true;w.MigrateLimitedRangeSetting();
 assert(!settings->legacy && settings->values[SETTING_VIDEOSCREEN_COLORRANGE]==0);
}

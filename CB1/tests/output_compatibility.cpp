// SPDX-License-Identifier: MIT
#include "DVBridgeState.h"
#include "Beta5State.h"
#include "DRMAtomic.h"
#include <cassert>
#include <iostream>
#include <sstream>

using namespace KODI::WINDOWING::GBM;
template<class State> static std::string run(unsigned backend,unsigned mutation)
{
  badBlob=badClone=badPlane=badResources=false;
  plane={30,59};transportBytes.clear();calls.clear();blobs.clear();nextBlob=1000;assert(clones==0);
  CDRMAtomic drm;
  drm.connector.props["HDR_OUTPUT_METADATA"]=33;
  if(backend) {
    if(backend==1)drm.connector.props.erase("DVBRIDGE_DV_STANDARD_LAB");
    drm.connector.props["NV_HDMI_VSIF_METADATA"]=0;
    drm.connector.props["dithering mode"]=1;
  }
  drm.crtc.props={{"CTM",31},{"GAMMA_LUT",32},{"DEGAMMA_LUT",34},{"VRR_ENABLED",1},
    {"NV_CRTC_REGAMMA_TF",1},{"NV_CRTC_REGAMMA_LUT",35},
    {"NV_CRTC_REGAMMA_DIVISOR",17},{"NV_CRTC_COLOR_PASSTHROUGH",1}};
  drm.plane.props={{"rotation",4},{"alpha",33000},{"COLOR_PIPELINE",3},{"pixel blend mode",1},
    {"NV_INPUT_COLORSPACE",1},{"NV_HDR_STATIC_METADATA",36},{"NV_PLANE_LMS_CTM",37},
    {"NV_PLANE_LMS_TO_ITP_CTM",38},{"NV_PLANE_ITP_TO_LMS_CTM",39},{"NV_PLANE_BLEND_CTM",40},
    {"NV_PLANE_DEGAMMA_TF",1},{"NV_PLANE_DEGAMMA_LUT",41},
    {"NV_PLANE_DEGAMMA_MULTIPLIER",19},{"NV_PLANE_TMO_LUT",42},{"NV_PLANE_COLOR_PASSTHROUGH",1}};
  std::vector<std::pair<CDRMObject*,std::string>> fields;
  for(auto* object:{&drm.connector,&drm.crtc,&drm.plane})
    for(auto& [name,value]:object->props)fields.emplace_back(object,name);
  uint64_t own=0;
  if(mutation && mutation<=fields.size())fields[mutation-1].first->props.erase(fields[mutation-1].second);
  switch(mutation) {
    case 50:badBlob=true;break;
    case 51:badClone=true;break;
    case 52:badPlane=true;break;
    case 53:badResources=true;break;
    case 54:plane.plane_id=31;break;
    case 55:drm.connector.badEnum="Colorspace";break;
    case 56:drm.plane.badEnum="NV_INPUT_COLORSPACE";break;
    case 57:drm.connector.props["NV_HDMI_VSIF_METADATA"]=700;break;
    case 58:drm.connector.props["NV_HDMI_VSIF_METADATA"]=own=700;break;
    case 59:drm.connector.props["DVBRIDGE_DV_STANDARD_LAB"]=1;break;
    case 60:drm.connector.connectorType="DP";break;
    case 61:drm.connector.props["HDR_OUTPUT_METADATA"]=0;break;
    case 62:failAdd="max bpc";break;
    case 63:drm.connector.badEnum="Broadcast RGB";break;
    case 64:drm.crtc.badEnum="NV_CRTC_REGAMMA_TF";break;
  }
  std::ostringstream result;
  {
    State state;
    bool accepted=state.Capture(drm,own);
    result<<accepted<<':'<<state.CaptureFailure()<<':'<<int(state.CapturedBackend())<<':'<<clones;
    result<<':'<<state.Stage(drm,false);
    for(const auto& [name,value]:drm.staged)result<<'|'<<name<<'='<<value;
    drm.staged.clear();
    result<<':'<<state.Stage(drm,true);
    for(const auto& [name,value]:drm.staged)result<<'|'<<name<<'='<<value;
    CDRMAtomic foreign;result<<':'<<state.Stage(foreign,false);
    if(accepted)result<<':'<<state.Capture(drm)<<':'<<state.CaptureFailure();
    for(unsigned char byte:transportBytes)result<<':'<<unsigned(byte);
    state.Restored();assert(!state.Captured());result<<':'<<clones;
  }
  assert(clones==0);failAdd.clear();
  for(auto& call:calls)result<<'\n'<<call;
  return result.str();
}
int main()
{
  unsigned cases=0;
  for(unsigned backend=0;backend<3;backend++)for(unsigned mutation=0;mutation<=64;mutation++) {
    auto expected=run<CBeta5OutputState>(backend,mutation);
    auto actual=run<CDVBridgeState>(backend,mutation);
    if(expected!=actual) {
      std::cerr<<"Output-state mismatch backend="<<backend<<" mutation="<<mutation
               <<"\nEXPECTED\n"<<expected<<"\nACTUAL\n"<<actual<<'\n';return 1;
    }
    cases++;
  }
  std::cout<<"{\"cases\":"<<cases<<",\"exact\":true,\"hardware_test\":false}\n";
}

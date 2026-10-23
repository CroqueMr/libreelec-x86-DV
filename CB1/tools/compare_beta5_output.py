#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare output capture/restore decisions and complete DRM API traces with frozen Beta5."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/cb1'))
from test_drm_state_capture import DRM_BOUNDARY, source


def extract(patch, name):
    part = patch.split('+++ b/xbmc/windowing/gbm/drm/'+name+'\n', 1)[1]
    part = re.split(r'\n(?:diff --git |--- )', part, maxsplit=1)[0]
    return '\n'.join(line[1:] for line in part.splitlines() if line.startswith('+'))+'\n'


def boundary_code():
    text = DRM_BOUNDARY.replace('inline unsigned clones=0;', r'''
inline unsigned clones=0, nextBlob=1000;
inline std::vector<std::string> calls;
inline std::string failAdd;
inline std::map<unsigned,std::vector<unsigned char>> blobs;
inline const std::map<std::string,std::pair<std::string,uint64_t>> enums={
  {"Broadcast RGB",{"Full",2}},{"Colorspace",{"Default",5}},
  {"dithering mode",{"off",11}},{"NV_CRTC_REGAMMA_TF",{"Default",13}},
  {"NV_INPUT_COLORSPACE",{"None",17}},{"NV_PLANE_DEGAMMA_TF",{"Default",19}},
  {"pixel blend mode",{"None",23}}};
inline void releaseBlob(unsigned id) {
  if(id) {calls.push_back("destroy-blob:"+std::to_string(id));--clones;}
}
''')
    replacements = {
        'inline Blob* drmModeGetPropertyBlob(int,unsigned) {return badBlob ? nullptr : &original;}': r'''
inline Blob* drmModeGetPropertyBlob(int,unsigned id) {
  calls.push_back("get-blob:"+std::to_string(id));if(badBlob)return nullptr;
  auto& bytes=blobs[id];
  if(bytes.empty())bytes={static_cast<unsigned char>(id),static_cast<unsigned char>(id>>8),0x71,0x93};
  return new Blob{static_cast<unsigned>(bytes.size()),bytes.data()};
}''',
        'inline void drmModeFreePropertyBlob(Blob*) {}':
            'inline void drmModeFreePropertyBlob(Blob* data) {calls.push_back("free-blob-view");delete data;}',
        'inline Planes* drmModeGetPlaneResources(int) {return badResources ? nullptr : &planes;}':
            'inline Planes* drmModeGetPlaneResources(int) {calls.push_back("get-plane-resources");return badResources ? nullptr : &planes;}',
        'inline Plane* drmModeGetPlane(int,unsigned) {return badPlane ? nullptr : &plane;}':
            'inline Plane* drmModeGetPlane(int,unsigned id) {calls.push_back("get-plane:"+std::to_string(id));return badPlane ? nullptr : &plane;}',
        'inline void drmModeFreePlane(Plane*) {}':
            'inline void drmModeFreePlane(Plane*) {calls.push_back("free-plane");}',
        'inline void drmModeFreePlaneResources(Planes*) {}':
            'inline void drmModeFreePlaneResources(Planes*) {calls.push_back("free-plane-resources");}',
        'if(value) --clones;': 'releaseBlob(value);',
        'auto it=props.find(name);': 'calls.push_back(std::string("get:")+name);auto it=props.find(name);',
        'bool SupportsProperty(const char* name) const {return props.contains(name);}':
            'bool SupportsProperty(const char* name) const {calls.push_back(std::string("supports:")+name);return props.contains(name);}',
        'std::string GetType() const {return connectorType;}':
            'std::string GetType() const {calls.push_back("connector-type:"+connectorType);return connectorType;}',
        'unsigned GetId() const {return 30;}':
            'unsigned GetId() const {calls.push_back("object-id");return 30;}',
        'unsigned GetCrtcId() const {return 59;}':
            'unsigned GetCrtcId() const {calls.push_back("crtc-id");return 59;}',
        'CDRMObject* GetConnector() {return &connector;}':
            'CDRMObject* GetConnector() {calls.push_back("connector");return &connector;}',
        'CDRMObject* GetCrtc() {return &crtc;}':
            'CDRMObject* GetCrtc() {calls.push_back("crtc");return &crtc;}',
        'CDRMObject* GetGuiPlane() {return &plane;}':
            'CDRMObject* GetGuiPlane() {calls.push_back("gui-plane");return &plane;}',
        'CDRMObject* GetVideoPlane() {return nullptr;}':
            'CDRMObject* GetVideoPlane() {calls.push_back("video-plane");return nullptr;}',
        'int GetFileDescriptor() const {return 4;}':
            'int GetFileDescriptor() const {calls.push_back("descriptor");return 4;}',
        'if(!object->props.contains(name)) return false;':
            'calls.push_back(std::string("set:")+name+"="+std::to_string(value)); '
            'if(failAdd==name || !object->props.contains(name)) return false;',
    }
    for before, after in replacements.items():
        if before not in text:
            raise ValueError('DRM boundary fixture changed: '+before)
        text = text.replace(before, after)
    text, count = re.subn(r'  CDRMPropertyBlob\(int,const void\* data,unsigned length\) \{.*?\n  \}', r'''
  CDRMPropertyBlob(int,const void* data,unsigned length) {
    auto* bytes=static_cast<const unsigned char*>(data);
    std::vector<unsigned char> payload(bytes,bytes+length);
    std::string event="create-blob:"+std::to_string(length);
    for(auto byte:payload)event+=":"+std::to_string(byte);
    calls.push_back(event);
    if(badClone)return;
    value=nextBlob++;++clones;blobs[value]=payload;
    if(length==27)transportBytes=payload;
  }''', text, flags=re.S)
    if count != 1:
        raise ValueError('Expected one blob constructor')
    text, count = re.subn(r'  std::optional<uint64_t> GetPropertyEnumValue\(const char\* name,const char\*\) const \{.*?\n  \}', r'''
  std::optional<uint64_t> GetPropertyEnumValue(const char* name,const char* choice) const {
    calls.push_back(std::string("enum:")+name+":"+choice);
    auto entry=enums.find(name);
    if(badEnum==name || !props.contains(name) || entry==enums.end() || entry->second.first!=choice)return std::nullopt;
    return entry->second.second;
  }''', text, flags=re.S)
    if count != 1:
        raise ValueError('Expected one enum reader')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True, help='Frozen normal Beta5 repository')
    parser.add_argument('--negative-control', action='store_true')
    args = parser.parse_args()
    old_path = args.baseline/'projects/Generic/patches/kodi/kodi-9990-native-dv.patch'
    if hashlib.sha256(old_path.read_bytes()).hexdigest() != '5d6fd14f9f8c7b518f3950a6c71c9c543f69d854473f78c581e1ff819235f706':
        parser.error('Baseline does not match normal Beta5 integration')
    old = old_path.read_text()
    path = 'xbmc/windowing/gbm/drm/'
    files = {'DRMObject.h': boundary_code(), 'DRMAtomic.h': '#include "DRMObject.h"\n',
        'DRMConnector.h': '#include "DRMObject.h"\n',
        'DVBridgeState.h': source(path+'DVBridgeState.h'),
        'DVBridgeState.cpp': source(path+'DVBridgeState.cpp'),
        'Beta5State.h': extract(old, 'DVBridgeState.h').replace('CDVBridgeState','CBeta5OutputState'),
        'Beta5State.cpp': extract(old, 'DVBridgeState.cpp').replace('CDVBridgeState','CBeta5OutputState').replace('"DVBridgeState.h"','"Beta5State.h"')}
    if args.negative_control:
        before='GetPropertyEnumValue(name, enumName)'
        if files['DVBridgeState.cpp'].count(before) != 1:
            raise ValueError('Expected one candidate enum reader for negative control')
        files['DVBridgeState.cpp']=files['DVBridgeState.cpp'].replace(before,'GetPropertyEnumValue(name, "WRONG_ENUM")')
    with tempfile.TemporaryDirectory(prefix='cb1-output-') as temp:
        folder = Path(temp)
        for name, content in files.items():
            (folder/name).write_text(content)
        command = ['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-UNDEBUG','-I'+temp,
            str(folder/'DVBridgeState.cpp'),str(folder/'Beta5State.cpp'),str(ROOT/'CB1/tests/output_compatibility.cpp'),'-o',str(folder/'compare')]
        subprocess.run(command, check=True)
        output = subprocess.check_output([str(folder/'compare')])
    print(json.dumps(json.loads(output), indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    main()

"""The compact app selector must resolve without an installed skin's assets."""
import copy
from pathlib import Path
import re
import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / 'projects/Generic/filesystem/usr/share/kodi/media'


class QuickSwitchResources(unittest.TestCase):
    def test_app_window_has_a_closed_include_and_asset_graph(self):
        definitions = ET.parse(MEDIA / 'cb1/IncludesDVProcessInfo.xml').getroot()
        includes = {node.attrib['name']: node for node in definitions.findall('include')}
        window = ET.parse(MEDIA / 'cb1/DialogPlaybackModes.xml').getroot()

        def expand(parent):
            for node in list(parent):
                if node.tag != 'include':
                    expand(node)
                    continue
                name = node.attrib.get('content', (node.text or '').strip())
                self.assertNotIn('condition', node.attrib, 'App includes must not retain skin conditions')
                if 'file' in node.attrib:
                    self.assertEqual(node.attrib['file'], 'special://xbmc/media/cb1/IncludesDVProcessInfo.xml')
                self.assertIn(name, includes, 'QuickSwitch depends on a skin include: ' + name)
                definition = includes[name].find('definition')
                children = list(definition if definition is not None else includes[name])
                index = list(parent).index(node)
                parent.remove(node)
                for child in reversed(children):
                    parent.insert(index, copy.deepcopy(child))
            if parent.findall('include'):
                expand(parent)
            for child in list(parent):
                if child.tag != 'include':
                    # Includes inserted above may themselves contain row includes.
                    if child.findall('.//include'):
                        expand(child)

        expand(window)
        self.assertFalse(window.findall('.//include'))
        for node in window.iter():
            if node.tag in ('texture', 'texturefocus', 'texturenofocus') and node.text:
                self.assertTrue(node.text.startswith('special://xbmc/media/cb1-'), node.text)
                self.assertTrue((MEDIA / node.text.removeprefix('special://xbmc/media/')).is_file())
            if node.tag == 'font':
                self.assertTrue((node.text or '').startswith('CB1.'), node.text)
            if node.tag in ('textcolor', 'colordiffuse', 'shadowcolor'):
                # Native list-label colors use container context, not row context.
                # Per-item color therefore belongs in item-aware label markup.
                self.assertRegex(node.text or '', '^[0-9A-Fa-f]{8}$')
            if 'colordiffuse' in node.attrib:
                self.assertRegex(node.attrib['colordiffuse'], '^[0-9A-Fa-f]{8}$')
        self.assertRegex(window.findtext('depth', ''), r'^\d+(?:\.\d+)?$')
        for kind in ('itemlayout','focusedlayout'):
            label=window.find('.//'+kind+"/control[@type='label']/label")
            self.assertEqual(label.text,'[COLOR $INFO[ListItem.Property(CB1.TextColor)]]$INFO[ListItem.Label][/COLOR]')

    @unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi tree')
    def test_prepare_routing_and_clone_ownership_only(self):
        import resource
        # Resolver/services are API boundaries here, not proof of native include
        # expansion or theme rendering. Real Kodi profiles qualify those.
        from test_native_video_source import body
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        select = (tree / 'xbmc/dialogs/GUIDialogSelect.cpp').read_text()
        base = (tree / 'xbmc/guilib/GUIWindow.cpp').read_text()
        signature = 'std::unique_ptr<TiXmlElement> CGUIDialogSelect::Prepare('
        owner = body(select, signature) if signature in select else body(base, 'std::unique_ptr<TiXmlElement> CGUIWindow::Prepare(')
        code = r'''
#include <cassert>
#include <memory>
#include <string>
struct TiXmlElement { int value=7; };
struct Skin { void ResolveIncludes(TiXmlElement* p, void*) { p->value=91; } };
struct GUI { Skin skin; Skin* GetSkinInfo(){return &skin;} };
struct CServiceBroker { static GUI* GetGUI(){static GUI g;return &g;} };
struct CGUIIncludes {
 std::string file;
 void Load(const std::string& p){file=p;}
 void Resolve(TiXmlElement* p){p->value=file=="special://xbmc/media/cb1/IncludesDVProcessInfo.xml"?7:99;}
};
struct Property {bool value;bool asBoolean()const{return value;}};
struct Base {
 std::unique_ptr<TiXmlElement> Prepare(const std::unique_ptr<TiXmlElement>& p){
  if(!p)return nullptr;auto copy=std::make_unique<TiXmlElement>(*p);copy->value=91;return copy;}
};
using CGUIDialogBoxBase=Base;
struct Dialog:Base {
 bool playback=false;int m_xmlIncludeConditions=0;
 Property GetProperty(const char*)const{return {playback};}
 std::unique_ptr<TiXmlElement> Prepare(const std::unique_ptr<TiXmlElement>& rootElement) OWNER
};
int main(){
 auto root=std::make_unique<TiXmlElement>();Dialog dialog;
 for(bool playback:{false,true,true,false,true,false}){
  dialog.playback=playback;auto out=dialog.Prepare(root);
  assert(out && out.get()!=root.get() && root->value==7);
  assert(out->value==(playback?7:91));
  std::unique_ptr<TiXmlElement> empty;assert(!dialog.Prepare(empty));
 }
}
'''.replace('OWNER', owner)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'test.cpp').write_text(code)
            built = subprocess.run(['c++', '-std=c++20', '-DHAVE_DVBRIDGE', str(path / 'test.cpp'), '-o', str(path / 'test')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(path / 'test')], capture_output=True, text=True,
                                 preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            self.assertEqual(run.returncode, 0, run.stderr)

    @unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi tree')
    def test_every_item_derives_explicit_color_from_its_admission_flag(self):
        import resource
        from test_native_video_source import body
        source = (Path(os.environ['KODI_NATIVE_SOURCE_TREE']) / 'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        owner = body(body(source, 'bool CDVPlaybackModes::ShowMenu('), 'for(const auto& option : options)')
        code = r'''
#include <cassert>
#include <map>
#include <string>
#include <vector>
constexpr int LOGINFO=1;
namespace DVBRIDGE {template<class... T>void DiagnosticLog(T...) {}}
struct Value {bool flag=false;std::string text;bool asBoolean()const{return flag;}};
struct CFileItem {
 explicit CFileItem(const std::string&){}
 std::map<std::string,Value> properties;
 void SetLabel2(const std::string&){}
 void SetProperty(const std::string& n,bool v){properties[n].flag=v;}
 void SetProperty(const std::string& n,const char* v){properties[n].text=v;}
 Value GetProperty(const std::string& n)const{auto i=properties.find(n);return i==properties.end()?Value{}:i->second;}
};
struct Option {int value;std::string label,label2;std::vector<std::pair<std::string,bool>> properties;};
struct Dialog {std::vector<CFileItem> items;void Add(const CFileItem& i){items.push_back(i);}};
int main(){
 Dialog d;auto* dialog=&d;
 std::vector<Option> options{{0,"A","",{}},{1,"B","",{{"disabled",true}}},{2,"C","",{{"disabled",false}}}};
 for(const auto& option:options) OWNER
 assert(d.items.size()==3);
 assert(d.items[0].GetProperty("CB1.TextColor").text=="FFF0F0F0");
 assert(d.items[1].GetProperty("CB1.TextColor").text=="FFA0A0A0");
 assert(d.items[2].GetProperty("CB1.TextColor").text=="FFF0F0F0");
 assert(d.items[1].GetProperty("disabled").asBoolean());
}
'''.replace('OWNER', owner)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            (path/'test.cpp').write_text(code)
            built=subprocess.run(['c++','-std=c++20',str(path/'test.cpp'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(path/'test')],capture_output=True,text=True,
                               preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
            self.assertEqual(run.returncode,0,run.stderr)


if __name__ == '__main__':
    unittest.main()

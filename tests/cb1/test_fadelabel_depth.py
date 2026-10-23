"""A scrolling label must use this frame's depth after deferred GUI drawing."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from shipped_kodi import shipped_code
from test_native_video_source import body


class FadeLabelDepth(unittest.TestCase):
    def test_scrolling_label_stays_visible_when_assigned_depth_changes(self):
        source = shipped_code('xbmc/guilib/GUIFadeLabelControl.cpp')
        assign = body(source, 'void CGUIFadeLabelControl::AssignDepth()')
        render = body(source, 'void CGUIFadeLabelControl::Render()')
        program = r'''
#include <cassert>
#include <cstdint>
#include <vector>
constexpr int RENDER_ORDER_FRONT_TO_BACK=0;
constexpr unsigned XBFONT_CENTER_X=2,XBFONT_CENTER_Y=4;
struct TransformMatrix {uint32_t depth=0;float alpha=1;};
struct Context {
  TransformMatrix gui;
  std::vector<TransformMatrix> stack;
  unsigned layers=68;
  int GetRenderOrder() const {return 1;}
  void SetTransform(TransformMatrix m){stack.push_back(gui);gui=m;}
  void RemoveTransform(){gui=stack.back();stack.pop_back();}
} context;
struct Window {Context& GetGfxContext(){return context;}} window;
struct CServiceBroker {static Window* GetWinSystem(){return &window;}};
struct CGUIControl {
  TransformMatrix m_cachedTransform;
  unsigned nextDepth=0;
  void AssignDepth(){m_cachedTransform.depth=nextDepth;}
  void Render(){}
};
struct Layout {
  bool visible=false;
  float alpha=0;
  unsigned scrolling=0;
  void Draw(){visible=context.gui.depth<=context.layers;alpha=context.gui.alpha;}
  void Render(float,float,float,unsigned,unsigned,unsigned,float){Draw();}
  void RenderScrolling(float,float,float,unsigned,unsigned,unsigned,float,float){++scrolling;Draw();}
};
struct CGUIFadeLabelControl:CGUIControl {
  struct {bool font=true;float offsetX=0,angle=0;unsigned align=0,textColor=0xffffffff,shadowColor=0;} m_label;
  float m_posX=0,m_posY=0,m_width=452,m_height=38,m_scrollInfo=12;
  std::vector<int> m_infoLabels{0};
  bool m_shortText=false,m_scroll=true,m_scrollOut=false;
  unsigned m_fadeDepth=130;
  TransformMatrix m_fadeMatrix{130,.75f};
  Layout m_textLayout;
  void AssignDepth() @@ASSIGN@@
  void Render() @@RENDER@@
};
int main(){
  CGUIFadeLabelControl label;
  // A retained frame made the previous allocator range larger; the next frame is smaller.
  for(unsigned next:{64u,130u,64u,28u}){
    label.m_fadeMatrix.depth=label.m_fadeDepth; // Process caches its animated transform.
    label.nextDepth=next;context.layers=next+4;
    label.AssignDepth();
    context.gui=label.m_cachedTransform;
    label.Render();
    assert(label.m_textLayout.visible && "scrolling title was clipped by stale frame depth");
    assert(label.m_textLayout.alpha==.75f && label.m_scrollInfo==12);
    assert(context.stack.empty());
  }
  assert(label.m_textLayout.scrolling==4);
  // Short static labels still use the caller's current transform and do not scroll.
  label.m_shortText=true;context.gui={20,.5f};context.layers=24;
  label.Render();
  assert(label.m_textLayout.visible && label.m_textLayout.alpha==.5f);
  assert(label.m_textLayout.scrolling==4 && context.stack.empty());
}
'''.replace('@@ASSIGN@@', assign).replace('@@RENDER@@', render)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'check.cpp'),
                                    '-o', str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()

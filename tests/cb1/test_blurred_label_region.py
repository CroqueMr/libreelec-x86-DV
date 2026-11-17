"""Check dirty rectangles for labels that render a cached font blur."""

import unittest
from test_native_video_source import TREE, body
from test_process_info_metadata import run


class BlurredLabelRegion(unittest.TestCase):
    def test_dirty_region_covers_halo_after_moving_and_hiding(self):
        source = (TREE / 'xbmc/guilib/GUILabelControl.cpp').read_text()
        region = body(source, 'CRect CGUILabelControl::CalcRenderRegion() const')
        program = r'''
#include <cassert>
#include "utils/Geometry.h"

struct Font
{
  CPoint padding;
  CPoint GetRenderPadding() const { return padding; }
};
struct LabelInfo { Font* font; };
struct Label
{
  CRect layout;
  LabelInfo info;
  const CRect& GetRenderRect() const { return layout; }
  const LabelInfo& GetLabelInfo() const { return info; }
};
struct CGUILabelControl
{
  Label m_label;
  CRect CalcRenderRegion() const;
};

CRect CGUILabelControl::CalcRenderRegion() const REGION

int main()
{
  const CRect layout{20, 25, 40, 38};
  Font sharp{{0, 0}};
  Font blur{{2.5f, 3.5f}};
  CGUILabelControl control{{layout, {nullptr}}};
  assert(control.CalcRenderRegion() == layout);
  control.m_label.info.font = &sharp;
  assert(control.CalcRenderRegion() == layout);
  control.m_label.info.font = &blur;
  const CRect original{17.5f, 21.5f, 42.5f, 41.5f};
  const CRect halo{18.0f, 22.0f, 19.0f, 24.0f};
  assert(control.CalcRenderRegion() == original);
  auto dirty = control.CalcRenderRegion();
  assert(dirty.Intersects(halo));
  control.m_label.layout += CPoint{10, 0};
  dirty.Union(control.CalcRenderRegion());
  assert(dirty == CRect(17.5f, 21.5f, 52.5f, 41.5f));
  assert(dirty.Intersects(halo));
  assert(!control.CalcRenderRegion().Intersects(halo));
  assert(control.m_label.layout == CRect(30, 25, 50, 38));
}
'''.replace('REGION', region)
        run(self, {'test.cpp': program})

"""Check when a native Blu-ray play-item event can keep the active demuxer."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class SeamlessPlayItemTests(unittest.TestCase):
    def test_only_compatible_adjacent_seamless_items_continue(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp').read_text()
        hold = body(source, 'bool CDVDInputStreamBluray::HoldEvent()')
        signature = 'bool CDVDInputStreamBluray::CanContinuePlayItem(uint32_t next) const'
        continuation = body(source, signature) if signature in source else '{ return false; }'
        program = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <vector>
enum { HOLD_NONE, HOLD_DATA, HOLD_HELD, HOLD_STILL, HOLD_ERROR, HOLD_EXIT };
enum { BD_EVENT_NONE, BD_EVENT_SEEK, BD_EVENT_TITLE, BD_EVENT_ANGLE, BD_EVENT_PLAYLIST,
       BD_EVENT_PLAYITEM, BD_EVENT_STILL_TIME };
enum class BLURAY_CONNECTION : unsigned { SEAMLESS = 1, NONSEAMLESS = 5, BRANCHING = 6 };
struct BLURAY_STREAM_INFO {
  int pid{4113}, coding_type{36}, format{6}, rate{1}, aspect{3}, subpath_id{},
      char_code{}, dynamic_range_type{}, color_space{}, cr_flag{}, hdr_plus_flag{};
};
struct BLURAY_CLIP_INFO {
  BLURAY_STREAM_INFO *video_streams{}, *audio_streams{}, *pg_streams{};
  unsigned video_stream_count{}, audio_stream_count{}, pg_stream_count{}, dv_stream_count{};
};
struct Title { unsigned clip_count{3}; BLURAY_CLIP_INFO clips[3]; };
struct CDVDInputStreamBluray {
  Title* m_titleInfo{};
  bool m_playlistInfoValid{true}, stereo{};
  struct PlayItem { BLURAY_CONNECTION connectionCondition; };
  struct { std::vector<PlayItem> playItems; } m_playlistInfo;
  uint32_t m_playItem{0};
  int m_hold{HOLD_NONE};
  struct { int event{BD_EVENT_PLAYITEM}; uint32_t param{1}; } m_event;
  bool IsStereoscopic() const { return stereo; }
  bool CanContinuePlayItem(uint32_t next) const;
  bool HoldEvent();
};
CONTINUATION
bool CDVDInputStreamBluray::HoldEvent()
HOLD
int main() {
  using enum BLURAY_CONNECTION;
  BLURAY_STREAM_INFO before, after;
  Title title;
  title.clips[0] = {.video_streams=&before, .video_stream_count=1};
  title.clips[1] = {.video_streams=&after, .video_stream_count=1};
  auto check = [&](auto setup, bool holds) {
    CDVDInputStreamBluray player;
    player.m_titleInfo = &title;
    player.m_playlistInfo.playItems = {{SEAMLESS}, {NONSEAMLESS}, {BRANCHING}};
    setup(player);
    assert(player.HoldEvent() == holds);
  };
  check([](auto&) {}, false);
  check([](auto& p) { p.m_playlistInfo.playItems[1].connectionCondition = BRANCHING; }, false);
  check([](auto& p) { p.m_playlistInfo.playItems[1].connectionCondition = SEAMLESS; }, true);
  check([](auto& p) { p.m_event.param = 2; }, true);
  check([](auto& p) { p.m_event.param = 0; }, true);
  check([](auto& p) { p.m_event.event = BD_EVENT_SEEK; }, true);
  check([](auto& p) { p.m_event.event = BD_EVENT_ANGLE; }, true);
  check([](auto& p) { p.m_hold = HOLD_STILL; }, true);
  check([](auto& p) { p.stereo = true; }, true);
  check([](auto& p) { p.m_playlistInfoValid = false; }, true);
  check([](auto& p) { p.m_titleInfo = nullptr; }, true);
  after.pid++;
  check([](auto&) {}, true);
  after = before;
  after.dynamic_range_type++;
  check([](auto&) {}, true);
  after = before;
  title.clips[1].dv_stream_count = 1;
  check([](auto&) {}, true);
}
'''.replace('CONTINUATION', signature + continuation).replace('\nHOLD\n', hold)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'seam.cpp'
            binary = Path(directory) / 'seam'
            path.write_text(program)
            build = subprocess.run(['c++', '-std=c++20', str(path), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

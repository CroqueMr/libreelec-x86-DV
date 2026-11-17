"""Exercise both background-open decisions from the patched Kodi sources."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("KODI_NATIVE_SOURCE_TREE"), "Requires the patched Kodi source")
class BackgroundHttpPlayback(unittest.TestCase):
    def test_only_resolved_http_media_bypasses_the_foreground_path(self):
        tree = Path(os.environ["KODI_NATIVE_SOURCE_TREE"]) / "xbmc"
        play = (tree / "application/ApplicationPlay.cpp").read_text()
        messages = (tree / "application/ApplicationMessageHandling.cpp").read_text()
        file_item = (tree / "FileItem.cpp").read_text()
        predicate = re.search(r"bool CFileItem::IsBackgroundHttpPlayback\(\) const\n\{.*?^}",
                              file_item, re.S | re.M)
        resolve = play.split("bool CApplicationPlay::ResolvePath()\n{\n", 1)[1]
        resolve = resolve.split("  // Translate/Resolve the url", 1)[0]
        event = messages.split("case GUI_MSG_PLAYBACK_STARTED:", 1)[1].split(
            "// we don't want a busy dialog when switching channels", 1)[0]
        updates = re.findall(r"m_app\.SetCurrentFileItem\(.*?\);|"
                             r"const bool backgroundHttpPlayback\s*=.*?;", event, re.S)
        self.assertEqual(sum(x.startswith("m_app.SetCurrentFileItem") for x in updates), 2)
        dispatch = []
        for statement in updates:
            if "message.GetItem()" in statement:
                dispatch.append("App m_app{item};")
            elif statement.startswith("m_app.SetCurrentFileItem"):
                dispatch.append("if (playlistItem) m_app.item = *playlistItem;")
            else:
                dispatch.append(statement)
        wait = messages.split("// we don't want a busy dialog when switching channels", 1)[1]
        wait = wait[wait.index("if ("):wait.index("CGUIDialogBusy::WaitOnEvent(")]

        harness = r'''
#include <cstdio>
#include <algorithm>
#include <cctype>
#include <string>

struct Property { bool value; bool asBoolean() const { return value; } };
struct Url {
  std::string protocol, path;
  const std::string& GetProtocol() const { return protocol; }
  bool IsDiscImage() const { return path.ends_with(".iso"); }
  bool IsOpticalMediaFile() const { return path.ends_with("index.bdmv"); }
};
namespace URIUtils {
bool IsArchive(const std::string& path) { return path.ends_with(".zip"); }
}
namespace StringUtils {
void Trim(std::string& s) {
  const auto first = s.find_first_not_of(" \t");
  s = first == s.npos ? "" : s.substr(first, s.find_last_not_of(" \t") - first + 1);
}
void ToLower(std::string& s) {
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c){ return std::tolower(c); });
}
}
struct Tag { std::string path, m_strFileNameAndPath; const auto& GetPath() const { return path; } };
struct CFileItem {
  std::string path, mime;
  bool opted, folder = false;
  Tag tag{};
  bool liveTV = false;
  mutable Url url{};
  Property GetProperty(const char*) const { return {opted}; }
  const auto& GetDynPath() const { return path; }
  const auto& GetMimeType() const { return mime; }
  bool IsFolder() const { return folder; }
  bool IsLiveTV() const { return liveTV; }
  const Url& GetDynURL() const { url = {path.substr(0, path.find("://")), path}; return url; }
  bool HasVideoInfoTag() const { return !tag.path.empty(); }
  const Tag* GetVideoInfoTag() const { return &tag; }
  void SetDynPath(const std::string& value) { path = value; }
  bool IsBackgroundHttpPlayback() const;
};
PREDICATE
struct App {
  CFileItem item;
  const CFileItem& CurrentFileItem() const { return item; }
};
struct Player {
  bool playing;
  bool IsPlayingVideo() const { return playing; }
  bool IsPlayingAudio() const { return playing; }
};
bool skipsProbe(CFileItem m_item) {
RESOLVE
  return false;
}
bool skipsWait(const CFileItem& item, bool playing = true, const CFileItem* playlistItem = nullptr) {
  DISPATCH
  Player player{playing};
  auto* appPlayer = &player;
  WAIT
    return false;
  return true;
}
int main() {
  auto check = [](CFileItem item, bool expected) {
    if (skipsProbe(item) == expected && skipsWait(item) == expected)
      return 0;
    std::fprintf(stderr, "%s (property=%d, folder=%d, mime=%s): probe bypass=%d, wait bypass=%d, expected=%d\n",
                 item.path.c_str(), item.opted, item.folder, item.mime.c_str(), skipsProbe(item),
                 skipsWait(item), expected);
    return 1;
  };
  int errors = 0;
  errors += check({"https://v/movie.m3u8", "application/vnd.apple.mpegurl", true}, true);
  errors += check({"http://v/live.ts", "video/mp2t", true}, true);
  errors += check({"https://v/live", " Application/Vnd.Apple.MPEGURL ; codecs=avc1", true}, true);
  errors += check({"https://v/video", "video/mp2t; charset=binary", true}, true);
  errors += check({"https://v/manifest", "application/dash+xml", true}, true);
  errors += check({"http://v/file", "video/mp4", false}, false);
  errors += check({"https://v/unknown", "", true}, false);
  errors += check({"http://v/library/", "x-directory/normal", true, true}, false);
  errors += check({"https://v/archive.zip", "application/zip", true}, false);
  errors += check({"https://v/archive", "application/zip; version=2", true}, false);
  errors += check({"https://v/disc.iso", "application/octet-stream", true}, false);
  errors += check({"https://v/disc.iso", "video/mp2t", true}, false);
  errors += check({"https://v/index.bdmv", "video/mp2t", true}, false);
  CFileItem preview{"https://v/preview", "video/mp4", true};
  CFileItem row{"plugin://original", "", false};
  if (!skipsWait(preview, true, &row) || skipsWait(row, true, &preview)) {
    std::fprintf(stderr, "Queued playlist replaced the decision for the resolved event item\n");
    ++errors;
  }
  for (auto path : {"/videos/movie.mkv", "plugin://a/play", "stack://http://v/a , http://v/b",
                    "zip://http%3a%2f%2fv%2fa.zip/movie", "special://profile/movie"})
    errors += check({path, "video/mp4", true}, false);
  CFileItem live{"pvr://channels/tv", "video/mp2t", false};
  live.liveTV = true;
  errors += !skipsWait(live, true) || skipsWait(live, false);
  CFileItem disc{"http://v/raw", "video/mp2t", true};
  disc.tag = {"bluray://disc", "bluray://disc/BDMV/index.bdmv"};
  errors += skipsProbe(disc);
  return errors != 0;
}
'''
        self.assertIsNotNone(predicate)
        program = harness.replace("PREDICATE", predicate[0])
        program = program.replace("DISPATCH", "\n".join(dispatch))
        program = program.replace("RESOLVE", resolve).replace("WAIT", wait)
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "background"
            subprocess.run(["c++", "-std=c++20", "-x", "c++", "-", "-o", str(executable)],
                           input=program, text=True, check=True)
            subprocess.run([str(executable)], check=True)

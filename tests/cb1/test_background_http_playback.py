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
        wait = messages.split("// we don't want a busy dialog when switching channels", 1)[1]
        wait = wait[wait.index("if ("):wait.index("CGUIDialogBusy::WaitOnEvent(")]

        harness = r'''
#include <cstdio>
#include <string>

struct Property { bool value; bool asBoolean() const { return value; } };
struct Url { std::string protocol; const std::string& GetProtocol() const { return protocol; } };
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
  const Url& GetDynURL() const { url.protocol = path.substr(0, path.find("://")); return url; }
  bool HasVideoInfoTag() const { return !tag.path.empty(); }
  const Tag* GetVideoInfoTag() const { return &tag; }
  void SetDynPath(const std::string& value) { path = value; }
  bool IsBackgroundHttpPlayback() const;
};
PREDICATE
struct App {
  const CFileItem& item;
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
bool skipsWait(const CFileItem& item, bool playing = true) {
  App m_app{item};
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
  errors += check({"http://v/file", "video/mp4", false}, false);
  errors += check({"https://v/unknown", "", true}, false);
  errors += check({"http://v/library/", "x-directory/normal", true, true}, false);
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
        # The original URI helper also accepts protocols wrapped around an HTTP URL.
        if "URIUtils::IsHTTP(" in resolve:
            harness = harness.replace("bool skipsProbe", """namespace URIUtils {
bool IsHTTP(const std::string& url) {
  return url.starts_with("https://") || url.starts_with("http://") ||
         url.starts_with("stack://http://") || url.starts_with("zip://http%3a");
}
}
bool skipsProbe""")
        program = harness.replace("PREDICATE", predicate[0] if predicate else "")
        program = program.replace("RESOLVE", resolve).replace("WAIT", wait)
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "background"
            subprocess.run(["c++", "-std=c++20", "-x", "c++", "-", "-o", str(executable)],
                           input=program, text=True, check=True)
            subprocess.run([str(executable)], check=True)

"""Exercise startup monitor choice using the shipped GBM code."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Requires the patched Kodi source')
class MonitorSelection(unittest.TestCase):
    def test_default_prefers_connected_hdmi_over_internal_panel(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree / 'xbmc/windowing/gbm/drm/DRMUtils.cpp').read_text()
        method = re.search(r'bool CDRMUtils::FindConnector\(\).*?^}', source, re.S | re.M)[0]
        program = r'''
#include <algorithm>
#include <cassert>
#include <memory>
#include <string>
#include <vector>

constexpr int LOGDEBUG = 0, LOGINFO = 0;
struct CLog { template<class... T> static void LogF(T...) {} };
struct CSettings
{
  static constexpr auto SETTING_VIDEOSCREEN_MONITOR = "monitor";
  std::string name = "Default";
  std::string GetString(const char*) const { return name; }
};
struct SettingsComponent
{
  CSettings settings;
  CSettings* GetSettings() { return &settings; }
};
struct CServiceBroker
{
  static inline SettingsComponent settings;
  static SettingsComponent* GetSettingsComponent() { return &settings; }
};
struct CDRMConnector
{
  std::string name, type;
  unsigned encoder = 1;
  bool connected = true;
  bool IsConnected() const { return connected; }
  unsigned GetEncoderId() const { return encoder; }
  std::string GetName() const { return name; }
  std::string GetType() const { return type; }
};
struct CDRMUtils
{
  std::vector<std::unique_ptr<CDRMConnector>> m_connectors;
  CDRMConnector* m_connector = nullptr;
  bool FindConnector();
};

METHOD

int main()
{
  CDRMUtils drm;
  const auto add = [&](const char* name, const char* type) {
    drm.m_connectors.push_back(std::make_unique<CDRMConnector>(CDRMConnector{name, type}));
    return drm.m_connectors.back().get();
  };
  auto* panel = add("eDP-1", "eDP");
  auto* hdmi = add("HDMI-A-1", "HDMI-A");
  auto& name = CServiceBroker::settings.settings.name;
  assert(drm.FindConnector() && drm.m_connector == hdmi);
  name = "eDP-1";
  assert(drm.FindConnector() && drm.m_connector == panel);
  name = "HDMI-A-1";
  assert(drm.FindConnector() && drm.m_connector == hdmi);
  hdmi->connected = false;
  assert(drm.FindConnector() && drm.m_connector == panel);
  name = "Default";
  hdmi->connected = true;
  hdmi->encoder = 0;
  assert(drm.FindConnector() && drm.m_connector == panel);
  hdmi->encoder = 1;
  panel->type = "DP";
  assert(drm.FindConnector() && drm.m_connector == panel);
  panel->connected = hdmi->connected = false;
  assert(!drm.FindConnector());
}
'''.replace('METHOD', method)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            source_file = path / 'test.cpp'
            binary = path / 'test'
            source_file.write_text(program, encoding='utf-8')
            build = subprocess.run(['c++', '-std=c++20', str(source_file), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

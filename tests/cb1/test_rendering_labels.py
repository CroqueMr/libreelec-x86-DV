"""Resolve independent rendering controls through the fully patched Kodi catalog."""
import re
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE


class RenderingLabelsTests(unittest.TestCase):
    def test_master_safety_and_hdr10plus_resolve_independent_labels(self):
        catalog=(TREE/'addons/resource.language.en_gb/resources/strings.po').read_text()
        entries=re.findall(r'msgctxt "#(\d+)"\s+msgid "([^"\n]*)"',catalog)
        labels={}
        for key,value in entries:
            if 40800<=int(key)<41000:
                self.assertNotIn(key,labels,'Ambiguous rendering control label '+key)
                labels[key]=value
        settings=ET.parse(TREE/'system/settings/settings.xml')
        safety=settings.find(".//setting[@id='dvbridge.masterfallback']")
        self.assertIsNone(safety, 'A saved switch must never replace Master with another circuit')
        method=settings.find(".//setting[@id='dvbridge.hdr10method']")
        dynamic=next(option for option in method.findall('./constraints/options/option')
                     if option.text=='2')
        self.assertEqual(labels[dynamic.get('label')],'HDR10+ Rendering')
        panel=ET.parse(Path(__file__).resolve().parents[2]/
            'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        for node in panel.iter('param'):
            for key in re.findall(r'\$LOCALIZE\[(409\d\d)\]',node.get('value','')):
                self.assertIn(key,labels,'Unresolved Player information label '+key)

    def test_dolby_vision_playback_lists_each_rendering_without_a_hidden_submenu(self):
        catalog=(TREE/'addons/resource.language.en_gb/resources/strings.po').read_text()
        labels=dict(re.findall(r'msgctxt "#(\d+)"\s+msgid "([^"\n]*)"',catalog))
        settings=ET.parse(TREE/'system/settings/settings.xml')
        playback=settings.find(".//setting[@id='dvbridge.playback']")
        self.assertIsNotNone(playback,'Expose all DV-input modes in one native selector')
        self.assertEqual(labels[playback.get('label')],'Dolby Vision default playback')
        self.assertEqual(playback.findtext('level'),'0')
        self.assertEqual(playback.get('type'),'action')
        self.assertEqual(playback.find('control').get('format'),'action')
        source=(TREE/'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        table=re.search(r'dvChoices\[\]=(.*?);',source,re.S).group(1)
        choices=re.findall(r'\{(\d+),(\d+),(\d+)\}',table)
        self.assertEqual([labels[label] for _,_,label in choices],[
            'Dolby Vision Reference', 'Dolby Vision Master Reference',
            'Dolby Vision Adaptive HDR Mapping', 'Kodi default',
            'HDR10 Rendering', 'HDR10 Rendering Reference', 'HDR10+ Rendering', 'SDR Rendering',
            'Dolby Vision Player-Led'])
        for key in ('dvbridge.outputmode','dvbridge.hdr10method'):
            self.assertEqual(settings.find(f".//setting[@id='{key}']").findtext('visible'),'false')
        self.assertIn('setting->GetId()=="dvbridge.playback") ShowMenu(true)',source)
        # An action reuses the dialog; no shadow setting or raw-to-view callbacks.
        # Those callbacks reverse native per-setting/output lock order under RPC.
        self.assertNotIn('SyncPlaybackChoice',source)
        self.assertIn('dialog->SetUseDetails(!settingsMenu);',source,
                      'Settings use the compact native list; Quick Switch keeps details')
        registered=(TREE/'xbmc/settings/Settings.cpp').read_text()
        callback=registered[registered.index('RegisterCallback(&CDVPlaybackModes::GetInstance()'):]
        callback=callback[:callback.index('});')]
        self.assertIn('"dvbridge.playback"',callback)
        self.assertNotIn('"dvbridge.outputmode"',callback)
        self.assertNotIn('"dvbridge.hdr10method"',callback)

    def test_kodi_default_exists_for_every_input(self):
        catalog=(TREE/'addons/resource.language.en_gb/resources/strings.po').read_text()
        labels=dict(re.findall(r'msgctxt "#(\d+)"\s+msgid "([^"\n]*)"',catalog))
        for key in ('40814','40866','41014'):
            self.assertEqual(labels[key],'Kodi default')
        settings=ET.parse(TREE/'system/settings/settings.xml')
        for key,label in [('dvbridge.hdr10source','40866'),('dvbridge.hdr10plussource','41014')]:
            node=settings.find(f".//setting[@id='{key}']")
            self.assertEqual(node.find(f"constraints/options/option[@label='{label}']").text,'0')
        self.assertIn(('2','0','40814'),re.findall(r'\{(\d+),(\d+),(\d+)\}',
            (TREE/'xbmc/dialogs/DVPlaybackModes.cpp').read_text()))

    def test_source_defaults_and_conversion_copy_use_localized_labels(self):
        catalog=(TREE/'addons/resource.language.en_gb/resources/strings.po').read_text()
        labels=dict(re.findall(r'msgctxt "#(\d+)"\s+msgid "([^"\n]*)"',catalog))
        settings=ET.parse(TREE/'system/settings/settings.xml')
        for key,title in [('dvbridge.hdr10source','HDR10 default playback'),
                          ('dvbridge.hdr10plussource','HDR10+ default playback'),
                          ('dvbridge.hlgsource','HLG default playback')]:
            self.assertEqual(labels[settings.find(f".//setting[@id='{key}']").get('label')],title)
        self.assertEqual(labels['40867'],'Dolby Vision rendering (AI)')
        self.assertEqual(labels['40970'],'Dolby Vision Rendering')
        self.assertEqual(labels['40823'],'HDR10 Rendering Reference')
        self.assertEqual(labels['41133'],'HDR/DV to SDR target')
        self.assertIn('HDR10',labels['41134']);self.assertIn('Dolby Vision',labels['41134'])
        for key in ('dvbridge.optimizedgui','dvbridge.encodedactivearea'):
            self.assertIsNone(settings.find(f".//setting[@id='{key}']"))
        for key in ('dvbridge.expertpeak','dvbridge.expertblack','dvbridge.expertblackcustom',
                    'dvbridge.expertgamut','dvbridge.tvpeak','dvbridge.tvpanel','dvbridge.tvgamut',
                    'dvbridge.sdrpeak','dvbridge.sdrgamma','dvbridge.sdrblack'):
            label=labels[settings.find(f".//setting[@id='{key}']").get('label')]
            self.assertTrue(label.startswith(' - '),label)
            self.assertNotIn('Reference',label)


if __name__=='__main__':unittest.main()

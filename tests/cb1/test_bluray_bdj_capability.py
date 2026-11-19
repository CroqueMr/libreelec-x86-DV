"""Do not advertise stereo Java planes missing from the bundled BD-J runtime."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class BlurayBDJCapability(unittest.TestCase):
    def test_unsupported_bdj_stereo_is_cleared_after_automatic_profile_initialization(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp').read_text()
        opening = body(source, 'bool CDVDInputStreamBluray::Open()')
        setup = body(source, 'void CDVDInputStreamBluray::SetupPlayerSettings()')
        initial = re.search(r'bd_set_player_setting\(m_bd, BLURAY_PLAYER_SETTING_3D_CAP, [^;]+;', setup).group()
        constants = '\n'.join(re.findall(r'^constexpr uint32_t BLURAY_3D_CAPABILITIES[^;]+;', source, re.M))
        signature = 'if (!bd_set_player_setting(m_bd, BLURAY_PLAYER_SETTING_3D_CAP,'
        post = ''
        if signature in opening:
            start = opening.index(signature)
            failure = body(opening, signature)
            end = opening.index(failure, start) + len(failure)
            post = opening[start:end]
        program = r'''
#include <cassert>
#include <cstdint>
constexpr uint32_t BLURAY_PLAYER_SETTING_3D_CAP=24;
constexpr int LOGERROR=0;
CONSTANTS
struct CLog{template<class... T>static void Log(T&&...){} };
struct Player {uint32_t cap=0xffffffff,display=0,profile=0x130240,initial=0;bool accept=true;};
bool bd_set_player_setting(Player* p,uint32_t key,uint32_t value){
 assert(key==24);if(!p->accept)return false;p->cap=value;return true;
}
void setup(Player* m_bd){INITIAL m_bd->initial=m_bd->cap;}
bool afterOpen(Player* m_bd){POST return true;}
int main(){
 Player p;setup(&p);
 // psr_init_3D supplies 0xffffffff during bd_open_stream, overriding setup.
 p.cap=0xffffffff;
 assert(afterOpen(&p));
 assert((p.cap&0x20)==0 && "Bundled Java cannot supply stereoscopic BD-J planes");
 assert(p.cap==0xffffffdf && p.initial==p.cap);
 assert(p.display==0 && p.profile==0x130240);
 p.cap=0xffffffff;p.accept=false;assert(!afterOpen(&p));assert(p.cap==0xffffffff);
}
'''.replace('CONSTANTS', constants).replace('INITIAL', initial).replace('POST', post)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(opening.index('bd_get_disc_info'), opening.index(signature))
        self.assertLess(opening.index(signature), opening.index('bd_play('))


if __name__ == '__main__':
    unittest.main()

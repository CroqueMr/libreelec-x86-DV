"""Execute the pinned libbluray owners against malformed/boundary inputs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

def body(text, signature):
    start = text.index('{', text.index(signature))
    depth, end = 1, start + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


class LibblurayHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        include = os.environ.get('LIBBLURAY_TEST_INCLUDE')
        if not include:
            raise unittest.SkipTest('Matched libbluray sources required')
        cls.temporary = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temporary.name)
        cls.src = cls.folder / 'src'
        shutil.copytree(include, cls.src)
        root = Path(__file__).resolve().parents[2]
        for name in ('0003-hdmv-bc-compare.patch', '0005-pre151-hardening.patch'):
            patch = root / 'packages/multimedia/libbluray/patches' / name
            if patch.exists():
                result = subprocess.run(['patch', '-p1', '--fuzz=0', '-i', str(patch)],
                                        cwd=cls.folder, capture_output=True, text=True)
                if result.returncode:
                    raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def native(self, fixture, cases, extra=(), substitutions=None):
        program = (Path(__file__).parent / ('libbluray_' + fixture + '.c')).read_text()
        for token, value in (substitutions or {}).items():
            program = program.replace('@' + token + '@', value)
        source = self.folder / (fixture + '.c')
        source.write_text(program)
        binary = self.folder / fixture
        built = subprocess.run(['cc', '-std=c11', '-O1', '-g', '-ffunction-sections',
                                '-fdata-sections', '-fsanitize=address,undefined',
                                '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
                                '-fno-pie', '-no-pie', '-Wl,--gc-sections',
                                '-I' + str(self.src), '-I' + str(self.src / 'libbluray'), str(source),
                                *[str(self.src / p) for p in extra], '-o', str(binary)],
                               capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        for case in cases:
            with self.subTest(owner=fixture, case=case):
                ran = subprocess.run([str(binary), case], capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)

    def test_hdmv_compares_full_masks_and_bounds_shifts(self):
        vm = (self.src / 'libbluray/hdmv/hdmv_vm.c').read_text()
        self.native('vm', ['bc', 'shifts'], substitutions={
            'STEP': body(vm, 'static int _hdmv_step('),
            'ADD': body(vm, 'static inline uint32_t ADD_u32('),
            'MUL': body(vm, 'static inline uint32_t MUL_u32('),
            'RAND': body(vm, 'static inline uint32_t RAND_u32(')})

    def test_navigation_rejects_equal_count_and_uses_clip_angle(self):
        self.native('navigation', ['chapter', 'mark', 'invalid-ref', 'empty', 'angle'])

    def test_clpi_empty_invalid_refs_and_stc_lower_bound(self):
        self.native('clpi', ['stc', 'no-map', 'empty-fine', 'invalid-ref', 'first-fine'],
                    ['util/bits.c'])

    def test_truncated_pes_and_graphics(self):
        self.native('pes', ['pts', 'dts', 'valid'])
        self.native('graphics', ['lookup', 'header', 'fragment'],
                    ['util/bits.c', 'libbluray/decoders/pg_decode.c',
                     'libbluray/decoders/pes_buffer.c', 'util/refcnt.c'])

    def test_bitreader_refill_errors_and_eof(self):
        self.native('bits', ['refill', 'seek-error', 'read-error', 'wide', 'skip-error'])

    def test_partial_subpath_cleanup_and_bounded_rle_allocation(self):
        self.native('subpath', ['missing', 'allocated'])
        self.native('rle', ['cap', 'overflow', 'valid'], ['util/bits.c'])

    def test_sound_data_offset_does_not_wrap_at_four_gib(self):
        self.native('sound', ['sparse'], ['util/bits.c', 'libbluray/bdnav/bdmv_parse.c'])

    def test_java_unload_and_api_access(self):
        java = self.src / 'libbluray/bdj/java'
        source = self.folder / 'java'
        classes = self.folder / 'classes'
        # Compile complete production owners and their API dependencies. Only
        # the native application context/logger/AWT bridge are inert stand-ins.
        for package in ('org/dvb/dsmcc', 'org/dvb/event', 'org/davic/resources', 'javax/tv/xlet'):
            shutil.copytree(java / package, source / package, dirs_exist_ok=True)
        for name in ('org/havi/ui/event/HRcEvent.java', 'org/davic/net/Locator.java',
                     'javax/tv/locator/Locator.java'):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(java / name, target)
        stubs = {
            'org/videolan/Logger.java': '''package org.videolan; public class Logger {
                public static Logger getLogger(String s){return new Logger();}
                public static void unimplemented(String a,String b){}
                public static String dumpStack(){return "";}
                public void warning(String s){} public void error(String s){} public void info(String s){}
            }''',
            'org/videolan/BDJAction.java': '''package org.videolan;
                public abstract class BDJAction {protected abstract void doAction();}''',
            'org/videolan/BDJXletContext.java': '''package org.videolan; public class BDJXletContext {
                public static BDJXletContext getCurrentContext(){return null;}
                public static BDJXletContext getFocusContext(){return null;}
                public boolean isReleased(){return false;} public void putUserEvent(BDJAction a){}
            }''',
            'java/awt/BDJHelper.java': '''package java.awt; public class BDJHelper {
                public static boolean postKeyEvent(int a,int b,int c){return false;}
            }''',
        }
        for name, contents in stubs.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents)
        check = source / 'LibblurayJavaHardening.java'
        shutil.copy2(Path(__file__).parent / check.name, check)
        owners = ['org/dvb/dsmcc/DSMCCObject.java', 'org/dvb/dsmcc/NPTRate.java',
                  'org/dvb/event/EventManager.java']
        built = subprocess.run(['javac', '--release', '8', '-Xlint:-options', '-sourcepath', str(source),
                                '-d', str(classes), str(check), *[str(source / p) for p in owners]],
                               capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        for case in ('unload', 'rate', 'events'):
            with self.subTest(api=case):
                ran = subprocess.run(['java', '-ea', '-cp', str(classes), 'LibblurayJavaHardening', case],
                                     capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


if __name__ == '__main__':
    unittest.main()

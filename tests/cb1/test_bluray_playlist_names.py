"""Run the shipped Blu-ray playlist pattern through Kodi's regex backend."""
import ctypes
from ctypes.util import find_library
import re
import unittest

from test_native_video_source import TREE, body


class BlurayPlaylistNames(unittest.TestCase):
    def test_backup_sidecars_cannot_register_a_second_playlist(self):
        source = (TREE / 'xbmc/filesystem/BlurayDirectory.cpp').read_text()
        function = body(source, 'bool GetPlaylistsFromDisc(')
        pattern = re.search(r'CRegExp pl\{true, CRegExp::autoUtf8, R"\(([^\n]+)\)"\};',
                            function)[1].encode()
        pcre = ctypes.CDLL(find_library('pcre2-8'))
        pcre.pcre2_compile_8.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32,
                                       ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_size_t),
                                       ctypes.c_void_p]
        pcre.pcre2_compile_8.restype = ctypes.c_void_p
        pcre.pcre2_match_data_create_from_pattern_8.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        pcre.pcre2_match_data_create_from_pattern_8.restype = ctypes.c_void_p
        pcre.pcre2_match_8.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
                                     ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
        pcre.pcre2_match_8.restype = ctypes.c_int
        pcre.pcre2_get_ovector_pointer_8.argtypes = [ctypes.c_void_p]
        pcre.pcre2_get_ovector_pointer_8.restype = ctypes.POINTER(ctypes.c_size_t)
        pcre.pcre2_code_free_8.argtypes = [ctypes.c_void_p]
        pcre.pcre2_match_data_free_8.argtypes = [ctypes.c_void_p]

        # PCRE2_CASELESS | PCRE2_DOTALL, the options selected by CRegExp here.
        code = pcre.pcre2_compile_8(pattern, len(pattern), 0x28, ctypes.byref(ctypes.c_int()),
                                   ctypes.byref(ctypes.c_size_t()), None)
        self.assertTrue(code)
        self.addCleanup(pcre.pcre2_code_free_8, code)
        matches = pcre.pcre2_match_data_create_from_pattern_8(code, None)
        self.assertTrue(matches)
        self.addCleanup(pcre.pcre2_match_data_free_8, matches)

        for filename in (b'00888.mpls.hash', b'.00888.mpls', b'100888.mpls', b'00888_mpls',
                         b'00888.mpls\n', b'0888.mpls'):
            with self.subTest(filename=filename):
                self.assertLess(pcre.pcre2_match_8(code, filename, len(filename), 0, 0, matches,
                                                 None), 0)
        for filename in (b'00888.mpls', b'00888.MPLS'):
            self.assertEqual(pcre.pcre2_match_8(code, filename, len(filename), 0, 0, matches,
                                              None), 2)
            offsets = pcre.pcre2_get_ovector_pointer_8(matches)
            self.assertEqual(filename[offsets[2]:offsets[3]], b'00888')

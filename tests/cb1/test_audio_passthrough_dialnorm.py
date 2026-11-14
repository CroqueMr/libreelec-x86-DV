"""Check the emitted bytes from the Kodi passthrough parser."""
import binascii
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


DRIVER = r"""
#include "AEStreamInfo.h"
#include <algorithm>
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

int main(int argc, char** argv)
{
  assert(argc == 4);
  const std::string options = argv[1];
  std::ifstream file(argv[2], std::ios::binary);
  std::vector<uint8_t> data{std::istreambuf_iterator<char>(file), {}};
  const auto original = data;
  const size_t chunk = std::stoul(argv[3]);
  assert(chunk > 0);
  CAEStreamParser parser;
  const auto enabled = [&](char c) { return options.find(c) != std::string::npos; };
  parser.SetDialnorm(enabled('d'), enabled('j'), enabled('p'), enabled('t'), enabled('s'));
  parser.SetCoreOnly(enabled('c'));
  uint8_t* packet = nullptr;
  unsigned int packetSize = 0;
  for (size_t pos = 0; pos < data.size();)
  {
    const size_t consumed = parser.AddData(data.data() + pos, std::min(chunk, data.size() - pos),
                                           &packet, &packetSize);
    if (packetSize)
      std::cout.write(reinterpret_cast<const char*>(packet), packetSize);
    assert(consumed || packetSize);
    pos += consumed;
    if (packetSize && enabled('l'))
      parser.SetDialnorm(true, false, false, false, false);
  }
  delete[] packet;
  assert(data == original);
}
"""


def getbits(data, start, width):
    return (int.from_bytes(data, 'big') >> (len(data) * 8 - start - width)) & ((1 << width) - 1)


def putbits(data, start, width, value):
    for offset in range(width):
        index, bit = divmod(start + offset, 8)
        mask = 1 << (7 - bit)
        data[index] = (data[index] & ~mask) | (mask if value & (1 << (width - offset - 1)) else 0)


def crc16(data, polynomial):
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (polynomial if crc & 0x8000 else 0)) & 0xffff
    return crc


def seal_eac3(frame):
    frame[-2:] = crc16(frame[2:-2], 0x8005).to_bytes(2, 'big')
    return bytes(frame)


def eac3_header(stream_type=0, joc=False, dual=False):
    frame = bytearray(64)
    frame[:6] = bytes((0x0b, 0x77, stream_type << 6, 31, 0x30 if dual else 0x34, 16 << 3))
    putbits(frame, 45, 5, 27)
    position = 51
    if dual:
        putbits(frame, position, 5, 24)
        position += 6
    if stream_type == 1:
        position += 1  # channel map absent
    position += 2  # mixmdate and infomdate absent
    if joc:
        putbits(frame, position, 23, (1 << 22) | (1 << 16) | (1 << 8) | 16)
    return seal_eac3(frame)


def seal_truehd(frame):
    end = 34 + 2 * (frame[30] >> 4) if frame[29] & 1 else 32
    crc = crc16(frame[4:end - 4], 0x2d) ^ int.from_bytes(frame[end - 4:end - 2], 'big')
    frame[end - 2:end] = crc.to_bytes(2, 'big')
    return bytes(frame)


def truehd_major(atmos):
    frame = bytearray(64)
    frame[1] = len(frame) // 2
    frame[4:8] = bytes.fromhex('f8726fba')
    frame[11] = 0x1b
    frame[20] = 0x30
    if atmos:
        frame[21] = 0x80
        frame[29] = 1
        putbits(frame, 240, 4, 2)
        putbits(frame, 244, 5, 27)
        putbits(frame, 255, 5, 15)
    return seal_truehd(frame)


def dts_extension(mixing=False, corrupt=False):
    frame = bytearray(32)
    header_size = 22
    frame[:4] = bytes.fromhex('64582025')
    position = 40
    for width, value in (
        (2, 0), (1, 0), (8, header_size - 1), (16, len(frame) - 1),
        (1, 1), (5, 0), (1, 0), (3, 0), (3, 0), (1, 0), (1, int(mixing)),
        (16, len(frame) - header_size - 1), (9, 5), (3, 0),
        (3, 0), (5, 23), (4, 12), (8, 1), (1, 0), (3, 0), (1, 0), (1, 1),
    ):
        putbits(frame, position, width, value)
        position += width
    putbits(frame, position, 5, 15)
    frame[header_size - 2:header_size] = binascii.crc_hqx(
        frame[5:header_size - 2], 0xffff).to_bytes(2, 'big')
    if corrupt:
        frame[header_size - 1] ^= 1
    frame[header_size:header_size + 4] = bytes.fromhex('41a29547')
    return bytes(frame), position


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE') and os.environ.get('FFMPEG_TEST_PREFIX'),
                     'Requires patched Kodi and matched FFmpeg')
class PassthroughDialnorm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.root = Path(temp.name)
        cls.prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        audio = Path(os.environ['KODI_NATIVE_SOURCE_TREE']) / 'xbmc/cores/AudioEngine/Utils'
        # Keep logging out of the link while compiling the real Kodi parser.
        (cls.root / 'utils').mkdir()
        (cls.root / 'utils/log.h').write_text(
            '#include <string>\nenum { LOGINFO, LOGERROR };\n'
            'struct CLog { template<class... Args> static void Log(Args&&...) {} };\n')
        (cls.root / 'driver.cpp').write_text(DRIVER)
        cls.binary = cls.root / 'check'
        result = subprocess.run(
            ['c++', '-std=c++20', '-O1', '-g', '-fsanitize=address,undefined',
             '-fno-sanitize-recover=all', '-no-pie', '-I' + str(cls.root), '-I' + str(audio),
             '-I' + str(cls.prefix / 'include'), audio / 'AEStreamInfo.cpp',
             cls.root / 'driver.cpp', '-L' + str(cls.prefix / 'lib'), '-lavutil', '-o', cls.binary],
            capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def parse(self, data, options='', chunk=67):
        source = self.root / 'source.bin'
        source.write_bytes(data)
        result = subprocess.run([self.binary, options, source, str(chunk)], capture_output=True,
                                env=dict(os.environ, LD_LIBRARY_PATH=str(self.prefix / 'lib')),
                                timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return result.stdout

    def encode(self, codec, rate, layout, dialnorm=None):
        command = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                   f'anullsrc=r={rate}:cl={layout}', '-t', '0.15', '-strict', '-2',
                   '-c:a', codec, '-b:a', '384k']
        if dialnorm is not None:
            command += ['-dialnorm', str(dialnorm)]
        return subprocess.check_output(command + ['-f', 'dts' if codec == 'dca' else codec, '-'])

    def test_dolby_generated_samples_decode_with_strict_crc(self):
        for codec, rate in [('ac3', 32000), ('ac3', 44100), ('ac3', 48000), ('eac3', 48000)]:
            for layout, field in [('mono', 52), ('stereo', 54), ('5.1', 56)]:
                with self.subTest(codec=codec, rate=rate, layout=layout):
                    original = self.encode(codec, rate, layout, -27)
                    disabled = self.parse(original)
                    actual = self.parse(original, 'd')
                    position = field if codec == 'ac3' else 45
                    self.assertTrue(disabled and len(disabled) == len(actual))
                    self.assertEqual(disabled, original[:len(disabled)])
                    self.assertEqual(getbits(disabled, position, 5), 27)
                    self.assertEqual(getbits(actual, position, 5), 31)
                    self.assertEqual(self.parse(actual * 2, 'd')[:len(actual)], actual)
                    changed = self.root / 'changed.bin'
                    changed.write_bytes(actual)
                    result = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-err_detect',
                                             'crccheck+explode', '-f', codec, '-i', changed,
                                             '-f', 'null', '-'], capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_joc_opt_in_dual_mono_and_dependent_substream(self):
        plain = eac3_header(dual=True)
        joc = eac3_header(joc=True)
        dependent = eac3_header(stream_type=1)
        expected = bytearray(plain)
        putbits(expected, 45, 5, 31)
        putbits(expected, 51, 5, 31)
        expected = seal_eac3(expected)
        self.assertTrue(self.parse((plain + dependent) * 3, 'd').startswith(expected + dependent))
        self.assertTrue(self.parse(plain * 3, 'l').startswith(plain + expected))
        self.assertTrue(self.parse(joc * 3, 'd').startswith(joc))
        self.assertTrue(self.parse(plain * 3, 'dp').startswith(plain))
        rewritten = bytearray(joc)
        putbits(rewritten, 45, 5, 31)
        self.assertTrue(self.parse(joc * 3, 'dj').startswith(seal_eac3(rewritten)))
        corrupt = bytearray(plain)
        corrupt[-1] ^= 1
        self.assertTrue(self.parse(bytes(corrupt) * 3, 'd').startswith(corrupt))

    def test_truehd_atmos_only_with_repaired_major_crc(self):
        standard = truehd_major(False)
        atmos = truehd_major(True)
        expected = bytearray(atmos)
        putbits(expected, 244, 5, 31)
        self.assertEqual(self.parse(standard * 2, 't'), standard * 2)
        self.assertEqual(self.parse(atmos * 2), atmos * 2)
        self.assertEqual(self.parse(atmos * 2, 't'), seal_truehd(expected) * 2)
        self.assertEqual(self.parse(seal_truehd(expected) * 2, 't'), seal_truehd(expected) * 2)

    def test_dts_core_and_exss_with_crc(self):
        data = self.encode('dca', 48000, 'stereo')
        size = getbits(data, 46, 14) + 1
        core = bytearray(data[:size])
        putbits(core, 100, 4, 5)
        expected = bytearray(core)
        putbits(expected, 100, 4, 0)
        self.assertTrue(self.parse(core * 3, 's').startswith(expected))
        for mixing, corrupt in [(False, False), (True, False), (False, True)]:
            extension, field = dts_extension(mixing, corrupt)
            original = (core + extension) * 3
            chunk = len(core + extension) * 2
            changed = self.parse(original, 's', chunk=chunk)
            self.assertTrue(changed.startswith(expected))
            rewritten = changed[size:size + len(extension)]
            if mixing or corrupt:
                self.assertEqual(rewritten, extension)
            else:
                self.assertEqual(getbits(rewritten, field, 5), 0)
                self.assertEqual(binascii.crc_hqx(rewritten[5:22], 0xffff), 0)
                self.assertEqual(rewritten[22:], extension[22:])
            self.assertTrue(self.parse(original, 'sc', chunk=chunk).startswith(expected * 2))

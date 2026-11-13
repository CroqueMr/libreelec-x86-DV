"""The BD-J presentation wait yields to the decoder and player loop."""
import unittest

from test_native_video_source import TREE, body


class BdjPresentationTiming(unittest.TestCase):
    def test_end_wait_does_not_block_the_demuxer(self):
        stream = (TREE / "xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp").read_text()
        read = body(stream, "int CDVDInputStreamBluray::Read(uint8_t* buf, int buf_size)")
        retry = body(stream, "CDVDInputStream::ENextStream CDVDInputStreamBluray::NextStream()")
        self.assertIn("m_bdjWaitingForPlaylist", read)
        self.assertIn("NEXTSTREAM_RETRY", retry.split("if (m_bdjWaitingForPlaylist)", 1)[1])

    def test_player_releases_on_video_progress_and_drains_at_playlist_end(self):
        source = (TREE / "xbmc/cores/VideoPlayer/VideoPlayer.cpp").read_text()
        pump = body(source, "void CVideoPlayer::ProcessBdjPresentation(")
        self.assertIn("GetCurrentPts()", pump)
        self.assertIn("ReleaseBdjEvents", pump)
        self.assertIn("PollBdjEvents", pump)
        self.assertIn("HasData()", pump)
        self.assertIn("ReleaseBdjEnd()", pump)
        loop = body(source, "void CVideoPlayer::Process()")
        self.assertIn("WaitingForBdjPlaylist()", loop)
        self.assertIn("VIDEO_DRAIN", loop)

    def test_terminal_drain_keeps_native_startup_and_sync_active(self):
        source = (TREE / "xbmc/cores/VideoPlayer/VideoPlayer.cpp").read_text()
        loop = body(source, "void CVideoPlayer::Process()")
        self.assertIn("    HandlePlaySpeed();", loop)
        speed = body(source, "void CVideoPlayer::HandlePlaySpeed()")
        self.assertIn("m_bdjDraining || isInMenu", speed)
        self.assertIn("GENERAL_RESYNC", speed)

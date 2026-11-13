"""BD-J replacement keeps only a viable demuxer and a drained PCM stream."""
import unittest

from test_native_video_source import TREE, body

PLAYER = TREE / "xbmc/cores/VideoPlayer"


class BdjAudioHandoff(unittest.TestCase):
    def test_abandoned_demuxer_never_opens_workers(self):
        loop = body((PLAYER / "VideoPlayer.cpp").read_text(), "void CVideoPlayer::Process()")
        probe = loop[loop.index("if (!m_pDemuxer)"):loop.index("    HandlePlaySpeed();")]
        self.assertLess(probe.index("OpenDemuxStream()"), probe.index("PollBdjEvents()"))
        self.assertLess(probe.index("PollBdjEvents()"), probe.rindex("TakeBdjPlaylistJump()"))
        self.assertLess(probe.index("CloseDemuxer()"), probe.index("OpenDefaultStreams()"))

    def test_retained_pcm_is_drained_and_paused_in_worker(self):
        loop = body((PLAYER / "VideoPlayer.cpp").read_text(), "void CVideoPlayer::Process()")
        boundary = loop[loop.index("if(next == CDVDInputStream::NEXTSTREAM_OPEN)"):
                        loop.index("if(next == CDVDInputStream::NEXTSTREAM_RETRY)")]
        self.assertIn("m_bdjDraining", boundary)
        self.assertIn("!m_VideoPlayerAudio->IsPassthrough()", boundary)
        self.assertIn("CDVDMsg::GENERAL_EOF", boundary)
        worker = body((PLAYER / "VideoPlayerAudio.cpp").read_text(), "void CVideoPlayerAudio::Process()")
        drain = body(worker, "pMsg->IsType(CDVDMsg::GENERAL_EOF)")
        self.assertLess(drain.index("m_audioSink.Drain()"), drain.index("m_audioSink.Pause()"))
        self.assertLess(drain.index("m_audioSink.GetDelay()"), drain.index("CThread::Sleep(tail)"))
        self.assertLess(drain.index("CThread::Sleep(tail)"), drain.index("m_audioSink.Pause()"))
        self.assertNotIn("m_audioSink.Destroy", drain)

    def test_seek_and_close_release_unselected_audio(self):
        source = (PLAYER / "VideoPlayer.cpp").read_text()
        close = body(source, "bool CVideoPlayer::CloseStream(")
        flush = body(source, "void CVideoPlayer::FlushBuffers(")
        opened = body(source, "bool CVideoPlayer::OpenAudioStream(")
        self.assertIn("m_bdjAudioHandoff", close)
        self.assertIn("CloseStream(m_CurrentAudio, false)", flush)
        self.assertIn("m_bdjAudioHandoff = false", opened)

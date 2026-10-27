"""Run production admission/assembly against tiny MOV and TS containers."""
import os
import base64
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE
from test_native_video_source import body


def atom(tag, data):
    return struct.pack('>I4s', len(data)+8, tag)+data


def mp4(kind, packet_pair=None, configuration=None, sample_entry=b'dvh1'):
    """Synthetic framing only, not decodable audiovisual content."""
    packets = [b'\0\0\0\3\x26\1\xaa', b'\0\0\0\3\x26\1\xbb\0\0\0\3\x7c\1\xcc']
    if packet_pair is not None:
        packets = packet_pair
    matrix = struct.pack('>9I', 65536, 0, 0, 0, 65536, 0, 0, 0, 0x40000000)
    ftyp = atom(b'ftyp', b'isom\0\0\0\0isomiso6')
    mvhd = bytearray(100)
    struct.pack_into('>IIIH', mvhd, 12, 1000, 2000, 65536, 256)
    mvhd[36:72] = matrix
    struct.pack_into('>I', mvhd, 96, 3)

    def track(i, offset):
        width, height = (3840, 2160) if i == 0 else (1920, 1080)
        tkhd = bytearray(84)
        struct.pack_into('>I', tkhd, 0, 3)
        struct.pack_into('>I', tkhd, 12, i+1)
        struct.pack_into('>I', tkhd, 20, 2000)
        tkhd[40:76] = matrix
        struct.pack_into('>II', tkhd, 76, width<<16, height<<16)
        mdhd = bytearray(24)
        struct.pack_into('>IIH', mdhd, 12, 1000, 2000, 0x55c4)
        hdlr = bytearray(24)
        hdlr[8:12] = b'vide'
        visual = bytearray(78)
        struct.pack_into('>H', visual, 6, 1)
        struct.pack_into('>HHII', visual, 24, width, height, 72<<16, 72<<16)
        struct.pack_into('>H', visual, 40, 1)
        struct.pack_into('>HH', visual, 74, 24, 65535)
        hvcc = configuration if configuration is not None else bytes([1])+bytes(20)+bytes([3, 0])
        codec = sample_entry if i == 1 else b'hvc1'
        extra = atom(b'hvcC', hvcc)
        if i == 1 and kind in ('paired', 'missing-reference'):
            flags = (7<<9)|(9<<3)|6  # P7.9, RPU + EL, no BL in this track.
            extra += atom(b'dvcC', bytes([1, 0, flags>>8, flags&255, 0x60])+bytes(19))
        stsd = atom(b'stsd', bytes(4)+struct.pack('>I', 1)+atom(codec, visual+extra))
        stts = atom(b'stts', struct.pack('>4I', 0, 1, 2, 1000))
        stsc = atom(b'stsc', struct.pack('>5I', 0, 1, 1, 2, 1))
        stsz = atom(b'stsz', struct.pack('>5I', 0, 0, 2, len(packets[i]), len(packets[i])))
        stco = atom(b'stco', struct.pack('>3I', 0, 1, offset))
        stss = atom(b'stss', struct.pack('>4I', 0, 2, 1, 2))
        stbl = atom(b'stbl', stsd+stts+stsc+stsz+stco+stss)
        mdia = atom(b'mdia', atom(b'mdhd', mdhd)+atom(b'hdlr', hdlr)+atom(b'minf', stbl))
        tref = b''
        if i == 1 and kind != 'independent':
            tref = atom(b'tref', atom(b'vdep', struct.pack('>I', 99 if kind == 'missing-reference' else 1)))
        return atom(b'trak', atom(b'tkhd', tkhd)+tref+mdia)

    moov = atom(b'moov', atom(b'mvhd', mvhd)+track(0, 0)+track(1, 0))
    offset = len(ftyp)+len(moov)+8
    moov = atom(b'moov', atom(b'mvhd', mvhd)+track(0, offset)+track(1, offset+2*len(packets[0])))
    return ftyp+moov+atom(b'mdat', packets[0]*2+packets[1]*2)


def transport(kind, m2ts=False, hevc_el=False):
    """Minimal PAT/PMT/PES with HDMV or explicit DV dependency signalling."""
    def section(table, body):
        data = bytes([table])+struct.pack('>H', 0xb000+len(body)+4)+body
        crc = 0xffffffff
        for byte in data:
            crc ^= byte<<24
            for _ in range(8):
                crc = ((crc<<1) ^ (0x04c11db7 if crc & 0x80000000 else 0)) & 0xffffffff
        return data+struct.pack('>I', crc)

    sequence = {}
    def ts(pid, payload):
        cc = sequence.get(pid, 0)
        sequence[pid] = (cc+1) & 15
        assert len(payload) <= 184
        return (bytes(4) if m2ts else b'')+bytes([0x47, 0x40+(pid>>8), pid&255, 0x10+cc])+payload+bytes([255])*(184-len(payload))

    base, el = (0x1011, 0x1015) if kind == 'hdmv' else (0x120, 0x121)
    registration = b'\x05\x04'+(b'HDMV' if kind.startswith('hdmv') else b'DOVI' if kind in ('dovi', 'late') else b'TEST')
    pat = section(0, b'\0\1\xc1\0\0'+struct.pack('>HH', 1, 0xe100))
    def pmt(descriptor, version=0):
        entries = b''
        for pid in (base, el):
            info = b''
            stream_type = 0x24
            if kind in ('dovi', 'late') and pid == el:
                stream_type = 0x24 if hevc_el else 6
                if descriptor:
                    flags = (7<<9)|(9<<3)|6
                    desc = bytes([1, 0, flags>>8, flags&255])+struct.pack('>H', base<<3)+b'\x60'
                    info = b'\x05\x04DOVI'+bytes([0xb0, len(desc)])+desc
            entries += bytes([stream_type])+struct.pack('>HH', 0xe000+pid, 0xf000+len(info))+info
        return section(2, bytes([0, 1, 0xc1+(version<<1), 0, 0])+struct.pack('>HH', 0xe000+base, 0xf000+len(registration))+registration+entries)
    def pts(value):
        return bytes([0x21+((value>>29)&14), (value>>22)&255, 1+((value>>14)&254), (value>>7)&255, 1+((value<<1)&254)])
    result = ts(0, b'\0'+pat)+ts(0x100, b'\0'+pmt(kind != 'late'))
    for frame in range(544 if kind == 'late' else 32):
        if kind == 'late' and frame == 512:
            result += ts(0x100, b'\0'+pmt(True, 1))
        for pid, nal in ((base, b'\0\0\0\1\x26\1\xaa'), (el, b'\0\0\0\1\x26\1\xbb\0\0\0\1\x7c\1\xcc')):
            payload = b'\x80\x80\x05'+pts(90000+frame*3754)+nal
            result += ts(pid, b'\0\0\1\xe0'+struct.pack('>H', len(payload))+payload)
    return result


class DualCarriage(unittest.TestCase):
    def test_joined_length_prefixed_tracks_keep_their_seek_framing(self):
        # Two uniform synthetic 64x64 IDR pictures, generated without media input.
        hvcc = base64.b64decode('AQQIAAAAn6gAAAAAHvAA/P34+AAADwMgAAEAF0ABDAH//wQIAAADAJ+oAAADAAAeugJAIQABACdCAQEECAAAAwCfqAAAAwAAHqAggQWW6SkwvAWgIAAAAwAgAAADACEiAAEABkQBwHGBEg==')
        packet = base64.b64decode('AAAAF0ABDAH//wQIAAADAJ+oAAADAAAeugJAAAAAJ0IBAQQIAAADAJ+oAAADAAAeoCCBBZbpKTC8BaAgAAADACAAAAMAIQAAAAZEAcBxgRIAAAALKAGt4NEXznMji4A=')
        self.run_carriage([('seek-paired.mp4', mp4('paired', [packet,packet], hvcc), True)])

    def test_mp4_group_admission_and_unrelated_track_rejection(self):
        self.run_carriage([('paired.mp4', mp4('paired'), True),
                           ('independent.mp4', mp4('independent'), False),
                           ('unrelated-vdep.mp4', mp4('unrelated-vdep'), False),
                           ('missing-reference.mp4', mp4('missing-reference'), False)])

    def test_mp4_declared_layer_reference_accepts_hevc_sample_entries(self):
        self.run_carriage([(tag.decode()+'-'+kind+'.mp4', mp4(kind, sample_entry=tag), want)
                           for tag in (b'hvc1', b'hev1')
                           for kind, want in (('paired', True), ('independent', False),
                                              ('unrelated-vdep', False), ('missing-reference', False))])

    def test_ts_group_admission_and_unrelated_pid_rejection(self):
        self.run_carriage([('hdmv.ts', transport('hdmv'), True),
                           ('hdmv.m2ts', transport('hdmv', True), True),
                           ('descriptor.ts', transport('dovi'), True),
                           ('unrelated-hdmv.ts', transport('hdmv-other'), False),
                           ('independent.ts', transport('independent'), False)])

    def test_late_ts_descriptor_updates_initialized_codec(self):
        self.run_carriage([('late.ts', transport('late'), True)])

    def test_late_group_preserves_saved_base_for_assembly(self):
        data = transport('late', hevc_el=True)
        self.run_carriage([('late-start.ts', data, True), ('late-start-el.ts', data, True),
                           ('late-start-audio.ts', data, True)])

    def run_carriage(self, fixtures):
        root_name = os.environ.get('CB1_CARRIAGE_ROOT')
        compiler = os.environ.get('CB1_CARRIAGE_CXX')
        prefix = os.environ.get('FFMPEG_TEST_PREFIX')
        target = bool(root_name and compiler)
        if not target and not prefix:
            self.skipTest('Matched FFmpeg prefix or isolated production runtime required')
        runtime = Path(root_name) if target else None
        compiler = compiler if target else 'c++'
        code = (TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        start = code.index('void CDVDDemuxFFmpeg::InitBlurayDovi(')
        end = code.index('\n#endif', start)
        add_start = code.index('CDemuxStream* CDVDDemuxFFmpeg::AddStream(int streamIdx)')
        add_end = code.index('  AVStream* pStream =', add_start)
        layer = code.index('      int64_t layerPosition = -1;')
        reset = code[code.rfind('#ifdef HAVE_DVBRIDGE', 0, layer)+len('#ifdef HAVE_DVBRIDGE'):layer]
        seek_byte = body(code, 'bool CDVDDemuxFFmpeg::SeekByte(')
        rebuild_start = code.index('          // update streams')
        rebuild = code[rebuild_start:code.index('          pPacket =', rebuild_start)]
        program = r'''
#define HAVE_DVBRIDGE 1
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
#include <climits>
#include <cstdio>
#include <mutex>
extern "C" {
#include <libavformat/avformat.h>
#include <libavutil/dovi_meta.h>
#include <libavcodec/avcodec.h>
#include "dvbridge_fel_seek.h"
}
std::deque<AVPacket*> scripted;
extern "C" int __real_av_read_frame(AVFormatContext*,AVPacket*);
extern "C" int __wrap_av_read_frame(AVFormatContext* f,AVPacket* p){
 if(scripted.empty())return __real_av_read_frame(f,p);
 auto* next=scripted.front();scripted.pop_front();av_packet_move_ref(p,next);av_packet_free(&next);return 0;
}
enum { DVDSTREAM_TYPE_BLURAY=1,LOGINFO,LOGWARNING,LOGERROR };
struct CLog { template<class... T> static void Log(T&&...) {} };
static int mode;
struct Settings {int GetInt(const char*) {return mode;}};
struct Component {Settings* GetSettings(){static Settings s;return &s;}};
struct CServiceBroker {static Component* GetSettingsComponent(){static Component c;return &c;}};
struct Input {bool IsStreamType(int){return false;}};
struct CDemuxStream {int index;};
constexpr double DVD_NOPTS_VALUE=-1;
struct CDVDDemuxFFmpeg {
 AVFormatContext* m_pFormatContext{};bool m_bMatroska{};Input input;Input* m_pInput{&input};
 std::unique_ptr<CBlurayDovi> m_blurayDovi;int m_blurayBase{-1},m_blurayEnhancement{-1};
 unsigned m_doviGroups=0,m_program=0;
 bool m_blurayAwaitBase=false;
 std::mutex m_critSection;double m_currentPts{};
 struct {int result{};AVPacket pkt{};} m_pkt;
 struct AVCodecParametersDeleter {void operator()(AVCodecParameters* p)const{avcodec_parameters_free(&p);}};
 void InitBlurayDovi(unsigned int);int ReadBlurayDovi(AVPacket*);CDemuxStream* AddStream(int);
 void CreateStreams(unsigned program){InitBlurayDovi(program);}
 void RebuildForTest(){ REBUILD_BODY }
 void BeforeSeek() { RESET_BODY }
 bool SeekByte(int64_t pos) SEEK_BYTE
};
''' .replace('RESET_BODY', reset).replace('SEEK_BYTE', seek_byte).replace('REBUILD_BODY', rebuild) + code[start:end] + code[add_start:add_end] + r'''
 return new CDemuxStream{streamIdx}; // Unchanged stream-construction boundary.
}
int main(int argc,char**argv) {
 setvbuf(stdout,nullptr,_IONBF,0);av_log_set_level(AV_LOG_QUIET);
 assert(av_find_input_format("mov") && av_find_input_format("mpegts"));
 for(int i=1;i<argc;i+=2)for(int disabled : {0,2}){
  CDVDDemuxFFmpeg d;assert(avformat_open_input(&d.m_pFormatContext,argv[i],nullptr,nullptr)==0);
  bool want=atoi(argv[i+1]);mode=disabled;
  if(strstr(argv[i],"late-start")){
   d.InitBlurayDovi(UINT_MAX);assert(!d.m_blurayDovi);
   while(av_read_frame(d.m_pFormatContext,&d.m_pkt.pkt)==0){
    if(d.m_pFormatContext->nb_stream_groups)break;
    av_packet_unref(&d.m_pkt.pkt);
   }
   const bool startsEl=strstr(argv[i],"start-el");
   const bool startsAudio=strstr(argv[i],"start-audio");
   if(startsEl){
    while(d.m_pkt.pkt.stream_index!=1){av_packet_unref(&d.m_pkt.pkt);
     assert(av_read_frame(d.m_pFormatContext,&d.m_pkt.pkt)==0);}
   }
   assert(d.m_pFormatContext->nb_stream_groups==1 && d.m_pkt.pkt.stream_index==int(startsEl));
   const auto savedPts=d.m_pkt.pkt.pts;
   if(startsAudio){
    // Model a queued audio packet returned while an EL triggers group discovery internally.
    for(int j=0;j<3;j++){
     const uint8_t el[]={0,0,0,1,0x26,1,uint8_t(j?0x22:0x11),0,0,0,1,0x7c,1,0xcc};
     const uint8_t bl[]={0,0,0,1,0x26,1,0xaa};
     auto* next=av_packet_alloc();assert(next && av_new_packet(next,j==1?sizeof(bl):sizeof(el))==0);
     memcpy(next->data,j==1?bl:el,next->size);next->stream_index=j==1?0:1;
     next->pts=next->dts=savedPts+(j?3754:0);
     scripted.push_back(next);
    }
    auto* audio=avformat_new_stream(d.m_pFormatContext,nullptr);assert(audio && audio->index==2);
    audio->codecpar->codec_type=AVMEDIA_TYPE_AUDIO;audio->codecpar->codec_id=AV_CODEC_ID_PCM_S16LE;
    d.m_pkt.pkt.stream_index=2;
   }
   d.m_pkt.result=0;d.RebuildForTest();
   if(!disabled){
    assert(d.m_blurayDovi && d.m_blurayDovi->Pending()==(!startsEl && !startsAudio));
    if(startsAudio){assert(d.m_pkt.result==0 && d.m_pkt.pkt.stream_index==2);av_packet_unref(&d.m_pkt.pkt);}
    else assert(d.m_pkt.result<0 && !d.m_pkt.pkt.data && "Saved BL must be queued, not emitted unjoined");
    AVPacket* joined=av_packet_alloc();assert(joined);
    int status;
    status=d.ReadBlurayDovi(joined);
    assert(status==0 && joined->stream_index==0 && joined->pts==savedPts+((startsEl||startsAudio)?3754:0));
    const uint8_t marker=startsAudio?0x22:0xbb;
    std::vector<uint8_t> expected={0,0,0,1,0x26,1,0xaa,0,0,0,1,0x7e,1,0x26,1,marker,0,0,0,1,0x7c,1,0xcc};
    assert(joined->size==int(expected.size()) && !memcmp(joined->data,expected.data(),expected.size()));
    av_packet_free(&joined);
   }else assert(d.m_pkt.result==0 && d.m_pkt.pkt.data && !d.m_blurayDovi);
   for(auto* p:scripted)av_packet_free(&p);scripted.clear();
   av_packet_unref(&d.m_pkt.pkt);avformat_close_input(&d.m_pFormatContext);continue;
  }
  if(strstr(argv[i],"late.ts")){
   assert(d.m_pFormatContext->nb_stream_groups==0);
   AVPacket* packet=av_packet_alloc();int ret;bool received=false;
   while((ret=av_read_frame(d.m_pFormatContext,packet))==0){
    if(d.m_pFormatContext->nb_stream_groups){
     const auto* el=d.m_pFormatContext->streams[1];
     assert(el->codecpar->codec_id==AV_CODEC_ID_HEVC && "Late DV descriptor must update the initialized codec context");
     received |= packet->stream_index==1;
    }
    av_packet_unref(packet);
   }
   assert(ret==AVERROR_EOF && received);av_packet_free(&packet);
   avformat_close_input(&d.m_pFormatContext);continue;
  }
  printf("%s format=%s groups=%u disabled=%d\n",argv[i],d.m_pFormatContext->iformat->name,d.m_pFormatContext->nb_stream_groups,disabled);
  for(unsigned stream=0;stream<d.m_pFormatContext->nb_streams;stream++){
   const auto* s=d.m_pFormatContext->streams[stream];
   printf(" stream=%u id=0x%x codec=%d tag=0x%x tb=%d/%d\n",stream,s->id,s->codecpar->codec_id,s->codecpar->codec_tag,s->time_base.num,s->time_base.den);
  }
  assert((d.m_pFormatContext->nb_stream_groups==1)==want);
  d.InitBlurayDovi(UINT_MAX);
  assert(bool(d.m_blurayDovi)==(want && !disabled) && "Qualified MOV/TS group must reach shared assembly");
  if(d.m_blurayDovi){
   if(strstr(argv[i],"seek-paired")){
    for(int rebuild=0;rebuild<2;++rebuild){
     int64_t position=-1;
     assert(dvbridge_fel_seek_point_at(d.m_pFormatContext,d.m_blurayBase,1000,&position,
                                     d.m_blurayDovi->OriginalBaseParameters())==1000);
     assert(position>=0);d.InitBlurayDovi(UINT_MAX);assert(d.m_blurayDovi);
    }
    continue;
   }
   auto seed=[&](){
    AVPacket* stale=av_packet_alloc();assert(stale);
    while(av_read_frame(d.m_pFormatContext,stale)==0){
     if(stale->stream_index==d.m_blurayBase){assert(d.m_blurayDovi->Push(stale,false));break;}
     av_packet_unref(stale);
    }
    av_packet_free(&stale);assert(d.m_blurayDovi->Pending());
   };
   seed();d.BeforeSeek();assert(!d.m_blurayDovi->Pending());
   assert(av_seek_frame(d.m_pFormatContext,d.m_blurayBase,0,AVSEEK_FLAG_BACKWARD)>=0);
   if(!strcmp(d.m_pFormatContext->iformat->name,"mpegts")){
    seed();assert(d.SeekByte(0));assert(!d.m_blurayDovi->Pending());
   }
   const int bl=d.m_blurayBase,el=d.m_blurayEnhancement;
   auto* visible=d.AddStream(bl);assert(visible);delete visible;assert(!d.AddStream(el));
   assert(d.m_pFormatContext->streams[el]->discard==AVDISCARD_NONE);
   const auto* cfg=av_packet_side_data_get(d.m_pFormatContext->streams[bl]->codecpar->coded_side_data,d.m_pFormatContext->streams[bl]->codecpar->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF);
   assert(cfg);auto* dv=(const AVDOVIDecoderConfigurationRecord*)cfg->data;
   assert(dv->dv_profile==7 && dv->bl_present_flag && dv->el_present_flag && dv->rpu_present_flag);
   if(strstr(argv[i],"paired")||strstr(argv[i],"descriptor"))assert(dv->dv_level==9 && dv->dv_bl_signal_compatibility_id==6);
   d.InitBlurayDovi(UINT_MAX);assert(d.m_blurayDovi);
   AVPacket* packet=av_packet_alloc();int count=0,ret;
   const bool mov=strstr(d.m_pFormatContext->iformat->name,"mov");
   while((ret=d.ReadBlurayDovi(packet))==0){
    const uint8_t expected[]={0,0,0,1,0x26,1,0xaa,0,0,0,1,0x7e,1,0x26,1,0xbb,0,0,0,1,0x7c,1,0xcc};
    assert(packet->stream_index==bl && packet->size==sizeof(expected) && !memcmp(packet->data,expected,sizeof(expected)));
    const int64_t timestamp=mov ? count*1000 : 90000+count*3754;
    assert(packet->pts==timestamp && packet->dts==timestamp);
    assert(packet->duration==(mov ? 1000 : 0));
    count++;av_packet_unref(packet);
   }
   assert(ret==AVERROR_EOF && count==(mov ? 2 : 32) && !d.m_blurayDovi->Pending());av_packet_free(&packet);
   d.m_blurayDovi->Reset(true);assert(!d.m_blurayDovi->Pending());
   mode=2;d.InitBlurayDovi(UINT_MAX);assert(!d.m_blurayDovi);
   assert(!av_packet_side_data_get(d.m_pFormatContext->streams[bl]->codecpar->coded_side_data,d.m_pFormatContext->streams[bl]->codecpar->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF));
   const auto* elcfg=av_packet_side_data_get(d.m_pFormatContext->streams[el]->codecpar->coded_side_data,d.m_pFormatContext->streams[el]->codecpar->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF);
   mode=0;
   if(elcfg){
    auto* declared=(AVDOVIDecoderConfigurationRecord*)elcfg->data;
    declared->dv_profile=8;d.InitBlurayDovi(UINT_MAX);assert(!d.m_blurayDovi);declared->dv_profile=7;
    declared->rpu_present_flag=0;d.InitBlurayDovi(UINT_MAX);assert(!d.m_blurayDovi);declared->rpu_present_flag=1;
   }
   auto* duplicate=avformat_stream_group_create(d.m_pFormatContext,AV_STREAM_GROUP_PARAMS_DOLBY_VISION,nullptr);assert(duplicate);
   assert(avformat_stream_group_add_stream(duplicate,d.m_pFormatContext->streams[bl])==0);
   assert(avformat_stream_group_add_stream(duplicate,d.m_pFormatContext->streams[el])==0);duplicate->params.layered_video->el_index=1;
   d.InitBlurayDovi(UINT_MAX);assert(!d.m_blurayDovi && "Ambiguous groups must not choose an arbitrary presentation");
  }
  avformat_close_input(&d.m_pFormatContext);
 }
}
'''
        with tempfile.TemporaryDirectory(prefix='cb1-carriage-', dir=runtime/'tmp' if target else None) as temporary:
            folder = Path(temporary)
            for name, data, _ in fixtures:
                (folder/name).write_bytes(data)
            source = folder/'check.cpp';source.write_text(program)
            binary = folder/'check'
            dependency_flags = [] if target else ['-I'+prefix+'/include', '-L'+prefix+'/lib',
                                                 '-Wl,-rpath,'+prefix+'/lib']
            built = subprocess.run([compiler, '-std=c++20', '-O2', '-I'+str(TREE/'xbmc'),
                                    '-I'+str(Path(__file__).resolve().parents[2]/'CB1/src'), *dependency_flags,
                                    str(source), '-Wl,--wrap=av_read_frame', '-lavformat', '-lavcodec', '-lavutil', '-o', str(binary)],
                                   text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            path = '/'+folder.relative_to(runtime).as_posix() if target else str(folder)
            args = [x for name, _, want in fixtures for x in (path+'/'+name, str(int(want)))]
            invocation = (['chroot', str(runtime), '/usr/lib/ld-linux-x86-64.so.2',
                           '--inhibit-cache', path+'/check'] if target else [str(binary)])
            result = subprocess.run([*invocation, *args], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)

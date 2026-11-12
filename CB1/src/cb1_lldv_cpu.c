// SPDX-License-Identifier: MIT
#include "cb1_lldv_cpu.h"

#if defined(__x86_64__)
#include <cpuid.h>
#include <immintrin.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

enum { W=3840, H=2160, LUT=1024*61, CHUNK=128, MAX_WORKERS=4 };

struct cb1_lldv_cpu {
    pthread_mutex_t lock;
    pthread_cond_t wake;
    pthread_t workers[MAX_WORKERS];
    struct cb1_lldv_cpu_frame frame;
    // Each entry stores the 22-bit PQ value and a 10-bit delta to the next sample.
    uint32_t words[LUT];
    float matrix[9];
    float peak_scale;
    unsigned threads, generation, running;
    atomic_uint next_row;
    bool closing;
};

#define CB1_AVX2 __attribute__((target("avx2,fma")))
static inline CB1_AVX2 __m256 pq(const struct cb1_lldv_cpu *cpu, __m256 x)
{
    // Index 10 mantissa bits per float exponent; interpolate over the other 13.
    const __m256i base=_mm256_set1_epi32(67u<<23);
    x=_mm256_mul_ps(_mm256_max_ps(_mm256_min_ps(_mm256_set1_ps(1),x),_mm256_setzero_ps()),_mm256_set1_ps(cpu->peak_scale));
    __m256i u=_mm256_sub_epi32(_mm256_max_epu32(_mm256_castps_si256(x),base),base);
    __m256i idx=_mm256_srli_epi32(u,13);
    __m256i entry=_mm256_i32gather_epi32((const int*)cpu->words,idx,4);
    __m256 l=_mm256_cvtepi32_ps(_mm256_and_si256(entry,_mm256_set1_epi32((1<<22)-1)));
    __m256 delta=_mm256_cvtepi32_ps(_mm256_srli_epi32(entry,22));
    __m256 f=_mm256_mul_ps(_mm256_cvtepi32_ps(_mm256_and_si256(u,_mm256_set1_epi32(8191))),_mm256_set1_ps(1.0f/8192));
    __m256 v=_mm256_mul_ps(_mm256_fmadd_ps(f,delta,l),_mm256_set1_ps(1.0f/4194304));
    return _mm256_blendv_ps(v,_mm256_set1_ps(7.309559e-7f),
        _mm256_cmp_ps(x,_mm256_setzero_ps(),_CMP_EQ_OQ));
}
static inline CB1_AVX2 __m256 range(__m256 x,float low,float high)
{
    return _mm256_min_ps(_mm256_max_ps(x,_mm256_set1_ps(low)),_mm256_set1_ps(high));
}
static inline CB1_AVX2 __m256 weighted(const float *p)
{
    __m256 a=_mm256_loadu_ps(p-1),b=_mm256_loadu_ps(p),c=_mm256_loadu_ps(p+1);
    __m256 value=_mm256_mul_ps(_mm256_add_ps(_mm256_add_ps(a,_mm256_add_ps(b,b)),c),_mm256_set1_ps(.25f));
    return _mm256_permutevar8x32_ps(value,_mm256_setr_epi32(0,0,2,2,4,4,6,6));
}
static inline CB1_AVX2 __m256 luminance(__m256 r,__m256 g,__m256 b)
{
    return _mm256_fmadd_ps(r,_mm256_set1_ps(.2627f),
           _mm256_fmadd_ps(g,_mm256_set1_ps(.6780f),_mm256_mul_ps(b,_mm256_set1_ps(.0593f))));
}
static inline CB1_AVX2 __m256 matrix_row(const float *m, __m256 r, __m256 g, __m256 b)
{
    return _mm256_fmadd_ps(_mm256_set1_ps(m[0]),r,
           _mm256_fmadd_ps(_mm256_set1_ps(m[1]),g,_mm256_mul_ps(_mm256_set1_ps(m[2]),b)));
}

static CB1_AVX2 void pack_rows(struct cb1_lldv_cpu *cpu)
{
    const struct cb1_lldv_cpu_frame *frame=&cpu->frame;
    unsigned padding=12-frame->bits;
    const __m128i pad=_mm_cvtsi32_si128(padding);
    const __m256 scale=_mm256_set1_ps(1.0f/(1u<<padding));
    const __m256 half=_mm256_set1_ps(.5f);
    float rline[CHUNK+2],gline[CHUNK+2],bline[CHUNK+2];
    // Share row groups so a decoder or GUI wakeup cannot strand one core's rows.
    enum { ROW_BATCH=16 };
    for(unsigned begin=atomic_fetch_add_explicit(&cpu->next_row,ROW_BATCH,memory_order_relaxed);
        begin<H;begin=atomic_fetch_add_explicit(&cpu->next_row,ROW_BATCH,memory_order_relaxed))
    for(unsigned y=begin;y<H && y<begin+ROW_BATCH;y++){
        const float *row=frame->linear+4*(size_t)y*W;
        const size_t out_y=frame->flip_y?H-1-y:y;
        uint32_t *out=frame->carrier+out_y*(frame->stride/sizeof(*out));
        const __m256i mask=_mm256_setr_epi32(0x7fffffff,0x7fffffff,0x7fffffff,0,
                                            0x7fffffff,0x7fffffff,0x7fffffff,0);
        const bool blank=y<frame->first_row || (frame->end_row && y>=frame->end_row);
        int probe=blank?W:0;
        for(;probe<W;probe+=2){
            __m256i value=_mm256_loadu_si256((const __m256i *)(row+probe*4));
            if(!_mm256_testz_si256(value,mask))break;
        }
        if(probe==W){
            __m256i black=_mm256_set1_epi32(frame->xrgb?0xff801000:0xff001080);
            for(int x=0;x<W;x+=8)_mm256_stream_si256((void *)(out+x),black);
            continue;
        }
        for(int x=0;x<W;x+=CHUNK){
            for(int k=0;k<CHUNK;k+=8){
                const float *p=row+4*(x+k);
                __m128 a=_mm_loadu_ps(p+0),b0=_mm_loadu_ps(p+4),c=_mm_loadu_ps(p+8),d=_mm_loadu_ps(p+12);
                __m128 e=_mm_loadu_ps(p+16),f=_mm_loadu_ps(p+20),g0=_mm_loadu_ps(p+24),h=_mm_loadu_ps(p+28);
                _MM_TRANSPOSE4_PS(a,b0,c,d);
                _MM_TRANSPOSE4_PS(e,f,g0,h);
                __m256 r=_mm256_set_m128(e,a),g=_mm256_set_m128(f,b0),b=_mm256_set_m128(g0,c);
                if(frame->to_bt2020){
                    const __m256 in_r=r,in_g=g,in_b=b;
                    r=matrix_row(cpu->matrix,in_r,in_g,in_b);
                    g=matrix_row(cpu->matrix+3,in_r,in_g,in_b);
                    b=matrix_row(cpu->matrix+6,in_r,in_g,in_b);
                }
                const int grey=_mm256_movemask_ps(_mm256_and_ps(_mm256_cmp_ps(r,g,_CMP_EQ_OQ),_mm256_cmp_ps(r,b,_CMP_EQ_OQ)));
                r=pq(cpu,r);
                if(grey==255){g=r;b=r;}else{g=pq(cpu,g);b=pq(cpu,b);}
                _mm256_storeu_ps(rline+1+k,r);_mm256_storeu_ps(gline+1+k,g);_mm256_storeu_ps(bline+1+k,b);
            }
            if(!x){rline[0]=rline[1];gline[0]=gline[1];bline[0]=bline[1];}
            // Each chroma pair is cosited at its even pixel; the rightmost halo is unused.
            rline[CHUNK+1]=rline[CHUNK];gline[CHUNK+1]=gline[CHUNK];bline[CHUNK+1]=bline[CHUNK];
            for(int k=0;k<CHUNK;k+=8){
                __m256 r=_mm256_loadu_ps(rline+1+k),g=_mm256_loadu_ps(gline+1+k),b=_mm256_loadu_ps(bline+1+k);
                __m256 yv=_mm256_fmadd_ps(range(luminance(r,g,b),0,1),_mm256_set1_ps(3504),_mm256_set1_ps(256));
                __m256 rw=weighted(rline+1+k),gw=weighted(gline+1+k),bw=weighted(bline+1+k);
                __m256 lw=luminance(rw,gw,bw);
                __m256 cb=_mm256_mul_ps(_mm256_sub_ps(bw,lw),_mm256_set1_ps(1.0f/1.8814f));
                __m256 cr=_mm256_mul_ps(_mm256_sub_ps(rw,lw),_mm256_set1_ps(1.0f/1.4746f));
                __m256 cv=_mm256_fmadd_ps(range(_mm256_blend_ps(cb,cr,0xaa),-.5,.5),_mm256_set1_ps(3584),_mm256_set1_ps(2048));
                __m256i Y=_mm256_sll_epi32(_mm256_cvttps_epi32(_mm256_fmadd_ps(yv,scale,half)),pad);
                __m256i C=_mm256_sll_epi32(_mm256_cvttps_epi32(_mm256_fmadd_ps(cv,scale,half)),pad);
                // Assemble the selected byte order once, including both low nibbles.
                const __m256i nibble=_mm256_set1_epi32(15);
                const __m256i low=_mm256_or_si256(
                    _mm256_slli_epi32(_mm256_and_si256(C,nibble),4),_mm256_and_si256(Y,nibble));
                const __m256i high_c=_mm256_srli_epi32(C,4);
                const __m256i high_y=_mm256_slli_epi32(_mm256_srli_epi32(Y,4),8);
                const __m256i red_blue=frame->xrgb ?
                    _mm256_or_si256(low,_mm256_slli_epi32(high_c,16)) :
                    _mm256_or_si256(high_c,_mm256_slli_epi32(low,16));
                const __m256i alpha_y=_mm256_or_si256(high_y,_mm256_set1_epi32(0xff000000));
                _mm256_stream_si256((void*)(out+x+k),_mm256_or_si256(red_blue,alpha_y));
            }
            rline[0]=rline[CHUNK];gline[0]=gline[CHUNK];bline[0]=bline[CHUNK];
        }
    }
    _mm_sfence();
}

static void *worker(void *opaque)
{
    struct cb1_lldv_cpu *cpu=opaque;
    unsigned seen=0;
    pthread_mutex_lock(&cpu->lock);
    for(;;){
        while(!cpu->closing && cpu->generation==seen)
            pthread_cond_wait(&cpu->wake,&cpu->lock);
        if(cpu->closing)break;
        seen=cpu->generation;
        pthread_mutex_unlock(&cpu->lock);
        pack_rows(cpu);
        pthread_mutex_lock(&cpu->lock);
        if(!--cpu->running)pthread_cond_broadcast(&cpu->wake);
    }
    pthread_mutex_unlock(&cpu->lock);
    return NULL;
}

static bool make_pq_table(struct cb1_lldv_cpu *cpu)
{
    uint32_t last=0;
    for(unsigned i=0;i<=LUT;i++){
        uint32_t u=(67u<<23)+(i<<13);
        float f;
        memcpy(&f,&u,sizeof(f));
        double v=pow(fmin(1,f),.1593017578125);
        unsigned value=fmin((1u<<22)-1,lround(pow((.8359375+18.8515625*v)/
            (1+18.6875*v),78.84375)*(1u<<22)));
        if(i){
            if(value<last || value-last>=1024)return false;
            cpu->words[i-1]=last|((value-last)<<22);
        }
        last=value;
    }
    return true;
}

static bool cpu_supported(void)
{
    unsigned eax,ebx,ecx,edx;
    const unsigned required=bit_AVX|bit_OSXSAVE|bit_FMA;
    if(!__get_cpuid(1,&eax,&ebx,&ecx,&edx) || (ecx&required)!=required)
        return false;
    unsigned xcr0,high;
    __asm__ volatile("xgetbv" : "=a"(xcr0),"=d"(high) : "c"(0));
    if((xcr0&6)!=6)return false; /* OS saves XMM and YMM state. */
    return __get_cpuid_count(7,0,&eax,&ebx,&ecx,&edx) && (ebx&bit_AVX2);
}

struct cb1_lldv_cpu *cb1_lldv_cpu_create(unsigned threads)
{
    if(!threads || threads>MAX_WORKERS || !cpu_supported())
        return NULL;
    struct cb1_lldv_cpu *cpu=calloc(1,sizeof(*cpu));
    if(!cpu)return NULL;
    atomic_init(&cpu->next_row,0);
    if(!make_pq_table(cpu) || pthread_mutex_init(&cpu->lock,NULL)){
        free(cpu);
        return NULL;
    }
    if(pthread_cond_init(&cpu->wake,NULL)){
        pthread_mutex_destroy(&cpu->lock);
        free(cpu);
        return NULL;
    }
    while(cpu->threads<threads){
        if(pthread_create(&cpu->workers[cpu->threads],NULL,worker,cpu)){
            cb1_lldv_cpu_destroy(cpu);
            return NULL;
        }
        cpu->threads++;
    }
    return cpu;
}

bool cb1_lldv_cpu_submit(struct cb1_lldv_cpu *cpu, const struct cb1_lldv_cpu_frame *frame)
{
    if(!cpu || !frame || !frame->linear || !frame->carrier ||
       (uintptr_t)frame->carrier%32 || frame->stride<W*sizeof(*frame->carrier) ||
       frame->stride%32 || frame->stride>SIZE_MAX/H ||
       !isfinite(frame->peak_nits) || frame->peak_nits<=0 || frame->peak_nits>10000 ||
       (frame->bits!=10 && frame->bits!=12) ||
       ((frame->first_row || frame->end_row) &&
        (frame->first_row>=frame->end_row || frame->end_row>H)))
        return false;

    pthread_mutex_lock(&cpu->lock);
    const bool ready=!cpu->running;
    if(ready){
        cpu->frame=*frame;
        if(frame->to_bt2020){
            memcpy(cpu->matrix,frame->to_bt2020,sizeof(cpu->matrix));
            cpu->frame.to_bt2020=cpu->matrix;
        }
        cpu->peak_scale=frame->peak_nits/10000.0f;
        atomic_store_explicit(&cpu->next_row,0,memory_order_relaxed);
        cpu->running=cpu->threads;
        cpu->generation++;
        pthread_cond_broadcast(&cpu->wake);
    }
    pthread_mutex_unlock(&cpu->lock);
    return ready;
}

bool cb1_lldv_cpu_ready(struct cb1_lldv_cpu *cpu, bool wait)
{
    if(!cpu)return false;
    pthread_mutex_lock(&cpu->lock);
    while(cpu->running && wait)pthread_cond_wait(&cpu->wake,&cpu->lock);
    const bool ready=!cpu->running;
    pthread_mutex_unlock(&cpu->lock);
    return ready;
}

void cb1_lldv_cpu_destroy(struct cb1_lldv_cpu *cpu)
{
    if(!cpu)return;
    cb1_lldv_cpu_ready(cpu,true);
    pthread_mutex_lock(&cpu->lock);
    cpu->closing=true;
    pthread_cond_broadcast(&cpu->wake);
    pthread_mutex_unlock(&cpu->lock);
    for(unsigned i=0;i<cpu->threads;i++)
        pthread_join(cpu->workers[i],NULL);
    pthread_cond_destroy(&cpu->wake);
    pthread_mutex_destroy(&cpu->lock);
    free(cpu);
}
#else
#include <stddef.h>

struct cb1_lldv_cpu *cb1_lldv_cpu_create(unsigned threads)
{
    (void)threads;
    return NULL;
}

bool cb1_lldv_cpu_submit(struct cb1_lldv_cpu *cpu, const struct cb1_lldv_cpu_frame *frame)
{
    (void)cpu;
    (void)frame;
    return false;
}

bool cb1_lldv_cpu_ready(struct cb1_lldv_cpu *cpu, bool wait)
{
    (void)cpu;
    (void)wait;
    return false;
}

void cb1_lldv_cpu_destroy(struct cb1_lldv_cpu *cpu)
{
    (void)cpu;
}
#endif

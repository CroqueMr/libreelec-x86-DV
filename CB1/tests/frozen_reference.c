/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Synthetic profile-category probes, not bitstream or licensed-DV conformance. */
#define main inherited_lifecycle_main
#include "render_lifecycle.c"
#undef main

static AVDOVIMetadata *reference_metadata(int category, size_t *bytes)
{
    AVDOVIMetadata *m = av_dovi_metadata_alloc(bytes);
    assert(m);
    AVDOVIRpuDataHeader *h = av_dovi_get_header(m);
    h->bl_bit_depth = h->el_bit_depth = h->vdr_bit_depth = 10;
    h->coef_log2_denom = 12;
    h->disable_residual_flag = category == 0 || category == 3;
    h->bl_video_full_range_flag = category == 0;
    AVDOVIColorMetadata *color = av_dovi_get_color(m);
    color->signal_eotf = 65535;
    color->signal_color_space = category == 0 ? 2 : 0;
    color->signal_bit_depth = 10;
    color->source_max_pq = 3696;
    for (int i = 0; i < 9; ++i) {
        color->ycc_to_rgb_matrix[i] = (AVRational){i % 4 == 0, 1};
        color->rgb_to_lms_matrix[i] = (AVRational){i % 4 == 0, 1};
    }
    AVDOVIDataMapping *map = av_dovi_get_mapping(m);
    map->nlq_method_idc = AV_DOVI_NLQ_LINEAR_DZ;
    for (int c = 0; c < 3; ++c) {
        color->ycc_to_rgb_offset[c] = (AVRational){0, 1};
        AVDOVIReshapingCurve *curve = &map->curves[c];
        curve->num_pivots = 2;
        curve->pivots[1] = 1023;
        curve->mapping_idc[0] = AV_DOVI_MAPPING_POLYNOMIAL;
        curve->poly_order[0] = category == 0 ? 2 : 1;
        curve->poly_coef[0][category == 0 ? 2 : 1] = 4096;
        if (category == 1)
            map->nlq[c].vdr_in_max = 4096;
        if (category == 2) {
            map->nlq[c].nlq_offset = 512;
            map->nlq[c].linear_deadzone_slope = 1;
        }
    }
    m->num_ext_blocks = 2;
    AVDOVIDmData *l1 = av_dovi_get_ext(m, 0);
    l1->level = 1;
    l1->l1.min_pq = 12;
    l1->l1.avg_pq = 3079;
    l1->l1.max_pq = 4095;
    AVDOVIDmData *l6 = av_dovi_get_ext(m, 1);
    l6->level = 6;
    l6->l6.max_luminance = 4000;
    return m;
}

static void print_pixels(pl_gpu gpu, pl_tex tex)
{
    const int positions[][2] = {{1000,100}, {1400,500}, {1920,1080}, {2500,1700}, {2900,2100}};
    printf("[");
    for (unsigned i = 0; i < 5; ++i) {
        float pixel[4];
        read_pixel(gpu, tex, positions[i][0], positions[i][1], pixel);
        printf("%s[%.9g,%.9g,%.9g,%.9g]", i ? "," : "", pixel[0],pixel[1],pixel[2],pixel[3]);
    }
    printf("]");
}

int main(void)
{
    setvbuf(stdout,NULL,_IONBF,0);
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display, NULL, NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    EGLint attributes[] = {EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,0x40,EGL_NONE};
    EGLConfig config;
    EGLint count;
    assert(eglChooseConfig(display, attributes, &config, 1, &count) && count);
    EGLint sa[] = {EGL_WIDTH,64,EGL_HEIGHT,64,EGL_NONE};
    EGLint ca[] = {EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLSurface surface = eglCreatePbufferSurface(display, config, sa);
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, ca);
    assert(eglMakeCurrent(display,surface,surface,context));
    pl_log log = pl_log_create(PL_API_VER,pl_log_params(.log_cb=pl_log_simple,.log_priv=stderr,.log_level=PL_LOG_WARN));
    pl_opengl gl = pl_opengl_create(log, pl_opengl_params(
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,
        .egl_display=display,.egl_context=context,.allow_software=true));
    assert(gl);
    struct dvbridge_renderer *renderer = dvbridge_renderer_create(gl->gpu);
    assert(renderer);
    pl_fmt fmt = pl_find_fmt(gl->gpu, PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE);
    float pixels[64*64*4];
    for (int y=0;y<64;y++) for (int x=0;x<64;x++) for (int c=0;c<4;c++)
        pixels[(y*64+x)*4+c] = c==3 ? 1 : .15f + .65f*x/63 + .05f*y/63;
    pl_tex input = pl_tex_create(gl->gpu,pl_tex_params(.w=64,.h=64,.format=fmt,
        .sampleable=true,.initial_data=pixels));
    assert(input);
    pl_fmt efmt = pl_find_fmt(gl->gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR);
    assert(efmt);
    uint16_t el_pixels[32*32*4];
    for (int i=0;i<32*32*4;i++) el_pixels[i] = i%4==3 ? UINT16_MAX : 576<<6;
    pl_tex el = pl_tex_create(gl->gpu,pl_tex_params(.w=32,.h=32,.format=efmt,
        .sampleable=true,.initial_data=el_pixels));
    assert(el);
    struct pl_frame enhancement = {.num_planes=1,.repr.bits={16,10,6},
        .planes={{.texture=el,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,32,32}};
    struct pl_frame frame = {.num_planes=1,
        .planes={{.texture=input,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,64,64}};
    struct dvbridge_geometry geometry = {64,64,840,0,2160,2160};
    const char *names[] = {"P5","P7_MEL","P7_FEL","P8.1"};
    printf("{\"renderer\":\"%s\",\"cases\":[",glGetString(GL_RENDERER));
    for (int category=0;category<4;category++) {
        size_t bytes;
        AVDOVIMetadata *m = reference_metadata(category,&bytes);
        frame.enhancement_layer = category==2 ? &enhancement : NULL;
        double el_pts = category==2 ? 0 : NAN;
        dvbridge_renderer_reset(renderer);
        struct dvbridge_color mapped;
        assert(dvbridge_map_color(&mapped,m,bytes,category==2));
        struct dvbridge_context *probe = dvbridge_create();
        struct dvbridge_candidate *candidate = dvbridge_prepare(probe,m,bytes,0,geometry,category==2);
        assert(candidate);
        dvbridge_candidate_destroy(candidate);
        dvbridge_destroy(probe);
        assert(dvbridge_render_rgb(renderer,&frame,m,bytes,0,el_pts,geometry));
        unsigned packets;
        const uint32_t *words = dvbridge_packets(dvbridge_render_candidate(renderer),&packets);
        assert(words && packets>0 && packets<=4);
        printf("%s{\"category\":\"%s\",\"packet_count\":%u,\"packet_words\":[",category ? "," : "",names[category],packets);
        for (unsigned i=0;i<packets*128;i++) printf("%s%u",i ? "," : "",words[i]);
        printf("],\"native_pq\":");
        print_pixels(gl->gpu,dvbridge_render_texture(renderer));
        struct dvbridge_hdr10_session session;
        assert(dvbridge_hdr10_session_init(&session,m,bytes));
        assert(dvbridge_render_hdr10_rgb(renderer,&session,&frame,m,bytes,0,el_pts,geometry));
        printf(",\"hdr10_basic_pq\":");
        print_pixels(gl->gpu,dvbridge_render_texture(renderer));
        printf("}");
        av_free(m);
    }
    printf("]}\n");
    dvbridge_renderer_destroy(renderer);
    pl_tex_destroy(gl->gpu,&el);
    pl_tex_destroy(gl->gpu,&input);
    pl_opengl_destroy(&gl);
    pl_log_destroy(&log);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,context);
    eglDestroySurface(display,surface);
    eglTerminate(display);
    return 0;
}

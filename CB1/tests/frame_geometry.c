/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_core.h"
#include "task3_fixture.h"
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void rejected(AVDOVIMetadata *m, size_t bytes, struct dvbridge_geometry geometry)
{
    unsigned margins[4] = {11, 22, 33, 44}, previous[4];
    memcpy(previous, margins, sizeof(margins));
    assert(!dvbridge_frame_area(margins, m, bytes, geometry));
    assert(!memcmp(previous, margins, sizeof(margins)));
}

static void target_geometries(AVDOVIMetadata *m, size_t bytes)
{
#ifndef DVBRIDGE_TARGET_API
    assert(!"Geometry must use the actual output raster instead of fixed UHD");
#else
    unsigned margins[4];
    int raster_w=0,raster_h=0;
    assert(dvbridge_geometry_raster((struct dvbridge_geometry){.target_width=3,.target_height=3},
        &raster_w,&raster_h) && raster_w==3 && raster_h==3);
    struct dvbridge_geometry g = {3840,2160,0,0,1920,1080,1920,1080};
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=5,.l5={.top_offset=100,.bottom_offset=102}};
    assert(dvbridge_frame_area(margins,m,bytes,g));
    assert(margins[0]==0 && margins[1]==0 && margins[2]==50 && margins[3]==51);
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1800}};
    struct dvbridge_context *context=dvbridge_create();
    struct dvbridge_candidate *candidate=dvbridge_prepare_output(context,m,bytes,0,g,false,false);
    assert(candidate && dvbridge_active_area(candidate,margins));
    assert(margins[2]==50 && margins[3]==51);
    dvbridge_candidate_destroy(candidate);dvbridge_destroy(context);
    m->num_ext_blocks=0;
    g=(struct dvbridge_geometry){1920,800,0,186,2560,1067,2560,1440};
    assert(dvbridge_frame_area(margins,m,bytes,g));
    assert(margins[0]==0 && margins[1]==0 && margins[2]==186 && margins[3]==187);
    g=(struct dvbridge_geometry){1536,864,0,0,2560,1440,2560,1440};
    assert(dvbridge_frame_area(margins,m,bytes,g));
    assert(!margins[0] && !margins[1] && !margins[2] && !margins[3]);
    const int invalid[][2]={{1920,0},{0,1080},{-1920,1080},{1921,1080},{INT_MAX-1,INT_MAX}};
    for(unsigned i=0;i<sizeof(invalid)/sizeof(*invalid);i++){
        g.target_width=invalid[i][0];g.target_height=invalid[i][1];
        rejected(m,bytes,g);
    }
#endif
}

static void native_crop_geometries(AVDOVIMetadata *m,size_t bytes)
{
#if DVBRIDGE_TARGET_API < 2
    assert(!"Native crop and pixel ratio must not be recomputed as a full-frame aspect");
#else
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=5,
        .l5={.left_offset=490,.right_offset=500,.top_offset=30,.bottom_offset=40}};
    struct dvbridge_geometry g={1920,1080,960,0,1920,2160,3840,2160,
        {480,0,1440,1080}};
    unsigned margins[4];
    assert(dvbridge_frame_area(margins,m,bytes,g));
    assert(margins[0]==980 && margins[1]==1000 && margins[2]==60 && margins[3]==80);
    g.crop[0]=-1;rejected(m,bytes,g);
    g.crop[0]=1440;rejected(m,bytes,g);
    g.crop[0]=480;g.crop[2]=1921;rejected(m,bytes,g);
    g.crop[2]=1440;g.crop[3]=NAN;rejected(m,bytes,g);
#endif
}

int main(void)
{
    size_t bytes;
    AVDOVIMetadata *m = task3_fixture(&bytes);
    struct dvbridge_context *context = dvbridge_create();
    struct dvbridge_geometry geometry = {3840, 2160, 0, 0, 3840, 2160};
    unsigned margins[4] = {1, 1, 1, 1};
    assert(dvbridge_frame_area(margins, m, bytes, geometry));
    assert(margins[0] == 0 && margins[1] == 0 && margins[2] == 0 && margins[3] == 0);
    assert(!dvbridge_prepare(context, m, bytes, 1.0, geometry, false));
    assert(!dvbridge_frame_area(NULL, m, bytes, geometry));
    rejected(NULL, bytes, geometry);
    rejected(m, sizeof(*m) - 1, geometry);
    geometry = (struct dvbridge_geometry){1920, 1080, 960, 540, 1920, 1080};
    assert(dvbridge_frame_area(margins, m, bytes, geometry));
    assert(margins[0] == 960 && margins[1] == 960 && margins[2] == 540 && margins[3] == 540);
    m->num_ext_blocks = 1;
    AVDOVIDmData *e = av_dovi_get_ext(m, 0);
    e->level = 5;
    e->l5.left_offset = 10; e->l5.right_offset = 20;
    e->l5.top_offset = 30; e->l5.bottom_offset = 40;
    assert(dvbridge_frame_area(margins, m, bytes, geometry));
    assert(margins[0] == 970 && margins[1] == 980 && margins[2] == 570 && margins[3] == 580);
    /* Last valid source pixel on both axes must remain an active area. */
    e->l5.left_offset = 1919; e->l5.right_offset = 0;
    e->l5.top_offset = 1079; e->l5.bottom_offset = 0;
    assert(dvbridge_frame_area(margins, m, bytes, geometry));
    assert(margins[0] == 2879 && margins[1] == 960 && margins[2] == 1619 && margins[3] == 540);
    e->l5.left_offset = 1920;
    rejected(m, bytes, geometry);
    e->l5.left_offset = 1919; e->l5.top_offset = 1080;
    rejected(m, bytes, geometry);
    e->l5.left_offset = 10; e->l5.right_offset = 20;
    e->l5.top_offset = 30; e->l5.bottom_offset = 40;
    *av_dovi_get_ext(m, 1) = *e; m->num_ext_blocks = 2;
    rejected(m, bytes, geometry);
    m->num_ext_blocks = 1; e->l5.left_offset = 1920;
    rejected(m, bytes, geometry);
    e->l5.left_offset = 10; e->l5.right_offset = 1910;
    rejected(m, bytes, geometry);
    e->l5.right_offset = 20; e->l5.top_offset = 1080;
    rejected(m, bytes, geometry);
    e->l5.top_offset = 30; e->l5.bottom_offset = 1050;
    rejected(m, bytes, geometry);
    m->num_ext_blocks = 0;
    const struct dvbridge_geometry invalid[] = {
        {INT_MAX,2160,0,0,3840,2160}, {3840,INT_MAX,0,0,3840,2160},
        {3840,2160,INT_MAX,0,3840,2160}, {3840,2160,0,INT_MAX,3840,2160},
        {3840,2160,0,0,INT_MAX,2160}, {3840,2160,0,0,3840,INT_MAX},
        {0,2160,0,0,3840,2160}, {3840,2160,-2,0,3840,2160},
        {3840,2160,0,0,1920,2160}, {3840,2160,1,0,3838,2160},
        {3840,2160,0,0,3839,2160}, {3840,2160,2,0,3840,2160}};
    for (unsigned i = 0; i < sizeof(invalid) / sizeof(*invalid); ++i)
        rejected(m, bytes, invalid[i]);
    target_geometries(m,bytes);
    native_crop_geometries(m,bytes);
    av_free(m); dvbridge_destroy(context);
    puts("PASS: common geometry without transport, L5 and integer bounds, untouched failures");
}

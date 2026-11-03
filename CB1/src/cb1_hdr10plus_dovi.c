/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Weighted-percentile adaptation: Copyright (C) 2024 Team Kodi. */
#include "cb1_hdr10plus_dovi.h"
#include <math.h>
#include <string.h>

/* Scene comparison adapted from Hades under its GPL-2.0-or-later offer.
 * Weighted PQ percentiles adapted from AVDVPlus HistogramPlus, generalized to
 * validated percentile counts with constant endpoint tails. See LICENSES/. */
struct hdr10plus_l1 { unsigned max_measured, avg_measured; };

/* SMPTE ST 2084, on light in [0, 1] of 10000 cd/m2 */
#define PQ_M1 (2610.0 / 16384.0)
#define PQ_M2 (2523.0 / 4096.0 * 128.0)
#define PQ_C1 (3424.0 / 4096.0)
#define PQ_C2 (2413.0 / 4096.0 * 32.0)
#define PQ_C3 (2392.0 / 4096.0 * 32.0)

static double pq_from_linear(double y)
{
    y = y < 0 ? 0 : y > 1 ? 1 : y;
    const double p = pow(y, PQ_M1);
    return pow((PQ_C1 + PQ_C2 * p) / (1 + PQ_C3 * p), PQ_M2);
}

static unsigned code12(double e)
{
    const double c = floor(e * 4095 + 0.5);
    return c < 0 ? 0 : c > 4095 ? 4095 : (unsigned)c;
}

/* (a value of ST 2094-40 in [0, 1], in multiples of 0.00001) */
static bool value(AVRational q, double *v)
{
    if (q.den <= 0 || q.num < 0)
        return false;
    *v = av_q2d(q);
    return *v <= 1.0;
}

#define MAX_KNOTS 17

static bool metadata_statistics(const AVDynamicHDRPlus *m, struct hdr10plus_l1 *l1)
{
    if (!m || !l1 || m->num_windows < 1)
        return false;
    memset(l1, 0, sizeof(*l1));
    const AVHDRPlusColorTransformParams *w = &m->params[0];
    double peak = 0, average;
    for (int c = 0; c < 3; ++c) {
        double v;
        if (!value(w->maxscl[c], &v))
            return false;
        if (v > peak)
            peak = v;
    }
    if (!value(w->average_maxrgb, &average))
        return false;
    const unsigned n = w->num_distribution_maxrgb_percentiles;
    if (n < 1 || n > 15)
        return false;
    /* ST 2094-40 8.5.4: with ApplicationVersion 1, the entries at 5 and 10 are not part of the distribution (0 and
     * 0.00255); an encoder that writes version 0 with those two values exactly is taken the same way */
    double v1 = -1, v2 = -1;
    if (n >= 3) {
        value(w->distribution_maxrgb[1].percentile, &v1);
        value(w->distribution_maxrgb[2].percentile, &v2);
    }
    const bool reserved = n >= 3 && w->distribution_maxrgb[1].percentage == 5 &&
                          w->distribution_maxrgb[2].percentage == 10 &&
                          (m->application_version >= 1 || (v1 == 0 && fabs(v2 - 0.00255) < 1e-9));
    double ps[MAX_KNOTS], vs[MAX_KNOTS];
    unsigned k = 0, last_percentage = 0;
    ps[k] = 0;
    vs[k++] = 0; /* (set to the first percentile below) */
    for (unsigned i = 0; i < n; ++i) {
        const unsigned j = w->distribution_maxrgb[i].percentage;
        double v;
        if (j > 100 || (i && j <= last_percentage) || !value(w->distribution_maxrgb[i].percentile, &v))
            return false;
        last_percentage = j;
        if (reserved && (i == 1 || i == 2))
            continue;
        if (v > peak || (k > 1 && v < vs[k - 1]))
            return false; /* percentiles that go down describe no distribution */
        ps[k] = j == 99 ? 0.9998 : j / 100.0;
        vs[k++] = v;
    }
    if (k < 3)
        return false;
    vs[0] = vs[1];
    ps[k] = 1;
    vs[k] = peak > vs[k - 1] ? peak : vs[k - 1];
    ++k;

    /* Reject contradictory distributions, independently of the PQ estimator.
     * One source quantization step is allowed. */
    double minimum_mean = 0, maximum_mean = 0;
    for (unsigned i = 0; i + 1 < k; ++i) {
        const double width = ps[i + 1] - ps[i];
        minimum_mean += (i ? vs[i] : 0) * width;
        maximum_mean += vs[i + 1] * width;
    }
    if (average + 0.00001 < minimum_mean || average > maximum_mean + 0.00001)
        return false;

    double es[MAX_KNOTS];
    for (unsigned i = 0; i < k; ++i)
        es[i] = pq_from_linear(vs[i]);
    /* MaxSCL bounds the unseen tail for validation, but does not describe its
     * distribution. Keep that tail constant in the PQ mean estimate. */
    es[k - 1] = es[k - 2];
    double mean_pq = 0;
    for (unsigned i = 0; i + 1 < k; ++i)
        mean_pq += (ps[i + 1] - ps[i]) * (es[i] + es[i + 1]) / 2;
    l1->max_measured = code12(pq_from_linear(peak));
    l1->avg_measured = code12(mean_pq);
    return true;
}

static bool same_q(AVRational a, AVRational b)
{
    return a.den > 0 && b.den > 0 && av_cmp_q(a, b) == 0;
}

bool cb1_hdr10plus_dovi_same_scene(const AVDynamicHDRPlus *a, const AVDynamicHDRPlus *b)
{
    if (!a || !b || a->itu_t_t35_country_code != b->itu_t_t35_country_code ||
        a->application_version != b->application_version ||
        a->num_windows != b->num_windows ||
        !same_q(a->targeted_system_display_maximum_luminance, b->targeted_system_display_maximum_luminance))
        return false;
    const int windows = a->num_windows < 1 ? 1 : a->num_windows > 3 ? 3 : a->num_windows;
    for (int i = 0; i < windows; ++i) {
        const AVHDRPlusColorTransformParams *p = &a->params[i], *q = &b->params[i];
        for (int c = 0; c < 3; ++c)
            if (!same_q(p->maxscl[c], q->maxscl[c]))
                return false;
        if (!same_q(p->average_maxrgb, q->average_maxrgb) ||
            p->num_distribution_maxrgb_percentiles != q->num_distribution_maxrgb_percentiles)
            return false;
        for (int j = 0; j < p->num_distribution_maxrgb_percentiles && j < 15; ++j)
            if (p->distribution_maxrgb[j].percentage != q->distribution_maxrgb[j].percentage ||
                !same_q(p->distribution_maxrgb[j].percentile, q->distribution_maxrgb[j].percentile))
                return false;
        /* (hdr10plus_tool: the curve where it is carried, its profile B) */
        if (p->tone_mapping_flag != q->tone_mapping_flag)
            return false;
        if (p->tone_mapping_flag) {
            if (!same_q(p->knee_point_x, q->knee_point_x) || !same_q(p->knee_point_y, q->knee_point_y) ||
                p->num_bezier_curve_anchors != q->num_bezier_curve_anchors)
                return false;
            for (int j = 0; j < p->num_bezier_curve_anchors && j < 15; ++j)
                if (!same_q(p->bezier_curve_anchors[j], q->bezier_curve_anchors[j]))
                    return false;
        }
    }
    return true;
}



static unsigned effective(unsigned code,unsigned offset)
{
    double value=code+((int)offset-2048)*(4095.0/2048);
    return (unsigned)lround(fmax(0,fmin(4095,value)));
}

enum cb1_hdr10plus_dovi_status cb1_hdr10plus_dovi_describe(
    struct cb1_hdr10plus_dovi_result *out,const AVDynamicHDRPlus *source,
    const struct cb1_l1l3 *estimate)
{
    if(!out || !source || source->itu_t_t35_country_code!=0xb5 ||
       source->application_version>1 || !source->num_windows || source->num_windows>3 ||
       (estimate && (estimate->l1_min>estimate->l1_avg || estimate->l1_avg>estimate->l1_max ||
       !estimate->l1_max || estimate->l1_max>4095 || estimate->l3_min>4095 ||
       estimate->l3_max>4095 || estimate->l3_avg>4095)))return CB1_HDR10PLUS_DOVI_INVALID;
    if(source->num_windows!=1)return CB1_HDR10PLUS_DOVI_UNSUPPORTED;
    unsigned peak_code=0;
    for(unsigned i=0;i<3;i++){
        AVRational value=source->params[0].maxscl[i];
        if(value.den<=0 || value.num<0 || value.num>value.den)return CB1_HDR10PLUS_DOVI_INVALID;
        uint64_t scaled=(uint64_t)value.num*100000;
        if(scaled%value.den)return CB1_HDR10PLUS_DOVI_INVALID;
        unsigned code=scaled/value.den;
        if(code>peak_code)peak_code=code;
    }
    const AVRational average=source->params[0].average_maxrgb;
    if(average.den<=0 || average.num<0 || average.num>average.den ||
       (peak_code && (uint64_t)average.num*100000>(uint64_t)peak_code*average.den))
        return CB1_HDR10PLUS_DOVI_INVALID;
    struct cb1_hdr10plus_dovi_result r={.estimated_fields=7,
        .untranslated_curve=source->params[0].tone_mapping_flag!=0,
        .untranslated_saturation=source->params[0].color_saturation_mapping_flag!=0};
    if(source->params[0].num_distribution_maxrgb_percentiles){
        const AVHDRPlusColorTransformParams *window=&source->params[0];
        if(window->num_distribution_maxrgb_percentiles>15)return CB1_HDR10PLUS_DOVI_INVALID;
        for(unsigned i=0;i<window->num_distribution_maxrgb_percentiles;i++){
            const AVHDRPlusPercentile *p=&window->distribution_maxrgb[i];
            if(p->percentage>100 || (i && p->percentage<=window->distribution_maxrgb[i-1].percentage) ||
               p->percentile.den<=0 || p->percentile.num<0 || p->percentile.num>p->percentile.den)
                return CB1_HDR10PLUS_DOVI_INVALID;
        }
        struct hdr10plus_l1 stats;
        if(metadata_statistics(source,&stats) && stats.max_measured){
            r.metadata=(struct cb1_l1l3){0,stats.max_measured,
                stats.avg_measured>stats.max_measured?stats.max_measured:stats.avg_measured,2048,2048,2048};
            r.source_fields=CB1_HDR10PLUS_DOVI_MAX|CB1_HDR10PLUS_DOVI_AVG;
            r.estimated_fields=CB1_HDR10PLUS_DOVI_MIN;
            *out=r;
            return CB1_HDR10PLUS_DOVI_OK;
        }
    }
    if(!estimate && !peak_code)return CB1_HDR10PLUS_DOVI_UNSUPPORTED;
    r.metadata=estimate ? *estimate : (struct cb1_l1l3){0};
    if(peak_code){
        /* MaxSCL is normalized linear light with 1 == 10000 nits. */
        double x=pow(peak_code/100000.0,2610.0/16384);
        unsigned maximum=(unsigned)lround(4095*pow((3424.0/4096+2413.0/128*x)/
            (1+2392.0/128*x),2523.0/32));
        if(!maximum)return CB1_HDR10PLUS_DOVI_UNSUPPORTED;
        unsigned minimum=estimate ? effective(estimate->l1_min,estimate->l3_min) : 0;
        /* AVDVPlus continuation for an unusable histogram. This is an estimate,
         * not mean(PQ) reconstructed from the authored distribution. */
        unsigned average=estimate ? effective(estimate->l1_avg,estimate->l3_avg) :
            code12(pq_from_linear(av_q2d(source->params[0].average_maxrgb)));
        if(average>maximum)average=maximum;
        if(minimum>average)minimum=average;
        r.metadata=(struct cb1_l1l3){minimum,maximum,average,2048,2048,2048};
        r.source_fields=CB1_HDR10PLUS_DOVI_MAX;
        r.estimated_fields=CB1_HDR10PLUS_DOVI_MIN|CB1_HDR10PLUS_DOVI_AVG;
    }
    *out=r;
    return CB1_HDR10PLUS_DOVI_OK;
}

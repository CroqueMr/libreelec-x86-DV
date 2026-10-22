/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

/* Only the state fields read by the production admission function. */
typedef uint8_t u8;
enum { DRM_MODE_CONNECTOR_HDMIA=11, HDMI_EOTF_SMPTE_ST2084=2,
       DRM_MODE_COLORIMETRY_BT2020_RGB=9, DRM_MODE_COLORIMETRY_BT2020_YCC=10 };
struct drm_property_blob { size_t length; void *data; };
struct hdr_output_metadata { unsigned metadata_type; struct { u8 eotf, metadata_type; } hdmi_metadata_type1; };
struct drm_display_info { bool hdr10plus_supported; unsigned hdr10plus_version; };
struct drm_connector { struct drm_display_info display_info; unsigned connector_type; };
struct drm_connector_state {
    struct drm_connector *connector;
    void *crtc;
    unsigned max_bpc,colorspace;
    struct drm_property_blob *hdr_output_metadata,*hdr10plus_metadata;
};
#include "connector_check.inc"

int main(void)
{
    struct drm_connector c={{true,1},DRM_MODE_CONNECTOR_HDMIA};
    struct hdr_output_metadata hdr={0,{2,0}};
    uint8_t packet[31]={0}; packet[7]=0x40;
    struct drm_property_blob static_blob={sizeof(hdr),&hdr},dynamic_blob={31,packet};
    struct drm_connector_state s={&c,&c,10,DRM_MODE_COLORIMETRY_BT2020_RGB,&static_blob,NULL};
    assert(!drm_connector_check_hdr10plus(&s));
    s.hdr10plus_metadata=&dynamic_blob;
    assert(!drm_connector_check_hdr10plus(&s));
    s.max_bpc=8; assert(drm_connector_check_hdr10plus(&s)==-EINVAL); s.max_bpc=10;
    s.crtc=NULL; assert(drm_connector_check_hdr10plus(&s)==-EINVAL); s.crtc=&c;
    c.connector_type=10; assert(drm_connector_check_hdr10plus(&s)==-EINVAL); c.connector_type=11;
    c.display_info.hdr10plus_supported=false;
    assert(drm_connector_check_hdr10plus(&s)==-EINVAL); c.display_info.hdr10plus_supported=true;
    c.display_info.hdr10plus_version=0;
    assert(drm_connector_check_hdr10plus(&s)==-EINVAL); packet[7]=0;
    assert(!drm_connector_check_hdr10plus(&s));
    hdr.hdmi_metadata_type1.eotf=3; assert(drm_connector_check_hdr10plus(&s)==-EINVAL);
    hdr.hdmi_metadata_type1.eotf=2; hdr.metadata_type=1;
    assert(drm_connector_check_hdr10plus(&s)==-EINVAL); hdr.metadata_type=0;
    hdr.hdmi_metadata_type1.metadata_type=1;
    assert(drm_connector_check_hdr10plus(&s)==-EINVAL); hdr.hdmi_metadata_type1.metadata_type=0;
    s.colorspace=0; assert(drm_connector_check_hdr10plus(&s)==-EINVAL);
    s.colorspace=DRM_MODE_COLORIMETRY_BT2020_YCC; assert(!drm_connector_check_hdr10plus(&s));
    static_blob.length--; assert(drm_connector_check_hdr10plus(&s)==-EINVAL);
    s.hdr_output_metadata=NULL; assert(drm_connector_check_hdr10plus(&s)==-EINVAL);
    s.hdr10plus_metadata=NULL; assert(!drm_connector_check_hdr10plus(&s));
    puts("hdr10plus connector admission: pass");
}

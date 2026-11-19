/* SPDX-License-Identifier: MIT */
#include <libavutil/dovi_meta.h>
int main(void)
{
    AVDOVIDmData d = {0};
    d.dvbridge_raw_magic = 0x41424456;
    d.dvbridge_original_length = sizeof(d.dvbridge_original_bytes);
    return d.dvbridge_original_bytes[0];
}

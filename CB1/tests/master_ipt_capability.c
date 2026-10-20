/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task3_fixture.h"
#include "cb1_circuit.h"
#include "cb1_master_ipt.h"
#include "dvbridge_metadata.h"
#include "dvbridge_policy.h"
#include "dvbridge_render.h"

int main(void)
{
    struct dvbridge_policy policy={.mode=DVBRIDGE_MODE_MASTER_REFERENCE};
    assert(dvbridge_policy_validate(&policy)==DVBRIDGE_POLICY_VALID);
    assert(cb1_circuit_version(CB1_DV_DV_MASTER_REFERENCE));
    policy.master_ipt=true;
#ifdef CB1_ENABLE_MASTER_IPT
    assert(dvbridge_policy_validate(&policy)==DVBRIDGE_POLICY_VALID);
    assert(cb1_circuit_version(CB1_DV_DV_MASTER_IPT));
    assert(CB1_MASTER_IPT_API && DVBRIDGE_IPT_OUTPUT_API && DVBRIDGE_MASTER_IPT_API);
#else
    assert(dvbridge_policy_validate(&policy)==DVBRIDGE_POLICY_INVALID_VALUE);
    assert(!cb1_circuit_version(CB1_DV_DV_MASTER_IPT));
#if defined(CB1_MASTER_IPT_API) || defined(DVBRIDGE_IPT_OUTPUT_API) || defined(DVBRIDGE_MASTER_IPT_API)
    assert(!"Disabled IPT must not advertise entry points");
#endif
    size_t bytes;
    AVDOVIMetadata *metadata=task3_fixture(&bytes);
    metadata->num_ext_blocks=1;
    *av_dovi_get_ext(metadata,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1200}};
    struct dvbridge_dv state={0};
    unsigned margins[4]={0};
    assert(dvbridge_dv_metadata(&state,metadata,0,margins));
    state.ipt_transport=true;
    assert(!dvbridge_dv_metadata(&state,metadata,0,margins));
    av_free(metadata);
#endif
    puts("PASS Master IPT compile capability and fail-closed policy");
}

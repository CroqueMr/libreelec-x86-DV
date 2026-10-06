/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_policy.h"
#include <assert.h>
#include <stdio.h>

int main(void)
{
    const struct dvbridge_identity a = {UINT64_MAX, UINT64_MAX - 1, UINT64_MAX};
    struct dvbridge_identity b = a;
    assert(dvbridge_identity_equal(&a, &b));
    --b.revision; assert(!dvbridge_identity_equal(&a, &b));
    b = a; ++b.picture; assert(!dvbridge_identity_equal(&a, &b));
    b = a; --b.stream; assert(!dvbridge_identity_equal(&a, &b));
    assert(!dvbridge_identity_equal(NULL, &a));
    assert(!dvbridge_identity_equal(&a, NULL));
    assert(!dvbridge_identity_equal(NULL, NULL));
    puts("PASS: exact stream, picture and policy revision equality");
}

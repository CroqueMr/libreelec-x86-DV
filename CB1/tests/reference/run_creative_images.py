# SPDX-License-Identifier: GPL-3.0-only
"""Compare real Expert gray intensity with its public anchored PQ curve."""
import json
import subprocess
import sys


def nits(pq):
    x = max(pq, 0)**(32/2523)
    return 10000*(max(x-3424/4096, 0)/(2413/128-2392/128*x))**(16384/2610)


def pq(nits):
    x = (max(nits, 0)/10000)**(2610/16384)
    return ((3424/4096+2413/128*x)/(1+2392/128*x))**(2523/32)


result = subprocess.run([sys.argv[1]], capture_output=True, text=True)
assert result.returncode == 0, result.stderr
data = json.loads(result.stdout.splitlines()[0])
maximum = 0
for before, actual in zip(data['neutral'], data['trimmed']):
    # Independent curve oracle, not the previous RGB SOP. Both endpoints
    # are fixed; positive power bends the middle down without clipping black.
    high = pq(800)
    power = (2600-2048)/2048
    expected = []
    for value in before:
        x = value/high
        expected.append(high*(x-4*power*x**3*(1-x)**3))
    error = max(abs(a-b) for a, b in zip(actual, expected))
    maximum = max(maximum, error)
    assert error <= 1e-5, (actual, expected, error)
print('PASS independent anchored-PQ Expert curve; maximum PQ error', maximum)

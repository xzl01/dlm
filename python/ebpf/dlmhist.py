#!/usr/bin/python
#
# This example shows how to capture latency between a dlm_lock() kernel
# call for DLM_LOCK_EX requests with flag DLM_LKF_NOQUEUE and the ast
# response.
#
# You will probably see two line peaks, one in case of that the current
# node is the lock master and another one which requires network
# communication. There is currently no way to filter them out, so the
# second peak is interessting to get an idea what time it takes to
# call dlm_lock() and get a response back.

from bcc import BPF

import threading

b = BPF(text="""
#include <uapi/linux/ptrace.h>
#include <uapi/linux/dlm.h>

BPF_HASH(start, u32);
BPF_HISTOGRAM(dist, u64);

#define DLM_HASH(args) (args->ls_id ^ args->lkb_id)

TRACEPOINT_PROBE(dlm, dlm_lock_start)
{
    u64 ts = bpf_ktime_get_ns();
    u32 hash = DLM_HASH(args);

    if (args->flags & DLM_LKF_NOQUEUE &&
        args->mode == DLM_LOCK_EX)
        start.update(&hash, &ts);

    return 0;
}

TRACEPOINT_PROBE(dlm, dlm_lock_end)
{
    u32 hash = DLM_HASH(args);

    if (args->error != 0)
        start.delete(&hash);

    return 0;
}

TRACEPOINT_PROBE(dlm, dlm_ast)
{
    u32 hash = DLM_HASH(args);
    u64 *tsp, delta;

    tsp = start.lookup(&hash);
    if (tsp != 0) {
        start.delete(&hash);
        delta = bpf_ktime_get_ns() - *tsp;

        if (args->sb_status != 0)
            return 0;

        dist.increment(bpf_log2l(delta));
    }

    return 0;
}
""")

print("Tracing... Hit Ctrl-C anytime to end.")

forever = threading.Event()
try:
    forever.wait()
except KeyboardInterrupt:
    print()

print("log2 histogram")
print("--------------")
b["dist"].print_log2_hist("ns")

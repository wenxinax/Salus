# -*- coding: future_fstrings -*-
"""
JCT for fairness scheduler
"""
from __future__ import absolute_import, print_function, division

from benchmarks.driver.server.config import presets
from benchmarks.driver.workload import WTL
from benchmarks.exps import run_seq, parse_actions_from_cmd


def main(argv):
    scfg = presets.MostEfficient

    if argv:
        run_seq(scfg.copy(output_dir="templogs"),
                *parse_actions_from_cmd(argv))
        return

    run_seq(scfg.copy(output_dir="templogs/makespan_3of"),
            WTL.create("overfeat", 50, 424),
            WTL.create("overfeat", 50, 424),
            WTL.create("overfeat", 50, 424),
            )

    run_seq(scfg.copy(output_dir="templogs/makespan_3res"),
            WTL.create("resnet50", 50, 265),
            WTL.create("resnet50", 50, 265),
            WTL.create("resnet50", 50, 265),
            )
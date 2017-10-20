#! /bin/env python
from __future__ import print_function, absolute_import, division

import os
import argparse
from collections import defaultdict
from functools import wraps

try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path  # python 2 backport

import matplotlib as mpl
import matplotlib.pyplot as plt

import parse_log as pl
import parse_nvvp as pn


cases = defaultdict(list)


def plotter(name):
    def plotter_decorator(func):
        filename = func.__name__.lstrip('plot_').replace('_', '-')

        @wraps(func)
        def wrapped(config):
            local_dir = os.path.join(config.log_dir, name)
            log_file = os.path.join(local_dir, 'alloc.output')
            iter_file = os.path.join(local_dir, 'mem-iter.output')
            logs = pl.load_file(log_file)
            sessstart, iters = pn.parse_iterations(iter_file)
            fig = func(config, local_dir, logs, iters)
            fig.set_size_inches(2.35, 2.35, forward=True)
            return fig

        cases[name].append((wrapped, filename))

        return wrapped

    return plotter_decorator


@plotter('conv25')
def plot_mem_conv25(config, local_dir, logs, iters):
    def smoother(ss):
        return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('conv50')
def plot_mem_conv50(config, local_dir, logs, iters):
    def smoother(ss):
        return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('conv100')
def plot_mem_conv100(config, local_dir, logs, iters):
    def smoother(ss):
        return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('mnist25')
def plot_mem_mnist25(config, local_dir, logs, iters):
    def smoother(ss):
        return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('mnist50')
def plot_mem_mnist50(config, local_dir, logs, iters):
    def smoother(ss):
        return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('mnist100')
def plot_mem_mnist100(config, local_dir, logs, iters):
    def smoother(ss):
        return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('vgg25')
def plot_mem_vgg25(config, local_dir, logs, iters):
    def smoother(ss):
        return ss
        # return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('vgg50')
def plot_mem_vgg50(config, local_dir, logs, iters):
    def smoother(ss):
        return ss
        # return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('vgg100')
def plot_mem_vgg100(config, local_dir, logs, iters):
    def smoother(ss):
        return ss
        # return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('res25')
def plot_mem_res25(config, local_dir, logs, iters):
    def smoother(ss):
        return ss
        # return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('res50')
def plot_mem_res50(config, local_dir, logs, iters):
    def smoother(ss):
        return ss
        # return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('res75')
def plot_mem_res75(config, local_dir, logs, iters):
    def smoother(ss):
        return ss
        # return ss.ewm(span=15).mean()

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('ptbT')
def plot_mem_ptbT(config, local_dir, logs, iters):
    def smoother(ss):
        return ss

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('ptbS')
def plot_mem_ptbS(config, local_dir, logs, iters):
    def smoother(ss):
        return ss

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('ptbM')
def plot_mem_ptbM(config, local_dir, logs, iters):
    def smoother(ss):
        return ss

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('ptbL')
def plot_mem_ptbL(config, local_dir, logs, iters):
    def smoother(ss):
        return ss

    df, _, fig = pl.memory_usage(logs, iter_times=iters[0:10],
                                 mem_type='GPU_0_bfc', smoother=smoother)
    return fig


@plotter('mix6')
def plot_mem_mix6(config, local_dir, logs, iters):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cases', nargs='*', metavar='CASE',
                        help='Case names to generate figures',
                        default=cases.keys())
    parser.add_argument('--log_dir',
                        help='Base directory containing logs',
                        default='logs')
    parser.add_argument('--save_dir',
                        help='Directory to generate outputs',
                        default='figures')
    parser.add_argument('--show', action='store_true', default=False,
                        help='Show figure instead of generate images')
    config = parser.parse_args()

    Path(config.save_dir).mkdir(exist_ok=True)

    # configure matplotlib style
    if config.show:
        plt.style.use('seaborn')
    else:
        plt.style.use('seaborn-paper')
        rc = {
            'font.family': 'Times New Roman',
            'font.weight': 'book',
            'font.size': 10,
            'axes.spines.top': False,
            'axes.spines.right': False,
            'figure.figsize': (3.45, 3.45),
            'figure.dpi': 600,
            'figure.autolayout': True,
            'savefig.transparent': True,
        }
        mpl.rcParams.update(rc)

    for name in config.cases:
        for f, filename in cases[name]:
            print("Generating " + filename)
            fig = f(config)
            if config.show:
                plt.show()
            else:
                fig.savefig(os.path.join(config.save_dir, filename + '.pdf'), transparent=True)


if __name__ == '__main__':
    main()

from __future__ import absolute_import, print_function, division
from builtins import super, str
from future.utils import with_metaclass

import os
from absl import flags
from abc import ABCMeta, abstractmethod
from collections import namedtuple
from enum import Enum
from typing import Iterable, Tuple, Union

from . import workload
from .server import SalusServer
from .utils import Popen, execute
from .utils.compatiblity import Path, DEVNULL

FLAGS = flags.FLAGS

flags.DEFINE_string('tfbench_base', '../../tf_benchmarks', 'Base dir of TFBenchmark based workloads')
flags.DEFINE_string('unit_base', '../tests', 'Base dir of unittest based workloads')
flags.DEFINE_string('fathom_base', '../../fathom', 'Base dir of Fathom based workloads')


RunConfig = namedtuple('RunConfig', [
    'batch_size',
    'batch_num',
    'cfgname',
])


class Executor(Enum):
    Salus = "salus"
    TF = "tf"


def enumerate_rcfgs(batch_sizes, batch_nums):
    # type: (Iterable[Union[int, str]], Iterable[int]) -> Iterable[RunConfig]
    """Convenient method to generate a list of RunConfig"""
    return [
        RunConfig(batch_size, batch_num, None)
        for batch_size in batch_sizes
        for batch_num in batch_nums
    ]


class Runner(with_metaclass(ABCMeta, object)):
    """A runner knows how to run a given workload"""
    def __init__(self, wl):
        # type: (workload.Workload) -> None
        super().__init__()
        self.wl = wl
        self.env = os.environ.copy()
        self.env['CUDA_VISIBLE_DEVICES'] = '0,1'
        self.env['TF_CPP_MIN_LOG_LEVEL'] = '4'

    @abstractmethod
    def __call__(self, executor, output_file):
        # type: (Executor, Path) -> Popen
        pass


class TFBenchmarkRunner(Runner):
    """Run a tf benchmark job"""

    def __init__(self, wl, base_dir=None):
        # type: (workload.Workload, Path) -> None
        super().__init__(wl)
        self.base_dir = base_dir
        if self.base_dir is None:
            self.base_dir = Path(FLAGS.tfbench_base)

    def __call__(self, executor, output_file):
        # type: (Executor, Path) -> Popen
        cwd = self.base_dir / 'scripts' / 'tf_cnn_benchmarks'
        cmd = [
            'stdbuf', '-o0', '-e0', '--',
            'python', 'tf_cnn_benchmarks.py',
            '--display_every=1',
            '--num_gpus=1',
            '--variable_update=parameter_server',
            '--nodistortions',
            '--executor={}'.format(executor),
            '--num_batches={}'.format(self.wl.batch_num),
            '--batch_size={}'.format(self.wl.batch_size),
            '--model={}'.format(self.wl.name),
        ]
        output_file.parent.mkdir(exist_ok=True, parents=True)
        with output_file.open('w') as f:
            return execute(cmd, cwd=cwd, env=self.env, stdout=f, stderr=DEVNULL)


class UnittestRunner(Runner):
    """Run a unittest job"""

    def __init__(self, wl, base_dir=None):
        # type: (workload.Workload, Path) -> None
        super().__init__(wl)
        self.base_dir = base_dir
        if self.base_dir is None:
            self.base_dir = Path(FLAGS.unit_base)

    def __call__(self, executor, output_file):
        # type: (Executor, Path) -> Popen
        cwd = self.base_dir
        pkg, method = self._construct_test_name(executor)
        cmd = [
            'stdbuf', '-o0', '-e0', '--',
            'python', '-m', pkg, method,
        ]
        output_file.parent.mkdir(exist_ok=True, parents=True)
        with output_file.open('w') as f:
            return execute(cmd, cwd=cwd, env=self.env, stdout=f, stderr=DEVNULL)

    def _construct_test_name(self, executor):
        # type: (Executor) -> Tuple[str, str]
        """Construct test class and name from RunConfig"""
        supported_model = {
            'seq2seq': ('test_tf.test_seq', 'TestSeqPtb', {
                'small': '1_small',
                'medium': '2_medium',
                'large': '3_large',
            })
        }

        if executor == Executor.Salus:
            prefix = 'test_rpc_'
        elif executor == Executor.TF:
            prefix = 'test_gpu_'
        else:
            raise ValueError(f'Unknown executor: {executor}')

        pkg, cls, names = supported_model[self.wl.name]
        method = '{}.{}{}'.format(cls, prefix, names[self.wl.batch_size])
        return pkg, method


class FathomRunner(Runner):
    """Run a fathom job"""

    def __init__(self, wl, base_dir=None):
        super().__init__(wl)
        self.base_dir = base_dir
        if self.base_dir is None:
            self.base_dir = FLAGS.fathom_base

    def __call__(self, executor, output_file):
        # type: (Executor, Path) -> Popen
        cwd = self.base_dir
        cmd = [
            'stdbuf', '-o0', '-e0', '--',
            'python', '-m', 'fathom.cli',
            '--workload', self.wl.name,
            '--action', 'train',
            '--num_iters', self.wl.batch_num,
            '--batch_size', self.wl.batch_size,
            '--dev', '/gpu:0',
        ]
        if executor == Executor.Salus:
            cmd += ['--target', SalusServer.current_server().endpoint]
        elif executor == Executor.TF:
            pass
        else:
            raise ValueError(f'Unknown executor: {executor}')

        output_file.parent.mkdir(exist_ok=True, parents=True)
        with output_file.open('w') as f:
            return execute(cmd, cwd=cwd, env=self.env, stdout=f, stderr=DEVNULL)
from __future__ import print_function, absolute_import, division

import re
from datetime import datetime
from collections import defaultdict

import pandas as pd
import seaborn as sns
import numpy as np
import matplotlib.pyplot as plt


ptn_exec = re.compile(r"""^\[(?P<timestamp>\d+-\d+-\d+\s\d+:\d+:\d+\.\d{6})\d{3}\]\s
                           \[(?P<thread>\d+)\]\s
                           \[(?P<loc>\w+)\]\s
                           \[(?P<level>\w+)\]\s
                           (?P<content>.*)$""",
                      re.VERBOSE)

ptn_tf = re.compile(r"""^.*(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{6}):\s  # time
                         (?P<level>\w)\s
                         (?P<loc>.+)\]\s
                         \[(?P<thread>\d+)\]\s
                         (?P<content>.*)$""", re.VERBOSE)


class Log(object):
    """Collection of logs"""
    def __init__(self, arg):
        super(Log, self).__init__()
        self.arg = arg


class Entry(object):
    """Base class for log entry"""
    def __init__(self, g, entry_type):
        super(Entry, self).__init__()

        self.entry_type = entry_type

        self.timestamp = datetime.strptime(g['timestamp'], '%Y-%m-%d %H:%M:%S.%f')
        self.thread = int(g['thread'])
        self.loc = g['loc']
        self.level = g['level']
        self.raw_content = g['content']

    def __repr__(self):
        return 'Entry{}'.format(self.__dict__.__repr__())

    def update(self, content):
        """append content"""
        self.raw_content += '\n' + content

    def finalize(self):
        if self.entry_type == 'exec':
            d = match_exec_content(self.raw_content, self)
        elif self.entry_type == 'tf':
            d = match_tf_content(self.raw_content, self)
        else:
            raise ValueError('Unknown entry type: "{}"'.format(self.entry_type))

        if 'type' not in d:
            d['type'] = 'unknown'

        del self.raw_content
        self.__dict__.update(d)
        return self


def load_file(path):
    """Load logs"""
    logs = []

    with open(path) as f:
        entry = None
        for line in f:
            line = line.rstrip('\n')

            m = ptn_exec.match(line)
            if m:
                if entry:
                    logs.append(entry.finalize())
                    entry = None
                # executor line
                entry = Entry(m.groupdict(), 'exec')
                continue

            m = ptn_tf.match(line)
            if m:
                if entry:
                    logs.append(entry.finalize())
                    entry = None
                # tf line
                entry = Entry(m.groupdict(), 'tf')
                continue

            # assume it belongs to previous line
            if entry:
                entry.update(line)
            else:
                print('Unhandled line: ' + line)
    return logs


def load_both(exec_file, tf_file):
    print('Loading ', exec_file)
    log1 = load_file(exec_file)
    print('Loaded {} entries'.format(len(log1)))

    print('Loading ', tf_file)
    log2 = load_file(tf_file)
    print('Loaded {} entries'.format(len(log2)))

    print('Merging...')
    logs = log1 + log2
    for seq, info in seq_info.items():
        if 'recv_evenlop' in info and 'tf_send_evenlop' in info:
            sending = (info['recv_evenlop'].timestamp - info['tf_send_evenlop'].timestamp).total_seconds()
            info['recv_evenlop'].travel_time = sending
        else:
            print('Either recv_evenlop or tf_send_evenlop missing in info:', info)

        if 'tf_rpc_return' in info and 'resp_sent' in info:
            replying = (info['tf_rpc_return'].timestamp - info['resp_sent'].timestamp).total_seconds()
            info['tf_rpc_return'].travel_time = replying
        else:
            print('Either tf_rpc_return or resp_sent missing in info:', info)

    return logs


thread_seq_map = {}
tf_thread_seq_map = {}
seq_info = defaultdict(dict)
blocks = {}
thread_alloc_type_map = {}


ptn_recv_frame = re.compile(r"""Received \w+ frame( \d+)?: zmq::message_t\(len=(?P<size>\d+),.*""")
ptn_recv_evenlop = re.compile(r"""Received request evenlop: .+type='executor.(?P<req_type>\w+)', seq=(?P<seq>\d+),.*""")
ptn_create_opkernel = re.compile(r"""Created OpKernel for seq (?P<seq>\d+)""")
ptn_running = re.compile(r"""running(?P<async> async)? in thread \d+""")
ptn_compute_done = re.compile(r"""OpKernel->Compute finished with status.*""")
ptn_compute_async_done = re.compile(r"""OpKernel->ComputeAsync for seq (?P<seq>\d+) finished with status.*""")
ptn_resp_sent = re.compile(r"""Response\sproto\sobject\shave\ssize\s\d+\swith\sevenlop\s.+
                               type='executor.(?P<req_type>\w+)',\s
                               seq=(?P<seq>\d+),.*""",
                           re.VERBOSE)
ptn_fwd_msg = re.compile(r"""Forwarding message part: zmq::message_t\(len=(?P<size>\d+),.*""")

ptn_mem_alloc = re.compile(r"""TFAllocator\s.+\s(?P<size>\d+)\sbytes\sof\smemory\sat\s
                               (?P<addr>\w+)\s.*\susing\sallocator\s
                               (?P<mem_type>\w+)@(?P<alloc_inst>\w+)""",
                           re.VERBOSE)
ptn_mem_dealloc = re.compile(r"""TFAllocator\sdeallocating\smemory\sat\s(?P<addr>\w+)\s
                                 using\sallocator\s(?P<mem_type>\w+)@(?P<alloc_inst>\w+)""",
                             re.VERBOSE)

ptn_tf_vanilla_start = re.compile(r"""\w+ Kernel Compute start: seq=(?P<seq>\d+)""")
ptn_tf_vanilla_done = re.compile(r"""\w+ Kernel Compute done: seq=(?P<seq>\d+)""")
ptn_tf_vanilla_start_async = re.compile(r"""\w+ ComputeAsync start: seq=(?P<seq>\d+)""")
ptn_tf_vanilla_done_async = re.compile(r"""\w+ ComputeAsync done: seq=(?P<seq>\d+)""")


def seq_from_entry(entry):
    map_to_use = thread_seq_map
    if entry.entry_type == 'tf':
        map_to_use = tf_thread_seq_map
    if entry.thread not in map_to_use:
        raise ValueError('Thread {} not found in thread_seq_map for entry {}'.format(entry.thread, entry))
    seq = map_to_use[entry.thread]
    return seq, seq_info[seq]


def match_exec_content(content, entry):
    m = ptn_recv_frame.match(content)
    if m:
        return {
            'type': 'recv_msg',
            'size': int(m.group('size'))
        }

    m = ptn_recv_evenlop.match(content)
    if m:
        seq = int(m.group('seq'))
        seq_info[seq]['recv_evenlop'] = entry
        return {
            'type': 'recv_evenlop',
            'seq': seq,
            'req_type': m.group('req_type')
        }

    m = ptn_create_opkernel.match(content)
    if m:
        seq = int(m.group('seq'))
        thread_seq_map[entry.thread] = seq
        seq_info[seq]['create_kernel'] = entry
        return {
            'type': 'create_kernel',
            'seq': seq
        }

    m = ptn_running.match(content)
    if m:
        seq, info = seq_from_entry(entry)
        info['start_running'] = entry
        if 'recv_evenlop' not in info:
            raise ValueError('Seq {} info does not contain expected event recv_evenlop: {}'.format(seq, info))
        got_evenlop_time = info['recv_evenlop'].timestamp
        return {
            'type': 'start_running',
            'seq': seq,
            'async': m.group('async') is not None,
            'prep_time': (entry.timestamp - got_evenlop_time).total_seconds()
        }

    m = ptn_compute_done.match(content)
    if m:
        seq, info = seq_from_entry(entry)
        info['compute_done'] = entry
        if 'start_running' not in info:
            raise ValueError('Seq {} info does not contain expected event start_running: {}'.format(seq, info))
        start_running_stamp = info['start_running'].timestamp
        return {
            'type': 'compute_done',
            'seq': seq,
            'compute_time': (entry.timestamp - start_running_stamp).total_seconds()
        }

    m = ptn_compute_async_done.match(content)
    if m:
        seq = int(m.group('seq'))
        info = seq_info[seq]
        info['compute_done'] = entry
        if 'start_running' not in info:
            raise ValueError('Seq {} info does not contain expected event start_running: {}'.format(seq, info))
        start_running_stamp = info['start_running'].timestamp
        return {
            'type': 'compute_done',
            'seq': seq,
            'compute_time': (entry.timestamp - start_running_stamp).total_seconds()
        }

    m = ptn_resp_sent.match(content)
    if m:
        seq = int(m.group('seq'))
        info = seq_info[seq]
        info['resp_sent'] = entry

        d = {
            'type': 'resp_sent',
            'seq': seq,
            'resp_type': m.group('req_type')
        }
        if m.group('req_type') != 'RunResponse':
            return d

        if 'compute_done' not in info:
            raise ValueError('Seq {} info does not contain expected event compute_done: {}'.format(seq, info))
        compute_done_stamp = info['compute_done'].timestamp
        d['process_time'] = (entry.timestamp - compute_done_stamp).total_seconds()
        return d

    m = ptn_fwd_msg.match(content)
    if m:
        return {
            'type': 'fwd_msg',
            'size': int(m.group('size'))
        }

    m = ptn_mem_alloc.match(content)
    if m:
        addr = m.group('addr')
        size = int(m.group('size'))
        mem_type = m.group('mem_type')
        alloc_inst = m.group('alloc_inst')
        block = {
            'size': size,
            'addr': addr,
            'mem_type': mem_type,
            'alloc_inst': alloc_inst
        }
        if addr in blocks:
            print('WARNING: overwriting existing mem block: ', addr)
        blocks[addr] = block
        return {
            'type': 'mem_alloc',
            'size': size,
            'addr': addr,
            'block': block
        }

    m = ptn_mem_dealloc.match(content)
    if m:
        addr = m.group('addr')
        if addr not in blocks:
            print('Unknown deallocation at: ', addr)
            size = 0
        else:
            block = blocks[addr]
            del blocks[addr]
            size = block['size']
        return {
            'type': 'mem_dealloc',
            'addr': addr,
            'size': size,
            'block': block
        }

    return {}


ptn_rpc_run = re.compile(r"""RpcClient::run(Async)?\s+calling rpc using rpc stub""")
ptn_send_evenlop = re.compile(r"""Sending evenlop message_t: executor\.(?P<req_type>\w+) seq (?P<seq>\d+)""")
ptn_evenlop_sent = re.compile(r"""Message sent for seq: (?P<seq>\d+)""")
ptn_recv_resp = re.compile(r"""Received evenlop: seq=(?P<seq>\d+) type=executor\.(?P<req_type>\w+)""")
ptn_rpc_return = re.compile(r"""RpcClient::run(Async)?\s+rpc returned with status:.*""")


def match_tf_content(content, entry):
    m = ptn_rpc_run.match(content)
    if m:
        return {}

    m = ptn_send_evenlop.match(content)
    if m:
        seq = int(m.group('seq'))
        tf_thread_seq_map[entry.thread] = seq
        seq_info[seq]['tf_send_evenlop'] = entry
        return {
            'type': 'tf_send_evenlop',
            'seq': seq,
            'req_type': m.group('req_type')
        }

    m = ptn_evenlop_sent.match(content)
    if m:
        seq = int(m.group('seq'))
        tf_thread_seq_map[entry.thread] = seq
        seq_info[seq]['tf_evenlop_sent'] = entry
        return {
            'type': 'tf_evenlop_sent',
            'seq': seq,
        }

    m = ptn_recv_resp.match(content)
    if m:
        seq = int(m.group('seq'))
        tf_thread_seq_map[entry.thread] = seq
        seq_info[seq]['tf_recv_resp'] = entry
        return {
            'type': 'tf_recv_resp',
            'seq': seq,
            'resp_type': m.group('req_type')
        }

    m = ptn_rpc_return.match(content)
    if m:
        seq, info = seq_from_entry(entry)
        info['tf_rpc_return'] = entry
        return {
            'type': 'tf_rpc_return',
            'seq': seq,
            'roundtrip': (entry.timestamp - info['tf_send_evenlop'].timestamp).total_seconds()
        }

    m = ptn_tf_vanilla_start.match(content)
    if m:
        seq = int(m.group('seq'))
        info = seq_info[seq]
        info['tf_vanilla_start'] = entry
        return {
            'type': 'tf_vanilla_start',
            'seq': seq
        }

    m = ptn_tf_vanilla_done.match(content)
    if m:
        seq = int(m.group('seq'))
        info = seq_info[seq]
        info['compute_done'] = entry
        return {
            'type': 'compute_done',
            'seq': seq,
            'compute_time': (entry.timestamp - info['tf_vanilla_start'].timestamp).total_seconds()
        }

    m = ptn_tf_vanilla_start_async.match(content)
    if m:
        seq = int(m.group('seq'))
        info = seq_info[seq]
        info['tf_vanilla_start'] = entry
        return {
            'type': 'tf_vanilla_start',
            'seq': seq
        }

    m = ptn_tf_vanilla_done_async.match(content)
    if m:
        seq = int(m.group('seq'))
        info = seq_info[seq]
        info['compute_done'] = entry
        return {
            'type': 'compute_done',
            'seq': seq,
            'compute_time': (entry.timestamp - info['tf_vanilla_start'].timestamp).total_seconds()
        }

    return {}


def message_size(logs):
    recv_sizes = [l.size for l in logs if l.type == 'recv_msg']
    rs = pd.Series(recv_sizes)

    send_sizes = [l.size for l in logs if l.type == 'fwd_msg']
    ss = pd.Series(send_sizes)

    print('Received {} messages'.format(len(rs)))
    print('Cumulative count at each point: ', np.array([.25, .75, .90, .999, .9999]) * len(rs))
    print(rs.quantile([.25, .75, .90, .999, .9999]))

    print('Sent {} messages'.format(len(ss)))
    print('Cumulative count at each point: ', np.array([.25, .75, .90, .999, .9999]) * len(ss))
    print(ss.quantile([.25, .75, .90, .999, .9999]))

    fig, axs = plt.subplots(ncols=2)

    ax = sns.distplot(rs, hist=True, kde=False, ax=axs[0])
    ax.grid(True)
    ax.set_xlabel('Size (byte)')
    ax.set_ylabel('Count')
    ax.set_yscale('log')
    ax.set_title('Message size of {} received messages'.format(len(rs)))

    ax = sns.distplot(ss, hist=True, kde=False, ax=axs[1])
    ax.grid(True)
    ax.set_xlabel('Size (byte)')
    ax.set_ylabel('Count')
    ax.set_yscale('log')
    ax.set_title('Message size of {} sent messages'.format(len(ss)))

    fig.tight_layout()

    return rs, ss


def scheduling_time(logs):
    times = [l.prep_time for l in logs if l.type == 'start_running']
    ts = pd.Series(times)

    print('Preparation times for {} RunRequests'.format(len(ts)))
    print('Cumulative count at each point: ', np.array([.25, .75, .90, .999, .9999]) * len(ts))
    print(ts.quantile([.25, .75, .90, .999, .9999]))

    ax = sns.distplot(ts, hist=True, kde=False)
    ax.grid(True)
    ax.set_xlabel('Preparation time (s)')
    ax.set_ylabel('Count')
    ax.set_yscale('log')
    ax.set_title('Preparation time for {} RunRequests'.format(len(ts)))
    ax.figure.tight_layout()

    return ts


def compute_time(logs):
    times = [l.compute_time for l in logs if l.type == 'compute_done']
    ts = pd.Series(times)

    print('Compute time for {} requests'.format(len(ts)))
    print('Cumulative count at each point: ', np.array([.25, .75, .90, .999, .9999]) * len(ts))
    print(ts.quantile([.25, .75, .90, .999, .9999]))

    ax = sns.distplot(ts, hist=True, kde=False)
    ax.grid(True)
    ax.set_xlabel('Compute time (s)')
    ax.set_ylabel('Count')
    ax.set_yscale('log')
    ax.set_title('Compute time for {} messages'.format(len(ts)))
    ax.figure.tight_layout()

    return ts


def process_time(logs):
    times = [l.process_time for l in logs if l.type == 'resp_sent' and hasattr(l, 'process_time')]
    ts = pd.Series(times)

    print('Post process time for {} requests'.format(len(ts)))
    print('Cumulative count at each point: ', np.array([.25, .75, .90, .999, .9999]) * len(ts))
    print(ts.quantile([.25, .75, .90, .999, .9999]))

    ax = sns.distplot(ts, hist=True, kde=False)
    ax.grid(True)
    ax.set_xlabel('Post process time (s)')
    ax.set_ylabel('Count')
    ax.set_yscale('log')
    ax.set_title('Post process time for {} messages'.format(len(ts)))
    ax.figure.tight_layout()

    return ts


def roundtrip_time(logs):
    times = [l.roundtrip for l in logs if l.type == 'tf_rpc_return']
    ts = pd.Series(times)

    print('Round-trip time for {} messages'.format(len(ts)))
    print('Cumulative count at each point: ', np.array([.25, .75, .90, .999, .9999]) * len(ts))
    print(ts.quantile([.25, .75, .90, .999, .9999]))

    ax = sns.distplot(ts, hist=True, kde=False)
    ax.grid(True)
    ax.set_xlabel('Round-trip time (s)')
    ax.set_ylabel('Count')
    ax.set_yscale('log')
    ax.set_title('Round-trip for {} messages'.format(len(ts)))
    ax.figure.tight_layout()

    return ts


def req_on_wire_time(logs):
    times = [l.travel_time for l in logs if l.type == 'recv_evenlop' and hasattr(l, 'travel_time')]
    ts = pd.Series(times)

    print('Transmission time for {} requests'.format(len(ts)))
    print('Cumulative count at each point: ', np.array([.25, .75, .90, .999, .9999]) * len(ts))
    print(ts.quantile([.25, .75, .90, .999, .9999]))

    ax = sns.distplot(ts, hist=True, kde=False)
    ax.grid(True)
    ax.set_xlabel('Transmission time (s)')
    ax.set_ylabel('Count')
    ax.set_yscale('log')
    ax.set_title('Transmission for {} requests'.format(len(ts)))
    ax.figure.tight_layout()

    return ts


def resp_on_wire_time(logs):
    times = [l.travel_time for l in logs if l.type == 'tf_rpc_return' and hasattr(l, 'travel_time')]
    ts = pd.Series(times)

    print('Transmission time for {} responses'.format(len(ts)))
    print('Cumulative count at each point: ', np.array([.25, .75, .90, .999, .9999]) * len(ts))
    print(ts.quantile([.25, .75, .90, .999, .9999]))

    ax = sns.distplot(ts, hist=True, kde=False)
    ax.grid(True)
    ax.set_xlabel('Transmission time (s)')
    ax.set_ylabel('Count')
    ax.set_yscale('log')
    ax.set_title('Transmission for {} responses'.format(len(ts)))
    ax.figure.tight_layout()

    return ts


def memory_usage(logs):
    mem_usages = [l for l in logs if l.type == 'mem_alloc' or l.type == 'mem_dealloc']

    mem_activities = []
    for m in mem_usages:
        if m.type == 'mem_alloc':
            mem_activities.append({
                'timestamp': m.timestamp,
                'size': m.size,
                'mem_type': m.block['mem_type'],
                'alloc_inst': m.block['alloc_inst']
            })
        elif m.type == 'mem_dealloc':
            mem_activities.append({
                'timestamp': m.timestamp,
                'size': -m.size,
                'mem_type': m.block['mem_type'],
                'alloc_inst': m.block['alloc_inst']
            })
        else:
            raise ValueError("Unexpected value: ", m)

    df = pd.DataFrame(mem_activities)
    df = df.set_index('timestamp').sort_index()
    fig, axs = plt.subplots(ncols=1, nrows=4, sharex=True)
    for (name, group), ax in zip(df.groupby('mem_type'), axs):
        group.cumsum().plot(ax=ax, title=name)
        ax.grid('on')
        ax.xaxis.label.set_visible(False)
    fig.tight_layout()
    fig.text(0.5, 0.04, 'Time (s)', ha='center')
    fig.text(0.04, 0.5, 'Memory Usage (bytes)', va='center', rotation='vertical')
    return df
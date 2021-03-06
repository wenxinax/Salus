#
# Copyright 2019 Peifeng Yu <peifeng@umich.edu>
# 
# This file is part of Salus
# (see https://github.com/SymbioticLab/Salus).
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import re
from collections import defaultdict

with open('tf.output') as f:
    lines = f.readlines()

requests = defaultdict(set)
rrequests = defaultdict(set)
pat_send = re.compile(r"Sending evenlop message_t: (?P<type>[a-zA-Z.]+) seq (?P<seq>\d+)")
pat_recv = re.compile(r"Received evenlop: seq=(?P<seq>\d+) type=(?P<type>[a-zA-Z.]+)")

for line in lines:
    if pat_send.search(line):
        res = pat_send.search(line)
        reqtype = res.group('type')

        s = requests[res.group('type')]
        if res.group('seq') in s:
            print('Request sent twice: ', line)
            import ipdb; ipdb.set_trace()
            continue
        s.add(res.group('seq'))
    elif pat_recv.search(line):
        res = pat_recv.search(line)

        reqtype = res.group('type')
        if reqtype.endswith('Response'):
            reqtype = reqtype.replace('Response', 'Request')

        if reqtype == 'executor.TFRendezRecvRequests':
            s = rrequests[reqtype]
            if res.group('seq') in s:
                print('Sending out twice requests: ', line)
                continue
            s.add(res.group('seq'))
            continue

        if reqtype not in requests:
            print('Response for non-exist request: ', line)
            import ipdb; ipdb.set_trace()
            continue
        s = requests[reqtype]
        if res.group('seq') not in s:
            print('Response for non-exist request seq: ', line)
            import ipdb; ipdb.set_trace()
            continue
        s.remove(res.group('seq'))

print('===========================================')
print('Remaining')

for k, v in requests.items():
    print(k)
    for seq in v:
        print('    ', seq)

for k, v in rrequests.items():
    print(k)
    for seq in v:
        print('    ', seq)

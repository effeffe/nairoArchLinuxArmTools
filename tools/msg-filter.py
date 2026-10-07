#!/usr/bin/env python3
import sys, os
M = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'commit-msgs')
msg = sys.stdin.read()
subj = msg.split('\n', 1)[0]
for n in ('02', '09', '10', '14'):
    new = open(os.path.join(M, n)).read()
    if new.split('\n', 1)[0] == subj:
        sys.stdout.write(new if new.endswith('\n') else new + '\n')
        break
else:
    sys.stdout.write(msg)

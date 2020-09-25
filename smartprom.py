#!/usr/bin/env python3

import glob
import os
import sys
import re
import subprocess
import time
from typing import List
from prometheus_client import start_http_server, Gauge


def isDrive(s: str) -> bool:
    return s.startswith('/dev/sd') and re.match('^/dev/sd[a-z]+$', s)


DRIVES = list(filter(lambda d: isDrive(d), glob.glob("/dev/*")))


def run(args: [str]):
    # print('Running: {}'.format(' '.join(args)))
    out = subprocess.Popen(args, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()

    if out.returncode != 0:
        if stderr:
            print(stderr.decode("utf-8"))
        raise Exception('Command returned code {}'.format(out.returncode))

    return stdout.decode("utf-8")


HEADER = 'ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE'
METRICS = {}
LABELS = ['drive']


def smart(dev: str) -> List[str]:
    results = run(['smartctl', '-A', dev])
    attributes = {}
    got_header = False
    for result in results.split('\n'):
        if not result:
            continue

        if result == HEADER:
            got_header = True
            continue

        if got_header:
            tokens = result.split()
            if len(tokens) > 3:
                attributes[int(tokens[0])] = (tokens[1], int(tokens[3]))
    return attributes


def collect():
    global METRICS

    for drive in DRIVES:
        try:
            # Grab all of the attributes that SMART gave us
            attrs = smart(drive)
            for key, values in attrs.items():
                # Create metric if does not exist
                if key not in METRICS:
                    name = values[0].replace('-', '_')
                    desc = values[0].replace('_', ' ')
                    num = hex(key)
                    skey = f'smartprom_{name}'
                    print(f'Adding new gauge {skey} ({num})')
                    METRICS[key] = Gauge(skey, f'({num}) {desc}', LABELS)

                # Update metric
                METRICS[key].labels(drive[5:]).set(values[1])
        except Exception as e:
            print(e)
            pass


def main():
    start_http_server(9902)
    collect()

    start_time = time.time()
    while True:
        elapsed_time = time.time() - start_time
        if elapsed_time > 20.0:
            start_time = time.time()
            collect()
        time.sleep(0.1)


if __name__ == '__main__':
    main()

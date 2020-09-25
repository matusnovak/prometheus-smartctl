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


def get_types():
    types = {}
    results = run(['smartctl', '--scan-open'])
    for result in results.split('\n'):
        if not result:
            continue

        tokens = result.split()
        if len(tokens) > 3:
            types[tokens[0]] = tokens[2]

    return types


DRIVES = list(filter(lambda d: isDrive(d), glob.glob("/dev/*")))
TYPES = get_types()
HEADER = 'ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE'
METRICS = {}
LABELS = ['drive']


def smart(dev: str) -> List[str]:
    typ = 'sat'
    if dev in TYPES:
        typ = TYPES[dev]

    results = run(['smartctl', '-A', '-d', typ, dev])
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
                raw = None
                try:
                    raw = int(tokens[9])
                except:
                    pass

                attributes[tokens[1]] = (int(tokens[0]), int(tokens[3]))
                if raw:
                    attributes[f'{tokens[1]}_raw'] = (int(tokens[0]), raw)
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
                    name = key.replace('-', '_')
                    desc = key.replace('_', ' ')
                    num = hex(values[0])
                    skey = f'smartprom_{name}'
                    skey_raw = f'smartprom_{name}_raw'

                    print(f'Adding new gauge {skey} ({num})')
                    METRICS[key] = Gauge(skey, f'({num}) {desc}', LABELS)

                # Update metric
                METRICS[key].labels(drive[5:]).set(values[1])
        except Exception as e:
            print('Exception:', e)
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

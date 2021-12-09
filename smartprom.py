#!/usr/bin/env python3

import glob
import re
import subprocess
import time
import json
from typing import List
from prometheus_client import start_http_server, Gauge


def isDrive(s: str) -> bool:
    return re.match('^/dev/(sd[a-z]+|nvme[0-9]+)$', s)


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


def smart_sat(dev: str) -> List[str]:
    results = run(['smartctl', '-A', '-d', 'sat', dev])
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


def smart_nvme(dev: str) -> List[str]:
    results = run(['smartctl', '-A', '-d', 'nvme', '--json=c', dev])
    attributes = {}

    health_info = json.loads(results)['nvme_smart_health_information_log']
    for k, v in health_info.items():
        if k == 'temperature_sensors':
            for i, value in enumerate(v, start=1):
                attributes['temperature_sensor{i}'.format(i=i)] = value
            continue
        attributes[k] = v

    return attributes


def collect():
    global METRICS
    global TYPES

    for drive in DRIVES:
        try:
            # Grab all of the attributes that SMART gave us
            if drive in TYPES:
                typ = TYPES[drive]

            if typ == 'sat':
                attrs = smart_sat(drive)
            elif typ == 'nvme':
                attrs = smart_nvme(drive)
            else:
                continue

            for key, values in attrs.items():
                # Create metric if does not exist
                if key not in METRICS:
                    name = key.replace('-', '_').replace(' ', '_').replace('.', '')
                    desc = key.replace('_', ' ')
                    if typ == 'sat':
                        num = hex(values[0])
                    else:
                        num = hex(values)
                    skey = f'smartprom_{name}'
                    skey_raw = f'smartprom_{name}_raw'

                    print(f'Adding new gauge {skey} ({num})')
                    METRICS[key] = Gauge(skey, f'({num}) {desc}', LABELS)

                # Update metric
                if typ == 'sat':
                    METRICS[key].labels(drive.replace('/dev/', '')).set(values[1])
                else:
                    METRICS[key].labels(drive.replace('/dev/', '')).set(values)

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

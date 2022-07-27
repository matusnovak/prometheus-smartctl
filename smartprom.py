#!/usr/bin/env python3

import subprocess
import time
import json
from typing import List
from prometheus_client import start_http_server, Gauge

def run(args: List[str]):
    """
    runs the smartctl command on the system
    """
    out = subprocess.Popen(args, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()

    if out.returncode != 0:
        if stderr:
            print(stderr.decode("utf-8"))
        raise Exception('Command returned code {}'.format(out.returncode))

    return stdout.decode("utf-8")


def get_drives():
    """
    returns a dictionary of devices and its types
    """
    disks = {}
    results = run(['smartctl', '--scan-open', '--json=c'])
    devices = json.loads(results)['devices']
    for device in devices:
        disks[device["name"]] = device["type"]
    print("Devices and its types", disks)
    return disks


DRIVES = get_drives()
HEADER = 'ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE'
METRICS = {}
LABELS = ['drive']


def smart_sat(dev: str) -> List[str]:
    """
    Runs the smartctl command on a "sat" device
    and processes its attributes
    """
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
                if raw is not None:
                    attributes[f'{tokens[1]}_raw'] = (int(tokens[0]), raw)
    return attributes


def smart_nvme(dev: str) -> List[str]:
    """
    Runs the smartctl command on a "nvme" device
    and processes its attributes
    """
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


def smart_scsi(dev: str) -> List[str]:
    """
    Runs the smartctl command on a "scsi" device
    and processes its attributes
    """
    results = run(['smartctl', '-A', '-d', 'scsi', '--json=c', dev])
    attributes = {}
    data = json.loads(results)
    for key, value in data.items():
        if type(value) == dict:
            for _label, _value in value.items():
                if type(_value) == int:
                    attributes[f"{key}_{_label}"] = _value
        elif type(value) == int:
            attributes[key] = value
    return attributes


def collect():
    """
    Collect all drive metrics and save them as Gauge type
    """
    global METRICS

    for drive, typ in DRIVES.items():
        try:
            if typ == 'sat':
                attrs = smart_sat(drive)
            elif typ == 'nvme':
                attrs = smart_nvme(drive)
            elif typ == 'scsi':
                attrs = smart_scsi(drive)
            else:
                continue

            for key, values in attrs.items():
                # Create metric if does not exist
                if key not in METRICS:
                    name = key.replace('-', '_').replace(' ', '_').replace('.', '').replace('/', '_').lower()
                    desc = key.replace('_', ' ')
                    if typ == 'sat':
                        num = hex(values[0])
                    else:
                        num = hex(values)
                    skey = f'smartprom_{name}'

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
    """
    starts a server at port 9902 and exposes the metrics
    """
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

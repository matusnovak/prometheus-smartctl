#!/usr/bin/env python3
import os
import subprocess
import time
import json
from typing import List
from prometheus_client import start_http_server, Gauge


def run(args: List[str]):
    """
    Runs the smartctl command on the system
    """
    out = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()

    if out.returncode != 0:
        stdout_msg = stdout.decode('utf-8') if stdout is not None else ''
        stderr_msg = stderr.decode('utf-8') if stderr is not None else ''
        raise Exception(f"Command returned code {out.returncode}. Stdout: '{stdout_msg}' Stderr: '{stderr_msg}'")

    return stdout.decode("utf-8")


def get_drives():
    """
    returns a dictionary of devices and its types
    """
    disks = {}
    result = run(['smartctl', '--scan-open', '--json=c'])
    result_json = json.loads(result)
    if 'devices' in result_json:
        devices = result_json['devices']
        for device in devices:
            disks[device["name"]] = device["type"]
        print("Devices and its types", disks)
    else:
        print("No devices found. Make sure you have enough privileges.")
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
                # Metric name in lower case
                metric = 'smartprom_' + key.replace('-', '_').replace(' ', '_').replace('.', '').replace('/', '_')\
                    .lower()

                # Create metric if it does not exist
                if metric not in METRICS:
                    desc = key.replace('_', ' ')
                    code = hex(values[0]) if typ == 'sat' else hex(values)
                    print(f'Adding new gauge {metric} ({code})')
                    METRICS[metric] = Gauge(metric, f'({code}) {desc}', LABELS)

                # Update metric
                metric_val = values[1] if typ == 'sat' else values
                METRICS[metric].labels(drive.replace('/dev/', '')).set(metric_val)

        except Exception as e:
            print('Exception:', e)
            pass


def main():
    """
    Starts a server and exposes the metrics
    """
    exporter_address = os.environ.get("SMARTCTL_EXPORTER_ADDRESS", "0.0.0.0")
    exporter_port = int(os.environ.get("SMARTCTL_EXPORTER_PORT", 9902))
    refresh_interval = int(os.environ.get("SMARTCTL_REFRESH_INTERVAL", 60))

    start_http_server(exporter_port, exporter_address)
    print(f"Server listening in http://{exporter_address}:{exporter_port}/metrics")

    while True:
        collect()
        time.sleep(refresh_interval)


if __name__ == '__main__':
    main()

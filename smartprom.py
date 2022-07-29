#!/usr/bin/env python3
import json
import os
import subprocess
import time

import prometheus_client

DRIVES = {}
METRICS = {}
LABELS = ['drive']


def run_smartctl_cmd(args: list):
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


def get_drives() -> dict:
    """
    Returns a dictionary of devices and its types
    """
    disks = {}
    result = run_smartctl_cmd(['smartctl', '--scan-open', '--json=c'])
    result_json = json.loads(result)
    if 'devices' in result_json:
        devices = result_json['devices']
        for device in devices:
            disks[device["name"]] = device["type"]
        print("Devices and its types", disks)
    else:
        print("No devices found. Make sure you have enough privileges.")
    return disks


def smart_sat(dev: str) -> dict:
    """
    Runs the smartctl command on a "sat" device
    and processes its attributes
    """
    results = run_smartctl_cmd(['smartctl', '-A', '-d', 'sat', '--json=c', dev])

    attributes = {}
    data = json.loads(results)['ata_smart_attributes']['table']
    for metric in data:
        code = metric['id']
        name = metric['name']
        value = metric['value']
        value_raw = metric['raw']['value']
        attributes[name] = (int(code), value)
        attributes[f'{name}_raw'] = (int(code), value_raw)
    return attributes


def smart_nvme(dev: str) -> dict:
    """
    Runs the smartctl command on a "nvme" device
    and processes its attributes
    """
    results = run_smartctl_cmd(['smartctl', '-A', '-d', 'nvme', '--json=c', dev])
    attributes = {}

    data = json.loads(results)['nvme_smart_health_information_log']
    for key, value in data.items():
        if key == 'temperature_sensors':
            for i, _value in enumerate(value, start=1):
                attributes[f'temperature_sensor{i}'] = _value
        else:
            attributes[key] = value
    return attributes


def smart_scsi(dev: str) -> dict:
    """
    Runs the smartctl command on a "scsi" device
    and processes its attributes
    """
    results = run_smartctl_cmd(['smartctl', '-A', '-d', 'scsi', '--json=c', dev])
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
    global DRIVES, METRICS, LABELS

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
                metric = 'smartprom_' + key.replace('-', '_').replace(' ', '_').replace('.', '').replace('/', '_') \
                    .lower()

                # Create metric if it does not exist
                if metric not in METRICS:
                    desc = key.replace('_', ' ')
                    code = hex(values[0]) if typ == 'sat' else hex(values)
                    print(f'Adding new gauge {metric} ({code})')
                    METRICS[metric] = prometheus_client.Gauge(metric, f'({code}) {desc}', LABELS)

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
    global DRIVES

    # Validate configuration
    exporter_address = os.environ.get("SMARTCTL_EXPORTER_ADDRESS", "0.0.0.0")
    exporter_port = int(os.environ.get("SMARTCTL_EXPORTER_PORT", 9902))
    refresh_interval = int(os.environ.get("SMARTCTL_REFRESH_INTERVAL", 60))

    # Get drives (test smartctl)
    DRIVES = get_drives()

    # Start Prometheus server
    prometheus_client.start_http_server(exporter_port, exporter_address)
    print(f"Server listening in http://{exporter_address}:{exporter_port}/metrics")

    while True:
        collect()
        time.sleep(refresh_interval)


if __name__ == '__main__':
    main()

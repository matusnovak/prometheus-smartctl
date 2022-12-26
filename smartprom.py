#!/usr/bin/env python3
import json
import multiprocessing
import multiprocessing.connection
import os
import pwd
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Tuple

import prometheus_client

LABELS = ['drive', 'type', 'model_family', 'model_name', 'serial_number']
DRIVES = {}
METRICS = {}

# https://www.smartmontools.org/wiki/USB
SAT_TYPES = ['sat', 'usbjmicron', 'usbprolific', 'usbsunplus']
NVME_TYPES = ['nvme', 'sntasmedia', 'sntjmicron', 'sntrealtek']
SCSI_TYPES = ['scsi']


class SmartctlRunner(ABC):
    @abstractmethod
    def run(self, args: list) -> Tuple[str, int]:
        pass


class RemoteSmartctlRunner(SmartctlRunner):
    """
    Sends the arguments to the parent process, and waits
    for the parent process to run smartctl and send the
    output back.
    """

    def __init__(self, connection):
        self.connection = connection

    def run(self, args: list) -> Tuple[str, int]:
        self.connection.send(args)
        return self.connection.recv()


class LocalSmartctlRunner(SmartctlRunner):
    """
    Run smartctl and returns the result.
    """
    def run(self, args: list) -> Tuple[str, int]:
        return run_smartctl_cmd(args)


def demote(user: str):
    """
    Change this process to run as user.
    """
    user_info = pwd.getpwnam(user)
    os.setgid(user_info.pw_gid)
    os.setuid(user_info.pw_uid)


def run_smartctl_cmd(args: list) -> Tuple[str, int]:
    """
    Runs the smartctl command on the system
    """
    out = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()

    # exit code can be != 0 even if the command returned valid data
    # see EXIT STATUS in
    # https://www.smartmontools.org/browser/trunk/smartmontools/smartctl.8.in
    if out.returncode != 0:
        stdout_msg = stdout.decode('utf-8') if stdout is not None else ''
        stderr_msg = stderr.decode('utf-8') if stderr is not None else ''
        print(f"WARNING: Command returned exit code {out.returncode}. Stdout: '{stdout_msg}' Stderr: '{stderr_msg}'")

    return stdout.decode("utf-8"), out.returncode


def get_drives(smartctl_runner: SmartctlRunner) -> dict:
    """
    Returns a dictionary of devices and its types
    """
    disks = {}
    result, _ = smartctl_runner.run(['smartctl', '--scan-open', '--json=c'])
    result_json = json.loads(result)
    if 'devices' in result_json:
        devices = result_json['devices']
        for device in devices:
            dev = device["name"]
            disk_attrs = get_device_info(smartctl_runner, dev)
            disk_attrs["type"] = device["type"]
            disks[dev] = disk_attrs
            print("Discovered device", dev, "with attributes", disk_attrs)
    else:
        print("No devices found. Make sure you have enough privileges.")
    return disks


def get_device_info(smartctl_runner: SmartctlRunner, dev: str) -> dict:
    """
    Returns a dictionary of device info
    """
    results, _ = smartctl_runner.run(['smartctl', '-i', '--json=c', dev])
    results = json.loads(results)
    return {
        'model_family': results.get("model_family", "Unknown"),
        'model_name': results.get("model_name", "Unknown"),
        'serial_number': results.get("serial_number", "Unknown")
    }


def get_smart_status(results: dict) -> int:
    """
    Returns a 1, 0 or -1 depending on if result from
    smart status is True, False or unknown.
    """
    status = results.get("smart_status")
    return +(status.get("passed")) if status is not None else -1


def smart_sat(smartctl_runner: SmartctlRunner, dev: str) -> dict:
    """
    Runs the smartctl command on a internal or external "sat" device
    and processes its attributes
    """
    results, exit_code = smartctl_runner.run(['smartctl', '-A', '-H', '-d', 'sat', '--json=c', dev])
    results = json.loads(results)

    attributes = {
        'smart_passed': (0, get_smart_status(results)),
        'exit_code': (0, exit_code)
    }
    data = results['ata_smart_attributes']['table']
    for metric in data:
        code = metric['id']
        name = metric['name']
        value = metric['value']

        # metric['raw']['value'] contains values difficult to understand for temperatures and time up
        # that's why we added some logic to parse the string value
        value_raw = metric['raw']['string']
        try:
            # example value_raw: "33" or "43 (Min/Max 39/46)"
            value_raw = int(value_raw.split()[0])
        except:
            # example value_raw: "20071h+27m+15.375s"
            if 'h+' in value_raw:
                value_raw = int(value_raw.split('h+')[0])
            else:
                print(f"Raw value of sat metric '{name}' can't be parsed. raw_string: {value_raw} "
                      f"raw_int: {metric['raw']['value']}")
                value_raw = None

        attributes[name] = (int(code), value)
        if value_raw is not None:
            attributes[f'{name}_raw'] = (int(code), value_raw)
    return attributes


def smart_nvme(smartctl_runner: SmartctlRunner, dev: str) -> dict:
    """
    Runs the smartctl command on a internal or external "nvme" device
    and processes its attributes
    """
    results, exit_code = smartctl_runner.run(['smartctl', '-A', '-H', '-d', 'nvme', '--json=c', dev])
    results = json.loads(results)

    attributes = {
        'smart_passed': get_smart_status(results),
        'exit_code': exit_code
    }
    data = results['nvme_smart_health_information_log']
    for key, value in data.items():
        if key == 'temperature_sensors':
            for i, _value in enumerate(value, start=1):
                attributes[f'temperature_sensor{i}'] = _value
        else:
            attributes[key] = value
    return attributes


def smart_scsi(smartctl_runner: SmartctlRunner, dev: str) -> dict:
    """
    Runs the smartctl command on a "scsi" device
    and processes its attributes
    """
    results, exit_code = smartctl_runner.run(['smartctl', '-A', '-H', '-d', 'scsi', '--json=c', dev])
    results = json.loads(results)

    attributes = {
        'smart_passed': get_smart_status(results),
        'exit_code': exit_code
    }
    for key, value in results.items():
        if type(value) == dict:
            for _label, _value in value.items():
                if type(_value) == int:
                    attributes[f"{key}_{_label}"] = _value
        elif type(value) == int:
            attributes[key] = value
    return attributes


def collect(smartctl_runner: SmartctlRunner):
    """
    Collect all drive metrics and save them as Gauge type
    """
    global LABELS, DRIVES, METRICS, SAT_TYPES, NVME_TYPES, SCSI_TYPES

    for drive, drive_attrs in DRIVES.items():
        typ = drive_attrs['type']
        try:
            if typ in SAT_TYPES:
                attrs = smart_sat(smartctl_runner, drive)
            elif typ in NVME_TYPES:
                attrs = smart_nvme(smartctl_runner, drive)
            elif typ in SCSI_TYPES:
                attrs = smart_scsi(smartctl_runner, drive)
            else:
                continue

            for key, values in attrs.items():
                # Metric name in lower case
                metric = 'smartprom_' + key.replace('-', '_').replace(' ', '_').replace('.', '').replace('/', '_') \
                    .lower()

                # Create metric if it does not exist
                if metric not in METRICS:
                    desc = key.replace('_', ' ')
                    code = hex(values[0]) if typ in SAT_TYPES else hex(values)
                    print(f'Adding new gauge {metric} ({code})')
                    METRICS[metric] = prometheus_client.Gauge(metric, f'({code}) {desc}', LABELS)

                # Update metric
                metric_val = values[1] if typ in SAT_TYPES else values

                METRICS[metric].labels(drive=drive,
                                       type=typ,
                                       model_family=drive_attrs['model_family'],
                                       model_name=drive_attrs['model_name'],
                                       serial_number=drive_attrs['serial_number']).set(metric_val)

        except Exception as e:
            print('Exception:', e)
            pass


def child_target(connection: multiprocessing.connection.Connection, run_as_user: str):
    """
    Demote to non-root user and start server with main loop
    """
    with connection as connection:
        demote(run_as_user)
        smartctl_runner = RemoteSmartctlRunner(connection)
        start_server(smartctl_runner)


def start_server(smartctl_runner: SmartctlRunner):
    """
    Starts a server and exposes the metrics
    """
    global DRIVES

    # Validate configuration
    exporter_address = os.environ.get("SMARTCTL_EXPORTER_ADDRESS", "0.0.0.0")
    exporter_port = int(os.environ.get("SMARTCTL_EXPORTER_PORT", 9902))
    refresh_interval = int(os.environ.get("SMARTCTL_REFRESH_INTERVAL", 60))

    # Get drives (test smartctl)
    DRIVES = get_drives(smartctl_runner)

    # Start Prometheus server
    prometheus_client.start_http_server(exporter_port, exporter_address)
    print(f"Server listening in http://{exporter_address}:{exporter_port}/metrics")

    while True:
        collect(smartctl_runner)
        time.sleep(refresh_interval)


def main():
    run_as_user = os.environ.get("SMARTCTL_EXPORTER_USER")
    if run_as_user:
        print(f"Configured to run as user {run_as_user}")
        parent_connection, child_connection = multiprocessing.Pipe()
        process = multiprocessing.Process(target=child_target, args=(child_connection, run_as_user))
        process.start()
        with parent_connection as connection:
            while True:
                args = connection.recv()
                result = run_smartctl_cmd(args)
                connection.send(result)
    else:
        runner = LocalSmartctlRunner()
        start_server(runner)


if __name__ == '__main__':
    main()

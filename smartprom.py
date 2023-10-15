#!/usr/bin/env python3
import json
import os
import subprocess
import time
import re
from typing import Tuple

import prometheus_client

LABELS = ['drive', 'type', 'model_family', 'model_name', 'serial_number']
DRIVES = {}
METRICS = {}

# https://www.smartmontools.org/wiki/USB
SAT_TYPES = ['sat', 'usbjmicron', 'usbprolific', 'usbsunplus']
NVME_TYPES = ['nvme', 'sntasmedia', 'sntjmicron', 'sntrealtek']
SCSI_TYPES = ['scsi']
MEGARAID_TYPE_PATTERN = r"(sat\+)?(megaraid,\d+)"


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


def get_drives() -> dict:
    """
    Returns a dictionary of devices and its types
    """
    disks = {}
    result, _ = run_smartctl_cmd(['smartctl', '--scan-open', '--json=c'])
    result_json = json.loads(result)

    # Ignore devices that fail on open, such as Virtual Drives created by MegaRAID.
    result_json["devices"] = list(
        filter(
            lambda x: (
                x.get("open_error", "")
                != "DELL or MegaRaid controller, please try adding '-d megaraid,N'"
            ),
            result_json["devices"],
        )
    )

    if 'devices' in result_json:
        devices = result_json['devices']
        for device in devices:
            dev = device["name"]
            if re.match(MEGARAID_TYPE_PATTERN, device["type"]):
                # If drive is connected by MegaRAID, dev has a bus name like "/dev/bus/0".
                # After retrieving the disk information using the bus name,
                # replace dev with a disk ID such as "megaraid,0".
                bus_name = dev
                disk_attrs = get_megaraid_device_info(device["type"], bus_name)
                disk_attrs["bus_device"] = bus_name
                disk_attrs["megaraid_id"] = get_megaraid_device_id(device["type"])
                dev = disk_attrs["megaraid_id"]

                # Generate device["type"] from device["protocol"]
                # because device["type"] contains strings such as "sat+megaraid,2" or "megaraid,4".
                disk_attrs["type"] = "sat" if device["protocol"] == "ATA" else "scsi"
            else:
                disk_attrs = get_device_info(dev)
                disk_attrs["type"] = device["type"]
            disks[dev] = disk_attrs
            print("Discovered device", dev, "with attributes", disk_attrs)
    else:
        print("No devices found. Make sure you have enough privileges.")
    return disks


def get_device_info(dev: str) -> dict:
    """
    Returns a dictionary of device info
    """
    results, _ = run_smartctl_cmd(['smartctl', '-i', '--json=c', dev])
    results = json.loads(results)
    return {
        'model_family': results.get("model_family", "Unknown"),
        'model_name': results.get("model_name", "Unknown"),
        'serial_number': results.get("serial_number", "Unknown")
    }


def get_megaraid_device_info(typ: str, dev: str) -> dict:
    """
    Get device information connected with MegaRAID,
    and process the information into get_device_info compatible format.
    """
    megaraid_id = get_megaraid_device_id(typ)
    if megaraid_id is None:
        return {}

    results, _ = run_smartctl_cmd(
        ["smartctl", "-i", "--json=c", "-d", megaraid_id, dev]
    )
    results = json.loads(results)
    serial_number = results.get("serial_number", "Unknown")
    model_family = results.get("model_family", "Unknown")

    # When using SAS drive and smartmontools r5286 and later,
    # scsi_ prefix is added to model_name field.
    # https://sourceforge.net/p/smartmontools/code/5286/
    model_name = results.get(
        "scsi_model_name",
        results.get("model_name", "Unknown"),
    )

    return {
        "model_family": model_family,
        "model_name": model_name,
        "serial_number": serial_number,
    }


def get_megaraid_device_id(typ: str) -> str | None:
    """
    Returns the device ID on the MegaRAID from the typ string
    """
    megaraid_match = re.search(MEGARAID_TYPE_PATTERN, typ)
    if not megaraid_match:
        return None

    return megaraid_match.group(2)


def get_smart_status(results: dict) -> int:
    """
    Returns a 1, 0 or -1 depending on if result from
    smart status is True, False or unknown.
    """
    status = results.get("smart_status")
    return +(status.get("passed")) if status is not None else -1


def smart_sat(dev: str) -> dict:
    """
    Runs the smartctl command on a internal or external "sat" device
    and processes its attributes
    """
    results, exit_code = run_smartctl_cmd(['smartctl', '-A', '-H', '-d', 'sat', '--json=c', dev])
    results = json.loads(results)

    attributes = table_to_attributes_sat(results["ata_smart_attributes"]["table"])
    attributes["smart_passed"] = (0, get_smart_status(results))
    attributes["exit_code"] = (0, exit_code)
    return attributes


def table_to_attributes_sat(data: dict) -> dict:
    """
    Returns a results["ata_smart_attributes"]["table"]
    processed into an attributes dict
    """
    attributes = {}
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


def smart_nvme(dev: str) -> dict:
    """
    Runs the smartctl command on a internal or external "nvme" device
    and processes its attributes
    """
    results, exit_code = run_smartctl_cmd(['smartctl', '-A', '-H', '-d', 'nvme', '--json=c', dev])
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


def smart_scsi(dev: str) -> dict:
    """
    Runs the smartctl command on a "scsi" device
    and processes its attributes
    """
    results, exit_code = run_smartctl_cmd(['smartctl', '-A', '-H', '-d', 'scsi', '--json=c', dev])
    results = json.loads(results)

    attributes = results_to_attributes_scsi(results)
    attributes["smart_passed"] = get_smart_status(results)
    attributes["exit_code"] = exit_code
    return attributes


def results_to_attributes_scsi(data: dict) -> dict:
    """
    Returns the result of smartctl -i on the SCSI device
    processed into an attributes dict
    """
    attributes = {}
    for key, value in data.items():
        if type(value) == dict:
            for _label, _value in value.items():
                if type(_value) == int:
                    attributes[f"{key}_{_label}"] = _value
        elif type(value) == int:
            attributes[key] = value
    return attributes


def smart_megaraid(megaraid_id: str, dev: str) -> dict:
    """
    Runs the smartctl command on device connected by MegaRAID
    and processes its attributes
    """
    results, exit_code = run_smartctl_cmd(
        ["smartctl", "-A", "-H", "-d", megaraid_id, "--json=c", dev]
    )
    results = json.loads(results)

    if results["device"]["protocol"] == "ATA":
        # SATA device on MegaRAID
        data = results["ata_smart_attributes"]["table"]
        attributes = table_to_attributes_sat(data)
        attributes["smart_passed"] = (0, get_smart_status(results))
        attributes["exit_code"] = (0, exit_code)
        return attributes
    elif results["device"]["protocol"] == "SCSI":
        # SAS device on MegaRAID
        attributes = results_to_attributes_scsi(results)
        attributes["smart_passed"] = get_smart_status(results)
        attributes["exit_code"] = exit_code
        return attributes
    return {}


def collect():
    """
    Collect all drive metrics and save them as Gauge type
    """
    global LABELS, DRIVES, METRICS, SAT_TYPES, NVME_TYPES, SCSI_TYPES

    for drive, drive_attrs in DRIVES.items():
        typ = drive_attrs['type']
        try:
            if "megaraid_id" in drive_attrs:
                attrs = smart_megaraid(
                    drive_attrs["megaraid_id"], drive_attrs["bus_device"]
                )
            elif typ in SAT_TYPES:
                attrs = smart_sat(drive)
            elif typ in NVME_TYPES:
                attrs = smart_nvme(drive)
            elif typ in SCSI_TYPES:
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

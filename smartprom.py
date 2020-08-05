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
                attributes[tokens[1]] = int(tokens[3])
    return attributes


def collect(metrics):
    for drive in DRIVES:
        try:
            attrs = smart(drive)
            for key, value in attrs.items():
                if key in metrics:
                    metrics[key].labels(drive[5:]).set(value)
        except:
            pass


def main():
    start_http_server(9902)

    metrics = {
        'Raw_Read_Error_Rate': Gauge('smartprom_Raw_Read_Error_Rate', 'Read Error Rate', ['drive']),
        'Spin_Up_Time': Gauge('smartprom_Spin_Up_Time', 'Spin-Up Time', ['drive']),
        'Start_Stop_Count': Gauge('smartprom_Start_Stop_Count', 'Start/Stop Count', ['drive']),
        'Reallocated_Sector_Ct': Gauge('smartprom_Reallocated_Sector_Ct', '     Reallocated Sectors Count', ['drive']),
        'Seek_Error_Rate': Gauge('smartprom_Seek_Error_Rate', 'Seek Error Rate', ['drive']),
        'Power_On_Hours': Gauge('smartprom_Power_On_Hours', 'Power-On Hours', ['drive']),
        'Spin_Retry_Count': Gauge('smartprom_Spin_Retry_Count', 'Spin Retry Count', ['drive']),
        'Power_Cycle_Count': Gauge('smartprom_Power_Cycle_Count', 'Power Cycle Count', ['drive']),
        'Runtime_Bad_Block': Gauge('smartprom_Runtime_Bad_Block', 'SATA Downshift Error Count', ['drive']),
        'End-to-End_Error': Gauge('smartprom_End_Error', 'End-to-End error', ['drive']),
        'Reported_Uncorrect': Gauge('smartprom_Reported_Uncorrect', 'Reported Uncorrectable Errors', ['drive']),
        'Command_Timeout': Gauge('smartprom_Command_Timeout', 'Command Timeout', ['drive']),
        'High_Fly_Writes': Gauge('smartprom_High_Fly_Writes', 'High Fly Writes', ['drive']),
        'Airflow_Temperature_Cel': Gauge('smartprom_Airflow_Temperature_Cel', 'Airflow Temperature', ['drive']),
        'G-Sense_Error_Rate': Gauge('smartprom_Sense_Error_Rate', 'G-sense Error Rate', ['drive']),
        'Power-Off_Retract_Count': Gauge('smartprom_Off_Retract_Count', 'Power-off Retract Count', ['drive']),
        'Load_Cycle_Count': Gauge('smartprom_Load_Cycle_Count', 'Load Cycle Count', ['drive']),
        'Temperature_Celsius': Gauge('smartprom_Temperature_Celsius', 'Temperature Celsius', ['drive']),
        'Hardware_ECC_Recovered': Gauge('smartprom_Hardware_ECC_Recovered', 'Hardware ECC Recovered', ['drive']),
        'Current_Pending_Sector': Gauge('smartprom_Current_Pending_Sector', 'Current Pending Sector Count', ['drive']),
        'Offline_Uncorrectable': Gauge('smartprom_Offline_Uncorrectable', 'Uncorrectable Sector Count', ['drive']),
        'UDMA_CRC_Error_Count': Gauge('smartprom_UDMA_CRC_Error_Count', 'UltraDMA CRC Error Count', ['drive']),
        'Head_Flying_Hours': Gauge('smartprom_Head_Flying_Hours', 'Head Flying Hours', ['drive']),
        'Total_LBAs_Written': Gauge('smartprom_Total_LBAs_Written', 'Total LBAs Written', ['drive']),
        'Total_LBAs_Read': Gauge('smartprom_Total_LBAs_Read', 'Total LBAs Read', ['drive'])
    }
    collect(metrics)

    start_time = time.time()
    while True:
        elapsed_time = time.time() - start_time
        if elapsed_time > 60.0:
            start_time = time.time()
            collect(metrics)
        time.sleep(0.1)


if __name__ == '__main__':
    main()
    
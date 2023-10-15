import json
import re

import smartprom

MEGARAID_TYPE_PATTERN = r"(sat\+)?(megaraid,\d+)"


def get_megaraid_device_info(dev: str, typ: str) -> dict:
    """
    Get device information connected with MegaRAID,
    and process the information into get_device_info compatible format.
    """
    megaraid_id = get_megaraid_device_id(typ)
    if megaraid_id is None:
        return {}

    results, _ = smartprom.run_smartctl_cmd(
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


def smart_megaraid(dev: str, megaraid_id: str) -> dict:
    """
    Runs the smartctl command on device connected by MegaRAID
    and processes its attributes
    """
    results, exit_code = smartprom.run_smartctl_cmd(
        ["smartctl", "-A", "-H", "-d", megaraid_id, "--json=c", dev]
    )
    results = json.loads(results)

    if results["device"]["protocol"] == "ATA":
        # SATA device on MegaRAID
        data = results["ata_smart_attributes"]["table"]
        attributes = smartprom.table_to_attributes_sat(data)
        attributes["smart_passed"] = (0, smartprom.get_smart_status(results))
        attributes["exit_code"] = (0, exit_code)
        return attributes
    elif results["device"]["protocol"] == "SCSI":
        # SAS device on MegaRAID
        attributes = smartprom.results_to_attributes_scsi(results)
        attributes["smart_passed"] = smartprom.get_smart_status(results)
        attributes["exit_code"] = exit_code
        return attributes
    return {}

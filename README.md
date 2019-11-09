# Prometheus S.M.A.R.T ctl metrics exporter

This is a simple exporter for the [Prometheus metrics](https://prometheus.io/) using [smartctl](https://www.smartmontools.org/). The script `smartprom.py` also comes with `smartprom.service` so that you can run this script in the background on your Linux OS via `systemctl`. The script will use port `9902`, you can change it by changing it directly in the script. This does not export **all** of the S.M.A.R.T data, only the ones I have been able to harvest from a Seagate Barracuda hard drive.

## Install

1. Copy the `smartprom.service` file into `/etc/systemd/system` folder.
2. Copy the `smartprom.py` file anywhere into your system.
3. Modify `ExecStart=` in the `smartprom.service` so that it points to `smartprom.py` in your system.
4. Run `chmod +x smartprom.py` 
5. Install `prometheus_client` for the root user, example: `sudo -H python3 -m pip install prometheus_client`
6. Run `systemctl enable smartprom` and `systemctl start smartprom`
7. Your metrics will now be available at `http://localhost:9902`

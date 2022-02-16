# Prometheus S.M.A.R.T ctl metrics exporter

![build](https://github.com/matusnovak/prometheus-smartctl/workflows/build/badge.svg)

This is a simple exporter for the [Prometheus metrics](https://prometheus.io/) using [smartctl](https://www.smartmontools.org/). The script `smartprom.py` also comes with `smartprom.service` so that you can run this script in the background on your Linux OS via `systemctl`. The script will use port `9902`, you can change it by changing it directly in the script. This script exports all of the data available from the smartctl.

Docker image here: <https://hub.docker.com/r/matusnovak/prometheus-smartctl>

## Install

_Note: You don't have to do this if you use the Docker image._

1. Copy the `smartprom.service` file into `/etc/systemd/system` folder.
2. Copy the `smartprom.py` file anywhere into your system.
3. Modify `ExecStart=` in the `smartprom.service` so that it points to `smartprom.py` in your system.
4. Run `chmod +x smartprom.py` 
5. Install `prometheus_client` for the root user, example: `sudo -H python3 -m pip install prometheus_client`
6. Run `systemctl enable smartprom` and `systemctl start smartprom`
7. Your metrics will now be available at `http://localhost:9902`

## Docker usage

No extra configuration needed, should work out of the box. The `privileged: true` is required in order for `smartctl` to be able to access drives from the host.

```yml
version: '3'
services:
  smartctl-metrics:
    image: matusnovak/prometheus-smartctl:latest
    restart: unless-stopped
    privileged: true
    ports:
      - 9902:9902
```

Your metrics will be available at <http://localhost:9902/metrics>

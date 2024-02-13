# Changelog


## v2.3.0 (20/01/2024)

* Add support for drives connected by MegaRAID
* Add user_capacity label (disk size in bytes) for each device
* Update prometheus-client 0.19.0
* Update Python 3.12
* Update base Docker image to Alpine 3.19

## v2.2.0 (20/09/2022)

* Add support for USB bridged drives

## v2.1.1 (17/09/2022)

* Handle smartctl exit code != 0 and add smartprom_exit_code metric

## v2.1.0 (21/08/2022)

* Include new metric with SMART Health Status => smartprom_smart_passed
* Add model_family, model_name, serial_number and type attributes for each device
* The "drive" attribute now includes the full path. sda => /dev/sda
* Add more detailed log traces about discovered devices
* Update the Grafana dashboard
* Update Readme to include example metrics

## v2.0.1 (29/07/2022)

* Fix duplicated timeseries error. Resolves #36 (#37)
* Add missing raw metrics for sat devices. Resolves #25 (#38)
* Chore: Code cleanup

## v2.0.0 (28/07/2022)

* Breaking change: Convert the metrics name into lower case (#13)
* Update base Docker image and reduce image size. Resolves #17 (#31)
* Publish Docker images for ARM architecture. Resolves #19 (#34)
* Make refresh interval configurable. Revolves #24 (#29)
* Make exporter port and address configurable via environment variable (#27)
* Include zero value raw metrics (#15)
* Return more information on smartctl error. Resolves #23 (#28)
* Handle error when devices are not detected (#32)
* Using SMART tool to get the devices instead of glob (#14)
* Avoid Python stdout buffering (#33)
* Add Grafana dashboard. Resolves #18 (#30)
* Added gitignore (#12)

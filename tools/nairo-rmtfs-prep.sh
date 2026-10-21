#!/bin/sh
# nairo: prepare the QRTR services the modem looks for while it starts; run
# by rmtfs.service before rmtfs, which starts the modem.
#
# A modem restart within the same boot stalls in its initialisation unless
# tqftpserv and the in-kernel PD mapper are restarted first (their services
# go stale). The first start after boot doesn't need that, and reloading the
# PD mapper right before it seems to be what makes about one cold start in
# five stall, so only do it on a restart.
F=/run/nairo-rmtfs-started
if [ -e "$F" ]; then
	systemctl restart tqftpserv.service
	modprobe -r qcom_pd_mapper
	modprobe qcom_pd_mapper
fi
touch "$F"

# then wait until tqftpserv's TFTP server (QRTR service 4096) is registered
for i in $(seq 1 100); do
	qrtr-lookup | awk '$4 == 1 && $1 == 4096 { f = 1 } END { exit !f }' && exit 0
	sleep 0.1
done
echo "TFTP server not registered after 10 s; starting anyway"

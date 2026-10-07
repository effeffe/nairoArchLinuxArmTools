#!/bin/sh
# nairo: restart the modem if its first start stalls.
#
# On some boots the modem firmware stops early in its startup: it publishes
# only its first two QRTR services (subsystem control, service-registry
# notification), never says hello to Linux's name service, never asks rmtfs
# for its EFS, and its watchdog restarts it 65 s later ("DOG detects stalled
# initialization"). The restart always works, so do it early instead.
for i in $(seq 1 30); do
	[ "$(cat /sys/class/remoteproc/remoteproc0/state 2>/dev/null)" = running ] && break
	sleep 1
done
sleep 15
n=$(qrtr-lookup | awk 'NR > 1 && $4 == 0' | wc -l)
if [ "$n" -le 2 ]; then
	echo "modem published only $n services 15 s after start: restarting it"
	systemctl --no-block restart rmtfs.service
else
	echo "modem up with $n services"
fi

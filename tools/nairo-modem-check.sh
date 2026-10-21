#!/bin/sh
# nairo: restart the modem if its first start stalls, then bring it online.
#
# On some boots the modem firmware stops early in its startup: it publishes
# only its first two QRTR services (subsystem control, service-registry
# notification), never says hello to Linux's name service, never asks rmtfs
# for its EFS, and its watchdog restarts it 65 s later ("DOG detects stalled
# initialization"). The restart always works, so do it early instead.
services() { qrtr-lookup | awk 'NR > 1 && $4 == 0' | wc -l; }

# the modem's remoteproc, found by name: the ADSP may come first
rproc=$(grep -lx modem /sys/class/remoteproc/*/name 2>/dev/null)
rproc=${rproc%/name}
for i in $(seq 1 30); do
	[ "$(cat "$rproc/state" 2>/dev/null)" = running ] && break
	sleep 1
done
sleep 15
n=$(services)
if [ "$n" -le 2 ]; then
	echo "modem published only $n services 15 s after start: restarting it"
	systemctl --no-block restart rmtfs.service
	for i in $(seq 1 60); do
		sleep 1
		n=$(services)
		[ "$n" -gt 2 ] && break
	done
	[ "$n" -gt 2 ] || { echo "modem still has only $n services; giving up"; exit 0; }
	sleep 5
fi
echo "modem up with $n services"

# Android's radio daemon sets the modem online and opens the SIM's GW
# provisioning session after boot. Without the session the USIM
# application stays "detected", and ModemManager reports the SIM missing.
q() { timeout 20 qmicli -d qrtr://0 "$@"; }

for i in 1 2 3 4 5; do
	q --dms-set-operating-mode=online >/dev/null 2>&1 && break
	sleep 2
done
echo "operating mode: $(q --dms-get-operating-mode 2>&1 | sed -n "s/.*Mode: '\(.*\)'/\1/p")"

status=$(q --uim-get-card-status 2>&1)
if ! echo "$status" | grep -q "Primary GW:.*session doesn't exist"; then
	echo "SIM provisioning session already active"
	exit 0
fi
# the slot holding a USIM application, and that application's ID
set -- $(echo "$status" | awk '
	/^Slot \[/ { gsub(/[^0-9]/, "", $2); slot = $2 }
	/Application type:.*usim/ { usim = 1 }
	usim && id { print slot, $1; exit }
	usim && /Application ID:/ { id = 1 }')
if [ -z "${2:-}" ]; then
	echo "no USIM application on the card"
	exit 0
fi
if q --uim-change-provisioning-session="slot=$1,activate=yes,session-type=primary-gw-provisioning,aid=$2" >/dev/null 2>&1; then
	echo "SIM provisioning session activated (slot $1)"
else
	echo "could not activate the SIM provisioning session"
fi

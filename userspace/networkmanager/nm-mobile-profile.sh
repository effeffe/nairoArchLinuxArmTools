#!/bin/sh
# Create a NetworkManager mobile data profile for the nairo modem (QMI).
# Usage: nm-mobile-profile.sh [NAME APN USER PASSWORD]
# Defaults: O2 UK pay-as-you-go. Autoconnect stays off.
set -e
name=${1:-PayAndGo}
apn=${2:-payandgo.o2.co.uk}
user=${3:-payandgo}
pass=${4:-password}

# The attach (initial EPS) bearer gets the same APN: the network refuses a
# second session to the gateway the modem is attached to. A QMI modem stores
# only PAP and CHAP, so refuse the rest or ModemManager's read-back check fails.
# Both passwords go in one command: modifying one alone drops the other.
nmcli connection add type gsm ifname '*' con-name "$name" \
	gsm.apn "$apn" gsm.username "$user" gsm.password "$pass" \
	gsm.initial-eps-bearer-configure yes \
	gsm.initial-eps-bearer-apn "$apn" \
	gsm.initial-eps-bearer-username "$user" \
	gsm.initial-eps-bearer-password "$pass" \
	gsm.initial-eps-bearer-noauth no \
	gsm.initial-eps-bearer-refuse-mschap yes \
	gsm.initial-eps-bearer-refuse-mschapv2 yes \
	gsm.initial-eps-bearer-refuse-eap yes \
	ipv4.method auto ipv6.method disabled \
	connection.autoconnect no

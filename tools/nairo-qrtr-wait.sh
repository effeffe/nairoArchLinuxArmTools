#!/bin/sh
# nairo: wait until tqftpserv's TFTP server (QRTR service 4096) is registered.
# rmtfs starts the modem as soon as it runs, and rmtfs's unit restarts
# tqftpserv just before; a modem that asks for its files before the server is
# announced stalls in its initialisation. (The PD mapper's service locator
# only registers once a remote processor starts, so it can't be waited for.)
for i in $(seq 1 100); do
	qrtr-lookup | awk '$4 == 1 && $1 == 4096 { f = 1 } END { exit !f }' && exit 0
	sleep 0.1
done
echo "TFTP server not registered after 10 s; starting anyway"

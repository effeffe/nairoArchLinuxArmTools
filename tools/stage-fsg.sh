#!/bin/sh
# Extract the modem configs (MCFG) from a dump of the FSG partition (ext2,
# label "FSG") into a directory, to be installed on the phone as
# /usr/lib/firmware/qcom/sm7250/motorola/nairo/fsg/. The patched tqftpserv
# (userspace/tqftpserv) serves it to the modem as /readonly/vendor/fsg/.
#
# Usage: tools/stage-fsg.sh ../backups/rmtfs_backup/modem_fsg out/fsg
set -eu
img=$1 out=$2
[ -e "$out" ] && { echo "$out exists" >&2; exit 1; }
mkdir -p "$out"
# rdump complains that it cannot chown as a normal user; the data is fine
debugfs -R "rdump / $out" "$img" 2>&1 | grep -v "changing ownership" || true
rm -rf "$out/lost+found"
chmod -R a+rX "$out"
test -f "$out/mcfg_sw/mbn_sw.dig" || { echo "no mcfg_sw/mbn_sw.dig in $img" >&2; exit 1; }
echo "$(find "$out" -type f | wc -l) files in $out"

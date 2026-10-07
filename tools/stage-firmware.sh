#!/bin/sh
# Pack the modem and Wi-Fi firmware from the LineageOS modem partition dump
# (vendor_firmware/mnt_image) into out/nairo-firmware.tar.gz, which unpacks to
# /usr/lib/firmware/qcom/sm7250/motorola/nairo/. Independent of the kernel
# version, so it is installed once instead of travelling in every boot image.
set -e
cd "$(dirname "$0")/.."
S=out/fwtree
D=$S/usr/lib/firmware/qcom/sm7250/motorola/nairo
rm -rf "$S"
mkdir -p "$D"
cp vendor_firmware/mnt_image/modem.mdt vendor_firmware/mnt_image/modem.b* \
   vendor_firmware/mnt_image/wlanmdsp.mbn vendor_firmware/mnt_image/bdwlan.* "$D/"
tar -C "$S" --owner=0 --group=0 -czf out/nairo-firmware.tar.gz usr
echo "out/nairo-firmware.tar.gz: $(ls "$D" | wc -l) files, $(du -sh "$D" | cut -f1)"

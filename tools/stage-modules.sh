#!/bin/sh
# Stage the kernel modules for the phone into out/nairo-modtree.tar.gz:
#
#   /usr/lib/modules/<ver>/          every module, indexed: modprobe, udev and
#                                    DKMS work as on any Arch install
#   /usr/local/lib/nairo-modules/... bring-up drivers listed in BRINGUP, not yet
#                                    approved for automatic loading; never
#                                    indexed for the running kernel, loaded only
#                                    by hand with
#                                    modprobe -d /usr/local/lib/nairo-modules <mod>
#                                    (empty: ipa approved for boot 2026-10-07)
#
# Also packs the GPU zap shader and the IPA GSI firmware extracted from the
# LineageOS vendor image.
set -e
cd "$(dirname "$0")/.."
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
# fixed release name: no "+" for uncommitted changes (see nairo.config)
export LOCALVERSION=
BRINGUP=""
S=out/modtree
rm -rf "$S"
make -s -C linux O=../build -j"$(nproc)" modules
make -s -C linux O=../build INSTALL_MOD_PATH="$PWD/$S/usr" INSTALL_MOD_STRIP=1 modules_install
V=$(cat build/include/config/kernel.release)
M=$S/usr/lib/modules/$V
# the headers package provides build/; a symlink here would clobber it
rm -f "$M/build"

P=$S/usr/local/lib/nairo-modules/lib/modules/$V/extra
if [ -n "$BRINGUP" ]; then mkdir -p "$P"; fi
for m in $BRINGUP; do
	f=$(find "$M" -name "$m.ko*")
	[ -n "$f" ] || { echo "bring-up module $m not built" >&2; exit 1; }
	mv $f "$P/"
done
depmod -b "$S/usr" "$V"
[ -z "$BRINGUP" ] || depmod -b "$S/usr/local/lib/nairo-modules" "$V"

Z=$S/usr/lib/firmware/qcom/sm7250/motorola/nairo
mkdir -p "$Z"
cp vendor_firmware/mnt_image/a620_zap.* "$Z/"
# IPA GSI firmware (qcom,gsi-loader = "self"), from the same vendor image
cp vendor_firmware/mnt_image/ipa_fws.* "$Z/"
# modem "software option" files the modem requests over TFTP at startup
# (/readonly/firmware/image/modem_pr/...); without them it stalls and its
# watchdog restarts it after 65 s
cp -r vendor_firmware/mnt_image/modem_pr "$Z/"

tar -C "$S" --owner=0 --group=0 -czf out/nairo-modtree.tar.gz usr
echo "out/nairo-modtree.tar.gz: modules for $V (bring-up, private: $BRINGUP) + a620 zap shader + ipa_fws + modem_pr"

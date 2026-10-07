#!/bin/sh
# Rebuild kernel + DTB + initramfs and pack out/nairo-boot.img (header v2, stock layout).
# fastboot boot is not supported on nairo: test via slot B (fastboot flash boot_b out/nairo-boot.img; set_active b).
set -e
cd "$(dirname "$0")"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
# fixed release name: no "+" for uncommitted changes (see nairo.config)
export LOCALVERSION=

make -s -C linux O=../build -j"$(nproc)" Image qcom/${DTB:=sm7250-motorola-nairo}.dtb \
	drivers/input/touchscreen/nt36xxx-spi/nt36xxx_spi.ko
mkdir -p initramfs/modules initramfs/firmware/novatek
for m in drivers/input/touchscreen/nt36xxx-spi/nt36xxx_spi.ko; do
	aarch64-linux-gnu-strip --strip-debug -o initramfs/modules/${m##*/} build/$m
done

# Module tree + headers matching this kernel, installed on the rootfs by
# /etc/arch-prep when its stamp differs from the installed one
tools/stage-modules.sh
tools/stage-headers.sh
mkdir -p initramfs/payload
cp out/nairo-modtree.tar.gz initramfs/payload/modules.tar.gz
cp out/nairo-headers.tar.gz initramfs/payload/headers.tar.gz
V=$(cat build/include/config/kernel.release)
echo "$V #$(cat build/.version) $(cat initramfs/payload/modules.tar.gz initramfs/payload/headers.tar.gz | sha256sum | cut -c1-16)" \
	> initramfs/payload/stamp

# proprietary touch firmware, extracted from the LineageOS vendor partition
cp vendor_firmware/firmware/novatek_ts_fw.bin initramfs/firmware/novatek/nt36672c-tianma.bin
aarch64-linux-gnu-gcc -static -Os -Wall -o initramfs/root/init initramfs/init.c
aarch64-linux-gnu-strip initramfs/root/init
tools/gen_init_cpio initramfs/initramfs.list | gzip -9 > initramfs/initramfs.cpio.gz

mkdir -p out
mkbootimg --header_version 2 --pagesize 4096 --base 0x0 \
	--kernel_offset 0x8000 --ramdisk_offset 0x01000000 \
	--tags_offset 0x100 --dtb_offset 0x01f00000 \
	--os_version 16.0.0 --os_patch_level 2026-07 \
	--kernel build/arch/arm64/boot/Image \
	--ramdisk initramfs/initramfs.cpio.gz \
	--dtb build/arch/arm64/boot/dts/qcom/$DTB.dtb \
	--cmdline "${CMDLINE:-earlycon console=tty0 ignore_loglevel clk_ignore_unused pd_ignore_unused panic=10 nairo.reboot=120 nairo.root=PARTLABEL=userdata}" \
	-o out/${OUT:=nairo-boot}.img
# the boot partition is 96 MiB (stock boot.img size)
SZ=$(stat -c %s out/$OUT.img)
[ "$SZ" -le 100663296 ] || { echo "out/$OUT.img is $SZ bytes, larger than the 96 MiB boot partition" >&2; exit 1; }
echo "built out/$OUT.img ($DTB, $((SZ / 1048576)) MiB, payload $(cat initramfs/payload/stamp))"

# nairoArchLinuxTools

Scripts, initramfs sources, kernel patches and configuration used to run a
mainline Linux kernel (linux-next 7.3-rc5) and Arch Linux ARM on the Motorola
Moto G 5G Plus (XT2075-3, codename **nairo**, Qualcomm SM7250).

The write-up of the problems and fixes is the blog post *Mainline Linux and Arch
Linux ARM on the Moto G 5G Plus* on effeffe.github.io.

Nothing here is proprietary or binary: no firmware, no boot images, no
prebuilt busybox/dropbear. Those come from your own phone or are built locally
(see below).

## Layout

The scripts expect to run from a project root laid out like this; this repo
provides the files marked (repo):

```
build-nairo.sh             (repo) builds kernel + DTB + initramfs, packs the boot image
tools/                     (repo) staging and helper scripts
initramfs/init.c           (repo) the initramfs init (static C)
initramfs/initramfs.list   (repo) gen_init_cpio list
initramfs/etc/             (repo) rc, arch-prep, passwd, ... (add authorized_keys)
initramfs/third-party/     (repo) busybox .config, dropbear localoptions.h
initramfs/bin/             busybox and dropbear, static aarch64 (build them)
initramfs/firmware/        touch firmware from the vendor partition
kernel/nairo.config        (repo) config fragment (also in the patch series)
kernel/patches/            (repo) the nairo branch as a patch series
linux/                     linux-next next-20261002 with kernel/patches applied
build/                     kernel build output (O=../build)
vendor_firmware/           firmware extracted from the phone (see below)
out/                       build artifacts
```

## Kernel

```
git clone https://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git linux
git -C linux checkout -b nairo next-20261002
git -C linux am ../kernel/patches/*.patch
make -C linux O=../build ARCH=arm64 defconfig nairo.config
```

The series contains, in order: the SM7250 v9 base series (pinctrl, clocks,
device tree; other authors, kept as they were posted), then the nairo work.
Commits marked `LOCAL:` are board or bring-up workarounds that are not meant
for upstream as they stand. Commits written with an AI assistant say so in
their message and carry no Signed-off-by; they need human review before any
submission.

The kernel must be built with a fixed release name (`LOCALVERSION=`, see
`build-nairo.sh`) so that the module payload matches the kernel.

## Firmware (not included)

Copy it from your own phone, e.g. from a LineageOS/stock install:

- `vendor_firmware/mnt_image/`: the contents of the modem partition
  (`/vendor/firmware_mnt/image`): `modem.*`, `wlanmdsp.mbn`, `bdwlan.*`,
  `ipa_fws.*`, `a620_zap.*`, the `modem_pr/` tree;
- `vendor_firmware/firmware/novatek_ts_fw.bin`: the touch firmware.

`tools/stage-modules.sh` puts the GPU zap shader, the IPA firmware and
`modem_pr/` next to the kernel modules; `tools/stage-firmware.sh` packs the
modem and Wi-Fi firmware for `/usr/lib/firmware/qcom/sm7250/motorola/nairo`.

## Initramfs binaries

- busybox 1.38.0, static, with `initramfs/third-party/busybox-1.38.0.config`
  (checksum of the tarball in `busybox-1.38.0.tar.bz2.sha256`);
- dropbear 2026.94, static, with `dropbear-2026.94-localoptions.h` and
  `./configure --host=aarch64-linux-gnu --enable-static --disable-zlib
  --disable-pam --disable-lastlog --disable-utmp --disable-utmpx --disable-wtmp
  --disable-wtmpx --disable-syslog`;
- `tools/gen_init_cpio`: build it from the kernel's `usr/gen_init_cpio.c`.

Put your SSH public key in `initramfs/etc/authorized_keys` (see the example).
`arch-prep` also installs it for root on the Arch system.

## Building and booting

```
./build-nairo.sh                       # out/nairo-boot.img
OUT=name CMDLINE="..." ./build-nairo.sh
fastboot flash boot_b out/nairo-boot.img
fastboot set_active b && fastboot reboot
```

`fastboot boot` does not work on nairo; test images go to slot b. The boot
image carries the matching module tree and kernel headers; `arch-prep` installs
them on the root filesystem when they change.

Root is selected with `nairo.root=` (a device path or `PARTLABEL=<GPT name>`);
the default command line boots `PARTLABEL=userdata` on UFS.

## Warnings

- **Do not repartition the UFS LUNs.** Motorola's bootloader loses every
  partition on every LUN as soon as the `sde` table differs from stock in
  anything but the end of the last partition. `tools/gpt-split-userdata.py`
  documents the experiments; the way back is
  `fastboot flash partition gpt.bin` from the matching stock firmware.
- **Never let sfdisk write these tables:** it drops Motorola's vendor
  attribute bits (3 to 6).
- A boot loop that ends in Qualcomm's 9008 mode is recoverable: hold
  Power + Volume Down into fastboot and flash a known-good boot image.

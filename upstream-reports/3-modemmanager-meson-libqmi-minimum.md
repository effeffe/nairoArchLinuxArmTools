Target: https://gitlab.freedesktop.org/mobile-broadband/ModemManager/-/issues
Title: build: main needs libqmi 1.40 but meson.build accepts >= 1.37.95

ModemManager `main` (7f0bf17) configures fine against the released libqmi
1.38.0, then fails at compile time:

    ../src/mm-modem-helpers-qmi.c: In function 'mm_bearer_ip_family_from_qmi_pdp_type':
    ../src/mm-modem-helpers-qmi.c:2376:10: error: 'QMI_WDS_PDP_TYPE_NON_IP' undeclared

libqmi's `qmi-enums-wds.h` documents `QMI_WDS_PDP_TYPE_NON_IP` as
"Since 1.40", but `meson.build` asks for
`dependency('qmi-glib', version: '>= 1.37.95')`. With the minimum raised to
the libqmi development version that adds the enum (1.39.x, so `>= 1.39.1`
for now), meson would report the missing dependency instead of the build
failing halfway.

Seen while building the AUR `modemmanager-git` package on Arch Linux ARM to
get the netlink use-after-free fix (!1509). Building libqmi from git fixed
the build.

# tqftpserv for nairo

The modem asks for its modem configs (MCFG) under
`/readonly/vendor/fsg/` (`mcfg_sw/mbn_sw.dig` plus the mbn files it lists).
Stock tqftpserv 1.2 rejects that path. The patch maps it to `fsg/` next to
the modem firmware.

Build it on the phone (gcc, meson and ninja are installed there) against
the packaged version:

    git clone https://github.com/linux-msm/tqftpserv && cd tqftpserv
    git checkout v1.2 && git am .../0001-translate-serve-readonly-vendor-fsg-*.patch
    meson setup b --buildtype=release && ninja -C b
    install -m755 b/tqftpserv /usr/local/bin/tqftpserv

Then point the service at it, so the pacman package stays untouched
(`/etc/systemd/system/tqftpserv.service.d/nairo-fsg.conf`):

    [Service]
    ExecStart=
    ExecStart=/usr/local/bin/tqftpserv

Stage the files with `tools/stage-fsg.sh` and copy them to
`/usr/lib/firmware/qcom/sm7250/motorola/nairo/fsg/`.

Reboot after changing anything the modem reads. A live
`systemctl restart rmtfs` right after swapping modem files hung the SoC
twice (watchdog reset, nothing in pstore).

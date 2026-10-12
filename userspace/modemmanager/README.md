# ModemManager for nairo

ModemManager 1.24.2 segfaults while it sets up the data interface
(`qmapmux0.0`): `transaction_complete()` in `src/mm-netlink.c` removes a
netlink request from its hash table, which frees it, and then calls the
request's callback. Whether it crashes depends on whether the memory has
been reused, so a connect sometimes works and sometimes kills
ModemManager. The coredump shows a call to `0x30` from
`ModemManager+0x19759c`.

Upstream fixed it in merge request !1509 (commit 9317cbc, 4 October 2026),
which is not in a release yet. Two ways to get it:

- **Build ModemManager from git** (what the phone runs): the AUR packages
  `libqmi-git` and `modemmanager-git`, built as a normal user, not root.
  ModemManager main needs libqmi 1.40 (`QMI_WDS_PDP_TYPE_NON_IP`), so build
  and install `libqmi-git` first, even though ModemManager's meson accepts
  1.38.

      cd ~/aur/libqmi-git && makepkg -si
      cd ~/aur/modemmanager-git && makepkg -si
      sudo systemctl restart ModemManager

- **Patch 1.24.2:** add the upstream commit
  (`0001-netlink-fix-use-after-free-calling-completion_fn-on-.patch`) to
  `prepare()` in Arch's `modemmanager` PKGBUILD, bump `pkgrel`, and add
  `IgnorePkg = modemmanager` to `/etc/pacman.conf` until a release with the
  fix is out. The patch applies cleanly to 1.24.2.

Once a release has the fix, go back to the official packages.

## Keeping the modem across suspend

By default ModemManager removes every modem when the system suspends and
probes again on resume. The nairo modem (QRTR, `qcom-soc` plugin) stays
powered in s2idle and is not announced again, so after the first suspend
`mmcli -L` reports "No modems were found" and calls and SMS stop working,
although the modem remoteproc is still running.

`--test-quick-suspend-resume` keeps the modem object and only resyncs its
state on resume, which is what a modem that stays on needs. Install the
drop-in:

    sudo install -Dm644 quick-resume.conf \
        /etc/systemd/system/ModemManager.service.d/quick-resume.conf
    sudo systemctl daemon-reload
    sudo systemctl restart ModemManager

# Mobile data with NetworkManager

`nm-mobile-profile.sh` creates a NetworkManager profile for mobile data.
The defaults are for O2 UK pay-as-you-go; pass the APN, user and password
for another network. The profile has autoconnect off, so data only comes
up when it's turned on from Plasma or with `nmcli c up <name>`.

    sudo ./nm-mobile-profile.sh                   # PayAndGo, payandgo.o2.co.uk
    sudo ./nm-mobile-profile.sh NAME APN USER PASSWORD

What it works around:

- **The APN.** Automatic APN lookup can't tell O2 from the virtual
  operators that share its operator code (23410), so the APN is set by hand.
- **The attach APN.** On LTE the modem already holds a data session from
  attaching, with the APN in modem profile 2, and the network refuses a
  second session to the same gateway (`multiple-connection-to-same-pdn-not-allowed`).
  The modem rewrites profile 2 from its carrier configuration at every
  boot, so the profile sets the attach APN too
  (`gsm.initial-eps-bearer-*`), and ModemManager updates it before each
  connect.
- **Authentication methods.** NetworkManager asks for every method for the
  attach bearer by default; a QMI modem stores only PAP and CHAP, and
  ModemManager then fails with "requested and reloaded initial EPS bearer
  settings don't match". The profile refuses the others.
- **Passwords.** `nmcli c modify` on only one of `gsm.password` and
  `gsm.initial-eps-bearer-password` drops the other from the saved profile.
  Always set both in the same command.

It needs a ModemManager with the netlink fix (see `../modemmanager`).

NetworkManager warns that it can't set the 1500-byte MTU the modem reports
(`rmnet_ipa0` is limited to 1496). The connection works anyway.

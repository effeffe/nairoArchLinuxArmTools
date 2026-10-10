Target: https://bugs.kde.org (product plasma-nm)
Title: Editing a mobile broadband connection drops NetworkManager's initial EPS bearer settings

### Summary
After a mobile broadband (gsm) connection is edited and saved in Plasma's
network settings, every `gsm.initial-eps-bearer-*` property is gone from
the saved profile: `initial-eps-bearer-configure`, `-apn`, `-username`,
`-noauth` and `-refuse-*`. Only the properties plasma-nm shows survive.

On LTE networks where the attach APN must match the data APN, the
connection then fails (`multiple-connection-to-same-pdn-not-allowed`).

### Versions
NetworkManager 1.58.1, plasma-nm from Plasma Mobile on Arch Linux ARM
(October 2026).

### Steps to reproduce
1. Create the profile with nmcli:

       nmcli c add type gsm ifname '*' con-name t gsm.apn example \
           gsm.initial-eps-bearer-configure yes \
           gsm.initial-eps-bearer-apn example \
           gsm.initial-eps-bearer-noauth no

2. Open it in Plasma's network settings, change any field (for example
   "Only use home network"), and save.
3. `nmcli -f gsm c show t`: `initial-eps-bearer-configure` is `no`, and
   the APN and the other initial EPS settings are empty.

NetworkManager's audit log shows the update coming from plasma-nm (uid
1000) with only the edited fields listed in `args`, but the stored keyfile
loses the whole set.

### Expected
Settings that plasma-nm doesn't display are kept when saving.

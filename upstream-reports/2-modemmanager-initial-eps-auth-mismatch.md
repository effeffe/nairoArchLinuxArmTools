Target: https://gitlab.freedesktop.org/mobile-broadband/ModemManager/-/issues
Title: QMI: setting initial EPS bearer settings fails when allowed-auth includes methods QMI can't store

### Summary
`SetInitialEpsBearerSettings` with an `allowed-auth` mask that includes
anything besides PAP and CHAP always fails:

    <wrn> [modem0] requested and reloaded initial EPS bearer settings don't match
    ... Initial EPS bearer settings were not updated

The modem has actually been updated (the profile shows the new APN and the
modem re-attaches with it), but the call reports failure. NetworkManager
stops the activation there (`gsm-apn-failed`).

NetworkManager hits this with its default settings. Unless the user sets
`gsm.initial-eps-bearer-noauth no` and refuses MSCHAP, MSCHAPv2 and EAP, it
requests `none|pap|chap|mschap|mschapv2|eap`
(`src/core/devices/wwan/nm-modem-broadband.c`, `CONNECT_STEP_INTIAL_EPS_BEARER`).

### Versions
- ModemManager main at 7f0bf17, and 1.24.2.
- libqmi main at 1c972b8.
- NetworkManager 1.58.1.
- Hardware: SM7250 (Motorola moto g 5G plus) over QRTR.

### Cause
- `mm_bearer_allowed_auth_to_qmi_authentication()` keeps only the PAP and
  CHAP bits when it writes the profile, and silently drops the rest.
- On reload the modem reports `pap, chap`.
- `handle_set_initial_eps_bearer_settings_reload_ready()` compares that to
  the original request with `MM_BEARER_PROPERTIES_CMP_FLAGS_EPS`.
  `cmp_allowed_auth()` requires an exact match (with the loose UNKNOWN cases
  only), so `pap|chap` never equals `none|pap|chap|mschap|mschapv2|eap`.

Possible fixes:
- before comparing, reduce the requested mask to what the backend can store
  (for QMI: PAP|CHAP, or NONE);
- or reject the request up front with "unsupported authentication methods"
  instead of writing it and then reporting failure.

### Workaround
In the NetworkManager profile:

    gsm.initial-eps-bearer-noauth no
    gsm.initial-eps-bearer-refuse-mschap yes
    gsm.initial-eps-bearer-refuse-mschapv2 yes
    gsm.initial-eps-bearer-refuse-eap yes

With these, the requested mask is `pap|chap` and the connection comes up.

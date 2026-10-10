Target: https://gitlab.freedesktop.org/NetworkManager/NetworkManager/-/issues
Title: nmcli connection modify of one gsm secret drops the other gsm secrets

### Summary
A gsm setting has several secrets (`gsm.password`, `gsm.pin`,
`gsm.initial-eps-bearer-password`). Running `nmcli connection modify` on one
of them saves the profile without the others. The connection then sits in
`need-auth` until it times out.

### Version
NetworkManager 1.58.1 (Arch Linux ARM, aarch64), keyfile plugin. I read the
code in 1.58.1 only and haven't checked `main`.

### Steps to reproduce
No modem is needed:

    nmcli c add type gsm ifname '*' con-name t \
        gsm.apn example gsm.password p1 gsm.initial-eps-bearer-password p2
    nmcli -s -f gsm.password,gsm.initial-eps-bearer-password c show t
    #   both set
    nmcli c modify t gsm.initial-eps-bearer-password p3
    nmcli -s -f gsm.password,gsm.initial-eps-bearer-password c show t
    #   gsm.password: --   (also gone from the keyfile)

Changing `gsm.password` on its own clears `gsm.initial-eps-bearer-password`
the same way. Setting both in one `modify` keeps both.

### Expected
Secrets that the command doesn't touch are kept.

### Cause (from reading the 1.58.1 code)
- `do_connection_modify()` in `src/nmcli/connections.c` doesn't fetch the
  existing secrets before calling Update. `edit` and `clone` do this through
  `update_secrets_in_connection()`.
- In `update_auth_cb()` (`src/core/settings/nm-settings-connection.c`), the
  daemon merges the stored secrets back into the new connection only when it
  carries no secrets at all (`_nm_connection_aggregate(...,
  NM_CONNECTION_AGGREGATE_ANY_SECRETS)`).
- So an update that carries exactly one secret replaces the whole set. That
  goes unnoticed for settings with a single secret, but not for gsm.

Possible fixes: have nmcli `modify` call `update_secrets_in_connection()` as
`edit` does, or have the daemon merge secrets per secret instead of all or
nothing.

### Impact
With `initial-eps-bearer-configure`, users have to set both passwords. Fixing
one of them later silently breaks the profile, and nothing in the logs says a
password went missing: the device just stays in `need-auth`.

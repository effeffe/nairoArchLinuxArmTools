# Device tree references

Decompiled device trees from the stock software, used as the reference
for the mainline DTS (regulators, GPIOs, panel timings, bus votes, ...).

| File | Source |
|---|---|
| `lito-moto-base.dts` | base DTB from the stock (Android 11) boot image |
| `nairo-pvt-overlay.dts` | nairo PVT entry of the stock dtbo |
| `nairo-pvt-merged.dts` | base with the overlay applied, as ABL does |
| `lineage-live.dts` | `/sys/firmware/fdt` from a running LineageOS 23 |
| `lineage-cmdline.txt` | `/proc/cmdline` from the same LineageOS boot |

Per-device values (serial number, Wi-Fi and Bluetooth MAC, CID, SoC
serial, ssm_data) are replaced with `REDACTED`. Recompile with
`dtc -I dts -O dtb` if a binary is needed.

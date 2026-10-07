#!/usr/bin/env python3
"""Build ath10k board-2.bin files from Motorola's nairo WLAN board data.

On Android, cnss-daemon picks the board data file by device and radio
(table in vendor/bin/cnss-daemon): bdwlan_nairo_<nv>.bin with
  radio NA -> ipa, VZW -> ipav, EMLA -> ipae, anything else -> ipa
and uses the "bdwlanu_" set only for WCN3990 chip_id 0x4320 (nairo reports
0x320). ath10k instead looks the board data up in board-2.bin by name; with
qcom,calibration-variant = "motorola_nairo" in the device tree that name is
  bus=snoc,qmi-board-id=ff,qmi-chip-id=320,variant=motorola_nairo

This writes one board-2-nairo-<nv>.bin per variant, each holding that single
entry; arch-prep installs the one matching androidboot.radio as
/usr/lib/firmware/updates/ath10k/WCN3990/hw1.0/board-2.bin.

Usage: make-nairo-board2.py <dir with bdwlan_nairo_*.bin> <output dir>
"""
import os
import struct
import sys

NAME = "bus=snoc,qmi-board-id=ff,qmi-chip-id=320,variant=motorola_nairo"
MAGIC = b"QCA-ATH10K-BOARD\0"
IE_BOARD, IE_NAME, IE_DATA = 0, 0, 1


def pad4(b):
    return b + b"\0" * (-len(b) % 4)


def ie(kind, data):
    return struct.pack("<II", kind, len(data)) + pad4(data)


def board2(bdf):
    board = ie(IE_NAME, NAME.encode()) + ie(IE_DATA, bdf)
    return pad4(MAGIC) + ie(IE_BOARD, board)


src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
for nv in ("ipa", "ipae", "ipav"):
    bdf = open(os.path.join(src, f"bdwlan_nairo_{nv}.bin"), "rb").read()
    path = os.path.join(out, f"board-2-nairo-{nv}.bin")
    open(path, "wb").write(board2(bdf))
    print(f"{path}: {len(bdf)} bytes of board data, {NAME}")

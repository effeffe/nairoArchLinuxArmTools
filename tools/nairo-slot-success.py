#!/usr/bin/env python3
"""Mark the active A/B slot as successfully booted, like Android's bootctrl.

Motorola's bootloader (Qualcomm A/B scheme) keeps the slot state in the GPT
attribute bits of boot_a/boot_b: bits 48-49 priority, 50 active, 51-53 retry
count, 54 successful, 55 unbootable. Every boot of a slot that is not marked
successful costs one retry; when they run out the bootloader falls back to
the other slot. Android sets "successful" after a good boot; nothing did on
Arch, so a few reboots without `fastboot set_active` switched to slot a.

This sets bit 54 on the active slot's boot partition entry, in both the
primary and the backup GPT of that LUN, and recomputes the two CRCs. Nothing
else changes; the bootloader rewrites these bits itself at every boot and on
`fastboot set_active`.

Usage: nairo-slot-success.py [--write]     (dry run without --write)
"""
import glob
import os
import struct
import sys
import zlib

ACTIVE, SUCCESSFUL, UNBOOTABLE = 1 << 50, 1 << 54, 1 << 55
write = "--write" in sys.argv


def die(msg):
    sys.exit("nairo-slot-success: " + msg)


def gpt(fd, bs, lba):
    h = bytearray(os.pread(fd, bs, lba * bs))
    if h[:8] != b"EFI PART":
        return None
    hsize, hcrc = struct.unpack("<II", h[12:20])
    chk = bytearray(h[:hsize])
    chk[16:20] = bytes(4)
    if zlib.crc32(chk) != hcrc:
        die(f"header CRC mismatch at LBA {lba}")
    alt = struct.unpack("<Q", h[32:40])[0]
    ent_lba, nent, esz, ecrc = struct.unpack("<QIII", h[72:92])
    n = (nent * esz + bs - 1) // bs
    e = bytearray(os.pread(fd, n * bs, ent_lba * bs))
    if zlib.crc32(e[:nent * esz]) != ecrc:
        die(f"entry CRC mismatch at LBA {ent_lba}")
    return dict(h=h, hsize=hsize, alt=alt, ent_lba=ent_lba, nent=nent, esz=esz, e=e)


def name(g, i):
    o = i * g["esz"]
    return g["e"][o + 56:o + 128].decode("utf-16le").rstrip("\0")


def attr(g, i):
    return struct.unpack("<Q", g["e"][i * g["esz"] + 48:i * g["esz"] + 56])[0]


found = []
for dev in sorted(glob.glob("/dev/sd[a-z]")):
    n = os.path.basename(dev)
    bs = int(open(f"/sys/class/block/{n}/queue/logical_block_size").read())
    fd = os.open(dev, os.O_RDONLY)
    p = gpt(fd, bs, 1)
    if p:
        for i in range(p["nent"]):
            if name(p, i) in ("boot_a", "boot_b") and attr(p, i) & ACTIVE:
                found.append((dev, bs, i, name(p, i)))
    os.close(fd)
if len(found) != 1:
    die(f"expected exactly one active boot slot, found {found}")
dev, bs, idx, slot = found[0]

fd = os.open(dev, os.O_RDWR | os.O_SYNC if write else os.O_RDONLY)
p = gpt(fd, bs, 1)
b = gpt(fd, bs, p["alt"])
if not b or name(b, idx) != slot or attr(b, idx) != attr(p, idx):
    die("backup GPT does not match the primary for " + slot)
a = attr(p, idx)
retry = (a >> 51) & 7
print(f"{slot} on {dev} entry {idx + 1}: attrs {a:#018x} (active, retry {retry}, "
      f"successful {int(bool(a & SUCCESSFUL))}, unbootable {int(bool(a & UNBOOTABLE))})")
if a & UNBOOTABLE:
    die("slot is marked unbootable; not touching it")
if a & SUCCESSFUL:
    print("already marked successful")
    sys.exit(0)
new = a | SUCCESSFUL
print(f"new attrs {new:#018x}")
if not write:
    print("dry run; rerun with --write")
    sys.exit(0)

for g, hdr_lba in ((b, p["alt"]), (p, 1)):        # backup first, primary last
    struct.pack_into("<Q", g["e"], idx * g["esz"] + 48, new)
    struct.pack_into("<I", g["h"], 88, zlib.crc32(g["e"][:g["nent"] * g["esz"]]))
    struct.pack_into("<I", g["h"], 16, 0)
    struct.pack_into("<I", g["h"], 16, zlib.crc32(g["h"][:g["hsize"]]))
    os.pwrite(fd, g["e"], g["ent_lba"] * bs)
    os.pwrite(fd, g["h"], hdr_lba * bs)
os.fsync(fd)
print(f"marked {slot} successful")

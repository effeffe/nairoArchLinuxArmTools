#!/usr/bin/env python3
"""Split nairo's userdata (sde27) to make room for Arch, editing the GPT in place.

Motorola's ABL (MotoBootModule) loses every partition on every LUN when the
sde table has more than its stock 27 entries (tested: 28 and 128), but it
accepts a smaller userdata. So Arch reuses entry 25, "padA": 640 KiB of
padding before super that no boot stage references (no ASCII/UTF-16 "padA"
in XBL, the XBL UEFI core or ABL) and that stock firmware never flashes.

Modes (each a dry run unless --write is given):
  --shrink-only        userdata ends at USERDATA_END; nothing else changes
  --reuse-pada         also move entry 25 (padA) to the freed space,
                       keeping its name, type GUID, unique GUID and attributes
  --reuse-pada --as-arch
                       as above, and rename entry 25 to "arch" with the Linux
                       filesystem type GUID
  --arch-first [--as-arch]
                       arch (entry 25) right after super, userdata moved up to
                       end the LUN, so userdata stays the last partition
  --undo FILE          write back the LBAs saved by an earlier --write

Only the touched entries' bytes, the entry-array CRC and the header CRC
change, in both the primary and the backup GPT. Header geometry (entry
count 27, first/last usable LBA) and every other entry, including its
GUIDs, names and vendor attribute bits, stay byte-for-byte identical; sfdisk
cannot do this (it drops attribute bits 3-6).
Before writing, the four original LBAs go to /root/sde-gpt-<time>.bin.
The full fallback is `fastboot flash partition gpt.bin` from stock firmware.
"""
import os
import struct
import sys
import time
import uuid
import zlib

USERDATA_START, USERDATA_FULL_END = 2404864, 30746618
USERDATA_END = 15512063          # 50 GiB (4 KiB sectors)
ARCH_START, ARCH_END = USERDATA_END + 1, USERDATA_FULL_END
PADA_START, PADA_END = 29024, 29183
# --arch-first: ABL rejected every table with a partition above userdata
# (28 entries, 128 entries, padA moved behind userdata), so put arch first:
# arch right after super, userdata (1 MiB aligned) last up to the end of the LUN
AF_ARCH_START, AF_ARCH_END = USERDATA_START, 17639423      # 58.115 GiB
AF_USERDATA_START = AF_ARCH_END + 1                        # 17639424 = 68904 MiB
BASIC_DATA = uuid.UUID("EBD0A0A2-B9E5-4433-87C0-68B6B72699C7")
LINUX_FS = uuid.UUID("0FC63DAF-8483-4772-8E79-3D69D8477DE4")
NENT = 27

# Stock attribute bits (RPNS31.Q4U-39-27-9-2-9 gpt.bin, LUN 4); all others 0
STOCK_ATTRS = {1: 0x1000000000000008, 2: 0x28, 3: 0x8, 4: 0x28, 5: 0x28, 6: 0x20,
               8: 0x1000000000000020, 9: 0x18, 10: 0x8, 12: 0x18, 13: 0x18,
               14: 0x18, 15: 0x18, 16: 0x38, 17: 0x1000000000000020,
               18: 0x1000000000000008, 19: 0x1000000000000008,
               20: 0x1000000000000008, 21: 0x8, 22: 0x1000000000000008,
               23: 0x1000000000000008, 24: 0x1000000000000008, 26: 0x48, 27: 0x18}

args = sys.argv[1:]
dev = args[0]
write = "--write" in args
undo = args[args.index("--undo") + 1] if "--undo" in args else None
arch_first = "--arch-first" in args
reuse = "--reuse-pada" in args or arch_first
as_arch = "--as-arch" in args
if not (undo or reuse or "--shrink-only" in args):
    sys.exit("give a mode: --shrink-only, --reuse-pada, --arch-first [--as-arch] or --undo FILE")
if as_arch and not reuse:
    sys.exit("--as-arch needs --reuse-pada or --arch-first")
if arch_first:
    ud_start, ud_end, a_start, a_end = AF_USERDATA_START, USERDATA_FULL_END, AF_ARCH_START, AF_ARCH_END
else:
    ud_start, ud_end, a_start, a_end = USERDATA_START, USERDATA_END, ARCH_START, ARCH_END

if os.path.isfile(dev):          # test image: 4 KiB sectors like the UFS LUN
    bs, nblocks = 4096, os.path.getsize(dev) // 4096
else:
    name = os.path.basename(dev)
    bs = int(open(f"/sys/class/block/{name}/queue/logical_block_size").read())
    nblocks = int(open(f"/sys/class/block/{name}/size").read()) * 512 // bs
fd = os.open(dev, os.O_RDWR | os.O_SYNC if (write or undo) else os.O_RDONLY)


def rd(lba, n=1):
    return bytearray(os.pread(fd, n * bs, lba * bs))


def die(msg):
    sys.exit("REFUSING: " + msg)


if undo:
    blob = open(undo, "rb").read()
    lbas = struct.unpack("<4Q", blob[:32])  # p_hdr, p_ent, b_ent, b_hdr
    for i, lba in enumerate(lbas):
        os.pwrite(fd, blob[32 + i * bs:32 + (i + 1) * bs], lba * bs)
    os.fsync(fd)
    print("restored LBAs", lbas, "from", undo)
    sys.exit(0)


def parse(hdr_lba):
    h = rd(hdr_lba)
    if h[:8] != b"EFI PART":
        die(f"no GPT header at LBA {hdr_lba}")
    hsize, hcrc = struct.unpack("<II", h[12:20])
    my, alt, first, last = struct.unpack("<4Q", h[24:56])
    ent_lba, nent, esz, ecrc = struct.unpack("<QIII", h[72:92])
    chk = bytearray(h[:hsize])
    chk[16:20] = b"\0\0\0\0"
    if zlib.crc32(chk) != hcrc:
        die(f"header CRC mismatch at LBA {hdr_lba}")
    ents = rd(ent_lba)
    if esz != 128 or nent * esz > bs:
        die(f"unexpected entry layout ({nent} x {esz})")
    if zlib.crc32(ents[:nent * esz]) != ecrc:
        die(f"entry array CRC mismatch at LBA {ent_lba}")
    return dict(h=h, hsize=hsize, my=my, alt=alt, first=first, last=last,
                ent_lba=ent_lba, nent=nent, ents=ents)


def entry(ents, i):
    e = ents[i * 128:(i + 1) * 128]
    t = uuid.UUID(bytes_le=bytes(e[:16]))
    u = uuid.UUID(bytes_le=bytes(e[16:32]))
    s, en, attr = struct.unpack("<QQQ", e[32:56])
    n = e[56:128].decode("utf-16le").rstrip("\0")
    return t, u, s, en, attr, n


p = parse(1)
b = parse(p["alt"])
if p["alt"] != nblocks - 1 or b["my"] != nblocks - 1 or b["alt"] != 1:
    die("primary/backup header locations are not the standard ones")
for g in (p, b):
    if g["nent"] != NENT or (g["first"], g["last"]) != (6, USERDATA_FULL_END):
        die(f"not the stock 27-entry geometry: {g['nent']} {g['first']} {g['last']}")
if p["ents"][:NENT * 128] != b["ents"][:NENT * 128]:
    die("primary and backup entry arrays differ")
for idx in range(1, NENT + 1):
    want, have = STOCK_ATTRS.get(idx, 0), entry(p["ents"], idx - 1)[4]
    if have != want:
        die(f"entry {idx} attributes {have:#x}, stock {want:#x}: flash the stock gpt.bin first")

t, u, s, en, attr, n = entry(p["ents"], 26)
if (n, t) != ("userdata", uuid.UUID("1B81E7E6-F50D-419B-A739-2AEEF8DA3335")) \
        or (s, en) not in ((USERDATA_START, USERDATA_FULL_END), (USERDATA_START, USERDATA_END),
                           (AF_USERDATA_START, USERDATA_FULL_END)):
    die(f"entry 27 is not userdata as expected: {n} {s}-{en}")
t, u, s, en, attr, n = entry(p["ents"], 24)
if (s, en) not in ((PADA_START, PADA_END), (ARCH_START, ARCH_END), (AF_ARCH_START, AF_ARCH_END)) \
        or n not in ("padA", "arch") or t not in (BASIC_DATA, LINUX_FS) or attr:
    die(f"entry 25 is not padA as expected: {n} {t} {s}-{en} attrs={attr:#x}")
if any(entry(p["ents"], i)[2] <= max(a_end, ud_end) and entry(p["ents"], i)[3] >= min(a_start, ud_start)
       for i in range(NENT) if i not in (24, 26)):
    die("another entry overlaps the new arch/userdata ranges")


def rebuild(g):
    ents = bytearray(g["ents"])
    struct.pack_into("<QQ", ents, 26 * 128 + 32, ud_start, ud_end)
    if reuse:
        o = 24 * 128
        struct.pack_into("<QQ", ents, o + 32, a_start, a_end)
        if as_arch:
            ents[o:o + 16] = LINUX_FS.bytes_le
            ents[o + 56:o + 128] = bytes(72)
            nm = "arch".encode("utf-16le")
            ents[o + 56:o + 56 + len(nm)] = nm
    h = bytearray(g["h"])
    struct.pack_into("<I", h, 88, zlib.crc32(ents[:NENT * 128]))
    struct.pack_into("<I", h, 16, 0)
    struct.pack_into("<I", h, 16, zlib.crc32(h[:g["hsize"]]))
    return h, ents


ph, pe = rebuild(p)
bh, be = rebuild(b)
for label, ents in (("primary", pe), ("backup", be)):
    for i in (24, 25, 26):
        t, u, s, en, attr, n = entry(ents, i)
        print(f"{label} #{i + 1}: {n:9s} {s:>9}-{en:<9} {(en - s + 1) * bs / 2**30:7.3f} GiB "
              f"attrs={attr:#x} type={t} uuid={u}")
changed = [i for i in range(NENT * 128) if p["ents"][i] != pe[i]]
if changed:
    print(f"entry bytes changed: {len(changed)}, in entries",
          sorted({i // 128 + 1 for i in changed}))
else:
    print("entry array already in the requested state")
print(f"header: {NENT} entries, first/last usable {p['first']}/{p['last']}, unchanged")

if not write:
    print("dry run only; rerun with --write")
    sys.exit(0)

save = time.strftime(os.environ.get("GPT_SAVE_DIR", "/root") + "/sde-gpt-%Y%m%d-%H%M%S.bin")
with open(save, "wb") as f:
    f.write(struct.pack("<4Q", 1, p["ent_lba"], b["ent_lba"], b["my"]))
    for lba in (1, p["ent_lba"], b["ent_lba"], b["my"]):
        f.write(rd(lba))
    f.flush()
    os.fsync(f.fileno())
print("saved the previous LBAs to", save, "(undo: --undo", save + ")")

# backup first, primary last: a torn write leaves one valid copy
os.pwrite(fd, be, b["ent_lba"] * bs)
os.pwrite(fd, bh, b["my"] * bs)
os.pwrite(fd, pe, p["ent_lba"] * bs)
os.pwrite(fd, ph, 1 * bs)
os.fsync(fd)
print("written; now: sgdisk -v", dev, "; blockdev --rereadpt", dev)

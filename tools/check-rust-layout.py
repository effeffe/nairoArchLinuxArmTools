#!/usr/bin/env python3
"""Compare struct layouts in the kernel (GCC, from vmlinux DWARF via pahole)
with the Rust bindings bindgen generated for the same build.

A mismatch means Rust code reads the wrong fields: with CONFIG_SCHEDSTATS off,
bindgen dropped the alignment of the empty struct sched_statistics and every
task_struct field after "stats" was 40 bytes off (rust_binder mmap -EINVAL).

Usage: tools/check-rust-layout.py [struct ...]   (run after a kernel build)
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
STRUCTS = sys.argv[1:] or ["task_struct", "mm_struct", "vm_area_struct", "file",
                           "inode", "cred", "page", "folio", "dentry", "super_block"]


def rust_layouts(bindings, structs):
    src = open(bindings).read()
    src = re.sub(r", MaybeZeroable\)", ")", src)
    src = re.sub(r"\(MaybeZeroable, ", "(", src)
    src = re.sub(r"#\[derive\(MaybeZeroable\)\]", "", src)
    src = re.sub(r"#\[cfi_encoding[^\]]*\]", "", src)
    fields = {}
    for s in structs:
        m = re.search(r"pub struct %s \{(.*?)\n\}\n" % s, src, re.S)
        if not m:
            continue
        fields[s] = re.findall(r"^\s+pub (\w+):", m.group(1), re.M)
    prints = []
    for s, fl in fields.items():
        prints.append('println!("{} size {}", "%s", size_of::<b::%s>());' % (s, s))
        prints += ['println!("{} {} {}", "%s", "%s", offset_of!(b::%s, %s));' % (s, f, s, f)
                   for f in fl]
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "bg.rs"), "w").write(src)
        open(os.path.join(d, "main.rs"), "w").write(
            "#![allow(warnings)]\n"
            "mod ffi { pub use core::ffi::*; }\n"
            "mod b { use super::ffi; type __kernel_size_t = usize; "
            "type __kernel_ssize_t = isize; type __kernel_ptrdiff_t = isize;\n"
            'include!("bg.rs"); }\n'
            "fn main() { use core::mem::{offset_of, size_of};\n" + "\n".join(prints) + "\n}\n")
        subprocess.run(["rustc", "--edition", "2021", "-O", "main.rs", "-o", "lay"],
                       cwd=d, check=True, capture_output=True)
        out = subprocess.run([os.path.join(d, "lay")], capture_output=True, text=True).stdout
    res = {}
    for line in out.splitlines():
        p = line.split()
        if p[1] == "size":
            res.setdefault(p[0], {})["<size>"] = int(p[2])
        else:
            res.setdefault(p[0], {})[p[1]] = int(p[2])
    return res


def gcc_layout(vmlinux, s):
    out = subprocess.run(["pahole", "-C", s, vmlinux], capture_output=True, text=True).stdout
    res = {}
    for line in out.splitlines():
        m = re.match(r"\s+.*?[\s\*](\w+)(\[[^\]]*\])?(?: __attribute__\(\(.*?\)\))?;"
                     r"\s+/\*\s+(\d+)\s+\d+\s+\*/", line)
        if m:
            res.setdefault(m.group(1), int(m.group(3)))
        m = re.match(r"\s+/\* size: (\d+),", line)
        if m:
            res["<size>"] = int(m.group(1))
    return res


def main():
    rust = rust_layouts(os.path.join(BUILD, "rust/bindings/bindings_generated.rs"), STRUCTS)
    bad = 0
    for s in STRUCTS:
        g = gcc_layout(os.path.join(BUILD, "vmlinux"), s)
        r = rust.get(s)
        if not g or not r:
            print("%-16s skipped (missing in %s)" % (s, "pahole" if not g else "bindings"))
            continue
        diffs = [(f, g[f], r[f]) for f in r if f in g and g[f] != r[f]]
        if diffs:
            bad += 1
            f, go, ro = diffs[0]
            print("%-16s MISMATCH: first at %s gcc %#x rust %#x (%d fields differ)"
                  % (s, f, go, ro, len(diffs)))
        else:
            print("%-16s ok (size %#x, %d fields)" % (s, g.get("<size>", -1), len(r) - 1))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

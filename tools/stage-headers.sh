#!/bin/sh
# Package the headers of the current build for out-of-tree modules (DKMS) on
# the phone: out/nairo-headers.tar.gz unpacks to /usr/lib/modules/<ver>/build,
# a merged source + build tree like Arch's linux-headers.
#
# The kernel is cross-compiled, so the host helpers that an external module
# build runs are rebuilt here for aarch64. This config needs only fixdep and
# modpost: no module versioning (genksyms), no module signing (sign-file),
# no active GCC plugins, no objtool on arm64.
set -e
cd "$(dirname "$0")/.."
S=linux
B=build
V=$(cat "$B/include/config/kernel.release")
O=out/headers
H=$O/usr/lib/modules/$V/build
CC=aarch64-linux-gnu-gcc

for c in MODVERSIONS MODULE_SIG GCC_PLUGIN_LATENT_ENTROPY KSTACK_ERASE; do
	grep -q "^CONFIG_$c=y" "$B/.config" &&
		{ echo "CONFIG_$c needs more aarch64 host tools; extend this script" >&2; exit 1; }
done

rm -rf "$O"
mkdir -p "$H"

# source: build system, headers, arm64 arch tree (without the DTS sources)
tar -C "$S" -cf - --exclude-vcs --exclude=arch/arm64/boot/dts \
	Makefile Kbuild Kconfig scripts include arch/arm64 localversion-next 2>/dev/null |
	tar -C "$H" -xf -

# build output: config, symbols, generated headers, generated script inputs
for f in .config Module.symvers System.map include/config include/generated \
	 arch/arm64/include/generated scripts/module.lds \
	 scripts/mod/elfconfig.h scripts/mod/devicetable-offsets.h; do
	[ -e "$B/$f" ] || continue
	mkdir -p "$H/$(dirname "$f")"
	cp -a "$B/$f" "$H/$f"
done

# aarch64 host helpers
CFLAGS="-O2 -Wall -I $S/scripts/include"
$CC $CFLAGS -o "$H/scripts/basic/fixdep" "$S/scripts/basic/fixdep.c"
$CC $CFLAGS -I "$B/scripts/mod" -o "$H/scripts/mod/modpost" \
	"$S/scripts/mod/modpost.c" "$S/scripts/mod/file2alias.c" \
	"$S/scripts/mod/sumversion.c" "$S/scripts/mod/symsearch.c"

# no x86 binaries may be left in the package
if find "$H" -type f -exec file -N -F '|' {} + | grep '| ELF' | grep -v aarch64 | grep .; then
	echo "non-aarch64 binaries in the headers tree" >&2
	exit 1
fi

tar -C "$O" --owner=0 --group=0 -czf out/nairo-headers.tar.gz usr
echo "out/nairo-headers.tar.gz: headers for $V ($(du -sh "$H" | cut -f1))"

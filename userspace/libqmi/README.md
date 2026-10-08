# qmicli --pdc-load-config crash

qmicli 1.38.0 (and main as of 2026-10) segfaults in `--pdc-load-config`
before sending anything: `load_config_file_from_string()` calls
`g_free()` on the contents of a `GMappedFile`, which is memory-mapped and
owned by the `GMappedFile`. The patch drops that line.

To use it without replacing the system libqmi, build it in place and run
qmicli from the build directory:

    meson setup b -Dintrospection=false -Dman=false -Dbash_completion=false \
        -Dgtk_doc=false -Dmbim_qmux=false -Dqrtr=true
    ninja -C b src/qmicli/qmicli
    b/src/qmicli/qmicli -d qrtr://0 --pdc-load-config=...

On nairo the modem then refuses the upload (`InvalidQosId`), apparently
because it already stores 25 configurations.

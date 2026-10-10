Target: https://gitlab.freedesktop.org/mobile-broadband/libqmi/-/issues (or MR with the patch)
Title: qmicli: --pdc-load-config crashes, frees GMappedFile contents

`qmicli --pdc-load-config=<file.mbn>` segfaults before sending anything to
the modem (crash in `free()`).

`load_config_file_from_string()` in `src/qmicli/qmicli-pdc.c` gets the file
data with `g_mapped_file_get_contents()` and then calls
`g_free (file_contents)`. That memory is owned by the `GMappedFile` (and is
usually an mmap), so it must not be freed. The `GMappedFile` is also kept in
`data->mapped_file` and used later to send the chunks.

Present in 1.38.0 and in main (1c972b8, line 1130).

Fix: drop the `g_free()`:

    --- a/src/qmicli/qmicli-pdc.c
    +++ b/src/qmicli/qmicli-pdc.c
    @@ -1127,7 +1127,6 @@
         hash_size = g_checksum_type_get_length (G_CHECKSUM_SHA1);
         checksum = g_checksum_new (G_CHECKSUM_SHA1);
         g_checksum_update (checksum, file_contents, file_size);
    -    g_free (file_contents);

         data = g_slice_new (LoadConfigFileData);
         data->mapped_file = g_mapped_file_ref (mapped_file);

With the fix, qmicli sends the file and the modem answers. (On my SM7250 the
modem then refuses it with `InvalidQosId`, which is a separate matter.)

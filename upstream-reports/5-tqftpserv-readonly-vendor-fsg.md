Target: https://github.com/linux-msm/tqftpserv (pull request; patch at
nairoArchLinuxTools/userspace/tqftpserv/0001-translate-serve-readonly-vendor-fsg-from-the-modem-f.patch)
Title: translate: serve /readonly/vendor/fsg/ from the modem firmware dir

The SM7250 modem (Motorola moto g 5G plus, "nairo") reads its modem
configurations (MCFG) over TFTP from `/readonly/vendor/fsg/`, which is the
FSG partition mounted at `/vendor/fsg` on Android. It asks for
`/readonly/vendor/fsg/mcfg_sw/mbn_sw.dig` and then the mbn files listed
there. tqftpserv rejects the path ("invalid path ..., rejecting"). Without
the files, the modem has no carrier configuration, and the SIM and network
setup stays incomplete.

The patch maps `/readonly/vendor/fsg/<file>` to `fsg/<file>`, looked up next
to the remoteproc firmware like the other readonly paths. On this phone that
is `/lib/firmware/qcom/sm7250/motorola/nairo/fsg/`. The FSG contents are
copied from the stock partition, not shipped.

Tested on 1.2. The patch applies cleanly to main (128cd6e).

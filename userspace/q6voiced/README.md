# q6voiced

Keeps the ADSP voice path (the VoiceMMode1 PCM, `hw:0,3`) open while
ModemManager reports a call as dialing, ringing out or active; opening that
PCM is what starts the q6voice MVM/CVP sessions in the kernel.

From postmarketOS (MIT), ported from tinyalsa to alsa-lib so it builds on
Arch Linux ARM without extra packages:

    gcc -O2 -Wall -o q6voiced q6voiced.c $(pkg-config --cflags --libs dbus-1 alsa)
    install -m 755 q6voiced /usr/local/bin/
    install -m 644 q6voiced.service /etc/systemd/system/

Needs the q6voice modules (q6voice-common, q6mvm, q6cvs, q6cvp, q6voice,
q6voice-dai) loaded and the "Voice Call" UCM verb.

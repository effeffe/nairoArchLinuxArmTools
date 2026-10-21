# callaudiod with speakerphone on split UCM devices

callaudiod toggles speakerphone by switching the port of the card's sink.
PipeWire (and PulseAudio >= 15) give every UCM device its own sink, and put
devices sharing a PCM (Earpiece and Speaker on MultiMedia1 here) in separate
profiles, so the speaker port is never on the earpiece sink. The patch makes
callaudiod switch to the best available profile of the same verb with (or
without) "Speaker" when the wanted port isn't on the current sink.

Built from upstream 0.1.99 + "Check if sink has an active port before
accessing it" (fe87a92), which matches the Arch package plus one fix.

    git clone https://gitlab.com/mobian1/callaudiod.git && cd callaudiod
    git checkout fe87a92
    patch -p1 < 0001-pulse-switch-profile-for-speaker-on-split-UCM.patch
    meson setup build && ninja -C build
    install -m 755 build/src/callaudiod /usr/local/bin/callaudiod

The per-user D-Bus service override (takes precedence over
/usr/share/dbus-1/services) makes the session start it instead of
/usr/bin/callaudiod:

    install -Dm644 org.mobian_project.CallAudio.service \
        ~/.local/share/dbus-1/services/org.mobian_project.CallAudio.service

Remove the override to go back to the packaged daemon.

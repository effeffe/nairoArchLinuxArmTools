# UCM2 profile

ALSA use-case configuration for the "Motorola Moto G 5G Plus" card
(sm8250 machine driver): the WCD9380 codec behind the LPASS RX/TX macros,
the AW882xx loudspeaker amplifier on secondary MI2S and the q6voice call
path.

    cp -r Motorola /usr/share/alsa/ucm2/
    cp "conf.d/sm8250/Motorola Moto G 5G Plus.conf" /usr/share/alsa/ucm2/conf.d/sm8250/

Verbs:

- HiFi: Speaker, Earpiece and Headphones, all on MultiMedia1 (hw:0,0),
  which each device routes to its backend; the internal microphones as a
  stereo source on MultiMedia2 (hw:0,1): left AMIC1 (bottom), right AMIC3
  (top); the headset microphone.
- Voice Call: the same outputs plus the voice downlink
  ("... Voice Mixer VoiceMMode1"), the bottom microphone as the mono
  uplink, without uplink processing (no calibration data). q6voiced opens
  the VoiceMMode1 PCM (hw:0,3) during calls; callaudiod switches the verb.

Outputs sharing a PCM end up in separate PipeWire profiles (one sink
each): callaudiod makes the card's first sink the default output, so this
keeps the loudspeaker default, and needs the patch in ../callaudiod for
speakerphone.

The mixer elements are chosen with the codec in mind: ADC1/ADC2 Switch
connect the microphones to SoundWire (they are not mutes, PipeWire must not
own them), and EAR_PA Volume counts down (0 is +6 dB, 16 is -18 dB). The
call mute is "VoiceMMode1 Capture/Playback Switch" (q6voice).

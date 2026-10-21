// SPDX-License-Identifier: MIT
/*
 * q6voiced from postmarketOS (https://gitlab.com/postmarketOS/q6voiced),
 * ported from tinyalsa to alsa-lib for Arch Linux ARM on the Moto G 5G Plus.
 */
#include <stdbool.h>
#include <stdio.h>
#include <unistd.h>
#include <dbus/dbus.h>
#include <alsa/asoundlib.h>

struct q6voiced {
	char name[32];
	snd_pcm_t *tx, *rx;
};

/* Note: These parameters have little relevance (no audio data written) */
static snd_pcm_t *voice_pcm_open(const char *name, snd_pcm_stream_t stream)
{
	snd_pcm_t *pcm;
	int ret;

	ret = snd_pcm_open(&pcm, name, stream, 0);
	if (ret < 0) {
		fprintf(stderr, "Failed to open %s %s: %s\n", name,
			snd_pcm_stream_name(stream), snd_strerror(ret));
		return NULL;
	}

	ret = snd_pcm_set_params(pcm, SND_PCM_FORMAT_S16_LE,
				 SND_PCM_ACCESS_RW_INTERLEAVED, 1, 8000, 0, 40000);
	if (ret >= 0)
		ret = snd_pcm_prepare(pcm);
	if (ret < 0)
		fprintf(stderr, "Failed to prepare %s %s: %s\n", name,
			snd_pcm_stream_name(stream), snd_strerror(ret));

	return pcm;
}

static void q6voiced_open(struct q6voiced *v)
{
	if (v->tx)
		return; /* Already active */

	/*
	 * Opening the PCM devices starts the stream.
	 * This should be replaced by a codec2codec link probably.
	 */
	/*
	 * The PCM only opens once the "Voice Call" UCM verb has routed it to
	 * the codec backends, and callaudiod switches the profile on the same
	 * call state change: retry for a while.
	 */
	for (int i = 0; i < 50; i++) {
		v->tx = voice_pcm_open(v->name, SND_PCM_STREAM_CAPTURE);
		v->rx = v->tx ? voice_pcm_open(v->name, SND_PCM_STREAM_PLAYBACK) : NULL;
		if (v->tx && v->rx)
			break;

		if (v->tx)
			snd_pcm_close(v->tx);
		v->tx = v->rx = NULL;
		usleep(100000);
	}
	if (!v->tx) {
		fprintf(stderr, "Giving up on %s\n", v->name);
		return;
	}

	printf("PCM devices were opened.\n");
}

static void q6voiced_close(struct q6voiced *v)
{
	if (!v->tx)
		return; /* Not active */

	snd_pcm_close(v->rx);
	snd_pcm_close(v->tx);
	v->rx = v->tx = NULL;

	printf("PCM devices were closed.\n");
}

/* See ModemManager-enums.h */
enum MMCallState {
	MM_CALL_STATE_DIALING		= 1,
	MM_CALL_STATE_RINGING_OUT	= 2,
	MM_CALL_STATE_ACTIVE		= 4,
};

static bool mm_state_is_active(int state)
{
	/*
	 * Some modems seem to be incapable of reporting DIALING -> ACTIVE.
	 * Therefore we also consider DIALING/RINGING_OUT as active.
	 */
	switch (state) {
	case MM_CALL_STATE_DIALING:
	case MM_CALL_STATE_RINGING_OUT:
	case MM_CALL_STATE_ACTIVE:
		return true;
	default:
		return false;
	}
}

static void handle_signal(struct q6voiced *v, DBusMessage *msg, DBusError *err)
{
	// Check if the message is a signal from the correct interface and with the correct name
	// TODO: Should we also check the call state for oFono?
	if (dbus_message_is_signal(msg, "org.ofono.VoiceCallManager", "CallAdded")) {
		q6voiced_open(v);
	} else if (dbus_message_is_signal(msg, "org.ofono.VoiceCallManager", "CallRemoved")) {
		q6voiced_close(v);
	} else if (dbus_message_is_signal(msg, "org.freedesktop.ModemManager1.Call", "StateChanged")) {
		/*
		 * For ModemManager call objects are created in advance
		 * and not necessarily immediately started.
		 * Need to listen for call state changes.
		 */
		int old_state, new_state;

		if (!dbus_message_get_args(msg, err,
					   DBUS_TYPE_INT32, &old_state,
					   DBUS_TYPE_INT32, &new_state,
					   DBUS_TYPE_INVALID))
			return;

		if (old_state == new_state)
			return; /* No change */

		if (mm_state_is_active(new_state))
			q6voiced_open(v);
		else if (mm_state_is_active(old_state) && !mm_state_is_active(new_state))
			q6voiced_close(v);
	}
}

int main(int argc, char **argv)
{
	struct q6voiced v = {0};

	DBusMessage *msg;
	DBusConnection *conn;
	DBusError err;

	unsigned int card, device;

	if (argc != 2 || sscanf(argv[1], "hw:%u,%u", &card, &device) != 2) {
		fprintf(stderr, "Usage: q6voiced hw:<card>,<device>\n");
		return 1;
	}
	snprintf(v.name, sizeof(v.name), "hw:%u,%u", card, device);

	// See: http://web.archive.org/web/20100309103206/http://dbus.freedesktop.org/doc/dbus/libdbus-tutorial.html
	// "Receiving a Signal"

	dbus_error_init(&err);

	conn = dbus_bus_get(DBUS_BUS_SYSTEM, &err);
	if (dbus_error_is_set(&err)) {
		fprintf(stderr, "Connection error: %s\n", err.message);
		dbus_error_free(&err);
		return 1;
	}
	if (!conn)
		return 1;

	dbus_bus_add_match(conn, "type='signal',interface='org.ofono.VoiceCallManager'", &err);
	dbus_bus_add_match(conn, "type='signal',interface='org.freedesktop.ModemManager1.Call'", &err);
	dbus_connection_flush(conn);
	if (dbus_error_is_set(&err)) {
		fprintf(stderr, "Match error: %s\n", err.message);
		dbus_error_free(&err);
		return 1;
	}

	// Loop listening for signals being emmitted
	while (dbus_connection_read_write(conn, -1)) {
		// We need to process all received messages
		while (msg = dbus_connection_pop_message(conn)) {
			handle_signal(&v, msg, &err);
			if (dbus_error_is_set(&err)) {
				fprintf(stderr, "Failed to handle signal: %s\n", err.message);
				dbus_error_free(&err);
			}

			dbus_message_unref(msg);
		}
	}

	return 0;
}

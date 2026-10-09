/*
 * Off-mode charging screen for nairo, run by init when the bootloader starts
 * the kernel with androidboot.mode=charger (phone off, charger plugged in).
 *
 * Everything runs from the initramfs: no root filesystem is mounted and
 * nothing is written to storage, so holding the power key for a hardware
 * reset is always safe.
 *
 * - draws a battery with its charge level and percentage on the bootloader
 *   framebuffer (simpledrm's /dev/fb0) and turns the backlight off after
 *   SCREEN_ON_S seconds
 * - a press of the power key turns the screen back on
 * - holding the power key for REBOOT_HOLD_S seconds reboots; a warm reboot
 *   does not enter charger mode again, so the phone starts the system
 * - unplugging the charger for UNPLUG_OFF_S seconds powers the phone off
 */
#include <dirent.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <linux/kd.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define SCREEN_ON_S	20
#define REBOOT_HOLD_S	5
#define UNPLUG_OFF_S	10

#define CHARGER		"/sys/class/power_supply/pm8150b-charger/"
#define BATTERY		"/sys/class/power_supply/qcom-qg/"
#define BACKLIGHT	"/sys/class/backlight/backlight/"

void say(const char *msg);	/* init.c: kernel log */

static uint32_t *fb, *back;
static unsigned int fb_w, fb_h, fb_stride;	/* stride in pixels */
static size_t fb_size;

static double now(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

static int read_int(const char *path, int def)
{
	char buf[32];
	int fd = open(path, O_RDONLY), n;

	if (fd < 0)
		return def;
	n = read(fd, buf, sizeof(buf) - 1);
	close(fd);
	if (n <= 0)
		return def;
	buf[n] = 0;
	return atoi(buf);
}

static int read_str(const char *path, char *buf, size_t len)
{
	int fd = open(path, O_RDONLY), n;

	if (fd < 0)
		return -1;
	n = read(fd, buf, len - 1);
	close(fd);
	if (n < 0)
		return -1;
	buf[n] = 0;
	buf[strcspn(buf, "\n")] = 0;
	return 0;
}

static void write_int(const char *path, int val)
{
	char buf[16];
	int fd = open(path, O_WRONLY), n;

	if (fd < 0)
		return;
	n = snprintf(buf, sizeof(buf), "%d", val);
	write(fd, buf, n);
	close(fd);
}

/* charger and fuel gauge are modules; there is no udev in here */
static void load_module(const char *path)
{
	char msg[128];
	int fd = open(path, O_RDONLY);

	if (fd < 0)
		return;
	if (syscall(SYS_finit_module, fd, "", 0)) {
		snprintf(msg, sizeof(msg), "charger: loading %s failed: %m", path);
		say(msg);
	}
	close(fd);
}

static int open_fb(void)
{
	struct fb_var_screeninfo var;
	struct fb_fix_screeninfo fix;
	int fd, i;

	for (i = 0; i < 100 && access("/dev/fb0", F_OK); i++)
		usleep(100000);
	fd = open("/dev/fb0", O_RDWR);
	if (fd < 0)
		return -1;
	if (ioctl(fd, FBIOGET_VSCREENINFO, &var) || ioctl(fd, FBIOGET_FSCREENINFO, &fix) ||
	    var.bits_per_pixel != 32) {
		close(fd);
		return -1;
	}
	fb_w = var.xres;
	fb_h = var.yres;
	fb_stride = fix.line_length / 4;
	fb_size = (size_t)fix.line_length * fb_h;
	fb = mmap(NULL, fb_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	close(fd);
	if (fb == MAP_FAILED) {
		fb = NULL;
		return -1;
	}
	back = calloc(1, fb_size);
	return back ? 0 : -1;
}

static void rect(int x, int y, int w, int h, uint32_t c)
{
	int i, j;

	if (x < 0) { w += x; x = 0; }
	if (y < 0) { h += y; y = 0; }
	if (x + w > (int)fb_w)
		w = fb_w - x;
	if (y + h > (int)fb_h)
		h = fb_h - y;
	for (j = 0; j < h; j++)
		for (i = 0; i < w; i++)
			back[(size_t)(y + j) * fb_stride + x + i] = c;
}

/* 5x7 glyphs, one byte per row, bit 4 = leftmost column */
static const uint8_t glyphs[][7] = {
	{ 0x0e, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0e },	/* 0 */
	{ 0x04, 0x0c, 0x04, 0x04, 0x04, 0x04, 0x0e },	/* 1 */
	{ 0x0e, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1f },	/* 2 */
	{ 0x1f, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0e },	/* 3 */
	{ 0x02, 0x06, 0x0a, 0x12, 0x1f, 0x02, 0x02 },	/* 4 */
	{ 0x1f, 0x10, 0x1e, 0x01, 0x01, 0x11, 0x0e },	/* 5 */
	{ 0x06, 0x08, 0x10, 0x1e, 0x11, 0x11, 0x0e },	/* 6 */
	{ 0x1f, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08 },	/* 7 */
	{ 0x0e, 0x11, 0x11, 0x0e, 0x11, 0x11, 0x0e },	/* 8 */
	{ 0x0e, 0x11, 0x11, 0x0f, 0x01, 0x02, 0x0c },	/* 9 */
	{ 0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03 },	/* % */
};

static void text(const char *s, int cx, int y, int scale, uint32_t c)
{
	int n = strlen(s), x = cx - (n * 6 - 1) * scale / 2, row, col;

	for (; *s; s++, x += 6 * scale) {
		const uint8_t *g = glyphs[*s == '%' ? 10 : *s - '0'];

		for (row = 0; row < 7; row++)
			for (col = 0; col < 5; col++)
				if (g[row] & (0x10 >> col))
					rect(x + col * scale, y + row * scale, scale, scale, c);
	}
}

/* lightning bolt, as a polygon on a 100 x 160 grid, filled point by point */
static void bolt(int cx, int cy, int h, uint32_t c)
{
	static const int px[] = { 58, 12, 46, 36, 88, 54, 70 };
	static const int py[] = { 0, 92, 92, 160, 62, 62, 0 };
	const int n = 7, w = h * 100 / 160;
	int x, y, i, j, in;

	for (y = 0; y < h; y++) {
		for (x = 0; x < w; x++) {
			/* even-odd test in grid units, scaled by 160 * h * 100 * w */
			long gx = (long)x * 100 * 160, gy = (long)y * 160 * 100;
			long sx = (long)w * 160, sy = (long)h * 100;

			in = 0;
			for (i = 0, j = n - 1; i < n; j = i++) {
				long yi = py[i] * sy, yj = py[j] * sy;
				long xi = px[i] * sx, xj = px[j] * sx;

				if ((yi > gy) != (yj > gy) &&
				    gx < xi + (double)(xj - xi) * (gy - yi) / (yj - yi))
					in = !in;
			}
			if (in)
				back[(size_t)(cy - h / 2 + y) * fb_stride + cx - w / 2 + x] = c;
		}
	}
}

static void draw(int capacity, int charging)
{
	const uint32_t white = 0xffd0d0d0, black = 0xff000000;
	int bw = 360, bh = 640, t = 18, cw = 140, ch = 50;
	int bx = (fb_w - bw) / 2, by = fb_h / 2 - bh / 2 - 200;
	int ih = bh - 4 * t, fill;
	uint32_t color = capacity < 15 ? 0xffe03030 : capacity < 30 ? 0xffe0a020 : 0xff30c050;
	char pct[8];

	memset(back, 0, fb_size);
	rect(bx + (bw - cw) / 2, by - ch, cw, ch, white);		/* cap */
	rect(bx, by, bw, bh, white);					/* outline */
	rect(bx + t, by + t, bw - 2 * t, bh - 2 * t, black);
	if (capacity >= 0) {
		fill = ih * (capacity > 100 ? 100 : capacity) / 100;
		if (fill < t && capacity > 0)
			fill = t;
		rect(bx + 2 * t, by + 2 * t + ih - fill, bw - 4 * t, fill, color);
		snprintf(pct, sizeof(pct), "%d%%", capacity > 100 ? 100 : capacity);
		text(pct, fb_w / 2, by + bh + 120, 20, white);
	}
	if (charging)
		bolt(fb_w / 2, by + bh / 2, 320, capacity > 50 ? black : white);
	memcpy(fb, back, fb_size);
}

static int open_pwrkey(void)
{
	char path[300], name[64];
	struct dirent *e;
	DIR *d;
	int fd = -1, i;

	/* pm8941-pwrkey is built in, but give the PMIC a moment */
	for (i = 0; i < 50 && fd < 0; i++) {
		d = opendir("/sys/class/input");
		while (d && (e = readdir(d))) {
			if (strncmp(e->d_name, "event", 5))
				continue;
			snprintf(path, sizeof(path), "/sys/class/input/%s/device/name", e->d_name);
			if (read_str(path, name, sizeof(name)) || strcmp(name, "pm8941_pwrkey"))
				continue;
			snprintf(path, sizeof(path), "/dev/input/%s", e->d_name);
			fd = open(path, O_RDONLY | O_NONBLOCK);
			break;
		}
		if (d)
			closedir(d);
		if (fd < 0)
			usleep(100000);
	}
	return fd;
}

static int charger_online(void)
{
	return read_int(CHARGER "online", 1);
}

void charger_main(void)
{
	char msg[128], status[32] = "";
	int key, tty, on_level, capacity, charging, screen_on = 1, pressed = 0;
	double t, screen_off_at, pressed_at = 0, unplugged_at = 0, redraw_at = 0;
	struct input_event ev;

	say("charger mode");
	load_module("/lib/modules/qcom_smbx.ko");
	load_module("/lib/modules/qcom_qg.ko");

	/* keep fbcon from drawing over the screen */
	tty = open("/dev/tty0", O_RDWR);
	if (tty >= 0)
		ioctl(tty, KDSETMODE, KD_GRAPHICS);
	if (open_fb())
		say("charger: no framebuffer, running without a screen");

	on_level = read_int(BACKLIGHT "brightness", 0);
	if (on_level <= 0)
		on_level = read_int(BACKLIGHT "max_brightness", 4095) * 3 / 10;
	write_int(BACKLIGHT "brightness", on_level);

	key = open_pwrkey();
	if (key < 0)
		say("charger: no power key input device");

	screen_off_at = now() + SCREEN_ON_S;
	for (;;) {
		struct pollfd pfd = { .fd = key, .events = POLLIN };

		poll(&pfd, key >= 0 ? 1 : 0, 250);
		while (waitpid(-1, NULL, WNOHANG) > 0)	/* we are PID 1 */
			;
		t = now();

		while (key >= 0 && read(key, &ev, sizeof(ev)) == sizeof(ev)) {
			if (ev.type != EV_KEY || ev.code != KEY_POWER)
				continue;
			if (ev.value == 1) {
				pressed = 1;
				pressed_at = t;
				if (!screen_on) {
					screen_on = 1;
					redraw_at = 0;
					write_int(BACKLIGHT "brightness", on_level);
				}
				screen_off_at = t + SCREEN_ON_S;
			} else if (ev.value == 0) {
				pressed = 0;
			}
		}

		if (pressed && t - pressed_at >= REBOOT_HOLD_S) {
			say("charger: power key held, rebooting into the system");
			if (fb) {
				memset(back, 0, fb_size);
				memcpy(fb, back, fb_size);
			}
			sync();
			reboot(RB_AUTOBOOT);
		}

		if (charger_online()) {
			unplugged_at = 0;
		} else if (!unplugged_at) {
			unplugged_at = t;
			say("charger: charger removed");
		} else if (t - unplugged_at >= UNPLUG_OFF_S) {
			say("charger: charger removed, powering off");
			write_int(BACKLIGHT "brightness", 0);
			sync();
			reboot(RB_POWER_OFF);
		}

		if (screen_on && t >= screen_off_at) {
			screen_on = 0;
			write_int(BACKLIGHT "brightness", 0);
		}
		if (screen_on && fb && t >= redraw_at) {
			capacity = read_int(BATTERY "capacity", -1);
			if (read_str(BATTERY "status", status, sizeof(status)))
				status[0] = 0;
			charging = !strcmp(status, "Charging") || !strcmp(status, "Full");
			draw(capacity, charging && !unplugged_at);
			snprintf(msg, sizeof(msg), "charger: battery %d%%, %s", capacity, status);
			if (!redraw_at)
				say(msg);
			redraw_at = t + 5;
		}
	}
}

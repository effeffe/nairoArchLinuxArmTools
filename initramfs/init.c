/*
 * Minimal first-boot init for nairo bring-up.
 *
 * Logs a heartbeat to the kernel log (visible on the framebuffer console and
 * captured by ramoops), then reboots so LineageOS can read the log from
 * /sys/fs/pstore/console-ramoops-0.
 *
 * Starts /etc/rc (busybox sh: USB gadget networking + dropbear). The reboot
 * timer is cancelled once /run/nairo-stay exists, which rc creates when the
 * USB host has configured the gadget.
 *
 * Kernel cmdline knobs:
 *   nairo.root=DEV   set up the USB gadget, mount DEV (ext4), prepare it for
 *                    headless access (/etc/arch-prep) and switch_root to its
 *                    /sbin/init; falls back to the initramfs shell on failure.
 *                    DEV is a device path or PARTLABEL=<GPT partition name>
 *   nairo.reboot=N   seconds before rebooting (default 60, 0 = never)
 *   nairo.off=10     power off as soon as init runs (boot-stage probe)
 */
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <dirent.h>
#include <unistd.h>

static int kmsg = -1;

static void say(const char *msg)
{
	char buf[256];
	int n = snprintf(buf, sizeof(buf), "<1>nairo-init: %s\n", msg);

	if (kmsg >= 0)
		write(kmsg, buf, n);
}

/* busybox reboot/halt/poweroff signal PID 1: SIGTERM, SIGUSR1, SIGUSR2 */
static void on_signal(int sig)
{
	sync();
	reboot(sig == SIGTERM ? RB_AUTOBOOT : sig == SIGUSR1 ? RB_HALT_SYSTEM : RB_POWER_OFF);
}

static char cmdline[4096];

static int cmdline_int(const char *key, int def)
{
	char *p = strstr(cmdline, key);

	return p ? atoi(p + strlen(key)) : def;
}

/* run argv[0] with argv and wait for it; returns its exit status or -1 */
static int run(const char *const argv[])
{
	pid_t pid = fork();
	int st;

	if (pid == 0) {
		execv(argv[0], (char *const *)argv);
		_exit(127);
	}
	if (pid < 0 || waitpid(pid, &st, 0) < 0)
		return -1;
	return WIFEXITED(st) ? WEXITSTATUS(st) : -1;
}

/*
 * Resolve PARTLABEL=<name> to /dev/<disk> by scanning the partition uevents
 * (no udev in here, so no /dev/disk/by-partlabel). Returns 0 when found.
 */
static int find_partlabel(const char *label, char *dev, size_t len)
{
	char path[300], line[128], devname[32];
	struct dirent *e;
	int found = -1;
	DIR *d = opendir("/sys/class/block");
	FILE *f;

	if (!d)
		return -1;
	while (found && (e = readdir(d))) {
		if (e->d_name[0] == '.')
			continue;
		snprintf(path, sizeof(path), "/sys/class/block/%s/uevent", e->d_name);
		f = fopen(path, "r");
		if (!f)
			continue;
		devname[0] = 0;
		int match = 0;
		while (fgets(line, sizeof(line), f)) {
			line[strcspn(line, "\n")] = 0;
			if (!strncmp(line, "DEVNAME=", 8))
				snprintf(devname, sizeof(devname), "%.31s", line + 8);
			else if (!strncmp(line, "PARTNAME=", 9) && !strcmp(line + 9, label))
				match = 1;
		}
		fclose(f);
		if (match && devname[0]) {
			snprintf(dev, len, "/dev/%s", devname);
			found = 0;
		}
	}
	closedir(d);
	return found;
}

/* nairo.root=DEV: hand over to the real root. Returns only on failure. */
static void try_switch_root(void)
{
	static const char *const moved[] = { "/dev", "/proc", "/sys", "/run" };
	const char *rc[] = { "/bin/sh", "/etc/rc", "gadget", NULL };
	const char *prep[] = { "/bin/sh", "/etc/arch-prep", "/newroot", NULL };
	char *p = strstr(cmdline, "nairo.root="), dev[80], label[80], msg[192];
	size_t n;
	int i;

	if (!p)
		return;
	p += strlen("nairo.root=");
	n = strcspn(p, " \n");
	if (n == 0 || n >= sizeof(dev))
		return;
	memcpy(dev, p, n);
	dev[n] = 0;

	run(rc);

	/* the SD card and the UFS LUNs may still be probing when init starts */
	if (!strncmp(dev, "PARTLABEL=", 10)) {
		snprintf(label, sizeof(label), "%.69s", dev + 10);
		for (i = 0; i < 100 && find_partlabel(label, dev, sizeof(dev)); i++)
			usleep(100000);
		snprintf(msg, sizeof(msg), "root PARTLABEL=%s is %s", label, dev);
		say(msg);
	}
	for (i = 0; i < 100 && access(dev, F_OK); i++)
		usleep(100000);
	mkdir("/newroot", 0755);
	if (mount(dev, "/newroot", "ext4", 0, NULL)) {
		snprintf(msg, sizeof(msg), "mounting %s failed: %m, staying in initramfs", dev);
		say(msg);
		return;
	}
	if (access("/newroot/sbin/init", X_OK)) {
		say("no /sbin/init on the new root, staying in initramfs");
		umount("/newroot");
		return;
	}
	run(prep);
	sync();

	umount("/tmp");
	for (i = 0; i < 4; i++) {
		char to[32];

		snprintf(to, sizeof(to), "/newroot%s", moved[i]);
		if (mount(moved[i], to, NULL, MS_MOVE, NULL)) {
			snprintf(msg, sizeof(msg), "moving %s failed: %m", moved[i]);
			say(msg);
		}
	}
	snprintf(msg, sizeof(msg), "switching root to %s", dev);
	say(msg);
	execl("/bin/busybox", "switch_root", "/newroot", "/sbin/init", (char *)NULL);
	say("switch_root failed");
}

int main(void)
{
	char msg[128];
	int delay, i;

	mkdir("/dev", 0755);
	mkdir("/proc", 0755);
	mkdir("/sys", 0755);
	mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
	mount("proc", "/proc", "proc", 0, NULL);
	mount("sysfs", "/sys", "sysfs", 0, NULL);

	signal(SIGTERM, on_signal);
	signal(SIGUSR1, on_signal);
	signal(SIGUSR2, on_signal);

	kmsg = open("/dev/kmsg", O_WRONLY);
	say("userspace reached");

	i = open("/proc/cmdline", O_RDONLY);
	if (i >= 0) {
		read(i, cmdline, sizeof(cmdline) - 1);
		close(i);
	}

	/* bring-up probe: power off once userspace runs (stage 10) */
	if (cmdline_int("nairo.off=", 0) == 10) {
		sync();
		reboot(RB_POWER_OFF);
	}

	try_switch_root();

	if (access("/etc/rc", X_OK) == 0 && fork() == 0) {
		execl("/bin/sh", "sh", "/etc/rc", (char *)NULL);
		_exit(127);
	}

	delay = cmdline_int("nairo.reboot=", 60);
	for (i = 0; delay == 0 || i < delay; i++) {
		while (waitpid(-1, NULL, WNOHANG) > 0)
			;
		if (access("/run/nairo-stay", F_OK) == 0) {
			say("USB configured, reboot timer cancelled");
			for (;;)	/* reap orphans forever */
				if (wait(NULL) < 0)
					sleep(1);
		}
		if (i % 10 == 0) {
			snprintf(msg, sizeof(msg), "alive %ds", i);
			say(msg);
		}
		sleep(1);
	}

	say("rebooting");
	sync();
	reboot(RB_AUTOBOOT);
	for (;;)
		pause();
}

#define _GNU_SOURCE
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

/* RESEARCH ONLY. The child remains owned/unreaped (waitid WNOWAIT), so its
 * numeric PID cannot be recycled while this supervisor may signal it.
 * Client commands never call kill(pid); the owning parent does.
 */
static volatile sig_atomic_t terminate_requested;
static void on_terminate(int sig) { (void)sig; terminate_requested = 1; }

static int child_exited(pid_t child) {
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    if (waitid(P_PID, (id_t)child, &info, WEXITED | WNOHANG | WNOWAIT) < 0) return -1;
    return info.si_pid == child;
}

static int valid_parent(const char *path) {
    if (path[0] != '/') return 0;
    const char *slash = strrchr(path, '/');
    if (!slash || !slash[1] || slash == path) return 0;
    size_t n = (size_t)(slash - path);
    if (n >= 1024) return 0;
    char parent[1024];
    memcpy(parent, path, n); parent[n] = 0;
    struct stat st;
    if (lstat(parent, &st) < 0 || !S_ISDIR(st.st_mode)) return 0;
    if (st.st_uid != geteuid() || (st.st_mode & 0077) != 0) return 0;
    return 1;
}

static int make_address(const char *path, struct sockaddr_un *addr) {
    memset(addr, 0, sizeof(*addr));
    addr->sun_family = AF_UNIX;
    if (strlen(path) >= sizeof(addr->sun_path)) return -1;
    strcpy(addr->sun_path, path);
    return 0;
}

static int send_command(const char *path, char command) {
    struct sockaddr_un addr;
    if (make_address(path, &addr) < 0) return 2;
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return 1;
    struct timeval tv = {.tv_sec = 3, .tv_usec = 0};
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    int ok = connect(fd, (struct sockaddr *)&addr, sizeof(addr)) == 0;
    if (ok) ok = write(fd, &command, 1) == 1;
    char reply = 'E';
    if (ok) ok = read(fd, &reply, 1) == 1 && reply == 'O';
    close(fd);
    return ok ? 0 : 1;
}

static int serve(const char *path, char **program) {
    if (!valid_parent(path)) {
        fprintf(stderr, "private, owned, non-symlink parent directory required\n");
        return 2;
    }
    struct stat old;
    if (lstat(path, &old) == 0 || errno != ENOENT) {
        fprintf(stderr, "control socket path already exists or is inaccessible\n");
        return 2; /* Never unlink a possibly active or substituted endpoint. */
    }
    struct sockaddr_un addr;
    if (make_address(path, &addr) < 0) return 2;
    int listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (listener < 0) return 1;
    mode_t previous_umask = umask(0077);
    int bound = bind(listener, (struct sockaddr *)&addr, sizeof(addr));
    umask(previous_umask);
    if (bound != 0) { close(listener); return 1; }
    struct stat owned;
    if (lstat(path, &owned) != 0 || !S_ISSOCK(owned.st_mode) ||
        listen(listener, 4) != 0) {
        close(listener); return 1;
    }
    pid_t child = fork();
    if (child < 0) { close(listener); unlink(path); return 1; }
    if (child == 0) {
        close(listener);
        execvp(program[0], program);
        _exit(127);
    }
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa)); sa.sa_handler = on_terminate;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    int shutdown_sent = 0, status = 1;
    for (;;) {
        int done = child_exited(child);
        if (done != 0) { status = (done > 0) ? 0 : 1; break; }
        if (terminate_requested && !shutdown_sent) {
            (void)kill(child, SIGTERM); /* Child PID is reserved until waitpid. */
            shutdown_sent = 1;
        }
        struct pollfd pfd = {.fd = listener, .events = POLLIN};
        int ready = poll(&pfd, 1, 200);
        if (ready <= 0 || !(pfd.revents & POLLIN)) continue;
        int peer = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
        if (peer < 0) continue;
        struct timeval receive_timeout = {.tv_sec = 1, .tv_usec = 0};
        (void)setsockopt(peer, SOL_SOCKET, SO_RCVTIMEO,
                         &receive_timeout, sizeof(receive_timeout));
        struct ucred creds;
        socklen_t len = sizeof(creds);
        char command = 0, reply = 'E';
        if (getsockopt(peer, SOL_SOCKET, SO_PEERCRED, &creds, &len) == 0 &&
            len == sizeof(creds) && creds.uid == geteuid() &&
            read(peer, &command, 1) == 1) {
            int alive = child_exited(child);
            if (alive == 0) {
                if (command == 'P') reply = 'O';
                else if (command == 'H' && !shutdown_sent && kill(child, SIGHUP) == 0) reply = 'O';
                else if (command == 'T' && !shutdown_sent && kill(child, SIGTERM) == 0) {
                    reply = 'O'; shutdown_sent = 1;
                }
            }
        }
        (void)write(peer, &reply, 1);
        close(peer);
    }
    /* WNOWAIT above never reaps; no PID reuse was possible during signals. */
    (void)waitpid(child, NULL, 0);
    close(listener);
    struct stat current;
    if (lstat(path, &current) == 0 && S_ISSOCK(current.st_mode) &&
        owned.st_dev == current.st_dev && owned.st_ino == current.st_ino) {
        (void)unlink(path);
    }
    return status;
}

int main(int argc, char **argv) {
    if (argc >= 5 && strcmp(argv[1], "serve") == 0 && strcmp(argv[3], "--") == 0)
        return serve(argv[2], &argv[4]);
    if (argc == 3) {
        if (strcmp(argv[1], "stop") == 0) return send_command(argv[2], 'T');
        if (strcmp(argv[1], "reload") == 0) return send_command(argv[2], 'H');
        if (strcmp(argv[1], "status") == 0) return send_command(argv[2], 'P');
    }
    fprintf(stderr, "usage: legacy-supervisor serve /private/ctl.sock -- command [args...] | stop|reload|status /private/ctl.sock\n");
    return 2;
}

//! Linux-only opt-in, process-owned control channel for TeleMT.
//!
//! Research patch for upstream TeleMT 3.5.17. It never signals a PID read
//! from a pidfile, and does not change the default pidfd-based CLI path.
use std::fs;
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;

use crate::util::secure_fs::AnchoredPath;

const COMMAND_TIMEOUT: Duration = Duration::from_secs(3);

fn private_parent(path: &Path) -> io::Result<AnchoredPath> {
    // All control sockets must live in an existing private directory.
    // Require a stable, absolute, symlink-free path, including the ancestors.
    if !path.is_absolute()
        || path
            .components()
            .any(|c| !matches!(c, Component::Normal(_) | Component::RootDir))
        || path.as_os_str().as_bytes().len() >= 108
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid control socket path",
        ));
    }
    let anchor = AnchoredPath::open_trusted_parent(path)?;
    let parent_file = fs::File::from(anchor.parent().try_clone()?);
    let metadata = parent_file.metadata()?;
    if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o077 != 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "control socket parent must be owned by this user and private",
        ));
    }
    Ok(anchor)
}

fn peer_uid(fd: i32) -> io::Result<libc::uid_t> {
    let mut credentials = libc::ucred {
        pid: 0,
        uid: 0,
        gid: 0,
    };
    let mut length = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    // SAFETY: SO_PEERCRED writes exactly a kernel-owned ucred value.
    let result = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut credentials as *mut libc::ucred).cast(),
            &mut length,
        )
    };
    if result != 0 {
        return Err(io::Error::last_os_error());
    }
    if length as usize != std::mem::size_of::<libc::ucred>() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid peer credentials",
        ));
    }
    Ok(credentials.uid)
}

/// Sends one bounded, opt-in command. Never sends a signal by PID.
pub fn send_command(path: &Path, command: u8) -> io::Result<()> {
    let _anchor = private_parent(path)?;
    if !matches!(command, b'S' | b'R') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid control command",
        ));
    }
    // CLI is invoked outside the long-running server's Tokio runtime.
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    runtime.block_on(async {
        tokio::time::timeout(COMMAND_TIMEOUT, async {
            let mut stream = UnixStream::connect(path).await?;
            if peer_uid(stream.as_raw_fd())? != unsafe { libc::geteuid() } {
                return Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "control endpoint belongs to an unexpected user",
                ));
            }
            stream.write_all(&[command]).await?;
            let mut response = [0u8; 1];
            stream.read_exact(&mut response).await?;
            if response != [b'O'] {
                return Err(io::Error::other("control operation was rejected"));
            }
            Ok(())
        })
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "local control request timed out"))?
    })
}

pub struct LocalControl {
    path: PathBuf,
    anchor: AnchoredPath,
    socket_device: u64,
    socket_inode: u64,
    cancelled: CancellationToken,
    worker: JoinHandle<()>,
}

impl LocalControl {
    /// Expose control only after the process has installed its runtime signal
    /// watchers. Caller must retain this owner through graceful shutdown.
    pub fn bind(path: &Path, stop_requests: mpsc::Sender<()>) -> io::Result<Self> {
        let anchor = private_parent(path)?;
        match fs::symlink_metadata(path) {
            Ok(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::AlreadyExists,
                    "control socket path already exists; refusing to remove it",
                ));
            }
            Err(error) if error.kind() != io::ErrorKind::NotFound => return Err(error),
            _ => {}
        }
        let listener = UnixListener::bind(path)?;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
        let metadata = fs::symlink_metadata(path)?;
        if !metadata.file_type().is_socket() || metadata.uid() != unsafe { libc::geteuid() } {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "control socket identity changed during bind",
            ));
        }
        let cancelled = CancellationToken::new();
        let cancellation = cancelled.clone();
        let uid = unsafe { libc::geteuid() };
        let worker = tokio::spawn(async move {
            let mut stopping = false;
            loop {
                tokio::select! {
                    _ = cancellation.cancelled() => break,
                    accepted = listener.accept() => {
                        let Ok((mut peer, _)) = accepted else { continue };
                        let mut response = b'E';
                        let mut request = [0u8; 1];
                        let accepted = tokio::time::timeout(COMMAND_TIMEOUT, async {
                            if peer_uid(peer.as_raw_fd())? != uid {
                                return Err(io::Error::new(io::ErrorKind::PermissionDenied,
                                    "unauthorized control client"));
                            }
                            peer.read_exact(&mut request).await?;
                            Ok::<(), io::Error>(())
                        }).await;
                        if matches!(accepted, Ok(Ok(()))) {
                            match request[0] {
                                b'S' if !stopping => {
                                    if stop_requests.try_send(()).is_ok() {
                                        stopping = true;
                                        response = b'O';
                                    }
                                }
                                b'R' if !stopping => {
                                    // Signal only the *current* live process/thread. There is
                                    // no PID lookup and therefore no PID-reuse race. The
                                    // config watcher registers SIGHUP before IPC is exposed.
                                    if unsafe { libc::raise(libc::SIGHUP) } == 0 {
                                        response = b'O';
                                    }
                                }
                                _ => {}
                            }
                        }
                        // MSG_NOSIGNAL avoids a disconnected local peer terminating the daemon.
                        // One-byte response does not need a blocking writer.
                        let _sent = unsafe {
                            libc::send(
                                peer.as_raw_fd(),
                                (&response as *const u8).cast(),
                                1,
                                libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
                            )
                        };
                    }
                }
            }
        });
        Ok(Self {
            path: path.to_path_buf(),
            anchor,
            socket_device: metadata.dev(),
            socket_inode: metadata.ino(),
            cancelled,
            worker,
        })
    }

    /// Refuse to unlink a replacement file, even on daemon shutdown.
    pub async fn close(self) -> io::Result<()> {
        self.cancelled.cancel();
        let _ = self.worker.await;
        let current = match fs::symlink_metadata(&self.path) {
            Ok(current) => current,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
            Err(error) => return Err(error),
        };
        if current.file_type().is_socket()
            && current.dev() == self.socket_device
            && current.ino() == self.socket_inode
        {
            nix::unistd::unlinkat(
                self.anchor.parent(),
                self.anchor.name(),
                nix::unistd::UnlinkatFlags::NoRemoveDir,
            )
            .map_err(|error| io::Error::from_raw_os_error(error as i32))?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn private_socket() -> (tempfile::TempDir, PathBuf) {
        let root = tempfile::tempdir().unwrap();
        let private = root.path().join("owned");
        fs::create_dir(&private).unwrap();
        fs::set_permissions(&private, fs::Permissions::from_mode(0o700)).unwrap();
        (root, private.join("control.sock"))
    }

    #[tokio::test]
    async fn stop_command_reaches_process_owner_without_pidfile() {
        let (_root, path) = private_socket();
        let (tx, mut rx) = mpsc::channel(1);
        let endpoint = LocalControl::bind(&path, tx).unwrap();
        let client_path = path.clone();
        let result = tokio::task::spawn_blocking(move || send_command(&client_path, b'S'))
            .await
            .unwrap();
        assert!(result.is_ok(), "local stop was not accepted: {result:?}");
        assert_eq!(rx.recv().await, Some(()));
        endpoint.close().await.unwrap();
        assert!(!path.exists());
    }

    #[tokio::test]
    async fn rejects_existing_socket_and_nonprivate_parent() {
        let (_root, path) = private_socket();
        let (tx, _rx) = mpsc::channel(1);
        let endpoint = LocalControl::bind(&path, tx.clone()).unwrap();
        assert!(LocalControl::bind(&path, tx.clone()).is_err());
        endpoint.close().await.unwrap();
        fs::set_permissions(path.parent().unwrap(), fs::Permissions::from_mode(0o777)).unwrap();
        assert!(LocalControl::bind(&path, tx).is_err());
    }

    #[tokio::test]
    async fn does_not_unlink_replaced_path() {
        let (_root, path) = private_socket();
        let (tx, _rx) = mpsc::channel(1);
        let endpoint = LocalControl::bind(&path, tx).unwrap();
        fs::remove_file(&path).unwrap();
        fs::write(&path, b"do-not-remove").unwrap();
        endpoint.close().await.unwrap();
        assert_eq!(fs::read(&path).unwrap(), b"do-not-remove");
    }

    #[test]
    fn refuses_missing_or_untrusted_control_path() {
        let (_root, path) = private_socket();
        assert!(send_command(&path, b'S').is_err());
        assert!(send_command(&path, b'X').is_err());
    }

    #[test]
    fn missing_opt_in_path_is_rejected_instead_of_pidfd_fallback() {
        let args = vec!["stop".to_string(), "--control-socket".to_string()];
        let command = crate::cli::parse_command(&args);
        assert_eq!(command.daemon_opts.control_socket, Some(PathBuf::new()));
        let path = command.daemon_opts.control_socket.as_deref().unwrap();
        assert!(send_command(path, b'S').is_err());
    }
}

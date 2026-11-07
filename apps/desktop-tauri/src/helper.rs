use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::path::Path;
use std::process::{Child, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::{mpsc, Arc, Condvar, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::policy::HelperCommand;
use crate::system;

const LOG_BYTES: u64 = 5 * 1024 * 1024;
const READY_BYTES: usize = 4096;

/// Where the page is served and the one-time secret that opens its session.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Endpoint {
    pub origin: String,
    pub secret: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Failure {
    Unavailable,
    Exited,
    Protocol,
    Timeout,
}

pub fn ready_line(line: &str) -> Result<Endpoint, Failure> {
    let value: serde_json::Value = serde_json::from_str(line).map_err(|_| Failure::Protocol)?;
    let text = |key: &str| value.get(key).and_then(serde_json::Value::as_str);
    match (text("origin"), text("secret")) {
        (Some(origin), Some(secret)) if loopback(origin) && secret.chars().count() >= 32 => {
            Ok(Endpoint { origin: origin.to_string(), secret: secret.to_string() })
        }
        _ => Err(Failure::Protocol),
    }
}

fn loopback(origin: &str) -> bool {
    origin
        .strip_prefix("http://127.0.0.1:")
        .is_some_and(|port| (1..=5).contains(&port.len()) && port.bytes().all(|byte| byte.is_ascii_digit()))
}

fn open_log(path: &Path) -> io::Result<File> {
    if let Some(folder) = path.parent() {
        system::private_folder(folder)?;
    }
    if fs::metadata(path).is_ok_and(|metadata| metadata.len() > LOG_BYTES) {
        let mut rotated = path.as_os_str().to_owned();
        rotated.push(".1");
        let _ = fs::rename(path, rotated);
    }
    system::private_file(OpenOptions::new().create(true).append(true)).open(path)
}

/// One line of the shell's own in the helper log, beside the service's error output; a failed write is dropped. The
/// first line comes before the helper's start has made the folder.
pub fn note(path: &Path, message: &str) {
    if let Some(folder) = path.parent() {
        let _ = system::private_folder(folder);
    }
    if let Ok(mut file) = system::private_file(OpenOptions::new().create(true).append(true)).open(path) {
        let _ = writeln!(file, "{} shell: {message}", utc(SystemTime::now()));
    }
}

/// The UTC time as 2026-11-07T09:30:00Z (days to a civil date after Howard Hinnant).
fn utc(time: SystemTime) -> String {
    let seconds = time.duration_since(UNIX_EPOCH).map_or(0, |elapsed| elapsed.as_secs());
    let (days, rest) = ((seconds / 86_400) as i64 + 719_468, seconds % 86_400);
    let era = days.div_euclid(146_097);
    let day_of_era = days - era * 146_097;
    let year_of_era = (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let shifted = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * shifted + 2) / 5 + 1;
    let month = if shifted < 10 { shifted + 3 } else { shifted - 9 };
    let year = year_of_era + era * 400 + i64::from(month <= 2);
    format!("{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z", rest / 3_600, rest / 60 % 60, rest % 60)
}

/// Reports the first stdout line, then drains the rest so the service never blocks on a full pipe.
fn read_ready(mut stdout: impl Read, report: mpsc::Sender<Result<Endpoint, Failure>>) {
    let (mut buffer, mut chunk, mut reported) = (Vec::new(), [0u8; 1024], false);
    loop {
        let count = match stdout.read(&mut chunk) {
            Ok(0) | Err(_) => break,
            Ok(count) => count,
        };
        if reported {
            continue;
        }
        buffer.extend_from_slice(&chunk[..count]);
        if let Some(end) = buffer.iter().position(|&byte| byte == b'\n') {
            let line = String::from_utf8_lossy(&buffer[..end]).into_owned();
            let _ = report.send(ready_line(&line));
            reported = true;
        } else if buffer.len() > READY_BYTES {
            let _ = report.send(Err(Failure::Protocol));
            reported = true;
        }
    }
    if !reported {
        let _ = report.send(Err(Failure::Exited));
    }
}

pub struct Helper {
    pub endpoint: Endpoint,
    child: Mutex<Child>,
    stdin: Mutex<Option<ChildStdin>>,
    status: Mutex<Option<ExitStatus>>,
    changed: Condvar,
}

impl Helper {
    /// Start the helper's `serve <root>` command; returns once the service reports its endpoint. Its stderr goes
    /// to `log`.
    pub fn start(command: &HelperCommand, environment: &[(OsString, OsString)], log: &Path, timeout: Duration)
        -> Result<Arc<Helper>, Failure> {
        let output = open_log(log).map_err(|_| Failure::Unavailable)?;
        let mut process = Command::new(&command.executable);
        process.args(&command.args)
            .env_clear()
            .envs(environment.iter().map(|(name, value)| (name, value)))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::from(output));
        // No console window on Windows; the service starts its own workers without one too.
        #[cfg(windows)]
        process.creation_flags(windows_sys::Win32::System::Threading::CREATE_NO_WINDOW);
        let mut child = process.spawn().map_err(|_| Failure::Unavailable)?;
        let stdout = child.stdout.take().expect("stdout is piped");
        let (report, ready) = mpsc::channel();
        thread::spawn(move || read_ready(stdout, report));
        let endpoint = match ready.recv_timeout(timeout) {
            Ok(Ok(endpoint)) => endpoint,
            outcome => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(match outcome { Ok(Err(failure)) => failure, _ => Failure::Timeout });
            }
        };
        let stdin = child.stdin.take();
        let helper = Arc::new(Helper { endpoint, child: Mutex::new(child), stdin: Mutex::new(stdin),
            status: Mutex::new(None), changed: Condvar::new() });
        let watched = helper.clone();
        // try_wait under the lock: a signal never reaches a reaped process id that the system gave to another one.
        thread::spawn(move || loop {
            if let Ok(Some(status)) = watched.child.lock().unwrap().try_wait() {
                *watched.status.lock().unwrap() = Some(status);
                watched.changed.notify_all();
                return;
            }
            thread::sleep(Duration::from_millis(100));
        });
        Ok(helper)
    }

    /// Waits up to `timeout` for the helper to end; true once it has.
    fn wait_for(&self, timeout: Duration) -> bool {
        let status = self.status.lock().unwrap();
        let (status, _) = self.changed.wait_timeout_while(status, timeout, |status| status.is_none()).unwrap();
        status.is_some()
    }

    pub fn wait(&self) -> ExitStatus {
        let status = self.changed.wait_while(self.status.lock().unwrap(), |status| status.is_none()).unwrap();
        status.expect("the helper has ended")
    }

    #[cfg(unix)]
    fn signal(&self, signal: libc::c_int) {
        let mut child = self.child.lock().unwrap();
        if let Ok(None) = child.try_wait() {
            // SAFETY: kill(2) on the id of our own child, which try_wait has not reaped.
            unsafe { libc::kill(child.id() as libc::pid_t, signal) };
        }
    }

    pub fn stop(&self) {
        // EOF on stdin asks for a graceful shutdown; the helper is ended only when it does not come.
        drop(self.stdin.lock().unwrap().take());
        if self.wait_for(Duration::from_secs(20)) {
            return;
        }
        self.end();
        self.wait();
    }

    #[cfg(unix)]
    fn end(&self) {
        self.signal(libc::SIGTERM);
        if !self.wait_for(Duration::from_secs(5)) {
            self.signal(libc::SIGKILL);
        }
    }

    /// Windows has no SIGTERM: the process ends at once, as with Electron's kill() there.
    #[cfg(windows)]
    fn end(&self) {
        let mut child = self.child.lock().unwrap();
        if let Ok(None) = child.try_wait() {
            let _ = child.kill();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    use std::time::Instant;

    const READY: &str = r#"{"origin": "http://127.0.0.1:4321", "secret": "0123456789abcdef0123456789abcdef"}"#;

    fn temporary(name: &str) -> std::path::PathBuf {
        let folder = std::env::temp_dir().join(format!("foldcv-shell-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&folder);
        fs::create_dir_all(&folder).unwrap();
        folder
    }

    /// A shell script stands in for the helper.
    #[cfg(unix)]
    fn fake(script: &str) -> HelperCommand {
        HelperCommand { executable: "/bin/sh".into(), args: vec!["-c".into(), script.into(), "helper".into(), "serve".into(), "/data/root".into()] }
    }

    #[cfg(unix)]
    fn environment() -> Vec<(OsString, OsString)> {
        crate::policy::helper_environment(|_| None, Path::new("/nonexistent"))
    }

    #[test]
    fn the_ready_line_names_a_loopback_origin_and_a_full_secret() {
        let endpoint = ready_line(READY).unwrap();
        assert_eq!((endpoint.origin.as_str(), endpoint.secret.len()), ("http://127.0.0.1:4321", 32));
        for line in [r#"{"origin": "http://localhost:4321", "secret": "0123456789abcdef0123456789abcdef"}"#,
            r#"{"origin": "http://127.0.0.1:4321/", "secret": "0123456789abcdef0123456789abcdef"}"#,
            r#"{"origin": "http://127.0.0.1:123456", "secret": "0123456789abcdef0123456789abcdef"}"#,
            r#"{"origin": "http://127.0.0.1:4321", "secret": "short"}"#, "[]", "nonsense"] {
            assert_eq!(ready_line(line), Err(Failure::Protocol), "{line}");
        }
    }

    #[test]
    fn notes_carry_the_utc_time() {
        assert_eq!(utc(UNIX_EPOCH), "1970-01-01T00:00:00Z");
        assert_eq!(utc(UNIX_EPOCH + Duration::from_secs(1_794_043_845)), "2026-11-07T09:30:45Z");
        assert_eq!(utc(UNIX_EPOCH + Duration::from_secs(951_782_400)), "2000-02-29T00:00:00Z");
        let folder = temporary("note");
        let log = folder.join("logs/helper.log");
        note(&log, "service ready");
        note(&log, "window shown");
        let text = fs::read_to_string(&log).unwrap();
        assert_eq!(text.lines().map(|line| line.split_once(' ').unwrap().1).collect::<Vec<_>>(),
            ["shell: service ready", "shell: window shown"]);
    }

    #[cfg(unix)]
    #[test]
    fn the_helper_serves_until_its_stdin_closes_and_logs_its_stderr() {
        let folder = temporary("serve");
        let log = folder.join("logs/helper.log");
        let script = format!("echo \"starting $1 $2\" >&2; echo '{READY}'; cat >/dev/null; echo stopped >&2");
        let helper = Helper::start(&fake(&script), &environment(), &log, Duration::from_secs(10)).unwrap();
        assert_eq!(helper.endpoint, ready_line(READY).unwrap());
        let started = Instant::now();
        helper.stop();
        assert!(started.elapsed() < Duration::from_secs(5));
        assert!(helper.wait().success());
        assert_eq!(fs::read_to_string(&log).unwrap(), "starting serve /data/root\nstopped\n");
    }

    #[cfg(unix)]
    #[test]
    fn a_helper_that_ignores_stdin_still_ends_on_sigterm() {
        let folder = temporary("term");
        let script = format!("echo '{READY}'; exec sleep 60");
        let helper = Helper::start(&fake(&script), &environment(), &folder.join("helper.log"), Duration::from_secs(10)).unwrap();
        helper.signal(libc::SIGTERM);
        assert!(helper.wait_for(Duration::from_secs(5)));
    }

    #[cfg(unix)]
    #[test]
    fn a_helper_that_exits_answers_garbage_or_is_missing_fails_the_start() {
        let folder = temporary("fail");
        let log = folder.join("helper.log");
        let start = |command: HelperCommand| Helper::start(&command, &environment(), &log, Duration::from_secs(10)).err();
        assert_eq!(start(fake("exit 3")), Some(Failure::Exited));
        assert_eq!(start(fake("echo nonsense; cat >/dev/null")), Some(Failure::Protocol));
        assert_eq!(start(fake("head -c 5000 /dev/zero | tr '\\0' x; cat >/dev/null")), Some(Failure::Protocol));
        assert_eq!(start(HelperCommand { executable: folder.join("missing"), args: vec![] }), Some(Failure::Unavailable));
        let silent = Helper::start(&fake("cat >/dev/null"), &environment(), &log, Duration::from_millis(300)).err();
        assert_eq!(silent, Some(Failure::Timeout));
    }

    #[test]
    fn a_large_log_moves_aside_before_the_next_start() {
        let folder = temporary("log");
        let log = folder.join("helper.log");
        fs::write(&log, vec![b'x'; LOG_BYTES as usize + 1]).unwrap();
        drop(open_log(&log).unwrap());
        assert_eq!(fs::metadata(&log).unwrap().len(), 0);
        assert_eq!(fs::metadata(folder.join("helper.log.1")).unwrap().len(), LOG_BYTES + 1);
    }
}

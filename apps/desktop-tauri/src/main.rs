// The desktop app: a Tauri window that starts the frozen service and shows its page. The page uses no Tauri API;
// preload.js gives it the download report and the desktop styles.
#![cfg_attr(all(windows, not(test)), windows_subsystem = "windows")]

mod helper;
mod policy;
// What differs between macOS and Windows: the window frame, the menu, alerts, links and file access.
#[cfg_attr(target_os = "macos", path = "macos.rs")]
#[cfg_attr(windows, path = "windows.rs")]
mod system;

use std::collections::HashMap;
use std::fs::{self, File, TryLockError};
use std::io;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::SeqCst};
use std::sync::{mpsc, Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use tauri::webview::{DownloadEvent, NewWindowResponse, PageLoadEvent, PageLoadPayload, PermissionKind, PermissionResponse};
use tauri::window::Color;
use tauri::{AppHandle, Manager, RunEvent, Url, Webview, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_dialog::DialogExt;

use helper::{note, Endpoint, Helper};

const WINDOW: &str = "main";
const PRELOAD: &str = include_str!("preload.js");

struct Download {
    file: PathBuf,
    name: String,
}

struct Shell {
    root: PathBuf,
    log: PathBuf,
    // Held while the app runs; the system drops the lock with the process.
    _lock: Option<File>,
    helper: OnceLock<Arc<Helper>>,
    shown: AtomicBool,
    stopping: AtomicBool,
    finished: AtomicBool,
    // While the app quits: hears that the blank page has loaded, so the service page has left.
    left: Mutex<Option<mpsc::Sender<()>>>,
    downloads: Mutex<HashMap<String, Download>>,
    next_download: AtomicU64,
}

/// One app per data root: a second service on the same root would reap the operations of the first.
fn claim(root: &Path) -> io::Result<Option<File>> {
    let folder = root.join("tauri");
    system::private_folder(&folder)?;
    let file = system::private_file(File::options().create(true).truncate(false).write(true)).open(folder.join("shell.lock"))?;
    match file.try_lock() {
        Ok(()) => Ok(Some(file)),
        Err(TryLockError::WouldBlock) => Ok(None),
        Err(TryLockError::Error(error)) => Err(error),
    }
}

fn open_external(raw: &str) {
    if let Some(url) = policy::external_url(raw) {
        system::open_url(url);
    }
}

fn notify(webview: &Webview, state: &str, name: &str) {
    let _ = webview.eval(format!("window.__foldcvDownloadDone?.({}, {})", serde_json::json!(state), serde_json::json!(name)));
}

/// The engine writes the file into the data root first; the save dialog follows, as Electron's did before the page heard.
fn download(shell: &Shell, webview: Webview, event: DownloadEvent<'_>) -> bool {
    match event {
        DownloadEvent::Requested { url, destination } => {
            let target = destination.clone();
            let folder = target.parent().unwrap_or(Path::new("/"));
            let name = policy::requested_name(&target, |name| folder.join(name).exists()).unwrap_or_else(|| "file".into());
            let file = shell.root.join("tauri/downloads").join(shell.next_download.fetch_add(1, SeqCst).to_string());
            if system::private_folder(&file).is_err() {
                return false;
            }
            let file = file.join(&name);
            *destination = file.clone();
            shell.downloads.lock().unwrap().insert(url.to_string(), Download { file, name });
            true
        }
        DownloadEvent::Finished { url, success, .. } => {
            let download = shell.downloads.lock().unwrap().remove(url.as_str());
            thread::spawn(move || deliver(&webview, download, success));
            true
        }
        _ => true,
    }
}

fn deliver(webview: &Webview, download: Option<Download>, success: bool) {
    let (state, name) = match &download {
        Some(download) if success => save(webview.app_handle(), download),
        _ => ("interrupted", String::new()),
    };
    if let Some(folder) = download.as_ref().and_then(|download| download.file.parent()) {
        let _ = fs::remove_dir_all(folder);
    }
    notify(webview, state, &name);
}

fn save(app: &AppHandle, download: &Download) -> (&'static str, String) {
    let mut dialog = app.dialog().file().set_file_name(&download.name);
    if let Ok(folder) = app.path().download_dir() {
        dialog = dialog.set_directory(folder);
    }
    if let Some(window) = app.get_webview_window(WINDOW) {
        dialog = dialog.set_parent(&window);
    }
    let Some(target) = dialog.blocking_save_file().and_then(|path| path.into_path().ok()) else {
        return ("cancelled", String::new());
    };
    // The dialog has asked before replacing a file; another volume needs a copy.
    match fs::rename(&download.file, &target).or_else(|_| fs::copy(&download.file, &target).map(|_| ())) {
        Ok(()) => ("completed", target.file_name().map(|name| name.to_string_lossy().into_owned()).unwrap_or_default()),
        Err(_) => ("interrupted", String::new()),
    }
}

fn page_loaded(shell: &Shell, window: &WebviewWindow, payload: PageLoadPayload<'_>) {
    if !matches!(payload.event(), PageLoadEvent::Finished) {
        return;
    }
    if shell.stopping.load(SeqCst) {
        if payload.url().scheme() == "about" && let Some(left) = shell.left.lock().unwrap().take() {
            let _ = left.send(());
        }
    } else if !shell.shown.swap(true, SeqCst) {
        let _ = window.show();
        let _ = window.set_focus();
        note(&shell.log, "window shown");
    }
}

fn window_size(app: &AppHandle) -> (f64, f64) {
    let area = app.primary_monitor().ok().flatten()
        .map(|monitor| monitor.work_area().size.to_logical::<f64>(monitor.scale_factor()));
    area.map_or((1440.0, 960.0), |area| (area.width.min(1440.0), area.height.min(960.0)))
}

fn open_window(app: &AppHandle, shell: &Arc<Shell>, endpoint: &Endpoint) -> tauri::Result<WebviewWindow> {
    let url = Url::parse(&format!("{}/#secret={}", endpoint.origin, endpoint.secret)).expect("the helper names a valid origin");
    let (width, height) = window_size(app);
    let (origin, downloads, loads) = (endpoint.origin.clone(), shell.clone(), shell.clone());
    let builder = WebviewWindowBuilder::new(app, WINDOW, WebviewUrl::External(url))
        .title(&app.package_info().name)
        .inner_size(width, height)
        .min_inner_size(800.0, 600.0)
        // Tauri sizes the page, not the window: the Windows title bar would push the bottom of the window under the
        // taskbar.
        .prevent_overflow()
        .center()
        .visible(false)
        .background_color(Color(0xea, 0xe9, 0xe2, 0xff))
        // Files dropped on the page go to the page, not to Tauri.
        .disable_drag_drop_handler()
        .devtools(false)
        .initialization_script(format!("{PRELOAD}({:?});", system::DESKTOP))
        // It also sees the loads of frames: the DOCX original is an about:srcdoc frame.
        .on_navigation(move |url| {
            if url.scheme() == "about" || policy::app_url(url.as_str(), &origin) {
                return true;
            }
            open_external(url.as_str());
            false
        })
        .on_new_window(|url, _| {
            open_external(url.as_str());
            NewWindowResponse::Deny
        })
        // The page needs no permission, so the shell refuses them. Files go through the shell's save dialog, so a
        // second download in a row is not held back.
        .on_permission_request(|_, kind| match kind {
            PermissionKind::AutomaticDownloads => PermissionResponse::Allow,
            _ => PermissionResponse::Deny,
        })
        .on_download(move |webview, event| download(&downloads, webview, event))
        .on_page_load(move |window, payload| page_loaded(&loads, &window, payload));
    let window = system::window(builder, &shell.root).build()?;
    let (handle, closing) = (app.clone(), shell.clone());
    window.on_window_event(move |event| {
        if let WindowEvent::CloseRequested { api, .. } = event && !closing.finished.load(SeqCst) {
            api.prevent_close();
            shutdown(&handle, &closing);
        }
    });
    // A page that never finishes loading still gets its window.
    let (shown, late) = (window.clone(), shell.clone());
    thread::spawn(move || {
        thread::sleep(Duration::from_secs(10));
        if !late.stopping.load(SeqCst) && !late.shown.swap(true, SeqCst) {
            let _ = shown.show();
            note(&late.log, "window shown before its page loaded");
        }
    });
    Ok(window)
}

fn start(app: AppHandle, shell: Arc<Shell>) {
    let name = app.package_info().name.clone();
    let webview = tauri::webview_version();
    note(&shell.log, &format!("{name} {} starting on {} {}, webview {}", app.package_info().version, std::env::consts::OS,
        std::env::consts::ARCH, webview.as_deref().unwrap_or("missing")));
    // Windows 11 has the WebView2 runtime; an old Windows 10 may not.
    #[cfg(windows)]
    if webview.is_err() {
        system::alert(&name, format!("Для {name} нужен Microsoft Edge WebView2 Runtime."),
            "Установите его с сайта Microsoft и запустите приложение снова.".into());
        return shutdown(&app, &shell);
    }
    let command = policy::helper_command(&app.path().resource_dir().unwrap_or_default(), &shell.root);
    let environment = policy::helper_environment(|key| std::env::var_os(key), &app.path().home_dir().unwrap_or_default());
    let started = Instant::now();
    let helper = match Helper::start(&command, &environment, &shell.log, Duration::from_secs(120)) {
        Ok(helper) => helper,
        Err(failure) => {
            note(&shell.log, &format!("service did not start: {failure:?} after {} ms", started.elapsed().as_millis()));
            return fatal(&app, &shell, format!("Не удалось запустить {name}."));
        }
    };
    note(&shell.log, &format!("service ready after {} ms", started.elapsed().as_millis()));
    let _ = shell.helper.set(helper.clone());
    let (watcher, watched, ended) = (app.clone(), shell.clone(), helper.clone());
    thread::spawn(move || {
        let status = ended.wait();
        note(&watched.log, &format!("service ended: {status}"));
        if !watched.stopping.load(SeqCst) {
            fatal(&watcher, &watched, format!("Сервис {name} остановился. Приложение будет закрыто."));
        }
    });
    if !shell.stopping.load(SeqCst) && let Err(error) = open_window(&app, &shell, &helper.endpoint) {
        note(&shell.log, &format!("window not opened: {error}"));
        fatal(&app, &shell, format!("Не удалось открыть окно {}.", app.package_info().name));
    }
}

/// Shows the error, then quits.
fn fatal(app: &AppHandle, shell: &Arc<Shell>, message: String) {
    system::alert(&app.package_info().name, message, format!("Подробности в журнале: {}", shell.log.display()));
    shutdown(app, shell);
}

fn shutdown(app: &AppHandle, shell: &Arc<Shell>) {
    if shell.stopping.swap(true, SeqCst) {
        return;
    }
    let (app, shell) = (app.clone(), shell.clone());
    thread::spawn(move || {
        if let Some(window) = app.get_webview_window(WINDOW) {
            // The page sends its last edits on pagehide: a blank page makes it leave, as closing the window does.
            let (left, gone) = mpsc::channel();
            *shell.left.lock().unwrap() = Some(left);
            if window.navigate(Url::parse("about:blank").expect("a valid URL")).is_ok() {
                let _ = gone.recv_timeout(Duration::from_secs(5));
            }
            let _ = window.hide();
        }
        if let Some(helper) = shell.helper.get() {
            helper.stop();
        }
        shell.finished.store(true, SeqCst);
        app.exit(0);
    });
}

fn main() {
    let app = system::app(tauri::Builder::default())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // Local, not roaming, on Windows; the same Application Support folder on macOS.
            let root = policy::data_root(std::env::var_os("FOLDCV_DESKTOP_ROOT").as_deref(), &app.path().local_data_dir()?);
            let lock = claim(&root);
            let another = matches!(lock, Ok(None));
            let shell = Arc::new(Shell { log: root.join("logs/helper.log"), root, _lock: lock.ok().flatten(),
                helper: OnceLock::new(), shown: AtomicBool::new(false), stopping: AtomicBool::new(another),
                finished: AtomicBool::new(another), left: Mutex::new(None), downloads: Mutex::new(HashMap::new()),
                next_download: AtomicU64::new(0) });
            app.manage(shell.clone());
            if another {
                // macOS opens the running app instead, and on Windows the single instance plugin hands a second start
                // to it; only a direct second start on macOS gets here.
                app.handle().exit(0);
                return Ok(());
            }
            let _ = fs::remove_dir_all(shell.root.join("tauri/downloads"));
            let handle = app.handle().clone();
            thread::spawn(move || start(handle, shell));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("the app builds");
    app.run(|app, event| {
        let Some(shell) = app.try_state::<Arc<Shell>>() else { return };
        match event {
            RunEvent::ExitRequested { api, .. } if !shell.finished.load(SeqCst) => {
                api.prevent_exit();
                shutdown(app, &shell);
            }
            // The system's quit (the Dock menu, logging out) ends the app without asking; the service still stops.
            RunEvent::Exit => {
                // Its end is expected now, so the watcher shows no alert.
                shell.stopping.store(true, SeqCst);
                if let Some(helper) = shell.helper.get() {
                    helper.stop();
                }
            }
            _ => {}
        }
    });
}

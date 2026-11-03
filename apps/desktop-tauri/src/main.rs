// The macOS app: a Tauri window that starts the frozen service and shows its page, as apps/desktop does with Electron
// on Windows. The page uses no Tauri API; preload.js gives it what the Electron preload gives.

mod helper;
mod policy;

use std::collections::HashMap;
use std::fs::{self, DirBuilder, File, TryLockError};
use std::io;
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::SeqCst};
use std::sync::{mpsc, Arc, Mutex, OnceLock};
use std::thread;
use std::time::Duration;

use dispatch2::DispatchQueue;
use objc2::{MainThreadMarker, MainThreadOnly};
use objc2_app_kit::{NSAlert, NSAlertStyle, NSBackingStoreType, NSWindow, NSWindowButton, NSWindowStyleMask,
    NSWindowTitleVisibility};
use objc2_foundation::{NSPoint, NSRect, NSSize, NSString};
use tauri::menu::{AboutMetadata, Menu, MenuEvent, MenuItem, PredefinedMenuItem, Submenu};
use tauri::webview::{DownloadEvent, NewWindowResponse, PageLoadEvent, PageLoadPayload};
use tauri::window::Color;
use tauri::{AppHandle, LogicalPosition, Manager, RunEvent, TitleBarStyle, Url, Webview, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder, WindowEvent};
use tauri_plugin_dialog::DialogExt;

use helper::{Endpoint, Helper};

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
    // In half zoom levels of Chromium, as the Electron menu steps.
    zoom: Mutex<i32>,
}

/// One app per data root: a second service on the same root would reap the operations of the first.
fn claim(root: &Path) -> io::Result<Option<File>> {
    let folder = root.join("tauri");
    DirBuilder::new().recursive(true).mode(0o700).create(&folder)?;
    let file = File::options().create(true).truncate(false).write(true).mode(0o600).open(folder.join("shell.lock"))?;
    match file.try_lock() {
        Ok(()) => Ok(Some(file)),
        Err(TryLockError::WouldBlock) => Ok(None),
        Err(TryLockError::Error(error)) => Err(error),
    }
}

fn open_external(raw: &str) {
    if let Some(url) = policy::external_url(raw) {
        thread::spawn(move || { let _ = Command::new("/usr/bin/open").arg(url).status(); });
    }
}

fn notify(webview: &Webview, state: &str, name: &str) {
    let _ = webview.eval(format!("window.__foldcvDownloadDone?.({}, {})", serde_json::json!(state), serde_json::json!(name)));
}

/// WebKit writes the file into the data root first; the save dialog follows, as Electron's did before the page heard.
fn download(shell: &Shell, webview: Webview, event: DownloadEvent<'_>) -> bool {
    match event {
        DownloadEvent::Requested { url, destination } => {
            let target = destination.clone();
            let folder = target.parent().unwrap_or(Path::new("/"));
            let name = policy::requested_name(&target, |name| folder.join(name).exists()).unwrap_or_else(|| "file".into());
            let file = shell.root.join("tauri/downloads").join(shell.next_download.fetch_add(1, SeqCst).to_string());
            if DirBuilder::new().recursive(true).mode(0o700).create(&file).is_err() {
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
    }
}

/// How high the close button sits above the bottom of the title bar in a window of this style (9 pt on macOS 26).
/// tao keeps that height when it moves the buttons and makes the bar their height plus its inset, so the Electron
/// inset from the top, which centres the buttons in their height plus twice the inset, needs it added.
fn button_offset() -> f64 {
    let mut offset = 9.0;
    DispatchQueue::main().exec_sync(|| {
        let style = NSWindowStyleMask::Titled | NSWindowStyleMask::Closable | NSWindowStyleMask::Miniaturizable
            | NSWindowStyleMask::Resizable | NSWindowStyleMask::FullSizeContentView;
        let frame = NSRect::new(NSPoint::new(0.0, 0.0), NSSize::new(800.0, 600.0));
        let window = NSWindow::alloc(MainThreadMarker::new().expect("the main queue runs on the main thread"));
        // SAFETY: a deferred window that is never shown; the Retained value releases it.
        let window = unsafe {
            let window = NSWindow::initWithContentRect_styleMask_backing_defer(window, frame, style,
                NSBackingStoreType::Buffered, true);
            window.setReleasedWhenClosed(false);
            window
        };
        window.setTitlebarAppearsTransparent(true);
        window.setTitleVisibility(NSWindowTitleVisibility::Hidden);
        if let Some(button) = window.standardWindowButton(NSWindowButton::CloseButton) {
            offset = button.frame().origin.y;
        }
    });
    offset
}

fn window_size(app: &AppHandle) -> (f64, f64) {
    let area = app.primary_monitor().ok().flatten()
        .map(|monitor| monitor.work_area().size.to_logical::<f64>(monitor.scale_factor()));
    area.map_or((1440.0, 960.0), |area| (area.width.min(1440.0), area.height.min(960.0)))
}

fn open_window(app: &AppHandle, shell: &Arc<Shell>, endpoint: &Endpoint) -> tauri::Result<WebviewWindow> {
    let url = Url::parse(&format!("{}/#secret={}", endpoint.origin, endpoint.secret)).expect("the helper names a valid origin");
    let (width, height) = window_size(app);
    let buttons = LogicalPosition::new(16.0, 12.0 + button_offset());
    let (origin, downloads, loads) = (endpoint.origin.clone(), shell.clone(), shell.clone());
    let window = WebviewWindowBuilder::new(app, WINDOW, WebviewUrl::External(url))
        .title(&app.package_info().name)
        .inner_size(width, height)
        .min_inner_size(800.0, 600.0)
        .center()
        .visible(false)
        // No title bar, the window buttons over the page corner, where the Electron window had them.
        .title_bar_style(TitleBarStyle::Overlay)
        .hidden_title(true)
        .traffic_light_position(buttons)
        .background_color(Color(0xea, 0xe9, 0xe2, 0xff))
        // Files dropped on the page go to the page, not to Tauri.
        .disable_drag_drop_handler()
        .allow_link_preview(false)
        .devtools(false)
        .initialization_script(PRELOAD)
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
        .on_download(move |webview, event| download(&downloads, webview, event))
        .on_page_load(move |window, payload| page_loaded(&loads, &window, payload))
        .build()?;
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
        }
    });
    Ok(window)
}

fn start(app: AppHandle, shell: Arc<Shell>) {
    let name = app.package_info().name.clone();
    let command = policy::helper_command(&app.path().resource_dir().unwrap_or_default(), &shell.root);
    let environment = policy::helper_environment(std::env::var_os("TMPDIR"), &app.path().home_dir().unwrap_or_default());
    let helper = match Helper::start(&command, &environment, &shell.log, Duration::from_secs(120)) {
        Ok(helper) => helper,
        Err(_) => return fatal(&app, &shell, format!("Не удалось запустить {name}.")),
    };
    let _ = shell.helper.set(helper.clone());
    let (watcher, watched, ended) = (app.clone(), shell.clone(), helper.clone());
    thread::spawn(move || {
        ended.wait();
        if !watched.stopping.load(SeqCst) {
            fatal(&watcher, &watched, format!("Сервис {name} остановился. Приложение будет закрыто."));
        }
    });
    if !shell.stopping.load(SeqCst) && open_window(&app, &shell, &helper.endpoint).is_err() {
        fatal(&app, &shell, format!("Не удалось открыть окно {}.", app.package_info().name));
    }
}

/// An app-modal alert, as Electron shows without a window; waits for it on a thread other than the main one.
fn alert(message: String, detail: String) {
    DispatchQueue::main().exec_sync(move || {
        let alert = NSAlert::new(MainThreadMarker::new().expect("the main queue runs on the main thread"));
        alert.setAlertStyle(NSAlertStyle::Critical);
        alert.setMessageText(&NSString::from_str(&message));
        alert.setInformativeText(&NSString::from_str(&detail));
        alert.runModal();
    });
}

/// Shows the error, then quits.
fn fatal(app: &AppHandle, shell: &Arc<Shell>, message: String) {
    alert(message, format!("Подробности в журнале: {}", shell.log.display()));
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

fn menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let info = app.package_info();
    let about = AboutMetadata { name: Some(info.name.clone()), version: Some(info.version.to_string()), ..Default::default() };
    let application = Submenu::with_items(app, &info.name, true, &[
        &PredefinedMenuItem::about(app, None, Some(about))?,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::services(app, None)?,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::hide(app, None)?,
        &PredefinedMenuItem::hide_others(app, None)?,
        &PredefinedMenuItem::show_all(app, None)?,
        &PredefinedMenuItem::separator(app)?,
        // Not the system's quit item: that one ends the app before the page can leave.
        &MenuItem::with_id(app, "quit", format!("Quit {}", info.name), true, Some("CmdOrCtrl+Q"))?,
    ])?;
    let file = Submenu::with_items(app, "File", true, &[&PredefinedMenuItem::close_window(app, None)?])?;
    let edit = Submenu::with_items(app, "Edit", true, &[
        &PredefinedMenuItem::undo(app, None)?,
        &PredefinedMenuItem::redo(app, None)?,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::cut(app, None)?,
        &PredefinedMenuItem::copy(app, None)?,
        &PredefinedMenuItem::paste(app, None)?,
        &PredefinedMenuItem::select_all(app, None)?,
    ])?;
    let view = Submenu::with_items(app, "View", true, &[
        &MenuItem::with_id(app, "reload", "Reload", true, Some("CmdOrCtrl+R"))?,
        &PredefinedMenuItem::separator(app)?,
        &MenuItem::with_id(app, "zoom-reset", "Actual Size", true, Some("CmdOrCtrl+0"))?,
        &MenuItem::with_id(app, "zoom-in", "Zoom In", true, Some("CmdOrCtrl+="))?,
        &MenuItem::with_id(app, "zoom-out", "Zoom Out", true, Some("CmdOrCtrl+-"))?,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::fullscreen(app, None)?,
    ])?;
    let window = Submenu::with_items(app, "Window", true, &[
        &PredefinedMenuItem::minimize(app, None)?,
        &PredefinedMenuItem::maximize(app, None)?,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::bring_all_to_front(app, None)?,
    ])?;
    window.set_as_windows_menu_for_nsapp()?;
    Menu::with_items(app, &[&application, &file, &edit, &view, &window])
}

fn menu_event(app: &AppHandle, event: MenuEvent) {
    let Some(shell) = app.try_state::<Arc<Shell>>() else { return };
    if event.id() == "quit" {
        return shutdown(app, &shell);
    }
    let Some(window) = app.get_webview_window(WINDOW).filter(|_| !shell.stopping.load(SeqCst)) else { return };
    match event.id().as_ref() {
        "reload" => { let _ = window.reload(); }
        id @ ("zoom-reset" | "zoom-in" | "zoom-out") => {
            let mut zoom = shell.zoom.lock().unwrap();
            *zoom = match id { "zoom-in" => (*zoom + 1).min(9), "zoom-out" => (*zoom - 1).max(-6), _ => 0 };
            let _ = window.set_zoom(1.2f64.powf(f64::from(*zoom) / 2.0));
        }
        _ => {}
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .menu(menu)
        .on_menu_event(menu_event)
        .setup(|app| {
            let root = policy::data_root(std::env::var_os("FOLDCV_DESKTOP_ROOT").as_deref(), &app.path().data_dir()?);
            let lock = claim(&root);
            let another = matches!(lock, Ok(None));
            let shell = Arc::new(Shell { log: root.join("logs/helper.log"), root, _lock: lock.ok().flatten(),
                helper: OnceLock::new(), shown: AtomicBool::new(false), stopping: AtomicBool::new(another),
                finished: AtomicBool::new(another), left: Mutex::new(None), downloads: Mutex::new(HashMap::new()),
                next_download: AtomicU64::new(0), zoom: Mutex::new(0) });
            app.manage(shell.clone());
            if another {
                // macOS opens the running app instead; only a direct second start gets here.
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

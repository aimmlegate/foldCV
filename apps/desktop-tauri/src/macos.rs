// The macOS side of the shell: AppKit for the alert and the window buttons, the app menu, owner-only files.

use std::fs::{DirBuilder, OpenOptions};
use std::io;
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::path::Path;
use std::process::Command;
use std::sync::atomic::Ordering::SeqCst;
use std::sync::{Arc, Mutex};
use std::thread;

use dispatch2::DispatchQueue;
use objc2::{MainThreadMarker, MainThreadOnly};
use objc2_app_kit::{NSAlert, NSAlertStyle, NSBackingStoreType, NSWindow, NSWindowButton, NSWindowStyleMask,
    NSWindowTitleVisibility};
use objc2_foundation::{NSPoint, NSRect, NSSize, NSString};
use tauri::menu::{AboutMetadata, Menu, MenuEvent, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Builder, LogicalPosition, Manager, TitleBarStyle, WebviewWindowBuilder, Wry};

use crate::{shutdown, Shell, WINDOW};

/// For the page's desktop styles; the window has no title bar, so the preload adds the strip that drags it.
pub const DESKTOP: &str = "macos";

// In half zoom levels of Chromium, as the Electron menu steps.
static ZOOM: Mutex<i32> = Mutex::new(0);

pub fn private_folder(path: &Path) -> io::Result<()> {
    DirBuilder::new().recursive(true).mode(0o700).create(path)
}

pub fn private_file(options: &mut OpenOptions) -> &mut OpenOptions {
    options.mode(0o600)
}

pub fn open_url(url: String) {
    thread::spawn(move || { let _ = Command::new("/usr/bin/open").arg(url).status(); });
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

/// No title bar, the window buttons over the page corner, where the Electron window had them.
pub fn window<'a>(builder: WebviewWindowBuilder<'a, Wry, AppHandle>, _root: &Path) -> WebviewWindowBuilder<'a, Wry, AppHandle> {
    builder
        .title_bar_style(TitleBarStyle::Overlay)
        .hidden_title(true)
        .traffic_light_position(LogicalPosition::new(16.0, 12.0 + button_offset()))
        .allow_link_preview(false)
}

/// An app-modal alert, as Electron shows without a window; waits for it on a thread other than the main one.
pub fn alert(_title: &str, message: String, detail: String) {
    DispatchQueue::main().exec_sync(move || {
        let alert = NSAlert::new(MainThreadMarker::new().expect("the main queue runs on the main thread"));
        alert.setAlertStyle(NSAlertStyle::Critical);
        alert.setMessageText(&NSString::from_str(&message));
        alert.setInformativeText(&NSString::from_str(&detail));
        alert.runModal();
    });
}

pub fn app(builder: Builder<Wry>) -> Builder<Wry> {
    builder.menu(menu).on_menu_event(menu_event)
}

fn menu(app: &AppHandle) -> tauri::Result<Menu<Wry>> {
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
            let mut zoom = ZOOM.lock().unwrap();
            *zoom = match id { "zoom-in" => (*zoom + 1).min(9), "zoom-out" => (*zoom - 1).max(-6), _ => 0 };
            let _ = window.set_zoom(1.2f64.powf(f64::from(*zoom) / 2.0));
        }
        _ => {}
    }
}

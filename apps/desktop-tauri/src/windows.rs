// The Windows side of the shell: the native frame, a message box, links through the system shell, one running app.

use std::fs::{self, OpenOptions};
use std::io;
use std::path::Path;
use std::ptr;
use std::thread;

use tauri::{AppHandle, Builder, Manager, WebviewWindowBuilder, Wry};
use windows_sys::Win32::System::Com::{CoInitializeEx, CoUninitialize, COINIT_APARTMENTTHREADED, COINIT_DISABLE_OLE1DDE};
use windows_sys::Win32::UI::Shell::ShellExecuteW;
use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_SETFOREGROUND, SW_SHOWNORMAL};

use crate::WINDOW;

/// For the page's desktop styles; the native frame needs no strip.
pub const DESKTOP: &str = "windows";

fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain([0]).collect()
}

/// Files under the profile's AppData get the user's own access from it.
pub fn private_folder(path: &Path) -> io::Result<()> {
    fs::create_dir_all(path)
}

pub fn private_file(options: &mut OpenOptions) -> &mut OpenOptions {
    options
}

/// The default browser or mail app, as Electron's shell.openExternal opens it.
pub fn open_url(url: String) {
    thread::spawn(move || {
        let (verb, url) = (wide("open"), wide(&url));
        // SAFETY: the strings end with a NUL and outlive the calls. Shell handlers of a link may need COM.
        unsafe {
            let com = CoInitializeEx(ptr::null(), (COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE) as u32);
            ShellExecuteW(ptr::null_mut(), verb.as_ptr(), url.as_ptr(), ptr::null(), ptr::null(), SW_SHOWNORMAL);
            if com >= 0 {
                CoUninitialize();
            }
        }
    });
}

/// The native frame. WebView2 keeps its storage in the data root, as Electron did, and zooms with Ctrl and +, - or
/// the wheel, as the Electron View menu did.
pub fn window<'a>(builder: WebviewWindowBuilder<'a, Wry, AppHandle>, root: &Path) -> WebviewWindowBuilder<'a, Wry, AppHandle> {
    builder.data_directory(root.join("tauri").join("webview")).zoom_hotkeys_enabled(true)
}

/// A message box without a window, as Electron shows; returns when it is closed.
pub fn alert(title: &str, message: String, detail: String) {
    let (text, caption) = (wide(&format!("{message}\n\n{detail}")), wide(title));
    // SAFETY: the strings end with a NUL and outlive the call.
    unsafe { MessageBoxW(ptr::null_mut(), text.as_ptr(), caption.as_ptr(), MB_ICONERROR | MB_SETFOREGROUND) };
}

/// A second start shows the running window. No menu bar: WebView2 has the edit, reload and zoom keys itself.
pub fn app(builder: Builder<Wry>) -> Builder<Wry> {
    builder.plugin(tauri_plugin_single_instance::init(|app, _, _| {
        if let Some(window) = app.get_webview_window(WINDOW) {
            let _ = window.unminimize();
            let _ = window.set_focus();
        }
    }))
}

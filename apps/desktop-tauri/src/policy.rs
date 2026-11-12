use std::ffi::{OsStr, OsString};
use std::path::{Path, PathBuf};

use tauri::Url;

// Its own folder, so the app runs next to the FoldCV Local builds and shows none of their data. The Electron builds
// use the same one.
// The data folder keeps the beta's name, so the beta's projects and sign-ins carry over (D169).
pub const DATA_FOLDER: &str = "foldCV Beta";

// Windows variables the frozen service and its workers need; everything else, PATH and PYTHON* included, stays out.
#[cfg(windows)]
const WINDOWS_VARIABLES: [&str; 23] = ["SystemRoot", "SystemDrive", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
    "CommonProgramFiles", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS", "USERNAME",
    "USERDOMAIN", "COMPUTERNAME"];

/// The helper executable and its arguments.
#[derive(Debug, PartialEq, Eq)]
pub struct HelperCommand {
    pub executable: PathBuf,
    pub args: Vec<OsString>,
}

/// FOLDCV_DESKTOP_ROOT for QA runs, else the app's folder in the user's data folder: Application Support on macOS,
/// the local AppData on Windows.
pub fn data_root(override_root: Option<&OsStr>, app_data: &Path) -> PathBuf {
    match override_root.map(Path::new) {
        Some(root) if root.is_absolute() => root.to_path_buf(),
        _ => app_data.join(DATA_FOLDER),
    }
}

/// `serve <root>` on the helper app inside the bundle.
#[cfg(target_os = "macos")]
pub fn helper_command(resources: &Path, root: &Path) -> HelperCommand {
    HelperCommand {
        executable: resources.join("../Helpers/FoldCV Helper.app/Contents/MacOS/foldcv-helper"),
        args: vec!["serve".into(), root.into()],
    }
}

/// `serve <root>` on the embeddable Python of the helper folder next to the exe.
#[cfg(windows)]
pub fn helper_command(resources: &Path, root: &Path) -> HelperCommand {
    let helper = resources.join("helper");
    HelperCommand {
        executable: helper.join(r"python\python.exe"),
        // UTF-8 mode: the service and its workers would use the ANSI code page otherwise.
        args: vec!["-X".into(), "utf8".into(), helper.join(r"app\packaging\helper_entry.py").into(), "serve".into(),
            root.into()],
    }
}

/// The only variables the helper gets, read through `variable`: PATH and PYTHON* of the user stay out.
#[cfg(target_os = "macos")]
pub fn helper_environment(variable: impl Fn(&str) -> Option<OsString>, home: &Path) -> Vec<(OsString, OsString)> {
    let mut environment: Vec<(OsString, OsString)> = vec![
        ("PATH".into(), "/usr/bin:/bin:/usr/sbin:/sbin".into()),
        ("HOME".into(), home.into()),
        ("LANG".into(), "en_US.UTF-8".into()),
    ];
    if let Some(temporary) = variable("TMPDIR").filter(|value| !value.is_empty()) {
        environment.push(("TMPDIR".into(), temporary));
    }
    environment
}

/// The only variables the helper gets, read through `variable`: the system's PATH and the Windows variables above,
/// which also name the user's folders.
#[cfg(windows)]
pub fn helper_environment(variable: impl Fn(&str) -> Option<OsString>, _home: &Path) -> Vec<(OsString, OsString)> {
    let present = |name: &str| variable(name).filter(|value| !value.is_empty());
    let mut environment: Vec<(OsString, OsString)> = WINDOWS_VARIABLES.iter()
        .filter_map(|&name| present(name).map(|value| (name.into(), value)))
        .collect();
    let system = present("SystemRoot").or_else(|| present("WINDIR")).unwrap_or_else(|| r"C:\Windows".into());
    if present("SystemRoot").is_none() {
        environment.push(("SystemRoot".into(), system.clone()));
    }
    let system = system.to_string_lossy();
    environment.push(("PATH".into(), format!(r"{system}\System32;{system};{system}\System32\Wbem").into()));
    environment
}

/// The window shows only pages of its own service.
pub fn app_url(raw: &str, origin: &str) -> bool {
    Url::parse(raw).is_ok_and(|url| url.origin().ascii_serialization() == origin)
}

/// A link for the default browser or mail app; anything else is dropped.
pub fn external_url(raw: &str) -> Option<String> {
    let url = Url::parse(raw).ok()?;
    (["https", "http", "mailto"].contains(&url.scheme()) && url.username().is_empty() && url.password().is_none())
        .then(|| url.to_string())
}

/// The file name the page asked for. When Downloads already holds it, the engine's default target there carries a
/// counter: "base (n).ext", which wry puts before the first dot on macOS and Chromium before the extension on Windows.
pub fn requested_name(target: &Path, exists: impl Fn(&str) -> bool) -> Option<String> {
    let name = target.file_name()?.to_str()?;
    for (start, _) in name.match_indices(" (") {
        let rest = &name[start + 2..];
        let digits = rest.bytes().take_while(u8::is_ascii_digit).count();
        if digits == 0 || !rest[digits..].starts_with(')') {
            continue;
        }
        let original = format!("{}{}", &name[..start], &rest[digits + 1..]);
        if counter_position(&original) == start && exists(&original) {
            return Some(original);
        }
    }
    Some(name.to_string())
}

#[cfg(target_os = "macos")]
fn counter_position(name: &str) -> usize {
    name.find('.').unwrap_or(name.len())
}

#[cfg(windows)]
fn counter_position(name: &str) -> usize {
    name.rfind('.').unwrap_or(name.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    const ORIGIN: &str = "http://127.0.0.1:4321";

    #[test]
    fn the_window_keeps_to_its_own_service_and_hands_web_and_mail_links_to_the_system() {
        assert!(app_url("http://127.0.0.1:4321/?project=a", ORIGIN));
        assert!(app_url("blob:http://127.0.0.1:4321/5f0c", ORIGIN));
        assert!(!app_url("http://127.0.0.1:4322/", ORIGIN));
        assert!(!app_url("about:blank", ORIGIN));
        assert!(!app_url("not a url", ORIGIN));
        assert_eq!(external_url("https://example.com/a").as_deref(), Some("https://example.com/a"));
        assert_eq!(external_url("mailto:person@example.com").as_deref(), Some("mailto:person@example.com"));
        for raw in ["file:///etc/passwd", "javascript:alert(1)", "https://user:pass@example.com/", "https://user@example.com/", "nonsense"] {
            assert_eq!(external_url(raw), None, "{raw}");
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn the_data_root_is_the_apps_own_folder_unless_qa_names_an_absolute_one() {
        let support = Path::new("/Users/a/Library/Application Support");
        assert_eq!(data_root(None, support), support.join("foldCV Beta"));
        assert_eq!(data_root(Some(OsStr::new("relative/root")), support), support.join("foldCV Beta"));
        assert_eq!(data_root(Some(OsStr::new("")), support), support.join("foldCV Beta"));
        assert_eq!(data_root(Some(OsStr::new("/private/tmp/qa")), support), Path::new("/private/tmp/qa"));
    }

    #[cfg(windows)]
    #[test]
    fn the_data_root_is_the_apps_own_folder_unless_qa_names_a_drive_or_network_path() {
        let local = Path::new(r"C:\Users\a\AppData\Local");
        assert_eq!(data_root(None, local), local.join("foldCV Beta"));
        for relative in [r"relative\root", r"\no-drive", "C:no-root", ""] {
            assert_eq!(data_root(Some(OsStr::new(relative)), local), local.join("foldCV Beta"), "{relative}");
        }
        assert_eq!(data_root(Some(OsStr::new(r"D:\qa")), local), Path::new(r"D:\qa"));
        assert_eq!(data_root(Some(OsStr::new(r"\\server\share\qa")), local), Path::new(r"\\server\share\qa"));
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn the_helper_runs_from_the_bundle_with_the_system_path_only() {
        let command = helper_command(Path::new("/Applications/foldCV.app/Contents/Resources"), Path::new("/data/root"));
        assert_eq!(command.executable, Path::new("/Applications/foldCV.app/Contents/Resources/../Helpers/FoldCV Helper.app/Contents/MacOS/foldcv-helper"));
        assert_eq!(command.args, ["serve", "/data/root"]);
        let environment = helper_environment(|name| (name == "TMPDIR").then(|| "/var/folders/t/".into()), Path::new("/Users/a"));
        assert_eq!(environment, [("PATH".into(), "/usr/bin:/bin:/usr/sbin:/sbin".into()), ("HOME".into(), "/Users/a".into()),
            ("LANG".into(), "en_US.UTF-8".into()), ("TMPDIR".into(), "/var/folders/t/".into())]);
        assert_eq!(helper_environment(|_| Some("".into()), Path::new("/Users/a")).len(), 3);
    }

    #[cfg(windows)]
    #[test]
    fn the_helper_runs_the_embedded_python_with_the_system_path_only() {
        let command = helper_command(Path::new(r"C:\Apps\foldCV"), Path::new(r"C:\Users\a\AppData\Local\foldCV Beta"));
        assert_eq!(command.executable, Path::new(r"C:\Apps\foldCV\helper\python\python.exe"));
        assert_eq!(command.args, ["-X", "utf8", r"C:\Apps\foldCV\helper\app\packaging\helper_entry.py", "serve",
            r"C:\Users\a\AppData\Local\foldCV Beta"]);
        let user = [("SystemRoot", r"C:\Windows"), ("TEMP", r"C:\Users\a\Temp"), ("USERNAME", ""),
            ("PATH", r"C:\Python;C:\Windows"), ("PYTHONHOME", r"C:\Python")];
        let variable = |name: &str| user.iter().find(|(key, _)| *key == name).map(|(_, value)| OsString::from(value));
        assert_eq!(helper_environment(variable, Path::new(r"C:\Users\a")), [("SystemRoot".into(), r"C:\Windows".into()),
            ("TEMP".into(), r"C:\Users\a\Temp".into()),
            ("PATH".into(), r"C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem".into())]);
        // Without SystemRoot the helper still gets one: WINDIR's, else the usual folder.
        let windir = |name: &str| (name == "WINDIR").then(|| OsString::from(r"D:\Win"));
        assert_eq!(helper_environment(windir, Path::new(r"C:\Users\a")), [("WINDIR".into(), r"D:\Win".into()),
            ("SystemRoot".into(), r"D:\Win".into()), ("PATH".into(), r"D:\Win\System32;D:\Win;D:\Win\System32\Wbem".into())]);
        assert_eq!(helper_environment(|_| None, Path::new(r"C:\Users\a"))[0], ("SystemRoot".into(), r"C:\Windows".into()));
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn the_save_dialog_offers_the_name_the_page_asked_for() {
        let downloads = ["Иванов И.И. резюме.docx", "cv.docx", "notes"];
        let exists = |name: &str| downloads.contains(&name);
        let name = |target: &str| requested_name(&Path::new("/Users/a/Downloads").join(target), exists).unwrap();
        assert_eq!(name("Петров.docx"), "Петров.docx");
        assert_eq!(name("cv (2).docx"), "cv.docx");
        assert_eq!(name("Иванов И (1).И. резюме.docx"), "Иванов И.И. резюме.docx");
        assert_eq!(name("notes (1)"), "notes");
        // Not a counter of wry: no such file in Downloads, or not before the first dot.
        assert_eq!(name("report (1).docx"), "report (1).docx");
        assert_eq!(name("cv.v2 (1).docx"), "cv.v2 (1).docx");
    }

    #[cfg(windows)]
    #[test]
    fn the_save_dialog_offers_the_name_the_page_asked_for() {
        let downloads = ["Иванов И.И. резюме.docx", "cv.docx", "notes"];
        let exists = |name: &str| downloads.contains(&name);
        let name = |target: &str| requested_name(&Path::new(r"C:\Users\a\Downloads").join(target), exists).unwrap();
        assert_eq!(name("Петров.docx"), "Петров.docx");
        assert_eq!(name("cv (2).docx"), "cv.docx");
        assert_eq!(name("Иванов И.И. резюме (1).docx"), "Иванов И.И. резюме.docx");
        assert_eq!(name("notes (1)"), "notes");
        // Not a counter of Chromium: no such file in Downloads, or not before the extension.
        assert_eq!(name("report (1).docx"), "report (1).docx");
        assert_eq!(name("Иванов И (1).И. резюме.docx"), "Иванов И (1).И. резюме.docx");
    }
}

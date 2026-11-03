use std::ffi::{OsStr, OsString};
use std::path::{Path, PathBuf};

use tauri::Url;

// Its own folder, so the app runs next to the FoldCV Local builds and shows none of their data. The earlier Electron
// builds of macOS used the same one.
pub const DATA_FOLDER: &str = "foldCV Beta";

/// The helper executable and its arguments.
#[derive(Debug, PartialEq, Eq)]
pub struct HelperCommand {
    pub executable: PathBuf,
    pub args: Vec<OsString>,
}

/// FOLDCV_DESKTOP_ROOT for QA runs, else the app's folder in Application Support.
pub fn data_root(override_root: Option<&OsStr>, app_data: &Path) -> PathBuf {
    match override_root.map(Path::new) {
        Some(root) if root.is_absolute() => root.to_path_buf(),
        _ => app_data.join(DATA_FOLDER),
    }
}

/// `serve <root>` on the helper app inside the bundle.
pub fn helper_command(resources: &Path, root: &Path) -> HelperCommand {
    HelperCommand {
        executable: resources.join("../Helpers/FoldCV Helper.app/Contents/MacOS/foldcv-helper"),
        args: vec!["serve".into(), root.into()],
    }
}

/// The only variables the helper gets: PATH and PYTHON* of the user stay out.
pub fn helper_environment(temporary: Option<OsString>, home: &Path) -> Vec<(OsString, OsString)> {
    let mut environment: Vec<(OsString, OsString)> = vec![
        ("PATH".into(), "/usr/bin:/bin:/usr/sbin:/sbin".into()),
        ("HOME".into(), home.into()),
        ("LANG".into(), "en_US.UTF-8".into()),
    ];
    if let Some(temporary) = temporary.filter(|value| !value.is_empty()) {
        environment.push(("TMPDIR".into(), temporary));
    }
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

/// The file name the page asked for. When Downloads already holds it, WebKit's default target there carries a
/// counter that wry puts before the first dot: "base (n).ext".
pub fn requested_name(target: &Path, exists: impl Fn(&str) -> bool) -> Option<String> {
    let name = target.file_name()?.to_str()?;
    for (start, _) in name.match_indices(" (") {
        let rest = &name[start + 2..];
        let digits = rest.bytes().take_while(u8::is_ascii_digit).count();
        if digits == 0 || !rest[digits..].starts_with(')') {
            continue;
        }
        let original = format!("{}{}", &name[..start], &rest[digits + 1..]);
        if original.find('.').unwrap_or(original.len()) == start && exists(&original) {
            return Some(original);
        }
    }
    Some(name.to_string())
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

    #[test]
    fn the_data_root_is_the_apps_own_folder_unless_qa_names_an_absolute_one() {
        let support = Path::new("/Users/a/Library/Application Support");
        assert_eq!(data_root(None, support), support.join("foldCV Beta"));
        assert_eq!(data_root(Some(OsStr::new("relative/root")), support), support.join("foldCV Beta"));
        assert_eq!(data_root(Some(OsStr::new("")), support), support.join("foldCV Beta"));
        assert_eq!(data_root(Some(OsStr::new("/private/tmp/qa")), support), Path::new("/private/tmp/qa"));
    }

    #[test]
    fn the_helper_runs_from_the_bundle_with_the_system_path_only() {
        let command = helper_command(Path::new("/Applications/foldCV Beta.app/Contents/Resources"), Path::new("/data/root"));
        assert_eq!(command.executable, Path::new("/Applications/foldCV Beta.app/Contents/Resources/../Helpers/FoldCV Helper.app/Contents/MacOS/foldcv-helper"));
        assert_eq!(command.args, ["serve", "/data/root"]);
        let environment = helper_environment(Some("/var/folders/t/".into()), Path::new("/Users/a"));
        assert_eq!(environment, [("PATH".into(), "/usr/bin:/bin:/usr/sbin:/sbin".into()), ("HOME".into(), "/Users/a".into()),
            ("LANG".into(), "en_US.UTF-8".into()), ("TMPDIR".into(), "/var/folders/t/".into())]);
        assert_eq!(helper_environment(Some("".into()), Path::new("/Users/a")).len(), 3);
    }

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
}

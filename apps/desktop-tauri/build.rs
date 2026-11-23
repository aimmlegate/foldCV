fn main() {
    // The page's own command needs a permission of its own: the page is a remote origin (the local service).
    tauri_build::try_build(tauri_build::Attributes::new()
        .app_manifest(tauri_build::AppManifest::new().commands(&["native_paste"])))
        .expect("the Tauri build step");
}

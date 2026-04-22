// Layer-3 Tauri shell entry. Deliberately zero invoke_handler commands:
// the UI reaches Layer-1 over HTTP+SSE at 127.0.0.1:8765, never through
// Rust. The only Rust-side plugins are the updater (for check/install)
// and process (so the updater can restart the app after install).

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// 退出应用。托盘菜单的「退出 Tadado」走这里 —— 前端只调 `getCurrentWindow()`
/// 的话只会关掉窗口，常驻进程还在。
#[tauri::command]
fn app_exit(app: tauri::AppHandle) {
    app.exit(0);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_sql::Builder::default().build())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        // persisted-scope 必须排在拥有 scope 的插件之后。
        .plugin(tauri_plugin_persisted_scope::init())
        .invoke_handler(tauri::generate_handler![app_exit])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

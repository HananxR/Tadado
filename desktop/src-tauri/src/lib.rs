use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};
use tauri_plugin_fs::FsExt;

/// 退出应用。托盘菜单的「退出 Tadado」走这里 —— 前端只调 `getCurrentWindow()`
/// 的话只会关掉窗口，常驻进程还在。
#[tauri::command]
fn app_exit(app: tauri::AppHandle) {
    app.exit(0);
}

/// 把一条路径放进 fs 作用域，好让前端写它。
///
/// 导出走的是「另存为」对话框（前端 `@tauri-apps/plugin-dialog`），用户选哪就
/// 该写到哪。而 fs 插件的作用域默认是**空的**（`tauri.conf.json` 里没有
/// `plugins.fs.scope`），于是写用户刚选的那条路径会被 `path forbidden` 挡下 ——
/// 挡掉的正是用户自己点的位置。
///
/// 所以写之前先放这一条：**只放这一条、不放大整个目录**，进程退出即失效。
/// 换成在配置里开一片通配作用域（`$HOME/**` 之类）也能写，但那样就把「整个用户
/// 目录可写」永久挂在应用身上了，而这里要的只是「这一次选中的那个文件」。
#[tauri::command]
fn allow_save_path(app: tauri::AppHandle, path: String) -> Result<(), String> {
    app.fs_scope()
        .allow_file(&path)
        .map_err(|error| format!("无法写入 {path}：{error}"))
}

// ─────────────────────────────────────────────────────────────────────────────
// 系统托盘。常驻应用的第二入口：左键切换窗口显隐，右键出菜单。
//
// 托盘必须建在**进程启动时、且只建一次**。曾经的错误做法是由前端创建：每次
// webview 重载（dev 热更新、路由跳转、异常重载）都会再注册一个托盘，而 Rust
// 侧的旧图标不会被回收 —— 于是托盘里堆出一排几十个同名图标。
// ─────────────────────────────────────────────────────────────────────────────

const MAIN_WINDOW: &str = "main";

fn show_main_window(app: &tauri::AppHandle) {
    let Some(window) = app.get_webview_window(MAIN_WINDOW) else {
        return;
    };
    let _ = window.show();
    let _ = window.set_focus();
}

fn hide_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW) {
        let _ = window.hide();
    }
}

/// 以窗口的**真实可见性**为准：窗口可能被外部隐藏（Win+D 显示桌面、DWM 最小化），
/// 只信自己记的状态就会出现「点了没反应」。
fn toggle_main_window(app: &tauri::AppHandle) {
    let Some(window) = app.get_webview_window(MAIN_WINDOW) else {
        return;
    };
    let visible = window.is_visible().unwrap_or(false);
    if visible {
        hide_main_window(app);
    } else {
        show_main_window(app);
    }
}

fn build_tray(app: &tauri::AppHandle) -> Result<(), String> {
    let settings = MenuItemBuilder::with_id("tray-settings", "设置")
        .build(app)
        .map_err(|e| e.to_string())?;
    let show = MenuItemBuilder::with_id("tray-show", "显示窗口")
        .build(app)
        .map_err(|e| e.to_string())?;
    let quit = MenuItemBuilder::with_id("tray-quit", "退出 Tadado2")
        .build(app)
        .map_err(|e| e.to_string())?;

    // 三项并排、各占一行，不加分隔线：Windows 原生菜单里那条线自带 8–10px 的
    // 上下留白，插在中间会让相邻两项看着比别的松。
    //
    // 「新建任务」曾经在这里，撤了（2026-09-17）：点它只能把主窗口叫出来再弹一层
    // 浮层，用户要的是「只有那个新建框、后面不出主界面」—— 那得另开一个窗口，
    // 不值当。记一条任务走热键唤起主窗口，本来也就一步。
    let menu = MenuBuilder::new(app)
        .items(&[&settings, &show, &quit])
        .build()
        .map_err(|e| e.to_string())?;

    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or_else(|| "default_window_icon() 为空，无法设置托盘图标".to_string())?;

    // 固定 id：重复调用 build 时如果 id 冲突会直接报错，等于把「托盘重复」从
    // 视觉问题降级成启动期的显式失败。
    TrayIconBuilder::with_id("tadado-tray")
        .icon(icon)
        .tooltip("Tadado2")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                toggle_main_window(tray.app_handle());
            }
        })
        .on_menu_event(move |app, event| match event.id.as_ref() {
            // 「设置」的真正动作在**前端**（要开抽屉），Rust 这边只负责把窗口叫出来，
            // 再发一条事件让前端去做。事件名统一叫 "tray"，payload 是动作名 ——
            // 以后再加这类「前端才知道怎么做」的项，两边各加一个分支即可。
            "tray-settings" => {
                show_main_window(app);
                let _ = app.emit("tray", "settings");
            }
            "tray-show" => show_main_window(app),
            "tray-quit" => app.exit(0),
            _ => {}
        })
        .build(app)
        .map_err(|e| e.to_string())?;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // 第二个实例的命令行/工作目录交给首个实例处理，同时把窗口拉回来。
        // 没有它，反复双击 exe 会各起一个进程、各挂一个托盘图标。
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_sql::Builder::default().build())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        // 开机自启动（设置面板里的那一行）。开关本身由插件写注册表，
        // 前端只调 enable / disable / isEnabled。
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        // persisted-scope 必须排在拥有 scope 的插件之后。
        .plugin(tauri_plugin_persisted_scope::init())
        .invoke_handler(tauri::generate_handler![app_exit, allow_save_path])
        .setup(|app| build_tray(app.handle()).map_err(|e| e.into()))
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

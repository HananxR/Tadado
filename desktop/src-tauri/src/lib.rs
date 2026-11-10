use std::str::FromStr;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};
use tauri_plugin_fs::FsExt;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

mod help;

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
// 系统托盘与全局热键。常驻应用的第二入口：左键切换窗口显隐，右键出菜单。
//
// 托盘必须建在**进程启动时、且只建一次**。曾经的错误做法是由前端创建：每次
// webview 重载（dev 热更新、路由跳转、异常重载）都会再注册一个托盘，而 Rust
// 侧的旧图标不会被回收 —— 于是托盘里堆出一排几十个同名图标。
//
// **这一层是「窗口能不能被叫回来」的唯一实现**：热键、托盘左键、托盘菜单
// 「显示窗口」、单实例第二次启动，全走下面这几个函数。曾经热键注册在前端
// （JS 的 register，回调要绕 webview 的 IPC 通道才回到 JS）—— 跨日续跑重载
// webview 后，通道没了而系统层的热键还挂着，按键就是没人接；而最小化的窗口
// 又会被「可见性」判定当成「已经开着」，于是按热键把它藏掉、再按一次只到
// 任务栏。症状是「有时候唤不回来 / 只到任务栏，还得再点一次任务栏」。
// ─────────────────────────────────────────────────────────────────────────────

const MAIN_WINDOW: &str = "main";

/// 全局热键。
///
/// **只有这一处定义**：注册用它，界面展示也用它（`hotkey_info` 命令把同一份
/// 字符串交给前端）。以前前端另有一份写死的 "Ctrl+Shift+Space" —— 两处写死
/// 必然漂移，漂了就是「按的键和看到的键对不上」。
///
/// 写法用 global-hotkey 认得的别名（"Ctrl" 与 "Control" 等价），所以同一份
/// 字符串既拿得去注册、也能直接显示。
const HOTKEY: &str = "Ctrl+Shift+Space";

/// 连按去抖：手抖连点、某些键盘在按住时重复上报，150ms 内的重复触发只算一次。
const HOTKEY_DEBOUNCE: Duration = Duration::from_millis(150);

/// 一次「唤起」该做的动作。
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum WindowAction {
    /// 从最小化拉回来（还原）。
    Restore,
    /// 显示出来。
    Show,
    /// 收起（藏到托盘）。
    Hide,
}

/// 判定该做什么。
///
/// 规则与前端 `desktop/src/shell/windowState.ts` 一致（那边有断言钉着，见
/// `desktop/e2e/window-state.mjs`），**两边必须同时改** —— 规则漂了就是
/// 「热键能唤回、托盘唤不回」这种最难查的毛病。
///
/// **最小化优先**：Windows 上最小化的窗口**仍然算可见**（IsWindowVisible 对
/// 最小化窗口返回 TRUE）。只看 visible 的话，最小化会被当成「已经开着」→
/// 按热键反而把窗口藏掉；再按一次走 show()，而 show() 是 SW_SHOW、**不还原
/// 最小化的窗口**（还原是 SW_RESTORE）—— 症状正是用户报的「只到任务栏，还要
/// 再点一次任务栏」。
fn decide_window_action(visible: bool, minimized: bool) -> WindowAction {
    if minimized {
        return WindowAction::Restore;
    }
    if visible {
        return WindowAction::Hide;
    }
    WindowAction::Show
}

/// 把主窗口叫到前台：显示 → 还原 → 聚焦。
///
/// **顺序不能颠倒**，每一步都有坑：
///   · 先 show：此刻窗口可能是隐藏的，不先显示就还原，等于还原一个看不见的窗口；
///   · 再 unminimize：Windows 的 show() 是 SW_SHOW、**不还原最小化的窗口**
///     （还原是 SW_RESTORE）—— 少了这一步，症状就是「只到任务栏」；
///   · 最后 set_focus：tao 的 set_focus 只在「可见 + 未最小化 + 当前不是前台」
///     时才真的去前置窗口，顺序错了它就是个空操作。
///
/// 三步都是**主线程内联执行**的（tauri 的窗口消息在主线程上就地处理），所以
/// 这里是同步的：按完热键，窗口已经在了。
fn present_main_window(app: &tauri::AppHandle) {
    let Some(window) = app.get_webview_window(MAIN_WINDOW) else {
        return;
    };

    let _ = window.show();
    let _ = window.unminimize();
    let _ = window.set_focus();

    // 前台锁兜底：Windows 的 SetForegroundWindow 受前台锁限制，不是任何时候都
    // 准（tao 内部会合成一次 Alt 按键去「偷」前台权限，但仍有失手的时候）。
    // 失手的表现是「窗口出来了却不在最前面」，用户还得自己去点一下。
    // 判据用「窗口此刻是不是前台窗口」—— 不是就说明前置没生效，用「置顶一帧
    // 再取消」强行把它拉到最前（代价是可能有一帧闪动）。
    if window.is_focused().unwrap_or(false) {
        return;
    }
    let _ = window.set_always_on_top(true);
    // 置顶与取消**不能挨太近**：tao 的 SetWindowPos 是异步投递的
    // （SWP_ASYNCWINDOWPOS），两个改动会一起落地，等于没抬过。所以让「置顶」真
    // 的落到 Z 序上，隔一帧再取消。
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(60));
        if let Some(window) = app.get_webview_window(MAIN_WINDOW) {
            let _ = window.set_always_on_top(false);
        }
    });
    let _ = window.set_focus();
}

fn hide_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW) {
        let _ = window.hide();
    }
}

/// 切换窗口显隐。
///
/// 以窗口的**真实状态**为准，不能只信自己记的那份：窗口可能被外部隐藏
/// （Win+D 显示桌面、DWM 最小化），状态不同步的症状就是「按热键没反应」。
fn toggle_main_window(app: &tauri::AppHandle) {
    let Some(window) = app.get_webview_window(MAIN_WINDOW) else {
        return;
    };
    let visible = window.is_visible().unwrap_or(false);
    let minimized = window.is_minimized().unwrap_or(false);
    match decide_window_action(visible, minimized) {
        WindowAction::Restore | WindowAction::Show => present_main_window(app),
        WindowAction::Hide => hide_main_window(app),
    }
}

/// 注册全局热键。
///
/// **在原生侧注册**，不经 webview：跨日续跑（见 `desktop/src/shell/rollover.ts`）
/// 会重载界面，重载后前端的回调通道已经没了 —— 那时系统层的热键还挂着却没人
/// 接，按键就是没反应。放在这里，界面活着死了都不影响唤回。
fn build_hotkey(app: &tauri::AppHandle) -> Result<(), String> {
    let shortcut = Shortcut::from_str(HOTKEY).map_err(|error| error.to_string())?;

    // 上次触发的时间：用来挡掉连按。
    let last_fired: Arc<Mutex<Option<Instant>>> = Arc::new(Mutex::new(None));

    app.global_shortcut()
        .on_shortcut(shortcut, move |app, _shortcut, event| {
            // 只认「按下」。「松开」是 global-hotkey 在 Windows 侧另起一个线程
            // 轮询键盘补发过来的（见它的 windows 实现），不处理。
            if event.state() != ShortcutState::Pressed {
                return;
            }

            {
                let mut last = last_fired.lock().unwrap_or_else(|error| error.into_inner());
                let now = Instant::now();
                if let Some(previous) = *last {
                    if now.duration_since(previous) < HOTKEY_DEBOUNCE {
                        return;
                    }
                }
                *last = Some(now);
            }

            toggle_main_window(app);
        })
        .map_err(|error| error.to_string())
}

/// 给前端的热键信息。
///
/// 加速键**只有 Rust 这一处定义**（`HOTKEY`），前端从这儿取 —— 注册用的和
/// 展示用的是同一份字符串。
#[derive(serde::Serialize)]
pub struct HotkeyInfo {
    /// 组合键本身（注册用的真值，也就是展示用的那一份）。
    pub accelerator: String,
    /// 标题栏那几枚键帽（["Ctrl", "Shift", "Space"]）。
    pub keys: Vec<String>,
    /// 真的注册上了吗（被别的应用占用 → false）。
    pub registered: bool,
}

#[tauri::command]
fn hotkey_info(app: tauri::AppHandle) -> HotkeyInfo {
    let registered = Shortcut::from_str(HOTKEY)
        .ok()
        .map(|shortcut| app.global_shortcut().is_registered(shortcut))
        .unwrap_or(false);

    HotkeyInfo {
        accelerator: HOTKEY.to_string(),
        keys: HOTKEY.split('+').map(str::to_string).collect(),
        registered,
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
                present_main_window(app);
                let _ = app.emit("tray", "settings");
            }
            // 「显示窗口」是**无条件叫到前台**，不是「切换」：窗口此刻最小化着，
            // 用户点它要的是「拿回来」，不是「藏起来」。
            "tray-show" => present_main_window(app),
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
            present_main_window(app);
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
        // 应用内更新（2026-10-17 起）：检查 / 下载 / 验签 / 安装都交给官方插件。
        // 端点在 tauri.conf.json 的 `plugins.updater.endpoints`，公钥也在那儿 ——
        // 公钥写错或换成另一个，已装的旧版就会拒绝新包（这是签名机制的意义）。
        .plugin(tauri_plugin_updater::Builder::new().build())
        // persisted-scope 必须排在拥有 scope 的插件之后。
        .plugin(tauri_plugin_persisted_scope::init())
        .invoke_handler(tauri::generate_handler![
            app_exit,
            allow_save_path,
            hotkey_info,
            help::open_help
        ])
        .setup(|app| {
            build_tray(app.handle())
                .map_err(|error| -> Box<dyn std::error::Error> { error.into() })?;

            // 热键注册失败**不拦启动**：托盘还在，窗口照样能从托盘叫出来。
            // 但必须让用户知道 —— 前端启动自检（`shell/main.ts`）读 hotkey_info，
            // registered=false 时会弹一句「热键不可用」。
            if let Err(error) = build_hotkey(app.handle()) {
                eprintln!(
                    "[tadado] 全局热键 {HOTKEY} 注册失败（可能已被其他应用占用）：{error}"
                );
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 三态判定：与前端 `shell/windowState.ts` 的规则逐条对应。
    ///
    /// 这几条断言是那个 bug 的护栏 —— 规则一改（「最小化优先」写成「可见优先」），
    /// 这里立刻红。
    #[test]
    fn hidden_window_shows() {
        assert_eq!(decide_window_action(false, false), WindowAction::Show);
    }

    #[test]
    fn minimized_window_restores() {
        assert_eq!(decide_window_action(true, true), WindowAction::Restore);
    }

    #[test]
    fn visible_window_hides() {
        assert_eq!(decide_window_action(true, false), WindowAction::Hide);
    }

    #[test]
    fn minimized_wins_over_hidden() {
        assert_eq!(decide_window_action(false, true), WindowAction::Restore);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 本地帮助文档：把说明页**嵌进二进制**，打开时落盘到缓存目录，再交给系统默认
// 浏览器。
//
// 为什么不走 `bundle.resources`：便携版交付的是一个裸 `Tadado2.exe`，安装目录
// 里没有任何附属文件。资源一旦只在安装包里，便携版点「帮助文档」就会 404。
// `include_str!` / `include_bytes!` 让 HTML 与截图成为可执行文件的一部分，
// 安装版和便携版行为完全一致。
//
// 为什么落盘而不是 `data:` URL：截图是 JPEG，塞进 data URL 会让单页变成几 MB
// 的超长地址，浏览器地址栏与「另存为」都会很难看。落盘一次、按版本隔离缓存，
// 升级后自动换新，用户也不用管清理。
// ─────────────────────────────────────────────────────────────────────────────

use std::fs;
use std::path::{Path, PathBuf};

use tauri::Manager;

/// 帮助文档唯一源文件（与 `resources/help/index.html` 同一份，编译期嵌入）。
const HELP_HTML: &str = include_str!("../resources/help/index.html");

/// 文档里引用的截图。文件名与 HTML 中 `<img src="img/...">` 必须一致。
const HELP_IMAGES: &[(&str, &[u8])] = &[
    ("overview.jpg", include_bytes!("../resources/help/img/overview.jpg")),
    ("tasks.jpg", include_bytes!("../resources/help/img/tasks.jpg")),
    ("drawer.jpg", include_bytes!("../resources/help/img/drawer.jpg")),
    ("graph.jpg", include_bytes!("../resources/help/img/graph.jpg")),
    ("activity.jpg", include_bytes!("../resources/help/img/activity.jpg")),
    ("manage.jpg", include_bytes!("../resources/help/img/manage.jpg")),
    ("task-form.jpg", include_bytes!("../resources/help/img/task-form.jpg")),
    ("settings-about.jpg", include_bytes!("../resources/help/img/settings-about.jpg")),
];

/// 版本号占位符：渲染时替换成当前版本，避免文档写着旧号。
const VERSION_PLACEHOLDER: &str = "{{VERSION}}";

/// 写完标记：有它就不再重复写盘（图片约 1–1.5 MB，没必要每次点都写）。
const READY_MARKER: &str = ".ready";

/// 打开本地帮助文档。失败返回可读原因，由前端 toast 出去。
#[tauri::command]
pub fn open_help(app: tauri::AppHandle) -> Result<(), String> {
    let version = app.package_info().version.to_string();
    let dir = help_dir(&app, &version)?;
    let index = dir.join("index.html");

    write_assets(&dir, &version)?;

    // 交给系统默认浏览器：HTML 里没有脚本、没有外部资源，离线也能完整显示。
    tauri_plugin_opener::open_path(&index, None::<&str>)
        .map_err(|error| format!("无法打开操作说明：{error}"))
}

/// 缓存目录按版本隔离：升级后路径变了，旧文件自然被忽略（系统会择机清理）。
fn help_dir(app: &tauri::AppHandle, version: &str) -> Result<PathBuf, String> {
    app.path()
        .app_cache_dir()
        .map(|dir| dir.join("help").join(version))
        .map_err(|error| format!("无法定位缓存目录：{error}"))
}

/// 首次打开时把嵌入的资源写出来；已写过就直接返回。
///
/// 写失败要**明确报错**：静默失败会表现为「点了没反应」，用户只会反复点。
fn write_assets(dir: &Path, version: &str) -> Result<(), String> {
    let index = dir.join("index.html");
    let ready = dir.join(READY_MARKER);
    if ready.exists() && index.exists() {
        return Ok(());
    }

    fs::create_dir_all(dir).map_err(|error| format!("无法创建帮助目录：{error}"))?;

    let html = HELP_HTML.replace(VERSION_PLACEHOLDER, version);
    fs::write(&index, html).map_err(|error| format!("无法写入操作说明：{error}"))?;

    let img_dir = dir.join("img");
    fs::create_dir_all(&img_dir).map_err(|error| format!("无法创建截图目录：{error}"))?;
    for (name, bytes) in HELP_IMAGES {
        fs::write(img_dir.join(name), bytes)
            .map_err(|error| format!("无法写入截图 {name}：{error}"))?;
    }

    fs::write(&ready, version).map_err(|error| format!("无法写入帮助标记：{error}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_dir() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|span| span.as_nanos())
            .unwrap_or_default();
        std::env::temp_dir().join(format!("tadado-help-test-{stamp}"))
    }

    /// 嵌入的资源要能原样写出来，版本占位符要真的被替换；第二次打开走 `.ready`，
    /// 不再覆盖已经写好的文件。
    #[test]
    fn writes_embedded_help_once() {
        let dir = temp_dir();
        write_assets(&dir, "9.9.9").expect("首次写入应当成功");

        let html = fs::read_to_string(dir.join("index.html")).expect("index.html 应当存在");
        assert!(html.contains("v9.9.9"), "版本占位符应当被替换");
        assert!(!html.contains(VERSION_PLACEHOLDER), "占位符不该残留");

        for &(name, bytes) in HELP_IMAGES {
            let written = fs::read(dir.join("img").join(name)).expect("截图应当存在");
            assert_eq!(written.len(), bytes.len(), "{name} 写出来不完整");
        }

        // 第二次：有 .ready 就跳过，别把用户/浏览器改动过的那份又覆盖掉
        fs::write(dir.join("index.html"), "sentinel").expect("写哨兵失败");
        write_assets(&dir, "9.9.9").expect("第二次写入应当成功");
        assert_eq!(
            fs::read_to_string(dir.join("index.html")).expect("读回失败"),
            "sentinel",
            "已写过就不该重写",
        );

        fs::remove_dir_all(&dir).ok();
    }
}

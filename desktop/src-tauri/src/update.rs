// ─────────────────────────────────────────────────────────────────────────────
// 检查更新：问一句「GitHub 上最新的是哪一版」，仅此而已 —— **不下载、不安装**。
//
// 为什么不用官方的 tauri-plugin-updater（自动更新）：它要求生成一对签名密钥、
// 把公钥写进 tauri.conf.json、每次发布用私钥签名产物、再额外上传一份 latest.json。
// 本仓库的发布是本地手动的（没有 CI），为了省用户点一次「下载」而背上整条链路
// 不划算。轻量检查 + 跳转下载页，同样能让用户知道自己是不是旧版。
//
// 为什么阿里云盘不能当检测源：阿里云盘没有官方 API，分享页是 JS 渲染的。旧版
// （v0.x PySide6）所谓的「阿里云优先检测」是调 **作者本机** 的 aliyunpan CLI 去
// `ls /Tadado` 解析文件名 —— 普通用户机器上没有这个 CLI，于是它每次都悄悄回落到
// GitHub。别把这个做法搬过来：阿里云盘只作下载渠道（国内可达），检测只走 Releases。
//
// 错误一律返回**稳定错误码**（network / rate_limit / http / parse），由前端翻译成
// 人话 —— 原始错误文本（超时栈、状态码细节）对用户没有意义，也不该混进界面。
// ─────────────────────────────────────────────────────────────────────────────

use std::time::Duration;

use reqwest::header::ACCEPT;
use serde::{Deserialize, Serialize};

/// 「最新的一条正式发布」。GitHub 的 `latest` 天然排除草稿与预发布。
const RELEASES_API: &str = "https://api.github.com/repos/HananxR/Tadado/releases/latest";

/// GitHub 的 API **强制要求** User-Agent，缺了直接 403；顺带标出请求来自谁。
const USER_AGENT: &str = "Tadado2-UpdateCheck";

/// 10 秒。检查更新是顺手点一下的事，让用户对着「检查中…」等半分钟，
/// 不如直接告诉他这次没查成、过会儿再试。
const TIMEOUT: Duration = Duration::from_secs(10);

/// 更新说明只留摘要：Release 正文常是整篇 markdown，几百行塞进 420px 的设置抽屉
/// 既读不完也读不懂。目前界面只用版本号与发布日期，摘要留给后续可能的信息卡。
const NOTES_LIMIT: usize = 500;

const ERR_NETWORK: &str = "network";
const ERR_RATE_LIMIT: &str = "rate_limit";
const ERR_HTTP: &str = "http";
const ERR_PARSE: &str = "parse";

#[derive(Serialize)]
pub struct UpdateInfo {
    /// 本地版本（`package_info`，纯数字，形如 `1.0.0`）。
    pub current: String,
    /// Releases 上的最新版本（已去掉 `v` 前缀）；一条发布都没有时为 `None`。
    pub latest: Option<String>,
    /// 结论由**这里**算：版本比较只留一处，前端拿到结果直接渲染。
    pub has_update: bool,
    pub release_url: String,
    pub published_at: String,
    pub notes: String,
}

/// GitHub Release 里我们真正用得到的几个字段，其余不解析。
#[derive(Deserialize)]
struct Release {
    tag_name: Option<String>,
    html_url: Option<String>,
    published_at: Option<String>,
    body: Option<String>,
}

#[tauri::command]
pub async fn check_update(app: tauri::AppHandle) -> Result<UpdateInfo, String> {
    let current = app.package_info().version.to_string();

    let client = reqwest::Client::builder()
        .user_agent(USER_AGENT)
        .timeout(TIMEOUT)
        .build()
        .map_err(|_| ERR_NETWORK.to_string())?;

    let response = client
        .get(RELEASES_API)
        .header(ACCEPT, "application/vnd.github+json")
        .send()
        .await
        .map_err(|_| ERR_NETWORK.to_string())?;

    let status = response.status().as_u16();

    // 仓库还没发过 Release（或发布被撤了）：这不是故障，只是没有可比的东西。
    if status == 404 {
        return Ok(no_release(current));
    }
    // 未认证的 API 配额是每小时 60 次，用光是 403；429 是明确限流。对用户来说
    // 两者是同一件事：「被挡了，过一会儿再试」，不再细分。
    if status == 403 || status == 429 {
        return Err(ERR_RATE_LIMIT.to_string());
    }
    if !(200..300).contains(&status) {
        return Err(ERR_HTTP.to_string());
    }

    let release: Release = response.json().await.map_err(|_| ERR_PARSE.to_string())?;

    // 认不出 tag 说明仓库的发布命名变了，这时「报解析失败」比「假装已是最新」诚实：
    // 前者会被人发现并修，后者会安静地骗下去。
    let tag = release.tag_name.unwrap_or_default();
    let Some(latest) = parse_version(&tag) else {
        return Err(ERR_PARSE.to_string());
    };

    // 本地版本解析不出来（理论上不会）时按「已是最新」处理：**不误报**优先于
    // 不漏报 —— 弹一个下载链接让用户白跑一趟，比晚几天告知更伤。
    let has_update = parse_version(&current).is_some_and(|current| is_newer(&latest, &current));

    Ok(UpdateInfo {
        current,
        latest: Some(join_version(&latest)),
        has_update,
        release_url: release.html_url.unwrap_or_default(),
        published_at: release.published_at.unwrap_or_default(),
        notes: truncate(&release.body.unwrap_or_default(), NOTES_LIMIT),
    })
}

fn no_release(current: String) -> UpdateInfo {
    UpdateInfo {
        current,
        latest: None,
        has_update: false,
        release_url: String::new(),
        published_at: String::new(),
        notes: String::new(),
    }
}

/// 把 `v1.0.0` / `1.0.2.3` / `1.0` 解析成数字段。
///
/// **必须容忍 3 段与 4 段**：v0.x 时代踩过这个坑（CHANGELOG 0.1.2.4）—— 那时按 3 段
/// 截断，`0.1.2.4` 被读成 `0.1.2`，于是「明明发了新版却说自己是最新的」。
fn parse_version(text: &str) -> Option<Vec<u64>> {
    let body = text.trim().trim_start_matches(['v', 'V']);
    let head: String = body
        .chars()
        .take_while(|c| c.is_ascii_digit() || *c == '.')
        .collect();
    let parts: Vec<u64> = head.split('.').map(str::parse).collect::<Result<_, _>>().ok()?;
    // 至少两段才算版本号：`2026` 这种单个数字多半是日期之类，不是版本。
    (parts.len() >= 2).then_some(parts)
}

/// 逐段比较，**缺的段按 0 补**：于是 `1.0.0` 与 `1.0.0.0` 相等，
/// `1.0.2.3` 大于 `1.0.2`。
fn is_newer(latest: &[u64], current: &[u64]) -> bool {
    for index in 0..latest.len().max(current.len()) {
        let a = latest.get(index).copied().unwrap_or(0);
        let b = current.get(index).copied().unwrap_or(0);
        if a != b {
            return a > b;
        }
    }
    false
}

/// 数字段还原成版本号：`1.0.0`。
fn join_version(parts: &[u64]) -> String {
    parts.iter().map(u64::to_string).collect::<Vec<_>>().join(".")
}

/// 按**字符**截断（中英混排时按字节切会把汉字劈成两半），超长才加省略号。
fn truncate(text: &str, limit: usize) -> String {
    let mut out: String = text.chars().take(limit).collect();
    if text.chars().count() > limit {
        out.push('…');
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_three_and_four_segment_versions() {
        assert_eq!(parse_version("1.0.0"), Some(vec![1, 0, 0]));
        assert_eq!(parse_version("v1.0.2.3"), Some(vec![1, 0, 2, 3]));
        assert_eq!(parse_version(" V1.2 "), Some(vec![1, 2]));
    }

    #[test]
    fn rejects_what_is_not_a_version() {
        assert_eq!(parse_version(""), None);
        assert_eq!(parse_version("v"), None);
        assert_eq!(parse_version("latest"), None);
        // 单个数字多半是日期，不是版本
        assert_eq!(parse_version("2026"), None);
        // 段里有非数字就不是版本
        assert_eq!(parse_version("1.x.0"), None);
    }

    #[test]
    fn compares_with_missing_segments_as_zero() {
        assert!(is_newer(&[1, 1, 0], &[1, 0, 0]));
        assert!(is_newer(&[1, 0, 2, 3], &[1, 0, 2]));
        // 四段与三段相等时**不算**有新版本 —— 否则每次检查都会提示同一版
        assert!(!is_newer(&[1, 0, 0, 0], &[1, 0, 0]));
        assert!(!is_newer(&[1, 0, 2, 3], &[1, 0, 2, 3]));
        assert!(!is_newer(&[1, 0, 1], &[1, 0, 2]));
    }

    #[test]
    fn truncates_on_char_boundaries() {
        assert_eq!(truncate("abc", 5), "abc");
        assert_eq!(truncate("更新说明", 2), "更新…");
    }
}

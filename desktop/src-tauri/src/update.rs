// ─────────────────────────────────────────────────────────────────────────────
// 检查更新：只回答一个问题 —— **有没有比当前更新的版本**。不下载、不安装。
//
// 主路径是 `GET /releases/latest` 的 **302 跳转**：GitHub 会把最新正式发布的页面
// 重定向到 `/releases/tag/<tag>`，我们只读 `Location` 里的 tag，不读响应体。
// 这样常规点击**不消耗 API 配额**（未认证 API 每小时只有 60 次），也不依赖
// `api.github.com` 在国内容易被墙的那条线路。
//
// 只有在**确实发现新版本**时，才顺手问一次 API 拿发布日期与说明；补不到也
// 不影响结论 —— 下载链接可以从 tag 拼出来，日期与说明留空即可。
//
// 为什么不用官方的 tauri-plugin-updater（自动更新）：它要求生成一对签名密钥、
// 把公钥写进 tauri.conf.json、每次发布用私钥签名产物、再额外上传一份 latest.json。
// 本仓库的发布是本地手动的（没有 CI），为了省用户点一次「下载」而背上整条链路
// 不划算。
//
// 结论只有两种：有新版 / 没有查到。网络失败、超时、被限流、GitHub 改了结构，
// 一律算「没有查到」—— 更新检查是个顺手的附加动作，不该给用户端出一屏错误码。
// ─────────────────────────────────────────────────────────────────────────────

use std::time::Duration;

use reqwest::header::{ACCEPT, LOCATION};
use reqwest::redirect::Policy;
use serde::{Deserialize, Serialize};

/// 「最新的一条正式发布」的**网页**地址。GitHub 的 `latest` 天然排除草稿与预发布。
const RELEASES_LATEST_PAGE: &str = "https://github.com/HananxR/Tadado/releases/latest";

/// 具体某个 tag 的发布页。详情补不到时用它拼出下载链接。
const RELEASES_TAG_PAGE: &str = "https://github.com/HananxR/Tadado/releases/tag/";

/// `Location` 里唯一认得的路径前缀：只认自家仓库的 tag 页。
const TAG_PATH_PREFIX: &str = "HananxR/Tadado/releases/tag/";

/// 补详情用的 API（只有发现新版本才会走到）。
const RELEASES_API: &str = "https://api.github.com/repos/HananxR/Tadado/releases/latest";

/// GitHub 的 API **强制要求** User-Agent，缺了直接 403；顺带标出请求来自谁。
const USER_AGENT: &str = "Tadado2-UpdateCheck";

/// 重定向这一跳给 12 秒：只取响应头，正常是几百毫秒的事，留足代理与慢网。
const REDIRECT_TIMEOUT: Duration = Duration::from_secs(12);

/// 补详情再给 8 秒。两次最坏 12 + 8 = 20 秒，前端按这个预算说「检查中…」。
const API_TIMEOUT: Duration = Duration::from_secs(8);

/// 更新说明只留摘要：Release 正文常是整篇 markdown，几百行塞进 420px 的设置抽屉
/// 既读不完也读不懂。目前界面只用版本号与发布日期，摘要留给后续可能的信息卡。
const NOTES_LIMIT: usize = 500;

#[derive(Serialize)]
pub struct UpdateInfo {
    /// 本地版本（`package_info`，纯数字，形如 `1.0.1`）。
    pub current: String,
    /// 最新版本（已去掉 `v` 前缀）；没有查到新版本或请求失败时为 `None`。
    pub latest: Option<String>,
    /// 结论由**这里**算：版本比较只留一处，前端拿到结果直接渲染。
    pub has_update: bool,
    pub release_url: String,
    pub published_at: String,
    pub notes: String,
}

impl UpdateInfo {
    /// 「没有查到新版本」。这是除「有新版」之外唯一的出口。
    fn none(current: String) -> Self {
        Self {
            current,
            latest: None,
            has_update: false,
            release_url: String::new(),
            published_at: String::new(),
            notes: String::new(),
        }
    }
}

/// GitHub Release 里我们真正用得到的几个字段，其余不解析。
#[derive(Deserialize)]
struct Release {
    html_url: Option<String>,
    published_at: Option<String>,
    body: Option<String>,
}

/// 检查更新。**不抛错**：任何异常都收敛成「没有查到新版本」，前端只有两种文案。
#[tauri::command]
pub async fn check_update(app: tauri::AppHandle) -> UpdateInfo {
    let current = app.package_info().version.to_string();

    let Some(latest) = latest_tag(&current).await else {
        return UpdateInfo::none(current);
    };

    let details = fetch_details().await;
    let release_url = details
        .as_ref()
        .and_then(|release| release.html_url.clone())
        .filter(|url| url.starts_with("http"))
        .unwrap_or_else(|| format!("{RELEASES_TAG_PAGE}v{latest}"));
    let published_at = details
        .as_ref()
        .and_then(|release| release.published_at.clone())
        .unwrap_or_default();
    let notes = details
        .map(|release| truncate(&release.body.unwrap_or_default(), NOTES_LIMIT))
        .unwrap_or_default();

    UpdateInfo {
        current,
        latest: Some(latest),
        has_update: true,
        release_url,
        published_at,
        notes,
    }
}

/// 读 `releases/latest` 的 302，把 tag 解析成版本号；比当前版本新才返回。
///
/// 不跟随重定向（`Policy::none()`）：只要第一跳的 `Location`，避免被带去登录页
/// 或其它站点，也省掉下载整页 HTML。3xx 之外的任何情况都算「没查到」。
async fn latest_tag(current: &str) -> Option<String> {
    let client = reqwest::Client::builder()
        .user_agent(USER_AGENT)
        .timeout(REDIRECT_TIMEOUT)
        .redirect(Policy::none())
        .build()
        .ok()?;

    let response = client.get(RELEASES_LATEST_PAGE).send().await.ok()?;
    if !response.status().is_redirection() {
        return None;
    }
    let location = response.headers().get(LOCATION)?.to_str().ok()?;

    let tag = tag_from_location(location)?;
    let latest = parse_version(&tag)?;
    // 本地版本解析不出来（理论上不会）时按「已是最新」处理：**不误报**优先于
    // 不漏报 —— 弹一个下载链接让用户白跑一趟，比晚几天告知更伤。
    let current = parse_version(current)?;
    is_newer(&latest, &current).then(|| join_version(&latest))
}

/// 补发布日期 / 说明 / 精确链接。**失败一律吞掉**：`has_update` 已经定了，
/// 这些只是让提示更好看，不该把「有新版」变成「检查失败」。
async fn fetch_details() -> Option<Release> {
    let client = reqwest::Client::builder()
        .user_agent(USER_AGENT)
        .timeout(API_TIMEOUT)
        .build()
        .ok()?;

    let response = client
        .get(RELEASES_API)
        .header(ACCEPT, "application/vnd.github+json")
        .send()
        .await
        .ok()?;

    if !response.status().is_success() {
        return None;
    }

    response.json::<Release>().await.ok()
}

/// 从 `Location` 头里取出 tag。
///
/// 只认 `https://github.com/HananxR/Tadado/releases/tag/<tag>`；去掉 `?` / `#`
/// 与首尾斜杠，tag 里不允许再有斜杠（多段路径不是 tag）。其余一律 `None`。
fn tag_from_location(location: &str) -> Option<String> {
    let rest = location
        .trim()
        .strip_prefix("https://github.com/")
        .or_else(|| location.trim().strip_prefix("http://github.com/"))?;
    let rest = rest.split(['?', '#']).next()?;
    let tag = rest.trim_end_matches('/').strip_prefix(TAG_PATH_PREFIX)?;
    let tag = tag.trim_matches('/');
    (!tag.is_empty() && !tag.contains('/')).then(|| tag.to_string())
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
    fn reads_tag_from_own_release_location() {
        assert_eq!(
            tag_from_location("https://github.com/HananxR/Tadado/releases/tag/v1.0.2"),
            Some("v1.0.2".to_string())
        );
        // 尾斜杠、查询串、片段都要吃掉
        assert_eq!(
            tag_from_location("https://github.com/HananxR/Tadado/releases/tag/v1.0.2/?from=x#y"),
            Some("v1.0.2".to_string())
        );
    }

    #[test]
    fn ignores_foreign_or_unexpected_locations() {
        // 不是自家仓库
        assert_eq!(
            tag_from_location("https://github.com/other/repo/releases/tag/v1.0.2"),
            None
        );
        // 不是 tag 页
        assert_eq!(
            tag_from_location("https://github.com/HananxR/Tadado/releases"),
            None
        );
        // 别的站点
        assert_eq!(
            tag_from_location("https://example.com/HananxR/Tadado/releases/tag/v1.0.2"),
            None
        );
        // 空 tag
        assert_eq!(
            tag_from_location("https://github.com/HananxR/Tadado/releases/tag/"),
            None
        );
        // 多段路径不是 tag
        assert_eq!(
            tag_from_location("https://github.com/HananxR/Tadado/releases/tag/a/b"),
            None
        );
        assert_eq!(tag_from_location(""), None);
    }

    #[test]
    fn truncates_on_char_boundaries() {
        assert_eq!(truncate("abc", 5), "abc");
        assert_eq!(truncate("更新说明", 2), "更新…");
    }
}

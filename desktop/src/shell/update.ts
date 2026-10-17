// ─────────────────────────────────────────────────────────────────────────────
// 「检查更新」的门面（2026-10-17 换成官方 updater）。
//
// 以前这里只回答「有没有新版」：Rust 侧读 GitHub 的 302 跳转拿 tag，再跟本机
// 版本比。现在多了下载与安装，那套自研命令整体退役，改由 `tauri-plugin-updater`
// 承担 —— 版本比较、拉取 `latest.json`、下载、验签、跑安装器都在插件里，前端
// 只负责「什么时候做、做到哪一步」。**比较只留一处**这条原则没变，只是那一处
// 从 `src-tauri/src/update.rs` 挪进了插件。
//
// 状态只有三种（与旧的三种一一对应，调用方不用改判断方式）：
//   · unsupported —— 纯网页预览、没有宿主；
//   · none        —— 已是最新 / 网络不通 / 清单不存在 / GitHub 异常；
//   · available   —— 有新版本，带版本号与发布日期。
// 下载与安装是**第二个动作**（用户再点一次才发生），单独一个函数，不塞进状态里。
//
// ⚠️ Windows 上 `downloadAndInstall` 会在安装器启动后**退出应用**，安装器装完
//    自动拉起新版（`restartAfterInstall` 默认 true）。所以这里没有「重启」按钮，
//    也不引入 process 插件 —— 那件事安装器已经做了。
// ─────────────────────────────────────────────────────────────────────────────

import { isTauri } from "@tauri-apps/api/core";
import { check, type Update } from "@tauri-apps/plugin-updater";

export type UpdateState =
  /** 纯网页预览：没有宿主，查不了。 */
  | { kind: "unsupported" }
  /** 没有查到新版本：已是最新、网络不通、超时、清单损坏都在这里。 */
  | { kind: "none" }
  | {
      kind: "available";
      /** 新版版本号（不含 `v`，与 `latest.json` 一致）。 */
      version: string;
      /** RFC 3339 时间串，界面只取日期那一段；清单没写就是空串。 */
      date: string;
      /** 更新说明（`latest.json` 的 notes），可以为空。 */
      notes: string;
    };

/** 预览环境（浏览器）里那一行的提示。 */
export const UPDATE_UNSUPPORTED = "仅桌面版可检查更新";

/**
 * `check()` 返回的句柄。它持有一份 Rust 侧资源，所以要点两次「检查更新」时
 * 先把上一次的关掉 —— 否则每点一次都留一份，虽然量小，但没有理由留着。
 */
let pending: Update | null = null;

/** 关掉上一个句柄；关不掉也不影响这次检查。 */
function releasePending(): void {
  const previous = pending;
  pending = null;
  if (previous) void previous.close().catch(() => {});
}

export async function checkForUpdate(): Promise<UpdateState> {
  if (!isTauri()) return { kind: "unsupported" };

  try {
    releasePending();
    const update = await check();
    pending = update;
    if (!update) return { kind: "none" };
    return {
      kind: "available",
      version: update.version,
      date: update.date ?? "",
      notes: update.body ?? "",
    };
  } catch {
    // 404（还没发过带 latest.json 的版本）、断网、证书错误、清单被改坏 —— 一律
    // 归入「没有查到」。更新检查是顺手点一下的附加动作，端出一屏错误码没有意义。
    pending = null;
    return { kind: "none" };
  }
}

/**
 * 下载并安装上一次 `checkForUpdate` 找到的更新。
 *
 * `onProgress` 收到 `0–99` 的百分比（清单没给总长度时为 `null`），下载完给 `100`
 * —— 调用方听到 100 就该把文案切成「正在安装」：紧接着应用会被安装器退出。
 *
 * 失败会**抛错**：走到这里说明用户已经明确要更新了，静默吞掉才是误导。调用方
 * 负责把失败落成「更新失败 · 可手动下载」，并展开下载渠道。
 */
export async function installUpdate(onProgress: (percent: number | null) => void): Promise<void> {
  const update = pending;
  if (!update) throw new Error("没有待安装的更新");

  let total = 0;
  let received = 0;

  try {
    await update.downloadAndInstall((event) => {
      if (event.event === "Started") {
        total = event.data.contentLength ?? 0;
        onProgress(total > 0 ? 0 : null);
        return;
      }
      if (event.event === "Progress") {
        received += event.data.chunkLength;
        // 留一格给「安装」：100 只在 Finished 时才出现，进度条不会提前停在满格
        onProgress(total > 0 ? Math.min(99, Math.round((received / total) * 100)) : null);
        return;
      }
      onProgress(100);
    });
  } finally {
    // 安装器已经接手（或失败）：句柄留着没有意义
    pending = null;
  }
}

/** 把 ISO 时间串截成 `2026-10-02`；认不出就原样返回（宁可显示得难看，也别丢信息）。 */
export function dateOf(publishedAt: string): string {
  return /^\d{4}-\d{2}-\d{2}/.test(publishedAt) ? publishedAt.slice(0, 10) : publishedAt;
}

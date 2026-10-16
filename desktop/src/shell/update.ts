// ─────────────────────────────────────────────────────────────────────────────
// 「检查更新」的门面。
//
// 真正的判断在 Rust 侧（`src-tauri/src/update.rs`）：那边的 `check_update` 拿本地
// 版本去跟 GitHub Releases 上的最新 tag 比，直接告诉这里「有没有新版」。这边**不做
// 第二次版本比较** —— v0.x 时代就栽在两处口径分叉上（一处按 3 段截断，于是
// `0.1.2.4` 被读成 `0.1.2`，明明发了新版却说「已是最新」）。比较只留一处。
//
// 这里只负责两件事：把结果翻译成界面能直接用的四种状态，以及在**没有 Tauri 宿主**
// 的纯网页预览里老老实实说「不可用」—— 不报错、不假装成功（`autostart.ts` 同款
// 门面写法）。
// ─────────────────────────────────────────────────────────────────────────────

import { invoke, isTauri } from "@tauri-apps/api/core";

export type UpdateErrorReason = "network" | "rate_limit" | "http" | "parse";

export type UpdateState =
  /** 纯网页预览：没有宿主，查不了。 */
  | { kind: "unsupported" }
  | { kind: "latest"; current: string }
  | {
      kind: "newer";
      current: string;
      latest: string;
      /** 这一版在 GitHub 上的发布页，供「查看更新说明」跳转。 */
      url: string;
      /** ISO 时间串（`2026-10-02T09:31:00Z`），界面只取日期那一段。 */
      publishedAt: string;
      notes: string;
    }
  | { kind: "error"; reason: UpdateErrorReason };

/** Rust 侧返回的原始结构，字段名与 `UpdateInfo` 一一对应。 */
interface UpdateInfo {
  current: string;
  latest: string | null;
  has_update: boolean;
  release_url: string;
  published_at: string;
  notes: string;
}

/** 预览环境（浏览器）里那一行的提示。 */
export const UPDATE_UNSUPPORTED = "仅桌面版可检查更新";

/** 错误码 → 人话。用户不需要知道状态码与超时栈，只需要知道下一步做什么。 */
export const UPDATE_ERRORS: Record<UpdateErrorReason, string> = {
  network: "网络不可达，无法检查更新",
  rate_limit: "请求过于频繁，稍后再试",
  http: "服务暂时不可用，稍后再试",
  parse: "返回的数据看不懂，暂时无法判断",
};

export async function checkForUpdate(): Promise<UpdateState> {
  if (!isTauri()) return { kind: "unsupported" };

  try {
    const info = await invoke<UpdateInfo>("check_update");
    if (!info.has_update || !info.latest) {
      return { kind: "latest", current: info.current };
    }
    return {
      kind: "newer",
      current: info.current,
      latest: info.latest,
      url: info.release_url,
      publishedAt: info.published_at,
      notes: info.notes,
    };
  } catch (error) {
    // 命令抛出来的就是我们自己给的稳定错误码（失败在 Rust 侧已经收敛）。认不出的
    // 一律按「网络」处理：这是最常见、也最可能自愈的一种。
    return { kind: "error", reason: reasonOf(error) };
  }
}

/** 把 ISO 时间串截成 `2026-10-02`；认不出就原样返回（宁可显示得难看，也别丢信息）。 */
export function dateOf(publishedAt: string): string {
  return /^\d{4}-\d{2}-\d{2}/.test(publishedAt) ? publishedAt.slice(0, 10) : publishedAt;
}

function reasonOf(error: unknown): UpdateErrorReason {
  return error === "network" || error === "rate_limit" || error === "http" || error === "parse"
    ? error
    : "network";
}

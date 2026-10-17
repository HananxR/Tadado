// ─────────────────────────────────────────────────────────────────────────────
// 「检查更新」的门面。
//
// 真正的判断在 Rust 侧（`src-tauri/src/update.rs`）：那边读 GitHub Releases 的
// 302 跳转拿到最新 tag，再跟本地版本比，直接告诉这里「有没有新版」。这边**不做
// 第二次版本比较** —— v0.x 时代就栽在两处口径分叉上（一处按 3 段截断，于是
// `0.1.2.4` 被读成 `0.1.2`，明明发了新版却说「已是最新」）。比较只留一处。
//
// 状态只有三种：没有宿主（浏览器预览）、有新版本、没有查到新版本。网络失败、
// 超时、限流、GitHub 改了结构，全都归入最后一种 —— 更新检查是顺手点一下的附加
// 动作，给用户端出「请求过于频繁」这种错误码，除了让他下次不敢点，没有别的用。
// ─────────────────────────────────────────────────────────────────────────────

import { invoke, isTauri } from "@tauri-apps/api/core";

export type UpdateState =
  /** 纯网页预览：没有宿主，查不了。 */
  | { kind: "unsupported" }
  | {
      kind: "newer";
      latest: string;
      /** 这一版在 GitHub 上的发布页，供「查看更新说明」跳转。 */
      url: string;
      /** ISO 时间串（`2026-10-02T09:31:00Z`），界面只取日期那一段。 */
      publishedAt: string;
      notes: string;
    }
  /** 没有查到新版本：已是最新、网络不通、超时、GitHub 异常都在这里。 */
  | { kind: "none" };

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

export async function checkForUpdate(): Promise<UpdateState> {
  if (!isTauri()) return { kind: "unsupported" };

  try {
    const info = await invoke<UpdateInfo>("check_update");
    if (!info.has_update || !info.latest) return { kind: "none" };
    return {
      kind: "newer",
      latest: info.latest,
      url: info.release_url,
      publishedAt: info.published_at,
      notes: info.notes,
    };
  } catch {
    // 命令本身已经把失败收敛成「没有查到」，这里的兜底只防宿主异常冒泡。
    return { kind: "none" };
  }
}

/** 把 ISO 时间串截成 `2026-10-02`；认不出就原样返回（宁可显示得难看，也别丢信息）。 */
export function dateOf(publishedAt: string): string {
  return /^\d{4}-\d{2}-\d{2}/.test(publishedAt) ? publishedAt.slice(0, 10) : publishedAt;
}

// ─────────────────────────────────────────────────────────────────────────────
// 对外的链接与文本复制。
//
// 四个地址只在**这一个文件**里出现：「关于」面板里的下载渠道、更新提示与联系方式
// 全都从这里取。散在各处的话，换一次下载渠道就得满仓库找哪里还写着旧链接 ——
// v0.x 换阿里云盘分享时就吃过这个亏。
//
// 打开外链走 `tauri-plugin-opener`（Rust 侧已注册），而不是 `window.open`：桌面端
// 的 WebView 里新开窗口会被拦下，只有交给系统才是「用默认浏览器打开」。纯网页预览
// 没有这个插件，退回 window.open（那里的浏览器自己会处理）。
// ─────────────────────────────────────────────────────────────────────────────

import { isTauri } from "@tauri-apps/api/core";

/**
 * 阿里云盘：**整个下载目录**的公开分享，长期有效、无需提取码。
 * 排在国内用户第一顺位（GitHub Releases 在国内经常打不开）。
 */
export const ALIYUN_URL = "https://www.alipan.com/s/E2FBppaMPZj";

/** GitHub Releases：备选下载渠道，也是「检查更新」的版本来源。 */
export const RELEASES_URL = "https://github.com/HananxR/Tadado/releases";

/** 仓库首页（反馈与联系里的那一行）。 */
export const REPO_URL = "https://github.com/HananxR/Tadado";

/** 作者的微信公众号。 */
export const WECHAT = "Pyvan";

/**
 * 用系统默认浏览器打开一条链接。
 *
 * @returns 是否真的交出去了；`false` 时调用方给一句提示，而不是静默失败
 *          （点了没反应，用户只会以为整个按钮是坏的）。
 */
export async function openExternal(url: string): Promise<boolean> {
  if (!url) return false;

  if (isTauri()) {
    try {
      // 动态 import：浏览器那支不该因为它出问题（`download.ts` 同款写法）
      const { openUrl } = await import("@tauri-apps/plugin-opener");
      await openUrl(url);
      return true;
    } catch {
      return false;
    }
  }

  window.open(url, "_blank", "noopener");
  return true;
}

/** 复制一段文本到剪贴板。浏览器里 `navigator.clipboard` 在非安全上下文会失败。 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

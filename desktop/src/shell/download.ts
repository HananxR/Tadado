// ─────────────────────────────────────────────────────────────────────────────
// 把内容交给用户存成文件。
//
// 文本（md / txt）和二进制（xlsx）都走这里：两处各写一遍必然分叉（一处加了
// BOM、一处忘了 revoke，谁也说不清哪个才是「下载」）。所以只有这一个实现。
//
// 桌面端（Tauri）**必须先问路径再写**：用户在「另存为」里选哪，文件就落在哪。
// 以前两地都走 `<a download>`，桌面上它直接落进 WebView 的默认下载目录 ——
// 用户没被问过一句，导出完还得去找文件在哪。
//
// 浏览器（`vite preview`、e2e）没有宿主对话框，退回 `<a download>`：那里「下载」
// 本来就是浏览器自己的事，也能在 e2e 里验。
// ─────────────────────────────────────────────────────────────────────────────

import { invoke, isTauri } from "@tauri-apps/api/core";
import { el } from "./dom";

export interface SaveOptions {
  /** 落地的文件名，含扩展名。对话框里它是默认名。 */
  name: string;
  /** 文件内容（md / txt）。与 `bytes` 二选一。 */
  text?: string;
  /** 文件内容（xlsx）。与 `text` 二选一。 */
  bytes?: ArrayBuffer;
  /** MIME 类型，如 `text/markdown`。 */
  mime: string;
  /**
   * 前缀 BOM。Excel 打开不带 BOM 的 UTF-8 CSV 会把中文显示成乱码，
   * 而「导出了一份打不开的表」比「没有导出」更让人上火。
   */
  bom?: boolean;
  /** 「另存为」里的文件类型筛选，如 `[{ name: "Markdown", extensions: ["md"] }]`。 */
  filters?: { name: string; extensions: string[] }[];
}

/**
 * 存文件。
 *
 * @returns 文件落在哪（桌面端是**完整路径** —— 导出完该知道它去哪了）；
 *          `null` 表示用户在对话框里**取消了**，这时一个字节都不该写。
 */
export async function saveAs(options: SaveOptions): Promise<string | null> {
  if (isTauri()) return saveByDialog(options);
  saveByLink(options);
  return options.name;
}

/** 桌面端：弹「另存为」→ 用户指定路径 → 写。 */
async function saveByDialog(options: SaveOptions): Promise<string | null> {
  // 动态 import：这两个模块只在 Tauri 里用得到，浏览器那支不该因为它们出问题
  const { save } = await import("@tauri-apps/plugin-dialog");
  const path = await save({ defaultPath: options.name, filters: options.filters });
  if (!path) return null;

  // fs 插件的作用域默认是**空的**（tauri.conf.json 里没配 `plugins.fs.scope`），
  // 于是写用户刚选的那条路径会被 `path forbidden` 挡下来 —— 而那个位置正是
  // 用户自己点的。所以写之前先把**这一条**路径放进作用域：只放这一条、不放大
  // 整个目录，进程退出即失效。（放在前端 import 里静态调不到，见 lib.rs）
  await invoke("allow_save_path", { path });

  const { writeFile, writeTextFile } = await import("@tauri-apps/plugin-fs");
  if (options.bytes) await writeFile(path, new Uint8Array(options.bytes));
  else await writeTextFile(path, `${options.bom ? "\uFEFF" : ""}${options.text ?? ""}`);

  return path;
}

/** 浏览器：<a download>。桌面端不该走这里。 */
function saveByLink(options: SaveOptions): void {
  const body = options.bytes ?? `${options.bom ? "\uFEFF" : ""}${options.text ?? ""}`;
  // 二进制不带 charset —— 它不是文本，写了反而错
  const blob = new Blob([body], {
    type: options.bytes ? options.mime : `${options.mime};charset=utf-8`,
  });

  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: options.name });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────────────────────────────────────────────
// 把内容交给用户存成文件。
//
// 文本（md / txt）和二进制（xlsx）都走这里：两处各写一遍必然分叉（一处加了
// BOM、一处忘了 revoke，谁也说不清哪个才是「下载」）。所以只有这一个实现。
//
// 用 Blob + <a download> 而不是走 Tauri 的文件对话框：浏览器里也能跑，e2e 里
// 也能验；用户点导出拿到的是真文件，不是一句「已导出（演示）」的提示。
// ─────────────────────────────────────────────────────────────────────────────

import { el } from "./dom";

export interface DownloadOptions {
  /** 落地的文件名，含扩展名。 */
  name: string;
  /** 文件内容。 */
  text: string;
  /** MIME 类型，如 `text/markdown`。 */
  mime: string;
  /**
   * 前缀 BOM。Excel 打开不带 BOM 的 UTF-8 CSV 会把中文显示成乱码，
   * 而「导出了一份打不开的表」比「没有导出」更让人上火。
   */
  bom?: boolean;
}

export function downloadText(options: DownloadOptions): void {
  const parts = options.bom ? ["\uFEFF", options.text] : [options.text];
  downloadBlob(options.name, new Blob(parts, { type: `${options.mime};charset=utf-8` }));
}

/** 二进制下载（xlsx）。MIME 里不带 charset —— 它不是文本，写了反而错。 */
export function downloadBlob(name: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

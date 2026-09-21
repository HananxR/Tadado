// ─────────────────────────────────────────────────────────────────────────────
// 导出按钮：点开选格式（md / txt / xlsx），选完弹「另存为」让用户指定路径。
//
// 为什么是一个菜单而不是三个按钮：三个按钮会把工具行挤满，而导出是低频动作；
// 折叠成一个「导出 ▾」，三种格式又都在**点开的一瞬间**看得到 —— 不用先猜
// 这个按钮会给自己什么格式。
//
// 内容在点击时现算（table / baseName 都是函数）：导出的是「现在看到的这批数据」，
// 建按钮时算好会停在打开页面那一刻。**路径由用户在对话框里定**（见 shell/download.ts）：
// 不问就写，导出完没人知道文件去了哪。
// ─────────────────────────────────────────────────────────────────────────────

import { EXPORT_FORMATS, buildExport, type ExportTable } from "../data/export";
import { saveAs } from "./download";
import { el } from "./dom";
import { toast } from "./toast";

export interface ExportButtonOptions {
  /** 按钮文字。默认「导出 ▾」。 */
  label?: string;
  /** 要导出的内容（点击时现算）。 */
  table: () => ExportTable;
  /** 文件名主体，不含扩展名。 */
  baseName: () => string;
  /** 提示里的数量词，如 `12 条活动`。 */
  countText: () => string;
  /** 现在还不能导出时给一句人话（如「先勾选标签」）。返回空串表示可以导出。 */
  blocked?: () => string;
}

let menu: HTMLElement | null = null;

function closeMenu(): void {
  menu?.remove();
  menu = null;
}

document.addEventListener("pointerdown", (event) => {
  if (menu && !menu.contains(event.target as Node)) closeMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeMenu();
});

export function exportButton(options: ExportButtonOptions): HTMLElement {
  const button = el("button", {
    class: "btn sm",
    type: "button",
    text: options.label ?? "导出 ▾",
  });

  button.addEventListener("click", (event) => {
    event.stopPropagation();

    if (menu) {
      closeMenu();
      return;
    }

    const blocked = options.blocked?.() ?? "";
    if (blocked) {
      toast(blocked);
      return;
    }

    const rect = button.getBoundingClientRect();
    menu = el("div", { class: "ctx-menu" });
    menu.style.left = `${Math.round(rect.left)}px`;
    // 默认贴在按钮下方；下面放不下就翻到上面，别让菜单在窗口底部被截掉
    menu.style.top = `${Math.round(rect.bottom + 4)}px`;

    for (const spec of EXPORT_FORMATS) {
      const item = el("div", { class: "menu-item", text: spec.label });
      item.addEventListener("click", (event) => {
        event.stopPropagation();
        closeMenu();

        const file = buildExport(spec.id, options.table(), options.baseName());

        void saveAs({
          name: file.name,
          mime: file.mime,
          text: file.text,
          bytes: file.bytes,
          // 对话框里只给这一种类型：选了 Markdown 就该存成 .md，不该顺手存成 .txt
          filters: [{ name: `${spec.ext.toUpperCase()} 文件`, extensions: [spec.ext] }],
        })
          .then((where) => {
            // 取消时一句话都不说：点了取消还要弹提示，等于没让人取消
            if (where) toast(`已导出 ${options.countText()} → ${where}`);
          })
          .catch((error: unknown) => {
            toast(
              `导出失败：${error instanceof Error ? error.message : String(error)}`,
            );
          });
      });
      menu.append(item);
    }

    document.body.append(menu);
    // 建完才知道多高，超底了就翻上去
    const box = menu.getBoundingClientRect();
    if (box.bottom > window.innerHeight - 8) {
      menu.style.top = `${Math.round(rect.top - box.height - 4)}px`;
    }
  });

  return button;
}

// ─────────────────────────────────────────────────────────────────────────────
// 导出：一处定义三种格式（md / txt / xlsx），两个用到导出的页面共用。
//
// 以前是两个页面各导出各的：管理页写 .md（任务行）、活动页写 .csv（逗号分隔），
// 于是「导出」在同一个应用里是两种互不相干的东西 —— 用户得先记住哪个页面会
// 给自己什么。现在统一：
//
//   · md 与 txt 是**同一套层次、两套符号**：md 走真正的 markdown 语法（能被
//     渲染器渲染成标题 + 嵌套列表），txt 用中性符号（`【】` / `1)` / `·`）把
//     同样的层次摆出来，但不含任何 md 语句 —— 丢进记事本、粘进工单系统都是一张
//     干净的清单。所以这里收的是**两份文本**，不是一份改名两次；
//   · xlsx 是同一批数据的**表格形态**，列由调用方给（表头 + 行）；
//   · 文件名由调用方给主体，扩展名在这儿补 —— 三处各拼一次必然出现
//     `tadado-xxx.md.txt` 这种东西。
//
// 不加 BOM：任务行文本一旦带上 BOM，首行 `- [ ] …` 前面就多了一个看不见的字符，
// 再粘回批量新建框时那一条会解析不出来（看起来像「第一条丢了」）。
// Excel 要 BOM 的是 CSV，而 xlsx 是二进制格式，不受影响。
// ─────────────────────────────────────────────────────────────────────────────

import { stampText } from "./time";
import { toXlsx } from "./xlsx";

// ─── 三层文本（标签 → 任务 → 活动）────────────────────────────────────────────
// 两个页面的导出都用它：活动分析按勾选标签查活动，任务管理按当前筛选列任务 ——
// 数据的来路不同，但「一份清单长什么样」必须只有一套说法。

export interface ExportRow {
  /** 活动时刻（epoch 毫秒），显示成 `MM-DD HH:MM`。 */
  at: number;
  text: string;
}

export interface ExportGroup {
  /** 标签名（含 `#`）。md 里原样写，txt 里换成 `【】`。 */
  tag: string;
  /** 一个标签下的若干任务，每个任务带自己的活动（时间倒序）。 */
  tasks: { title: string; /** 表格格式（xlsx）要，文本格式不写。 */ status?: string; rows: ExportRow[] }[];
}

/** 标签名去掉 `#`：txt 里它是个分块标题，`#` 在那边没有意义。 */
const tagLabel = (tag: string): string => tag.replace(/^#/, "");

/**
 * 三层结构 → markdown。
 *
 *     #后端
 *
 *     1. 重构认证模块
 *        - 09-11 09:30 完成接口联调
 *
 * 标签行写 `#后端`、**`#` 后不留空格**：留了空格md 就把它当一级标题渲染成一行
 * 大号字，比任务本身还抢眼（这份文件的主角是任务和进展）。
 *
 * 活动缩进**三个空格**是有讲究的：有序列表的内容从第 3 列开始（`1. ` 正好三格），
 * 子列表缩进到这一列才会被算作它的嵌套；缩 2 格或 4 格在 CommonMark 里分别会变成
 * 「懒惰续行」和「缩进代码块」—— 后者直接把整段原文吐出来。
 */
function groupedMarkdown(groups: ExportGroup[]): string {
  return groups
    .flatMap((group) => [
      group.tag,
      "",
      ...group.tasks.flatMap((entry, index) => [
        `${index + 1}. ${entry.title}`,
        ...entry.rows.map((row) => `   - ${stampText(row.at)} ${row.text}`),
      ]),
      "",
    ])
    .join("\n");
}

/**
 * 三层结构 → 纯文本。
 *
 * 层次和上面那份**一模一样**，但一个 md 语法符号都不用：`【】` 代替 `#`、
 * `1)` 代替 `1.`、`·` 代替 `-`。txt 的用处就是丢给不认 markdown 的地方（记事本、
 * 工单、聊天窗口），在那里 `#后端` 会被原样显示、`- ` 是一串莫名其妙的小横杠 ——
 * 与其指望对方渲染，不如让它在任何地方都长成一张干净的清单。
 *
 * 缩进：任务 2 格，活动 5 格（= 2 + `1) ` 的 3 格宽），于是活动和任务名左对齐，
 * 与 md 渲染出来的观感一致。
 */
function groupedPlain(groups: ExportGroup[]): string {
  return groups
    .flatMap((group) => [
      `【${tagLabel(group.tag)}】`,
      ...group.tasks.flatMap((entry, index) => [
        `  ${index + 1}) ${entry.title}`,
        ...entry.rows.map((row) => `     · ${stampText(row.at)} ${row.text}`),
      ]),
      "",
    ])
    .join("\n");
}

/** 按格式给这份三层清单的文本。 */
export const groupedText = (groups: ExportGroup[], format: "md" | "txt"): string =>
  format === "md" ? groupedMarkdown(groups) : groupedPlain(groups);

export type ExportFormat = "md" | "txt" | "xlsx";

export interface ExportFormatSpec {
  id: ExportFormat;
  /** 菜单里的名字。带扩展名：选完之后就该知道会拿到什么文件。 */
  label: string;
  ext: string;
  mime: string;
}

export const EXPORT_FORMATS: ExportFormatSpec[] = [
  { id: "md", label: "Markdown（.md）", ext: "md", mime: "text/markdown" },
  { id: "txt", label: "文本（.txt）", ext: "txt", mime: "text/plain" },
  {
    id: "xlsx",
    label: "表格（.xlsx）",
    ext: "xlsx",
    mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  },
];

export interface ExportTable {
  /**
   * md / txt 的文本，各给一份：两者层次一样、符号不同（md 用 markdown 语法，
   * txt 用中性符号），所以不能共用一段。
   */
  text: { md: string; txt: string };
  /** xlsx 的表头。 */
  head: string[];
  /** xlsx 的数据行，每行长度应与表头一致（少几个单元格不会坏，Excel 留空）。 */
  rows: string[][];
}

export interface ExportFile {
  name: string;
  mime: string;
  /** md / txt 的内容。 */
  text?: string;
  /** xlsx 的内容。 */
  bytes?: ArrayBuffer;
}

/**
 * 按格式把一张「表」变成一个待下载的文件。
 *
 * @param baseName 文件名主体（不含扩展名），扩展名在这儿补。
 */
export function buildExport(
  format: ExportFormat,
  table: ExportTable,
  baseName: string,
): ExportFile {
  const spec = EXPORT_FORMATS.find((item) => item.id === format) ?? EXPORT_FORMATS[0];

  if (format === "xlsx") {
    return {
      name: `${baseName}.${spec.ext}`,
      mime: spec.mime,
      bytes: toXlsx([table.head, ...table.rows]),
    };
  }

  return { name: `${baseName}.${spec.ext}`, mime: spec.mime, text: table.text[format] };
}

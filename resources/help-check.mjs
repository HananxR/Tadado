#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────────
// 帮助文档与功能的一致性检查。
//
// 为什么要这一步：帮助文档是**随程序分发**的，改了界面却忘了改说明，用户看到的
// 就是一份理直气壮的过期手册。人工核对挡不住 —— 这份文档有两百多处文案，改一次
// 功能就要再通读一遍，谁都会漏。
//
// 查四类事：
//   1. 目录里每个锚点都真的存在（点空链接比没有目录更糟）；
//   2. 该说的说了：五个页面名、关于里的六条功能、快捷键、当前版本号；
//   3. 不该说的没说：已经撤掉的能力不许再出现（负向清单）；
//   4. 只用一种格式：没有脚本、没有外链样式、没有行内 style；图片都在本地。
//
// 用法（仓库根）：node resources/help-check.mjs
// 失败时非零退出；不静默通过。
// ─────────────────────────────────────────────────────────────────────────────

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const HELP_DIR = join(ROOT, "desktop", "src-tauri", "resources", "help");
const HTML_PATH = join(HELP_DIR, "index.html");
const CONF_PATH = join(ROOT, "desktop", "src-tauri", "tauri.conf.json");

const failures = [];
const check = (ok, label, detail = "") => {
  if (ok) {
    console.log(`OK   ${label}`);
  } else {
    failures.push(`${label}${detail ? ` —— ${detail}` : ""}`);
    console.log(`FAIL ${label}${detail ? ` —— ${detail}` : ""}`);
  }
};

if (!existsSync(HTML_PATH)) {
  console.error(`缺少帮助文档：${HTML_PATH}`);
  process.exit(1);
}

let html = "";
let version = "";
try {
  html = readFileSync(HTML_PATH, "utf8");
  version = JSON.parse(readFileSync(CONF_PATH, "utf8")).version;
} catch (error) {
  console.error(`读取帮助文档或版本号失败：${error.message}`);
  process.exit(1);
}

if (!html.trim()) {
  console.error("帮助文档是空的");
  process.exit(1);
}
if (!version) {
  console.error("tauri.conf.json 里没有 version");
  process.exit(1);
}

// ── 1. 目录锚点 ─────────────────────────────────────────────────────────────
const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]));
const anchors = [...html.matchAll(/href="#([^"]*)"/g)].map((match) => match[1]);
const missingAnchors = [...new Set(anchors.filter((id) => !ids.has(id)))];
check(anchors.length >= 10, "目录有足够的章节", `${anchors.length} 个锚点`);
check(
  missingAnchors.length === 0,
  "目录里的每个锚点都能在文档中找到",
  missingAnchors.length ? `缺：${missingAnchors.join(", ")}` : "",
);

// ── 2. 必须出现的内容 ───────────────────────────────────────────────────────
const PAGES = ["总览", "任务", "任务图谱", "活动分析", "任务管理"];
for (const page of PAGES) {
  check(new RegExp(`>${page}<`).test(html), `页面名出现在文档里：${page}`);
}

// 「关于」里那六条功能清单：换成文档里可核对的六个短句，改功能时这里会先红
const FEATURES = [
  "五个视图：总览、任务、任务图谱、活动分析、任务管理",
  "创建 → 截止",
  "整年热力图",
  "无账号",
  "Ctrl+1–5",
  "Ctrl+Shift+Space",
  "活动时间线",
];
for (const item of FEATURES) {
  check(html.includes(item), `功能清单覆盖：${item}`);
}

check(
  html.includes(`v${version}`),
  `文档写明当前版本 v${version}`,
  `找不到 v${version}`,
);
check(html.includes("{{VERSION}}"), "保留版本占位符 {{VERSION}}（打开时由 Rust 替换）");

// ── 3. 负向清单：已经撤掉的能力 ─────────────────────────────────────────────
const FORBIDDEN = [
  ["AI 助手", "不存在的页签"],
  ["循环", "不存在的循环字段"],
  ["保存后收起", "抽屉不会在保存后自动关闭"],
  ["全年档位", "任务页没有这一档"],
  ["窗口置顶", "设置里的第二个图钉入口已撤"],
];
for (const [text, why] of FORBIDDEN) {
  check(!html.includes(text), `不再承诺已撤掉的能力：${text}（${why}）`);
}

// ── 4. 只用一种格式：无脚本、无外链资源、无行内样式 ─────────────────────────
check(!/<script[\s>]/i.test(html), "没有 <script>");
check(!/<link[\s>]/i.test(html), "没有外链 <link>（字体 / 样式）");
check(!/\ssrc\s*=\s*["']https?:/i.test(html), "没有远程图片");
check(!/\sstyle\s*=\s*["']/i.test(html), "正文没有行内 style（样式只在顶部 <style> 里）");
check((html.match(/<style[\s>]/gi) ?? []).length === 1, "只有一个 <style> 块");

// 图片都在本地，且文件真的存在
const images = [...html.matchAll(/\ssrc\s*=\s*"([^"]+)"/gi)].map((match) => match[1]);
check(images.length >= 5, "至少有五张界面截图", `${images.length} 张`);
for (const src of images) {
  check(!/^https?:/i.test(src), `图片是本地资源：${src}`);
  check(existsSync(join(HELP_DIR, src)), `图片文件存在：${src}`);
}

// ── 结果 ────────────────────────────────────────────────────────────────────
console.log("");
if (failures.length > 0) {
  console.error(`帮助文档检查未通过：${failures.length} 项`);
  for (const failure of failures) console.error(`  · ${failure}`);
  process.exit(1);
}
console.log(`帮助文档检查通过（对应 v${version}，${dirname(HTML_PATH)}）`);

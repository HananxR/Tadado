#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────────
// 生成应用内更新的清单 `latest.json`（Tauri updater 的静态接口）。
//
// 为什么要有这一步：`npm run tauri build` 在开了 `createUpdaterArtifacts` 之后
// 会给安装器补一个 `.sig`，但**不会**替你写清单 —— 而 updater 只认 `latest.json`。
// 清单里有两样东西必须与这次构建严格对应：包的文件名（拼下载 URL）和签名内容。
// 手抄一次就可能抄错一个字符，于是「用户点更新 → 验签失败」。
//
// 用的是哪个包：Tauri 2.x 默认给 **NSIS 安装器本体**签名（`*-setup.exe` +
// `*-setup.exe.sig`）；若改用 v1 兼容产物则会是 `*.nsis.zip` + `.sig`。两种都认，
// 优先 zip（大小略小），没有就退回 exe —— 这里不猜，按目录里实际有的文件来。
//
// 用法（在 desktop/ 下，构建之后）：
//   npm run updater:manifest
// 产物：src-tauri/target/release/bundle/latest.json
// 发布时把它和那个安装器一起传到同一个 Release ——
// `releases/latest/download/latest.json` 只有在该 Release 是最新正式版时才成立。
//
// 任何一项缺失都**非零退出**：宁可发布脚本停下，也不要发出一个装了也验不过的包。
// ─────────────────────────────────────────────────────────────────────────────

import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const DESKTOP = fileURLToPath(new URL("../", import.meta.url));
const CONF = join(DESKTOP, "src-tauri", "tauri.conf.json");
const BUNDLE = join(DESKTOP, "src-tauri", "target", "release", "bundle");
const NSIS_DIR = join(BUNDLE, "nsis");
const CHANGELOG = join(DESKTOP, "..", "CHANGELOG.md");
const REPO = "HananxR/Tadado";

const fail = (message) => {
  console.error(`\n[updater:manifest] ${message}\n`);
  process.exit(1);
};

const read = (path) => readFileSync(path, "utf8");

const version = JSON.parse(read(CONF)).version;
if (!version) fail(`tauri.conf.json 里没有 version（${CONF}）`);

if (!existsSync(NSIS_DIR)) {
  fail(`找不到 NSIS 产物目录：${NSIS_DIR}\n先跑 \`npm run tauri build\`（需要签名环境变量）。`);
}

// 只认**这一次构建**的包：文件名里带版本号，避免拿到上一次的残留。
// zip 是 v1 兼容产物，exe 是 2.x 的默认形态 —— 两种都支持，优先 zip
const names = readdirSync(NSIS_DIR);
const archives = names.filter(
  (name) =>
    name.includes(`_${version}_`) &&
    (name.endsWith(".nsis.zip") || name.endsWith("-setup.exe")),
);
const zipped = archives.filter((name) => name.endsWith(".nsis.zip"));
const chosen = zipped.length > 0 ? zipped : archives.filter((name) => name.endsWith(".exe"));
if (chosen.length === 0) {
  fail(
    `没有找到 ${version} 的更新包（*.nsis.zip 或 *-setup.exe）。\n` +
      `目录里现有：${names.join("、") || "（空）"}\n` +
      "构建时记得设置 TAURI_SIGNING_PRIVATE_KEY / TAURI_SIGNING_PRIVATE_KEY_PASSWORD。",
  );
}
if (chosen.length > 1) {
  fail(`找到不止一个更新包：${chosen.join("、")} —— 先清理旧产物再构建。`);
}

const archive = chosen[0];
const archivePath = join(NSIS_DIR, archive);
const signaturePath = `${archivePath}.sig`;
if (!existsSync(signaturePath)) {
  fail(`更新包没有签名文件：${signaturePath}\n签名缺失通常是构建时没给私钥。`);
}

const signature = read(signaturePath).trim();
if (!signature) fail(`签名文件是空的：${signaturePath}`);

/**
 * 更新说明取 CHANGELOG 里对应版本的一节。
 *
 * 取不到不算错（有些补丁版本可能没写日志），留空即可；截断是怕整篇塞进清单 ——
 * 它只用于「更新了什么」的提示，不是发布页。
 */
function notesFor(target) {
  if (!existsSync(CHANGELOG)) return "";
  const text = read(CHANGELOG);
  const start = text.indexOf(`## [${target}]`);
  if (start < 0) return "";
  const rest = text.slice(start);
  const end = rest.indexOf("\n---", 1);
  const section = (end < 0 ? rest : rest.slice(0, end)).trim();
  return section.length > 1500 ? `${section.slice(0, 1500)}…` : section;
}

const manifest = {
  version,
  notes: notesFor(version),
  pub_date: new Date().toISOString(),
  platforms: {
    // NSIS 安装包：updater 会下载这个 zip、验签、再以被动模式跑安装器
    "windows-x86_64": {
      signature,
      url: `https://github.com/${REPO}/releases/download/v${version}/${encodeURIComponent(archive)}`,
    },
  },
};

const out = join(BUNDLE, "latest.json");
writeFileSync(out, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

console.log(`
[updater:manifest] 已生成 ${out}
  版本      ${version}
  安装包    ${archive}
  下载地址  ${manifest.platforms["windows-x86_64"].url}
  签名      ${signature.split("\n")[1]?.slice(0, 24) ?? ""}…（${signature.length} 字符）

发布时把 latest.json 与 ${archive} 一起传到 v${version} 这个 Release。
`);

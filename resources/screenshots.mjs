#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────────
// 生成 README 用的界面截图（拍的是**真实构建**，不是手绘示意图）。
//
// 用法（在**仓库根**执行）：
//   cd desktop && npm run build && cd ..      # 先有 dist/
//   node resources/screenshots.mjs
//
// 产出：resources/screenshots/*.png，README 直接引用这些文件。
//
// 三处刻意的设定：
//   · 视口 1180×760 —— 正是应用窗口的默认尺寸（见 DESIGN.md 的窗口形态）。
//     截出来就是用户打开软件看到的那一屏，而不是「一个网页」。
//   · deviceScaleFactor 2 —— 高分屏上看不清字的截图等于没截。
//   · 画面里的数据就是**演示空间那 100 条样例**，不另造数据：README 展示的
//     必须是用户装上就能看到的东西。
//
// 脚本放在 resources/ 而不是 desktop/ 下：它服务的是**仓库的文档**（产物就在隔壁的
// resources/screenshots/），不属于那个应用。仓库根也不再留 tools/ 那一层 —— 工具住在
// **它所服务的东西旁边**（迁移工具同理，见 resources/skill/tadado-activity-import/scripts/）。
// Playwright 装在 desktop/node_modules（只有那边是 Node 工程），所以用 createRequire
// 从 desktop/package.json 出发去解析 —— ESM 的 import 不会往上找 desktop 的依赖。
// ─────────────────────────────────────────────────────────────────────────────

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const DESKTOP = fileURLToPath(new URL("../desktop/", import.meta.url));
const OUT = fileURLToPath(new URL("screenshots/", import.meta.url));
const require = createRequire(new URL("../desktop/package.json", import.meta.url));
const { chromium } = require("playwright");

const PORT = 4180;
// 别叫 `URL`：模块作用域里的 const 会把全局 URL 顶掉，上面 new URL(...) 就撞上
// 暂时性死区（`Cannot access 'URL' before initialization`）
const PREVIEW = `http://localhost:${PORT}/`;
/** 应用窗口的默认尺寸，见 DESIGN.md「窗口形态」。 */
const WIDTH = 1180;
const HEIGHT = 760;

if (!existsSync(join(DESKTOP, "dist", "index.html"))) {
  console.error("没有 dist/ —— 先构建：cd desktop && npm run build");
  process.exit(1);
}

mkdirSync(OUT, { recursive: true });

/** 临时材料落在这里，跑完删掉（「数据迁入」要真选一个文件）。 */
const TMP = mkdtempSync(join(tmpdir(), "tadado-shot-"));

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const server = spawn(
  process.execPath,
  ["node_modules/vite/bin/vite.js", "preview", "--port", String(PORT), "--strictPort"],
  { cwd: DESKTOP, stdio: "ignore" },
);

/** 等 vite preview 起来。用 fetch 探活：拿定时器猜启动耗时会随机失败。 */
async function waitServer() {
  for (let i = 0; i < 60; i += 1) {
    try {
      const response = await fetch(PREVIEW);
      if (response.ok) return;
    } catch {
      /* 还没起来 */
    }
    await sleep(250);
  }
  throw new Error(`preview 服务器没起来：${PREVIEW}`);
}

let browser;

try {
  await waitServer();
  browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: WIDTH, height: HEIGHT },
    deviceScaleFactor: 2,
    // 固定亮色：默认的 prefers-color-scheme 随机器走，截出来的图不该看运气
    colorScheme: "light",
  });
  // 关掉动效：入场动画拍到一半会让每张图都糊一点
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(PREVIEW, { waitUntil: "networkidle" });
  await page.waitForSelector(".rail-btn", { timeout: 15000 });

  const shot = async (name, action) => {
    if (action) await action();
    await sleep(420);
    await page.screenshot({ path: join(OUT, `${name}.png`) });
    console.log(`OK   ${name}.png`);
  };

  const goPage = (id) => page.locator(`.rail-btn[data-page="${id}"]`).click();

  // ── 五个页面 ──
  await shot("overview", () => goPage("overview"));
  await shot("tasks", () => goPage("tasks"));
  await shot("graph", () => goPage("graph"));
  await shot("activity", () => goPage("activity"));
  await shot("manage", () => goPage("manage"));

  // ── 维护抽屉：一条任务的全部信息与它的历史 ──
  // 挑的是手写样例里历史最丰富的那条（8 条进展 + 一次状态变更）。**不能**随手开
  // 第一行：列表默认按截止排序，前十几行全是压测生成的任务，每行只有一条「创建
  // 任务」—— 而抽屉这张图要证明的正是「过程留在时间线上」，拍空历史等于没拍。
  await shot("drawer", async () => {
    await goPage("tasks");
    await page.waitForSelector(".tt-row");

    await page.locator("#page-tasks .tools input").fill("优化列表页性能");
    await sleep(420);
    await page
      .locator(".tt-row")
      .filter({ has: page.locator(".lt1 .t", { hasText: /^优化列表页性能$/ }) })
      .first()
      .dblclick();
    await page.waitForSelector("#task-drawer.open");

    // 筛完再把搜索框清掉：截图里挂着一个搜索词，看起来像「这是搜索结果」，
    // 而这张图要说的是「打开一条任务」。抽屉挂在自己的任务上，清搜索不影响它
    await page.locator("#page-tasks .tools input").fill("");
    console.log(
      `     （抽屉打开了「优化列表页性能」，${await page.locator("#task-drawer .tl-entry").count()} 条记录）`,
    );
  });
  await page.keyboard.press("Escape");
  await sleep(300);

  // ── 数据迁入：把「一行一条任务」直接拍出来（选一个文件 → 当场解析出几条）──
  await shot("import", async () => {
    await goPage("manage");
    await page.locator('#page-manage button:has-text("数据迁入")').click();
    await page.waitForSelector(".modal-card .batch-file");
    // 对话框只吃文件：现写一个临时 md 再选进去，相当于用户点「选择文件…」
    const sample = join(TMP, "sample-tasks.md");
    writeFileSync(
      sample,
      [
        "- [ ] 示例任务一 #学习 ⏰09-21 :: 40%",
        "- [~] 示例任务二 #项目 ⏰09-29 14:30 :: 80%",
        "- [x] 示例任务三 #后端 ⏰09-12",
      ].join("\n"),
      "utf8",
    );
    await page.setInputFiles(".modal-card input[type=file]", sample);
  });
  await page.keyboard.press("Escape");
  await sleep(300);

  // ── 暗色主题：同一套设计令牌的另一端 ──
  await shot("dark", async () => {
    await page.click("#tb-theme");
    await goPage("overview");
  });

  // ── 仓库的社交预览图（GitHub 设置里上传的那张，1280×640）──────────────
  // 用 HTML 现拼一张：品牌 + tagline + 一张缩小的真实界面。拼完才截图，
  // 这样它和上面那些图用的是同一份界面、同一套字色，不会两个来源两种观感。
  const card = await browser.newPage({
    viewport: { width: 1280, height: 640 },
    deviceScaleFactor: 2,
    colorScheme: "light",
  });
  const app = readFileSync(join(OUT, "overview.png")).toString("base64");
  const warm = readFileSync(
    join(DESKTOP, "..", "resources", "icons", "app.png"),
  ).toString("base64");

  await card.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>
    * { margin: 0; box-sizing: border-box; }
    body {
      width: 1280px; height: 640px; display: flex; align-items: center; gap: 56px;
      padding: 0 72px; background: #f4f3ef; color: #38362f;
      font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
      overflow: hidden;
    }
    .left { flex: none; width: 430px; }
    .brand { display: flex; align-items: center; gap: 18px; }
    .brand img { width: 78px; height: 78px; }
    .brand b { font-size: 46px; letter-spacing: -0.5px; color: #2f2d28; }
    .line { margin-top: 30px; font-size: 31px; font-weight: 600; line-height: 1.45; color: #4c56c0; }
    .sub { margin-top: 22px; font-size: 17px; line-height: 1.7; color: #8d8675; }
    .shot {
      flex: 1; border-radius: 12px; overflow: hidden; border: 1px solid #e3dfd3;
      box-shadow: 0 18px 44px -14px rgba(40, 36, 28, 0.34);
    }
    .shot img { display: block; width: 100%; }
  </style></head><body>
    <div class="left">
      <div class="brand"><img src="data:image/png;base64,${warm}"><b>Tadado2</b></div>
      <div class="line">任务是一行字，<br>过程是一条线。</div>
      <div class="sub">本地优先的桌面任务管理器<br>Markdown 就是数据格式 · 数据只在你自己的机器上</div>
    </div>
    <div class="shot"><img src="data:image/png;base64,${app}"></div>
  </body></html>`);
  await sleep(400);
  await card.screenshot({ path: join(OUT, "social-preview.png") });
  console.log("OK   social-preview.png（GitHub 设置 → Social preview 上传这张）");

  await card.close();
} finally {
  await browser?.close();
  server.kill();
  rmSync(TMP, { recursive: true, force: true });
}

console.log(`\n全部写到 ${OUT}`);

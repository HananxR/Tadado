// ─────────────────────────────────────────────────────────────────────────────
// 端到端冒烟：真浏览器跑一遍主要交互。
//
//   npm run e2e
//
// 它存在的理由：桌面端此前唯一的自动检查是 `tsc`（npm run build），而 tsc 看不出
// 运行时故障 —— 有一次 `dropdown.setValue` 会回调 onPick，造成 paint → setValue →
// onPick 无限递归，抽屉节点建出来了却永远加不上 .open：类型完全合法，构建照过，
// 表现是「双击、右键都没反应」。这类问题只能靠真点一遍。
//
// 覆盖的都曾经真出过问题：开抽屉、右键菜单、新建、批量新建、切分区、报告搜索，
// 外加一条「不许有 console 报错」。
// ─────────────────────────────────────────────────────────────────────────────

import { spawn } from "node:child_process";
import { chromium } from "playwright";

const PORT = 4173;
// vite preview 默认只监听 ::1，写 127.0.0.1 会连不上
const URL = `http://localhost:${PORT}/`;

// 用 node 拉 vite 的 JS 入口：spawn("npx.cmd") 在 Windows 上会 EINVAL
const server = spawn(
  process.execPath,
  ["node_modules/vite/bin/vite.js", "preview", "--port", String(PORT), "--strictPort"],
  { stdio: "ignore" },
);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const failures = [];

function check(name, ok, extra = "") {
  console.log(`${ok ? "OK  " : "FAIL"} ${name}${extra ? ` — ${extra}` : ""}`);
  if (!ok) failures.push(name);
}

// 等服务器起来：spawn 是异步的，直接 goto 会撞上 ECONNREFUSED
let ready = false;
for (let attempt = 0; attempt < 40 && !ready; attempt += 1) {
  try {
    ready = (await fetch(URL)).ok;
  } catch {
    await sleep(500);
  }
}
if (!ready) {
  console.log("预览服务器没起来 —— 先跑 `npm run build`");
  server.kill();
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });

const consoleErrors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (error) => consoleErrors.push(String(error)));

try {
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector(".rail-btn", { timeout: 15000 });

  // ── 任务页 ──
  await page.locator(".rail-btn").nth(1).click();
  await page.waitForSelector(".tt-row");
  check("任务页有行", (await page.locator(".tt-row").count()) > 0);

  // 双击开抽屉（回归：递归 bug 曾让它打不开）
  await page.locator(".tt-row").first().dblclick();
  await sleep(400);
  check("双击打开维护抽屉", (await page.locator("#task-drawer.open").count()) === 1);
  await page.keyboard.press("Escape");
  await sleep(300);
  check("Esc 关闭抽屉", (await page.locator("#task-drawer.open").count()) === 0);

  // 编辑标题（回归：标题、标签、截止曾经全是只读节点）
  // 挑一条「待办」的：已完成的任务按设计不会被标成逾期，拿它测逾期等于测了个空
  const todoRow = page
    .locator(".tt-row")
    .filter({ has: page.locator(".tt-bar.st-todo") })
    .first();
  await todoRow.dblclick();
  await page.waitForSelector("#task-drawer.open");
  await page.fill(".dr-title", "改过标题的任务");
  await page.locator(".dr-title").press("Enter");
  await sleep(300);
  check(
    "抽屉可改标题",
    (await page.locator(".tt-label", { hasText: "改过标题的任务" }).count()) >= 1,
  );

  // 设成过去的日期 → 应被自动标为逾期
  await page.fill(".dr-due", "2026-09-01");
  await page.locator(".dr-due").press("Enter");
  await sleep(300);
  const badge = (await page.locator("#task-drawer .dr-h .st").textContent()) ?? "";
  check("截止早于今天自动标逾期", badge.includes("逾期"), badge.trim());

  // 清除截止 → 退回待办
  await page.click(".due-quick button:has-text('清除')");
  await sleep(300);
  const badge2 = (await page.locator("#task-drawer .dr-h .st").textContent()) ?? "";
  check("清除截止后退回待办", !badge2.includes("逾期"), badge2.trim());

  // Markdown 源：以前能打字、后面没接任何东西（敲了没反应，看着像坏了）。
  // 现在边敲边渲染，写回要显式点按钮；状态不进 md，写回时不许被 md 改掉。
  await page.click("#task-drawer details.md-d summary");
  await sleep(200);
  await page.fill("#task-drawer textarea.md", "- [ ] md 改过的名字 #md ⏰09-30 :: 60%");
  await sleep(250);
  check(
    "md 预览跟着敲的字变",
    (await page.locator(".md-prev .mdp-title").textContent() ?? "").includes("md 改过的名字"),
  );

  const badgeBeforeMd = (await page.locator("#task-drawer .dr-h .st").first().textContent()) ?? "";
  await page.click("#task-drawer button:has-text('按 md 更新任务')");
  await sleep(300);
  check(
    "按 md 更新写入，且状态不被 md 改掉",
    (await page.locator(".tt-label", { hasText: "md 改过的名字" }).count()) === 1 &&
      ((await page.locator("#task-drawer .dr-h .st").first().textContent()) ?? "") === badgeBeforeMd,
  );

  await page.keyboard.press("Escape");
  await sleep(300);

  // 右键菜单
  await page.locator(".tt-row").first().click({ button: "right" });
  await sleep(200);
  const items = await page.locator(".ctx-menu .menu-item").allTextContents();
  check("右键菜单出现", items.length === 3, items.join(" / "));
  await page.keyboard.press("Escape");

  // 快速新建
  await page.fill(".qc-input", "冒烟新建的任务 #学习");
  await page.keyboard.press("Enter");
  await sleep(300);
  check(
    "快速新建出现在时间轴上",
    (await page.locator(".tt-label", { hasText: "冒烟新建的任务" }).count()) === 1,
  );

  // 草稿：没提交的字不是数据，但也不该因为切页 / 刷新就消失
  await page.fill(".qc-input", "打了一半的任务");
  await sleep(700); // 草稿是防抖写的，等它落盘
  check("草稿条出现", await page.locator(".draft-bar").first().isVisible());

  await page.reload({ waitUntil: "networkidle" });
  await page.locator(".rail-btn").nth(1).click();
  await page.waitForSelector(".qc-input");
  await sleep(700);
  check(
    "刷新后草稿还在输入框里",
    (await page.locator(".qc-input").inputValue()) === "打了一半的任务",
  );

  await page.click(".draft-bar button:has-text('丢弃')");
  await sleep(250);
  check(
    "丢弃草稿后草稿条消失",
    (await page.locator(".qc-input").inputValue()) === "" &&
      !(await page.locator(".draft-bar").first().isVisible()),
  );

  // 批量新建
  await page.click("button:has-text('批量')");
  await page.waitForSelector(".modal-card textarea");
  await page.fill(
    ".modal-card textarea",
    "- [ ] 批量一 #工作 ⏰09-20 14:30 :: 20%\n- [x] 批量二 #工作\n这句不是任务",
  );
  await sleep(200);
  const preview = await page.locator(".modal-detail").last().textContent();
  check("批量预览条数", preview.includes("将创建 2 条"), preview.trim());
  await page.click(".modal-actions button:has-text('创建')");
  await sleep(400);
  check(
    "批量建出两条（非任务行被跳过）",
    (await page.locator(".tt-label", { hasText: "批量一" }).count()) === 1 &&
      (await page.locator(".tt-label", { hasText: "批量二" }).count()) === 1,
  );

  // 批量提交成功后不该留着草稿 —— 下次打开又冒出上次那十行内容很吓人
  await page.click("button:has-text('批量')");
  await sleep(350);
  check("批量提交后草稿已清", !(await page.locator(".modal-card .draft-bar").isVisible()));
  await page.keyboard.press("Escape");
  await sleep(250);

  // 切分区
  const before = await page.locator(".tt-row").count();
  await page.click("#part-btn");
  await sleep(150);
  await page.click(".part-item[data-part='study']");
  await sleep(400);
  const after = await page.locator(".tt-row").count();
  check("切分区换一批数据", after !== before, `${before} -> ${after}`);

  // 活动报告搜索
  await page.locator(".rail-btn").nth(3).click();
  await page.waitForSelector(".act-item, .empty");
  const all = await page.locator(".act-item").count();
  await page.fill(".act-search", "zzz不可能匹配zzz");
  await sleep(250);
  const filtered = await page.locator(".act-item").count();
  check("活动报告搜索能过滤", all > 0 && filtered === 0, `${all} -> ${filtered}`);

  // 热力图：月份标签必须落在「当月 1 号所在的那一列」。这类错位不报错、编译照过，
  // 只有把量出来的像素对照日历算一遍才看得出来（曾经每个月都偏一格）。
  const heat = await page.evaluate(() => {
    const cells = [...document.querySelectorAll(".hm .hc")].map((node) => {
      const box = node.getBoundingClientRect();
      return { title: node.title, x: Math.round(box.x), y: Math.round(box.y) };
    });
    const xs = [...new Set(cells.map((c) => c.x))].sort((a, b) => a - b);
    const pitch = xs[1] - xs[0];
    const cols = xs.map((x) => {
      const titles = cells
        .filter((c) => c.x === x)
        .sort((a, b) => a.y - b.y)
        .map((c) => c.title)
        .filter(Boolean);
      return { first: titles[0]?.slice(0, 5), last: titles[titles.length - 1]?.slice(0, 5) };
    });
    const want = [];
    let prev = null;
    cols.forEach((col, index) => {
      const month = Number((index === 0 ? col.first : col.last).slice(0, 2));
      if (month !== prev) {
        want.push(`${month} 月@${index}`);
        prev = month;
      }
    });
    const got = [...document.querySelectorAll(".hmcols span")].map(
      (node) => `${node.textContent}@${Math.round(parseFloat(node.style.left) / pitch)}`,
    );
    return { want: want.join(" "), got: got.join(" "), pitch };
  });
  check("热力图月份标签落在正确的那一列", heat.want === heat.got, `${heat.pitch}px pitch · 应 ${heat.want} · 实 ${heat.got}`);

  // 图谱：画布按量出来的容器排布，不能高过容器 —— .gwrap 是 overflow:hidden，
  // 画布一高就把底下一排节点剪掉（曾经就差 36px，是工具行插入后才占的高度）
  await page.locator('.rail-btn[data-page="graph"]').click();
  await page.waitForSelector(".gcanvas");
  await sleep(600);
  const frame = await page.evaluate(() => {
    const wrap = document.querySelector(".gwrap").getBoundingClientRect();
    const canvas = document.querySelector(".gcanvas").getBoundingClientRect();
    const nodes = [...document.querySelectorAll(".gcanvas .node")].map((n) => n.getBoundingClientRect());
    return {
      wrap: [Math.round(wrap.width), Math.round(wrap.height)],
      canvas: [Math.round(canvas.width), Math.round(canvas.height)],
      allInside: nodes.every(
        (r) => r.top >= wrap.top - 1 && r.bottom <= wrap.bottom + 1 && r.left >= wrap.left - 1 && r.right <= wrap.right + 1,
      ),
      nodes: nodes.length,
    };
  });
  check(
    "图谱画布贴合容器且节点都在框内",
    // 节点数不写死：这时停在「学习」分区（上一条测的就是切分区），只有几个任务
    frame.canvas[0] <= frame.wrap[0] && frame.canvas[1] <= frame.wrap[1] && frame.allInside && frame.nodes >= 3,
    `容器 ${frame.wrap.join("x")} · 画布 ${frame.canvas.join("x")} · ${frame.nodes} 节点`,
  );

  await page.locator('.rail-btn[data-page="activity"]').click();
  await sleep(300);

  // 分区口令 → 切过去被挡 → 错口令不放行 → 对口令解锁。
  // 给「工作」上锁（当前停在「学习」）：给正在看的分区上锁会立刻把设置面板
  // 自己挡住 —— 那是缺陷，不是这里要测的场景。
  await page.click("#set-btn");
  await page.waitForSelector("#set-drawer.open");
  await page.click("#set-drawer .rowctl .seg button:has-text('工作')");
  await page.click("#set-drawer .rowctl button:has-text('设置口令')");
  await page.waitForSelector(".mask .pr-input");
  await page.fill(".mask .pr-input", "1234");
  await page.click(".modal-actions button:has-text('设置')");
  await sleep(400);
  await page.click("#set-close");
  await sleep(250);

  await page.click("#part-btn");
  await sleep(150);
  await page.click(".part-item[data-part='work']");
  await sleep(400);
  check("切到上锁分区会挡一层", (await page.locator(".lock-screen.show").count()) === 1);

  await page.fill(".lock-screen .pr-input", "0000");
  await page.keyboard.press("Enter");
  await sleep(250);
  const hint = (await page.locator(".lock-hint").textContent()) ?? "";
  check(
    "错误口令不放行",
    (await page.locator(".lock-screen.show").count()) === 1 && hint.includes("不对"),
    hint.trim(),
  );

  await page.fill(".lock-screen .pr-input", "1234");
  await page.keyboard.press("Enter");
  await sleep(400);
  check("正确口令解锁", (await page.locator(".lock-screen.show").count()) === 0);

  check("无 console 报错", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));
} finally {
  await browser.close();
  server.kill();
}

console.log(failures.length === 0 ? "\n全部通过" : `\n失败：${failures.join("、")}`);
process.exit(failures.length === 0 ? 0 : 1);

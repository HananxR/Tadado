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
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
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

/** 导出下载落在这里，跑完删掉。 */
const TMP = mkdtempSync(join(tmpdir(), "tadado-e2e-"));

const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) value = value & 1 ? -306674912 ^ (value >>> 1) : value >>> 1;
    table[index] = value;
  }
  return table;
})();

function crc32(buffer) {
  let crc = -1;
  for (const byte of buffer) crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ byte) & 0xff];
  return (crc ^ -1) >>> 0;
}

/**
 * xlsx 是一个 zip，而「浏览器下载成功」不代表这个包是好的：CRC 写错时下载照样
 * 完成，Excel 打开才报「文件已损坏」—— 用户只会看到导出失败。所以逐个本地文件头
 * 走一遍，把 CRC 真的算一遍。
 */
function zipProblem(buffer) {
  if (buffer.readUInt32LE(0) !== 0x04034b50) return "不是 zip（缺 PK 头）";

  let offset = 0;
  let entries = 0;
  while (offset + 30 <= buffer.length) {
    if (buffer.readUInt32LE(offset) !== 0x04034b50) break;
    const crc = buffer.readUInt32LE(offset + 14);
    const size = buffer.readUInt32LE(offset + 22);
    const start = offset + 30 + buffer.readUInt16LE(offset + 26) + buffer.readUInt16LE(offset + 28);
    const name = buffer.toString("utf8", offset + 30, offset + 30 + buffer.readUInt16LE(offset + 26));
    if (crc32(buffer.subarray(start, start + size)) !== crc) return `${name} 的 CRC 不符`;
    entries += 1;
    offset = start + size;
  }
  return entries >= 5 ? "" : `只有 ${entries} 个条目`;
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

  // ── 切页只显示一页 ──
  // 显隐由 `.page.active` 控制。曾有一条 ID 选择器规则（`#page-graph` 上的
  // display:flex）优先级压过 `.page { display:none }`，图谱页于是永远可见，把
  // 排在它后面的活动分析 / 任务管理的页头整个顶了下去 —— 类型和构建都看不出
  // 这类问题，只有真量一次「此刻有几页在显示」才发现。
  const visiblePages = () =>
    page.evaluate(() =>
      [...document.querySelectorAll(".page")]
        .filter((node) => getComputedStyle(node).display !== "none")
        .map((node) => node.id),
    );

  let leak = "";
  for (const id of ["overview", "tasks", "graph", "activity", "manage"]) {
    await page.click(`.rail-btn[data-page='${id}']`);
    await sleep(200);
    const shown = await visiblePages();
    if (shown.length !== 1 || shown[0] !== `page-${id}`) leak += `${id}:${shown.join("+")} `;
  }
  check("任一时刻只有一页可见", leak === "", leak.trim());

  // 问候语按墙上的时钟说，且不该出现占位人名。
  // 之前是写死的「早上好，HananxR」：晚上八点打开也说早上好，还把 mock 里的
  // 占位值当成用户摆在最显眼的位置。
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(250);
  const greet = await page.evaluate(() => document.querySelector(".greet .g1")?.textContent ?? "");
  const hour = new Date().getHours();
  const want =
    hour < 5 ? "夜深了" : hour < 11 ? "早上好" : hour < 13 ? "中午好" : hour < 18 ? "下午好" : "晚上好";
  check("问候语按真实时钟", greet === want, `「${greet}」· 现在 ${hour} 点`);
  check("问候语里没有占位人名", !greet.includes("HananxR"), greet);

  // 焦点时间轴的「现在」也必须指向真实时刻：它以前读 mock 里写死的 09:30
  // （DEMO_NOW_MINUTES），晚上打开也停在上午九点半 —— 这块界面上唯一能证明
  // 「知道现在几点」的地方在说谎。轴的范围是 6:00–24:00
  const nowMark = await page.evaluate(() => {
    const node = document.querySelector("#page-overview .tdt-now");
    return node ? { left: Number.parseFloat(node.style.left), title: node.title } : null;
  });
  const clock = new Date();
  const dayMinutes = clock.getHours() * 60 + clock.getMinutes();
  const expectedPct = ((dayMinutes - 6 * 60) / ((24 - 6) * 60)) * 100;
  check(
    "焦点时间轴的「现在」指向真实时刻",
    nowMark !== null && Math.abs(nowMark.left - expectedPct) <= 1.5,
    `标记 ${nowMark?.left?.toFixed(1)}% · 应 ${expectedPct.toFixed(1)}% · ${nowMark?.title}`,
  );

  // ── 四张表都能翻页、档位一致（100 条数据下才看得出）────────────────────────
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(300);
  const feedBar = await page.evaluate(() => {
    const bar = document.querySelector("#page-overview .ov-right .card .pager");
    return bar
      ? { has: true, text: bar.textContent ?? "", sizes: [...bar.querySelectorAll(".menu-item")].map((n) => n.textContent?.trim()) }
      : { has: false, text: "", sizes: [] };
  });
  // 活动时间在界面 / 导出 / 库里是同一个东西：**绝对日期**。以前存的就是
  // 「今天 09:12」这句话，隔一天它自己就说不通了
  const feedTime = await page.evaluate(
    () => document.querySelector("#page-overview .feed-item .tm")?.textContent?.trim() ?? "",
  );
  check(
    "活动时间统一显示成绝对日期（不再是「今天 / 昨天 / 刚刚」）",
    /^\d{2}-\d{2} \d{2}:\d{2}$/.test(feedTime),
    feedTime,
  );

  check(
    "总览近期活动可分页，档位是 20/30/50/100",
    feedBar.has && feedBar.sizes.join("/") === "20 条/页/30 条/页/50 条/页/100 条/页",
    `${feedBar.sizes.join(" / ")} · ${feedBar.text.trim().slice(0, 24)}`,
  );

  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(300);

  // ── 交付口径：启动状态就是「演示空间 100 条，其他分区为空」─────────────────
  // 100 = mock.ts 的 28（原型手写）+ 72（压测生成），也是性能验收的输入规模：
  // 100 条挤在同一个分区里，任务页的窗口自适应 / 图谱的力导向 / 管理页的分页
  // 才压得出真实表现。这条必须放在**早期** —— 后面几段测试会自己建任务，
  // 等到末尾再数就不是启动状态了（那时是 103）
  //
  // 任务页只列**未归档**的，所以是 99：种子里有 1 条是「已归档」样例，留给管理页
  // 的归档列（99 + 1 = 100）。两处一起数才算真的验了 100
  const bootTotal = await page.evaluate(() => {
    const bar = document.querySelector("#page-tasks .pager")?.textContent ?? "";
    return Number.parseInt(/共 (\d+) 条/.exec(bar)?.[1] ?? "-1", 10);
  });

  await page.locator('.rail-btn[data-page="manage"]').click();
  await sleep(350);
  await page.locator("#page-manage .chip:has-text('已归档')").click();
  await sleep(300);
  const archivedRows = await page.locator("#page-manage .mrow").count();
  check(
    "启动即演示空间 100 条演示任务",
    bootTotal === 99 && archivedRows === 1,
    `未归档 ${bootTotal} · 归档 ${archivedRows} · 合计 ${bootTotal + archivedRows}`,
  );

  // 把归档筛选拨回默认那档（「未归档」）再回任务页：上面那段动的筛选别留给
  // 后面的用例。归档那排的文案是 未归档 / 已归档 / 含归档
  await page.locator("#page-manage .chip:has-text('未归档')").click();
  await sleep(200);
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(300);

  const tasksPaged = await page.evaluate(() => {
    const bar = document.querySelector("#page-tasks .pager");
    if (!bar) return { has: false };
    const first = document.querySelector("#page-tasks .tt-row .lt1 .t")?.textContent ?? "";
    return { has: true, text: bar.textContent ?? "", first };
  });
  await page.locator("#page-tasks .pager .navbtn").last().click();
  await sleep(350);
  const tasksNext = await page.evaluate(
    () => document.querySelector("#page-tasks .tt-row .lt1 .t")?.textContent ?? "",
  );
  check(
    "任务页时间轴可翻页，且翻页后是另一批任务",
    tasksPaged.has && tasksNext !== "" && tasksNext !== tasksPaged.first,
    `${tasksPaged.first} → ${tasksNext} · ${tasksPaged.text?.trim()}`,
  );

  await page.locator('.rail-btn[data-page="activity"]').click();
  await sleep(350);
  const reportPager = await page.evaluate(() => {
    const bar = document.querySelector(
      "#page-activity .split-filter .card:nth-child(2) .pager",
    );
    return bar ? { has: true, text: bar.textContent ?? "" } : { has: false, text: "" };
  });
  check(
    "活动报告的查询结果可分页",
    reportPager.has && /\d+ 条\/页/.test(reportPager.text),
    reportPager.text.trim(),
  );

  // ── 总览的数字必须点得开、且对得上 ─────────────────────────────────────────
  // 以前任务页先按档位定窗口、再拿窗口砍任务：总览写「逾期 4」，点进来只有 3 条
  // —— 第 4 条的起止落在窗口外，它没丢，只是没被画出来。现在窗口反过来迁就
  // 筛选结果（fitWindow）：先有结果，再让窗口去装它。
  for (const label of ["逾期", "进行中", "已完成"]) {
    await page.locator('.rail-btn[data-page="overview"]').click();
    await sleep(250);
    const claimed = Number.parseInt(
      (await page.locator(`.tile:has-text('${label}') .num`).first().textContent())?.trim() ?? "",
      10,
    );
    await page.locator(`.tile:has-text('${label}')`).first().click();
    await sleep(350);
    // 比的是**筛出来的总数**（分页器上那个「共 N 条」），不是当前页的行数：
    // 演示空间 100 条之后，逾期就有 38 条，一页只放得下 20
    const opened = await page.evaluate(() => {
      const bar = document.querySelector("#page-tasks .pager")?.textContent ?? "";
      return {
        total: Number.parseInt(/共 (\d+) 条/.exec(bar)?.[1] ?? "-1", 10),
        // 换了筛选必须回到第一页：停在上次翻到的第 2 页，看到的是这批的后半截
        firstPage: /第 1[–-]/.test(bar),
        rows: document.querySelectorAll("#page-tasks .tt-row").length,
      };
    });
    check(
      `总览「${label}」的数字 = 点开后筛出的总数`,
      claimed === opened.total && opened.firstPage && opened.rows > 0,
      `${claimed} vs 共 ${opened.total} 条（本页 ${opened.rows} 行 · 第一页 ${opened.firstPage}）`,
    );
  }

  // 优先级分布：每一档都是一个入口（以前这一整块点了没反应）
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(250);
  // 挑一档真的有任务的来点：拿一档 0 条的测，0 = 0 也算通过，什么都没验到
  const buckets = await page.evaluate(() =>
    [...document.querySelectorAll(".ubar")].map((node) => ({
      label: node.querySelector(".un")?.textContent?.trim() ?? "",
      count: Number.parseInt(node.querySelector(".uc")?.textContent ?? "0", 10),
    })),
  );
  const target = buckets.find((item) => item.count > 0) ?? buckets[0];
  const urgentClaimed = target.count;
  await page.locator(".ubar").nth(buckets.indexOf(target)).click();
  await sleep(350);
  const prio = await page.evaluate(() => {
    const bar = document.querySelector("#page-tasks .pager")?.textContent ?? "";
    return {
      onTasks:
        [...document.querySelectorAll(".page")].filter(
          (n) => getComputedStyle(n).display !== "none",
        )[0]?.id ?? "?",
      picks: [...document.querySelectorAll("#page-tasks .tools .dd-btn")]
        .map((b) => b.textContent?.trim() ?? "")
        .join(" | "),
      // 同理比总数：某一档超过一页时，比当前页行数会误判
      total: Number.parseInt(/共 (\d+) 条/.exec(bar)?.[1] ?? "-1", 10),
      rows: document.querySelectorAll("#page-tasks .tt-row").length,
    };
  });
  check(
    `点优先级分布的一档（${target.label}）：跳任务页并按该优先级筛出`,
    prio.onTasks === "page-tasks" &&
      prio.picks.includes(target.label) &&
      prio.total === urgentClaimed &&
      prio.rows > 0,
    JSON.stringify({ ...prio, claimed: urgentClaimed }),
  );

  // 近期活动点一条 → 那一条必须真的出现在任务页列表里。
  // 抽屉开了、列表里却没有它（窗口把任务挡在外面），看着就像跳转坏了
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(250);
  const feedTitle = (await page.locator(".feed-item .tx b").first().textContent())?.trim() ?? "";
  await page.locator(".feed-item").first().click();
  await sleep(400);
  const found = await page.evaluate(
    (title) =>
      [...document.querySelectorAll("#page-tasks .tt-row .lt1 .t")].some(
        (n) => (n.textContent ?? "").trim() === title,
      ),
    feedTitle,
  );
  check("点近期活动：那条任务真的出现在任务页列表里", feedTitle !== "" && found, feedTitle);

  // ── 任务页 ──
  await page.locator(".rail-btn").nth(1).click();
  await page.waitForSelector(".tt-row");
  check("任务页有行", (await page.locator(".tt-row").count()) > 0);

  // 档位切到「本月」再往下走：这一页现在是**聚焦窗口**（窗口外的任务不进表），
  // 而下面的用例会改截止日期，把任务挪出默认的「本周」—— 那样它们会凭空从表里
  // 消失，后面的断言就会以为是坏了。
  await page.click("#page-tasks .seg button:has-text('本月')");
  await sleep(350);

  // 双击开抽屉（回归：递归 bug 曾让它打不开）
  await page.locator(".tt-row").first().dblclick();
  await sleep(400);
  check("双击打开维护抽屉", (await page.locator("#task-drawer.open").count()) === 1);
  await page.keyboard.press("Escape");
  await sleep(300);
  check("Esc 关闭抽屉", (await page.locator("#task-drawer.open").count()) === 0);

  // 同一条再双击一次就收起。双击是唯一的打开手势，没有反手势就只能去够右上角。
  await page.locator(".tt-row").first().dblclick();
  await sleep(250);
  const openThen = (await page.locator("#task-drawer.open").count()) === 1;
  await page.locator(".tt-row").first().dblclick();
  await sleep(250);
  check(
    "同一条再双击一次收起",
    openThen && (await page.locator("#task-drawer.open").count()) === 0,
  );

  // 关闭按钮必须和标题同行、贴在抽屉右缘。
  // 以前 badge/title/close/tags 挤在同一个 flex-wrap 容器里，标题一长就把关闭挤到
  // 下一行 —— 表现就是「关闭」显示在任务信息底下，而且长得和其它图标按钮一样。
  await page.locator(".tt-row").first().dblclick();
  await page.waitForSelector("#task-drawer.open");
  const closeBox = await page.evaluate(() => {
    const close = document.querySelector("#task-drawer .dr-close");
    // 头部那个任务名（只读展示）。可编辑的输入框在下面的「任务定义」区里，
    // 同一个字段只有一处输入 —— 这里要量的是「关闭有没有和头部同一行」
    const title = document.querySelector("#task-drawer .dr-name");
    const root = document.querySelector("#task-drawer");
    if (!close || !title || !root) return null;
    const c = close.getBoundingClientRect();
    const t = title.getBoundingClientRect();
    const r = root.getBoundingClientRect();
    return {
      sameRow: Math.abs(c.top - t.top) < 8,
      gapFromRight: Math.round(r.right - c.right),
      side: Math.round(c.width),
    };
  });
  check(
    "关闭按钮与标题同行且贴右缘",
    closeBox !== null && closeBox.sameRow && closeBox.gapFromRight < 30 && closeBox.side >= 24,
    JSON.stringify(closeBox),
  );

  // 切页自动收起：抽屉讲的是「这一页的这条任务」，翻到别的模块还挂着它说不清是谁的
  await page.locator('.rail-btn[data-page="graph"]').click();
  await sleep(300);
  check("切页自动收起任务抽屉", (await page.locator("#task-drawer.open").count()) === 0);
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(250);

  // 右侧只有一块地方：两个抽屉同时开只会互相盖住
  await page.locator(".tt-row").first().dblclick();
  await page.waitForSelector("#task-drawer.open");
  await page.click("#set-btn");
  await sleep(350);
  const both = await page.evaluate(() => ({
    task: document.querySelector("#task-drawer")?.classList.contains("open") === true,
    set: document.querySelector("#set-drawer")?.classList.contains("open") === true,
  }));
  check("设置与任务抽屉不同时打开", both.set && !both.task, JSON.stringify(both));
  await page.click("#set-close");
  await sleep(250);

  // 编辑标题（回归：标题、标签、截止曾经全是只读节点）
  // 挑一条「待办」的：已完成的任务按设计不会被标成逾期，拿它测逾期等于测了个空。
  //
  // 压测数据下先筛出待办：按截止排序时，排在最前的那批几乎都是逾期 / 已完成
  // （截止早 = 早过期），待办要筛出来才看得见
  await page.click("#page-tasks .tools .chip:has-text('待办')");
  await sleep(300);
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
  // 恢复「全部」：下面要测「截止挪到过去 → 自动逾期」，而逾期在「待办」筛选下看不见
  await page.click("#page-tasks .tools .chip:has-text('全部')");
  await sleep(300);

  // 设成过去的日期 → 应被自动标为逾期。
  // 起点是带时分的那一行（容器里有时刻框），开始那行没有 —— 这就是
  // 「开始只到日期、结束带时分」在 DOM 上的样子
  const endDate = page.locator("#task-drawer .dt:has(.dt-time) .dt-date");
  await endDate.fill("2026-09-01");
  await sleep(350);
  const badge = (await page.locator("#task-drawer .dr-h .st").textContent()) ?? "";
  check("结束早于今天自动标逾期", badge.includes("逾期"), badge.trim());

  // 清除结束 → 退回待办
  await page.click("#task-drawer .dt:has(.dt-time) .dt-quick button:has-text('清除')");
  await sleep(350);
  const badge2 = (await page.locator("#task-drawer .dr-h .st").textContent()) ?? "";
  check("清除结束后退回待办", !badge2.includes("逾期"), badge2.trim());

  // 结束时间能填时分。列表行上的「⏰ …」显示的正是这个时刻 ——
  // 以前这里只有一个日期框，列表上却写着「今天 15:00」，没有地方能改它
  await endDate.fill("2026-09-18");
  await page.fill("#task-drawer .dt:has(.dt-time) .dt-time", "15:30");
  await sleep(350);
  // 必须限定在这一条任务的行上：直接取 .dlt 会拿到表里第一行（另一条任务）的截止
  const dueCell = page.locator(".tt-row", { hasText: "改过标题的任务" }).locator(".dlt").first();
  check(
    "结束时分写进了列表行的 ⏰",
    ((await dueCell.textContent()) ?? "").includes("15:30"),
    (await dueCell.textContent())?.trim(),
  );

  // 进度可以直接键入，不用来回蹭滑杆
  await page.fill("#task-drawer .pct-input", "65");
  await page.locator("#task-drawer .pct-input").press("Enter");
  await sleep(300);
  check(
    "进度可以直接指定",
    (await page.locator("#task-drawer .pct-input").inputValue()) === "65" &&
      (await page.locator("#task-drawer .range").inputValue()) === "65",
    `输入框 ${await page.locator("#task-drawer .pct-input").inputValue()} · 滑杆 ${await page.locator("#task-drawer .range").inputValue()}`,
  );

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

  // 新建任务：页头按钮 → 对话框，一次把状态、优先级、起止时间填全。
  // 原来那个「快速新建」输入框只能填名称和标签，建出来的永远是「待办 + 普通 +
  // 无起止」，必须再开抽屉补一遍 —— 那正是它被撤掉的原因。
  await page.click("#page-tasks .ph button");
  await page.waitForSelector(".modal-card.wide");
  await page.fill(".modal-card .dr-title", "冒烟新建的任务");
  await page.fill(".modal-card .dr-tags", "#学习");
  await page.click(".modal-card .chip:has-text('进行中')");
  await page.click(".modal-card .urg-pick:has-text('紧急')");
  // 结束时间是必填（没有截止的任务在建的时候就不该存在）
  await page.click(".modal-card .dt:has(.dt-time) .dt-quick button:has-text('今天')");
  await sleep(150);
  await page.click(".modal-card .modal-actions button:has-text('创建')");
  await sleep(450);

  const created = page.locator(".tt-row", { hasText: "冒烟新建的任务" }).first();
  check(
    "新建对话框建出的任务带着状态与优先级",
    (await created.count()) === 1 &&
      (await created.locator(".tt-bar.st-doing").count()) === 1 &&
      (await created.locator(".urg.u0").count()) === 1,
  );

  // 总览是**事件驱动**重画的（onDataChange → render），页面一直挂在 DOM 里，
  // 所以这里站在任务页就能验总览：还在后台的那一页有没有跟着变。
  // 「刚刚」以前落到排序键 0，会被排到「按时间倒序」的最底下、进不了前 7 条 ——
  // 现象就是「总览没刷新」，其实是刷新了、只是排在看不见的地方
  const feedTop = await page.evaluate(() =>
    [...document.querySelectorAll("#page-overview .feed-item")]
      .slice(0, 3)
      .map((node) => node.textContent ?? ""),
  );
  check(
    "新建的任务排在总览近期活动的第一条（不必切页刷新）",
    (feedTop[0] ?? "").includes("冒烟新建的任务"),
    feedTop.join(" ⟂ "),
  );

  // 列表上的优先级徽标必须和编辑界面里选中的那个一致：当初那个 8px 圆点其实
  // 是**状态色**，优先级根本没画出来，两边对不上就是这么来的
  await created.dblclick();
  await page.waitForSelector("#task-drawer.open");
  check(
    "抽屉里的优先级与列表徽标一致",
    (await page.locator("#task-drawer .urg-pick.on .urg.u0").count()) === 1,
  );

  // 活动记录：发送即保存，而且写错了能改、能删
  await page.fill("#task-drawer .tl-compose input", "先写一条记录");
  await page.locator("#task-drawer .tl-compose input").press("Enter");
  await sleep(300);
  const entry = page.locator("#task-drawer .tl-entry", { hasText: "先写一条记录" }).first();
  check("追加记录后立刻出现在时间线上", (await entry.count()) === 1);

  await entry.hover();
  await entry.locator(".tl-op:has-text('编辑')").click();
  await page.fill("#task-drawer .tl-edit", "改过的记录");
  await page.locator("#task-drawer .tl-edit").press("Enter");
  await sleep(300);
  const edited = page.locator("#task-drawer .tl-entry", { hasText: "改过的记录" }).first();
  check(
    "记录可编辑且标出「已编辑」",
    (await edited.count()) === 1 && (await edited.locator(".tl-edited").count()) === 1,
    (await edited.textContent())?.trim().slice(0, 40),
  );

  await edited.hover();
  await edited.locator(".tl-op:has-text('删除')").click();
  await sleep(300);
  check(
    "记录可删除",
    (await page.locator("#task-drawer .tl-entry", { hasText: "改过的记录" }).count()) === 0,
  );

  // 改状态必须留痕。以前四个入口（总览勾选框 / 任务页右键菜单 / 管理页批量 / 抽屉
  // 状态按钮）没有一处写活动记录：勾了完成，近期活动里没有这一条，「本周完成」也
  // 只能拿结束日去猜完成时间 —— 刚完成一个结束日在上周的任务，统计里就数不到它。
  const badgeBefore = await page.evaluate(
    () => document.querySelector("#task-drawer .dr-h .st")?.textContent ?? "",
  );
  await page.click("#task-drawer .chip:has-text('已完成')");
  await sleep(300);
  const entries = await page.evaluate(() =>
    [...document.querySelectorAll("#task-drawer .tl-entry")].map((n) =>
      (n.textContent ?? "").trim(),
    ),
  );
  const statusBadge = await page.evaluate(
    () => document.querySelector("#task-drawer .dr-h .st")?.textContent ?? "",
  );
  // 记的时间戳是「刚刚」那一刻，显示成绝对日期 —— 不再是「刚刚」这个词
  // （那个词隔一夜就读不通了：「刚刚完成」的记录第二天还写着刚刚）
  check(
    "改状态会留一条活动记录（近期活动 / 本周完成才数得到）",
    entries.some(
      (text) => /\d{2}-\d{2} \d{2}:\d{2}/.test(text) && text.includes("→ 已完成"),
    ),
    `徽标 ${badgeBefore}→${statusBadge} · ${entries.length} 条 · ${entries.slice(0, 3).join(" / ").slice(0, 70)}`,
  );

  // 底部那两个按钮随即时保存一起撤了：所有字段本来就是改完即存，
  // 「保存」按钮只是把抽屉收起来 —— 名字在骗人
  check(
    "抽屉底部不再有删除 / 保存",
    (await page.locator("#task-drawer .dr-f").count()) === 0,
  );
  await page.keyboard.press("Escape");
  await sleep(300);

  // ── 标签：带不带 # 都认，最多 3 个，标签不是固定集合 ──
  // 以前解析只认带 `#` 的写法，「学习 新标签」会被解析成空数组，再被兜底成单个
  // #工作 —— 用户看到的就是「我维护了好几个标签，列表里只剩一个」
  await page.click("#page-tasks .ph button");
  await page.waitForSelector(".modal-card.wide");
  await page.fill(".modal-card .dr-title", "多标签任务");
  await page.fill(".modal-card .dr-tags", "学习 新标签 生活 多余的");
  await page.click(".modal-card .dt:has(.dt-time) .dt-quick button:has-text('今天')");
  await sleep(200);
  await page.click(".modal-card .modal-actions button:has-text('创建')");
  await sleep(450);

  // 先搜出来再断言：100 条数据下这张表按截止排序，今天截止的新任务排在几十条
  // 逾期任务**后面**，多半不在当前这一页上 —— 直接 locator 一行都匹配不到，
  // 表现就是「(没有标签)」这种看不出所以然的失败（曾经当成 flaky 放过去两次）
  await page.fill("#page-tasks .searchbox input", "多标签任务");
  await sleep(350);
  const multi = page.locator(".tt-row", { hasText: "多标签任务" }).first();
  const rowTags = await multi.locator(".lt2 .tag").allTextContents();
  check(
    "不带 # 的多个标签能入库，最多 3 个",
    rowTags.length === 3 && rowTags.join(" ") === "#学习 #新标签 #生活",
    rowTags.join(" ") || "(没有标签)",
  );
  check(
    "标签独立成行（和截止分开）",
    (await multi.locator(".lt1 .dlt").count()) === 1 &&
      (await multi.locator(".lt2 .dlt").count()) === 0,
  );
  // 搜索词留着会污染后面的用例（它们按行文案找元素）
  await page.fill("#page-tasks .searchbox input", "");
  await sleep(300);

  // 焦点时间轴（今天档）以前把「没有时刻」的任务整条丢掉 —— 新建时的时分是可选的，
  // 于是「今天到期、没填时分」的任务在轴上永远不出现，看着就是「显示不全」。
  // 现在它们列在轴下方的「未排时刻」里；顺带量一下有没有互相遮挡/溢出卡片：
  // 第一版把它们塞进左侧那条钉住的通道，9 条时压了 6 对，肉眼看只是"有点乱"
  const axis = await page.evaluate(() => {
    const card = document.querySelector("#page-overview .card").getBoundingClientRect();
    const nodes = [
      ...document.querySelectorAll("#page-overview .tdt-p"),
      ...document.querySelectorAll("#page-overview .tdt-chip"),
    ];
    const boxes = nodes.map((n) => {
      const b = n.getBoundingClientRect();
      return { t: (n.textContent ?? "").slice(0, 12), x: b.x, y: b.y, w: b.width, h: b.height };
    });
    const overlaps = [];
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i];
        const b = boxes[j];
        if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) {
          overlaps.push(`${a.t}×${b.t}`);
        }
      }
    }
    return {
      chips: [...document.querySelectorAll("#page-overview .tdt-chip")].map((n) => n.textContent ?? ""),
      bubbles: [...document.querySelectorAll("#page-overview .tdt-p")].map(
        (n) => n.textContent ?? "",
      ),
      overlapCount: overlaps.length,
      overlapSample: overlaps.slice(0, 4),
      spilled: boxes.filter((b) => b.y + b.h > card.bottom).length,
    };
  });
  // 轴改成「活动驱动」：只列这一天的活动记录（含新建任务那一条），没动静的任务
  // 不占位置。以前这里列的是任务本身，于是「今天到期但没排时刻」和「今天根本
  // 没动过」混在一处 —— 前者是排布问题，后者压根不该出现在这条轴上。
  // 同一分钟里新建了好几条时会合成一簇，气泡上不再写「创建任务」而是「N 条」——
  // 两种形态都算「出现在今天的轴上」，簇里的明细由下面「点开簇」那条断言兜住
  check(
    "新建的任务的活动出现在今天的轴上",
    axis.bubbles.some((text) => text.includes("创建任务") || /\d{2}:\d{2}–\d{2}:\d{2}/.test(text)),
    axis.bubbles.join(" | ").slice(0, 120),
  );
  check(
    "今天没有活动的任务不占轴",
    ![...axis.bubbles, ...axis.chips].some((text) => text.includes("多标签任务")),
    axis.chips.join(" | ").slice(0, 120),
  );
  check(
    "焦点时间轴不互相遮挡、不溢出卡片",
    axis.overlapCount === 0 && axis.spilled === 0,
    `重叠 ${axis.overlapCount} 对 ${axis.overlapSample.join(" ")} · 溢出 ${axis.spilled} 个`,
  );

  // 档位窗口以前是写死的一张日期表（本周 = 9/7–9/13），于是总览的「本周」和任务页
  // 的「本周」是同一个按钮名、两个窗口，换一天打开就整体错位。现在两边都读
  // data/timeline.ts 那一处定义，这里按真实日历算出期望区间再比对。
  const focusDayMs = 86400000;
  const focusTodayNum = Math.floor(
    Date.UTC(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()) / focusDayMs,
  );
  const mdText = (day) => {
    const d = new Date(day * focusDayMs);
    return `${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
  };
  // 上面的断言都是 evaluate 里读的（隐藏页也读得到），这里要真点档位按钮，得先切过去
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(250);
  const focusCard = page.locator("#page-overview .card", {
    has: page.locator(".t", { hasText: "焦点时间轴" }),
  });
  const focusDesc = async () => (await focusCard.locator(".d").first().textContent()) ?? "";
  const pickFocus = async (label) => {
    await focusCard.locator(".seg button", { hasText: label }).click();
    await sleep(250);
    return focusDesc();
  };

  const monday = focusTodayNum - ((new Date(focusTodayNum * focusDayMs).getUTCDay() + 6) % 7);
  const weekDesc = await pickFocus("本周");
  check(
    "总览「本周」的窗口 = 真实这一周（与任务页同一份定义）",
    weekDesc.includes(`${mdText(monday)} – ${mdText(monday + 6)}`),
    weekDesc.trim(),
  );

  const monthStart = Math.floor(
    Date.UTC(new Date().getFullYear(), new Date().getMonth(), 1) / focusDayMs,
  );
  const monthDays = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate();
  const monthDesc = await pickFocus("本月");
  check(
    "总览「本月」的窗口 = 真实这一月（天数随月份走）",
    monthDesc.includes(`${mdText(monthStart)} – ${mdText(monthStart + monthDays - 1)}`),
    monthDesc.trim(),
  );
  await pickFocus("今天");

  // 计数口径：右上角那个数必须等于「轴上的活动 + 时刻在轴外的」。过期那批是任务
  // 维度的提示、不属于这一天的活动，单独列在下面并另行报数 —— 混在一起就会出现
  //「今日到期 2，轴上却排着 7 条」
  const tally = await page.evaluate(() => {
    const card = [...document.querySelectorAll("#page-overview .card")].find(
      (node) => node.querySelector(".t")?.textContent === "焦点时间轴",
    );
    const rows = [...(card?.querySelectorAll(".tdt-untimed") ?? [])];
    const chipsOf = (label) => {
      const row = rows.find((node) => node.querySelector(".lbl")?.textContent === label);
      return row ? row.querySelectorAll(".tdt-chip").length : 0;
    };
    return {
      label: card?.querySelector(".dim.mono")?.textContent ?? "",
      bubbles: card?.querySelectorAll(".tdt-p").length ?? 0,
      untimed: chipsOf("时刻在轴外"),
      late: chipsOf("已过期未完成"),
    };
  });
  const axisCount = Number(/^(\d+)\s*(?:项|条活动|处)/.exec(tally.label)?.[1] ?? -1);
  check(
    "今天档的计数 = 轴上的标记 + 时刻在轴外的（过期那批另外报数）",
    axisCount === tally.bubbles + tally.untimed,
    `${tally.label.trim()} · 轴 ${tally.bubbles} + 轴外 ${tally.untimed} · 过期 ${tally.late}`,
  );
  // 挤在一起时同侧自动多开一条道，而不是「切甘特」：甘特的粒度是天，今天的十几条
  // 活动切过去全落在同一格里，照样叠着，还把时刻弄丢了
  const lanes = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#page-overview .tdt-p")].map((p) => {
      const b = p.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y) };
    });
    const atSameX = new Map();
    for (const r of rows) atSameX.set(r.x, (atSameX.get(r.x) ?? 0) + 1);
    return {
      total: rows.length,
      distinctY: new Set(rows.map((r) => r.y)).size,
      stacked: rows.length === 0 ? 0 : Math.max(...atSameX.values()),
    };
  });
  check(
    "同一时刻的活动被分到不同道（不互相压住）",
    lanes.stacked <= 1 || lanes.distinctY >= lanes.stacked,
    `${lanes.total} 个气泡 · ${lanes.distinctY} 个不同高度 · 同一时刻最多 ${lanes.stacked} 条`,
  );

  // mock 里下午 14:02–15:03 那 7 条是刻意造的密集数据：轴上必须合成一簇，而不是
  // 靠加道把轴撑高；点开簇要能看全里面每一条
  const clusterText = await page.evaluate(() => {
    const pill = [...document.querySelectorAll("#page-overview .tdt-p.st-plain")].find((n) =>
      /\d+ 条$/.test((n.textContent ?? "").trim()),
    );
    return [
      pill ? pill.textContent.trim() : "",
      [...document.querySelectorAll("#page-overview .tdt-p")].map((n) => n.textContent.trim()),
    ];
  });
  check(
    "密集时段在轴上合成一簇",
    /\d{2}:\d{2}–\d{2}:\d{2}/.test(clusterText[0]),
    `${clusterText[0] || "没找到簇"} · 轴上共 ${clusterText[1].length} 个标记`,
  );

  await page.locator("#page-overview .tdt-p.st-plain").first().click();
  await sleep(300);
  const clusterDetail = await page.evaluate(() => {
    const row = [...document.querySelectorAll("#page-overview .tdt-untimed")].find((n) =>
      /^\d{2}:\d{2}–\d{2}:\d{2}$/.test(n.querySelector(".lbl")?.textContent?.trim() ?? ""),
    );
    return row ? row.querySelectorAll(".tdt-chip").length : -1;
  });
  check("点开簇看得到里面每一条", clusterDetail >= 3, `明细 ${clusterDetail} 条`);

  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(250);

  // 必填：任务名 / 标签 / 结束时间，缺一个都不落库
  await page.click("#page-tasks .ph button");
  await page.waitForSelector(".modal-card.wide");
  await page.fill(".modal-card .dr-title", "缺东西的任务");
  await page.click(".modal-card .modal-actions button:has-text('创建')");
  await sleep(350);
  check(
    "缺标签或结束时间时拒绝创建并提示",
    (await page.locator(".modal-card.wide").count()) === 1 &&
      ((await page.locator("#toast").textContent()) ?? "").includes("还差") &&
      (await page.locator(".tt-label", { hasText: "缺东西的任务" }).count()) === 0,
    (await page.locator("#toast").textContent())?.trim(),
  );
  await page.keyboard.press("Escape");
  await sleep(300);

  // ── 图谱：标签集合按数据现算，多标签任务连到它的每一条标签 ──
  await page.locator('.rail-btn[data-page="graph"]').click();
  await page.waitForSelector(".gcanvas .node");
  await sleep(600);

  const newTagNode = page.locator(".gcanvas .node.tag", { hasText: "#新标签" });
  check(
    "新标签在图上自动成为节点",
    (await newTagNode.count()) >= 1,
    (await page.locator(".gcanvas .node.tag").allTextContents()).join(" "),
  );

  // 分区名和标签名可能一字不差（分区「工作」、标签「#工作」）：中心节点必须自带
  // 「分区」小签，标签节点必须带 `#` —— 两者靠记法分开，不靠读者去比字
  const graphNames = await page.evaluate(() => ({
    core: document.querySelector(".gcanvas .node.partition")?.textContent ?? "",
    tags: [...document.querySelectorAll(".gcanvas .node.tag")].map((n) => n.textContent ?? ""),
  }));
  check(
    "分区节点与标签节点不混淆",
    graphNames.core.includes("分区") &&
      graphNames.tags.every((tag) => tag.startsWith("#") || tag === "未分类"),
    `中心「${graphNames.core}」· 标签 ${graphNames.tags.join(" ")}`,
  );

  // 中心节点那两行文字要真的在圆心：`.node` 只给了 place-items（交叉轴），
  // 分区节点换成 flex 列之后主轴要靠 justify-content —— 少那一行，文字会贴着圆顶
  // 排（实测偏上 19px），而这类偏差肉眼只会觉得「有点怪」
  const centered = await page.evaluate(() => {
    const node = document.querySelector(".gcanvas .node.partition");
    const spans = [...node.querySelectorAll("span")];
    const r = node.getBoundingClientRect();
    const first = spans[0].getBoundingClientRect();
    const last = spans[spans.length - 1].getBoundingClientRect();
    const cx = r.x + r.width / 2;
    const cy = r.y + r.height / 2;
    return {
      dxName: Math.round(Math.abs(first.x + first.width / 2 - cx)),
      dxBadge: Math.round(Math.abs(last.x + last.width / 2 - cx)),
      dyBlock: Math.round(Math.abs((first.y + last.bottom) / 2 - cy)),
    };
  });
  check(
    "中心节点的名称与「分区」签居中",
    centered.dxName <= 1 && centered.dxBadge <= 1 && centered.dyBlock <= 1,
    JSON.stringify(centered),
  );

  await newTagNode.first().click();
  await sleep(300);
  check(
    "点标签节点能看到挂在它下面的任务（含锚在别处的多标签任务）",
    ((await page.locator(".gdetail").textContent()) ?? "").includes("多标签任务"),
    ((await page.locator(".gdetail").textContent()) ?? "").trim().slice(0, 60),
  );

  await page.locator('.rail-btn[data-page="tasks"]').click();
  await page.waitForSelector(".tt-row");
  await sleep(300);

  // 草稿：批量对话框里打了一半的内容，关掉窗口 / 刷新都不该丢
  // （原来这一条测的是「快速新建」输入框，那个框撤了之后挪到这里）
  await page.click("button:has-text('批量')");
  await page.waitForSelector(".modal-card textarea");
  await page.fill(".modal-card textarea", "- [ ] 打了一半的任务");
  await sleep(700); // 草稿是防抖写的，等它落盘
  await page.keyboard.press("Escape");
  await sleep(300);

  await page.reload({ waitUntil: "networkidle" });
  await page.locator(".rail-btn").nth(1).click();
  await page.waitForSelector(".tt-row");
  await page.click("#page-tasks .seg button:has-text('本月')");
  await sleep(350);
  await page.click("button:has-text('批量')");
  await sleep(700);
  check(
    "刷新后批量草稿还在",
    (await page.locator(".modal-card textarea").inputValue()) === "- [ ] 打了一半的任务" &&
      (await page.locator(".modal-card .draft-bar").isVisible()),
  );

  await page.click(".modal-card .draft-bar button:has-text('丢弃草稿')");
  await sleep(250);
  check(
    "丢弃草稿后草稿条消失",
    (await page.locator(".modal-card textarea").inputValue()) === "" &&
      !(await page.locator(".modal-card .draft-bar").isVisible()),
  );
  await page.keyboard.press("Escape");
  await sleep(300);

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
  // 压测数据下（一屏最多 ROW_LIMIT 行），新任务可能排在那一屏之外 ——
  // 所以判据是「搜得到」（确实入库），而不是「就在当前这一屏里」
  await page.fill("#page-tasks .searchbox input", "批量");
  await sleep(350);
  check(
    "批量建出两条（非任务行被跳过）",
    (await page.locator(".tt-label", { hasText: "批量一" }).count()) === 1 &&
      (await page.locator(".tt-label", { hasText: "批量二" }).count()) === 1,
  );
  await page.fill("#page-tasks .searchbox input", "");
  await sleep(300);

  // 批量提交成功后不该留着草稿 —— 下次打开又冒出上次那十行内容很吓人
  await page.click("button:has-text('批量')");
  await sleep(350);
  check("批量提交后草稿已清", !(await page.locator(".modal-card .draft-bar").isVisible()));
  await page.keyboard.press("Escape");
  await sleep(250);

  // ── 方言里的「活动行」：任务下面缩进的一行，属于它的活动时间线 ──────────────
  // 活动分析导出的清单就是这个形状（标签 → 任务 → 活动三层），迁移旧数据时它是
  // 唯一带着**活动历史**的载体 —— 不带这一条，导进来就只剩标题
  await page.click("button:has-text('批量')");
  // 批量对话框是普通 .modal-card（.wide 那个是「新建任务」的表单宽版）
  await page.waitForSelector(".modal-card .md");
  await page.fill(
    ".modal-card .md",
    "- [~] 带活动历史的任务 #迁移 ⏰09-30 :: 60%\n" +
      "   - 08-25 16:50 记一条进展\n" +
      "   - 09-09 08:47 记第二条进展",
  );
  await sleep(250);
  const withActivity = await page.locator(".modal-detail").last().textContent();
  check("带活动行的粘贴按「一条任务」预览", withActivity.includes("将创建 1 条"), withActivity.trim());
  await page.click(".modal-actions button:has-text('创建')");
  await sleep(450);

  await page.fill("#page-tasks .searchbox input", "带活动历史");
  await sleep(350);
  await page.locator(".tt-row", { hasText: "带活动历史" }).first().dblclick();
  await page.waitForSelector("#task-drawer.open");
  await sleep(300);
  const timelineText = ((await page.locator("#task-drawer").textContent()) ?? "").replace(/\s+/g, " ");
  check(
    "导入的活动行进了时间线，且按「新的在前」排",
    timelineText.includes("记一条进展") &&
      timelineText.includes("记第二条进展") &&
      timelineText.indexOf("09-09") < timelineText.indexOf("08-25"),
    timelineText.slice(0, 140),
  );
  check(
    "带了活动行就不再补一条「导入任务」",
    !timelineText.includes("导入任务"),
    timelineText.slice(0, 140),
  );
  await page.keyboard.press("Escape");
  await sleep(300);
  await page.fill("#page-tasks .searchbox input", "");
  await sleep(300);

  // 切分区：切到「学习」应当**空出来**（演示数据统一收进演示空间，见 mock.ts
  // 的 SEED_TASKS），切回演示空间又是一批
  const before = await page.locator(".tt-row").count();
  await page.click("#part-btn");
  await sleep(150);
  await page.click(".part-item[data-part='study']");
  await sleep(400);
  const after = await page.locator(".tt-row").count();
  check("切分区换一批数据", after !== before, `${before} -> ${after}`);
  check("切到没有数据的「学习」分区是空的", after === 0, `${after} 条`);

  // 下面几条（活动报告搜索、图谱）都要有数据可看，切回演示空间再跑
  await page.click("#part-btn");
  await sleep(150);
  await page.click(".part-item[data-part='demo']");
  await sleep(400);

  // 活动报告搜索
  await page.locator(".rail-btn").nth(3).click();
  // 限定在活动页里等：全局的 `.empty` 会先匹配到任务页那个（display:none），
  // 于是永远等不到「可见」，报的是超时而不是真正的失败原因
  await page.waitForSelector("#page-activity .act-item, #page-activity .empty");
  const all = await page.locator(".act-item").count();
  await page.fill(".act-search", "zzz不可能匹配zzz");
  await sleep(250);
  const filtered = await page.locator(".act-item").count();
  check("活动报告搜索能过滤", all > 0 && filtered === 0, `${all} -> ${filtered}`);
  // 清掉搜索词再往下走：搜索框是模块级单实例，值会跨重画保留。留着它的话，
  // 后面所有跟条数、空态有关的断言都在「筛掉一切」的状态下量 —— 看着通过，
  // 其实什么都没验证（这一条就是被它坑出来的）。
  await page.fill(".act-search", "");
  await sleep(250);
  check("清空搜索后恢复全部", (await page.locator(".act-item").count()) > 0);

  // 热力图：一年 = 12 个月块，每块一张**完整月历**。
  //
  // 这段断言也换过几轮，教训是别把当下的实现抄成期望值：第一版断言「应 3 月@0
  // 4 月@1」——那正是重叠 -5px 的症状，测试替 bug 签了字；之后又有一版按行优先
  // 追加格子，而 CSS 是列优先填充，于是整年 361 个日期全落在错误的行上，当时的
  // 断言只看几何、看不出日期错位。现在按「逐格核对日历」来断言：每个月的格子数
  // 必须等于该月真实天数、日期不重不漏、每一格都落在它该在的行和列上。
  const heat = await page.evaluate(() => {
    const area = document.querySelector(".hm-area");
    const areaBox = area.getBoundingClientRect();
    const problems = [];

    const blocks = [...document.querySelectorAll(".hm-mo")].map((node, index) => {
      const box = node.getBoundingClientRect();
      const weeks = Number(
        getComputedStyle(node.querySelector(".hm-grid")).getPropertyValue("--weeks"),
      );
      const cells = [...node.querySelectorAll(".hc")];
      const dates = [];

      cells.forEach((cell, i) => {
        const row = i % 7;
        const col = Math.floor(i / 7);
        if (cell.classList.contains("blank")) {
          // 空白只能出现在首末两列（月历本来就有半截的周），中间有空洞就是丢日期
          if (col !== 0 && col !== weeks - 1) problems.push(`${index + 1} 月第 ${col} 列中间有空洞`);
          return;
        }
        const iso = cell.title.slice(0, 10);
        const [y, m, d] = iso.split("-").map(Number);
        const date = new Date(Date.UTC(y, m - 1, d));
        if (m - 1 !== index) problems.push(`${index + 1} 月块里出现 ${iso}`);
        if ((date.getUTCDay() + 6) % 7 !== row) problems.push(`${iso} 行错位`);
        if (col >= weeks) problems.push(`${iso} 列错位`);
        dates.push(iso);
      });

      const daysInMonth = new Date(Date.UTC(2026, index + 1, 0)).getUTCDate();
      if (new Set(dates).size !== daysInMonth) {
        problems.push(`${index + 1} 月 ${new Set(dates).size} 天 ≠ ${daysInMonth} 天`);
      }
      if (dates.length !== new Set(dates).size) problems.push(`${index + 1} 月有重复日期`);

      return {
        label: node.querySelector(".hm-mo-t").textContent,
        left: Math.round(box.left - areaBox.left),
        right: Math.round(box.right - areaBox.left),
        dateLabels: [...node.querySelectorAll(".hm-weeks span")].map((s) => Number(s.textContent)),
      };
    });

    // 第一块的第一列（7 个格子）中心 y，对照左侧星期列
    const firstCol = [...document.querySelectorAll(".hm-mo:first-child .hm-grid .hc")].slice(0, 7);
    const rows = firstCol.map((n) => {
      const box = n.getBoundingClientRect();
      return Math.round(box.y + box.height / 2);
    });
    const labelCenters = [...document.querySelectorAll(".hm-lab span:not(.hm-sp)")].map((n) => {
      const box = n.getBoundingClientRect();
      return Math.round(box.y + box.height / 2);
    });

    return {
      blocks,
      problems: problems.slice(0, 6),
      problemCount: problems.length,
      areaWidth: Math.round(areaBox.width),
      dayLabels: [...document.querySelectorAll(".hm-lab span:not(.hm-sp)")].map((n) => n.textContent),
      rowDrift: rows.map((y, index) => Math.round(Math.abs(y - labelCenters[index]))),
      cell: getComputedStyle(document.querySelector(".hm")).getPropertyValue("--cell").trim(),
      year: document.querySelector(".hmyear")?.textContent ?? "",
    };
  });

  check(
    "每个月的格子数 = 该月真实天数，且不重不漏",
    heat.problemCount === 0,
    heat.problemCount ? heat.problems.join(" | ") : `12 个月块 · 格子 ${heat.cell}`,
  );
  check(
    "月份块不重叠、标签覆盖 1–12 月",
    heat.blocks.map((b) => b.label).join("") ===
      Array.from({ length: 12 }, (_, i) => `${i + 1} 月`).join("") &&
      heat.blocks.slice(1).every((b, i) => heat.blocks[i].right <= b.left),
    heat.blocks.map((b) => b.label).join(" "),
  );
  check(
    "每列都有一个日期序号，且逐列递增",
    heat.blocks.every(
      (b) => b.dateLabels.length > 0 && b.dateLabels.every((n, i) => i === 0 || n > b.dateLabels[i - 1]),
    ),
    heat.blocks.map((b) => `${b.label}:${b.dateLabels.join("/")}`).join("  "),
  );
  check(
    "周几标签逐行对齐且周一开头",
    heat.dayLabels.join("") === "周一周二周三周四周五周六周日" && heat.rowDrift.every((d) => d <= 2),
    `${heat.dayLabels.join(" ")} · 偏移 ${heat.rowDrift.join("/")}px`,
  );
  check(
    "热力图左右铺满（不挤在左侧）",
    heat.blocks[0].left <= 1 && heat.areaWidth - heat.blocks[heat.blocks.length - 1].right <= 1,
    `左 ${heat.blocks[0].left}px · 右空 ${heat.areaWidth - heat.blocks[heat.blocks.length - 1].right}px`,
  );

  // 范围条的位置：横跨整页、压在「标签筛选 + 活动报告」两列之上。
  // 它同时管左边标签行的条数和右边报告的内容，塞进任何一张卡里都会显得
  // 只作用于那一张。
  const barBox = await page.evaluate(() => {
    const bar = document.querySelector("#page-activity .act-filter").getBoundingClientRect();
    const split = document.querySelector("#page-activity .split-filter").getBoundingClientRect();
    const heat = document.querySelector("#page-activity .card").getBoundingClientRect();
    return {
      above: Math.round(split.top - bar.bottom) >= 0,
      sameWidth: Math.abs(bar.width - split.width) < 2,
      belowHeat: Math.round(bar.top - heat.bottom) >= 0,
      width: Math.round(bar.width),
    };
  });
  check(
    "范围条横跨整页、压在报告区之上",
    barBox.above && barBox.sameWidth && barBox.belowHeat,
    JSON.stringify(barBox),
  );

  // 年份切换：热力图换一年，下面的活动报告跟着换窗口
  const reportRangeText = () =>
    page.locator(".act-filter .d.mono").textContent();
  const reportCountText = () =>
    page.evaluate(() => {
      // 报告卡 = .split-filter 里的第二张（左边那张是标签筛选）。
      // 范围条已经移到两列之上、不再是卡片的一部分，不能靠它来定位了。
      const card = document.querySelectorAll("#page-activity .split-filter .card")[1];
      return card?.querySelector(".card-h .d")?.textContent?.trim() ?? "?";
    });

  const yearNow = heat.year;
  await page.locator(".hmyear").locator("xpath=preceding-sibling::button[1]").click();
  await sleep(350);
  const yearPrev = await page.locator(".hmyear").textContent();
  check(
    "年份切换翻到上一年，且报告范围跟着走",
    yearPrev === yearNow.replace(/(\d+)/, (m) => String(Number(m) - 1)) &&
      (await reportRangeText()).includes(String(Number(yearNow.match(/\d+/)[0]) - 1)),
    `${yearNow} → ${yearPrev} · 报告 ${(await reportRangeText())?.trim()}`,
  );
  await page.locator(".hmyear").click();
  await sleep(350);
  check("点年份回到今年", (await page.locator(".hmyear").textContent()) === yearNow);

  // 报告快捷范围：每个档位都要真的换窗口，且条数随之变化
  const ranges = [
    ["今天", 1],
    ["昨天", 1],
    ["本周", 7],
    ["上周", 7],
    ["本月", 30],
    ["全年", 365],
  ];
  let rangeBad = "";
  for (const [label, spanDays] of ranges) {
    await page.locator(`.act-filter .chip:has-text('${label}')`).click();
    await sleep(220);
    const text = (await reportRangeText())?.trim() ?? "";
    const [from, to] = text.split(" · ")[0].split(" – ");
    const days = to
      ? (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400000 + 1
      : 1;
    if (days !== spanDays) rangeBad += `${label}:${days}≠${spanDays} `;
  }
  check("报告快捷范围各自覆盖正确的天数", rangeBad === "", rangeBad.trim() || "今天/昨天/本周/上周/本月/全年");

  // 指定范围：两个日期框只在选中这一档时才出现 —— 平时摆着两个空日期框，
  // 会被读成结果的一部分，也说不清和哪一档有关
  check("未选「指定范围」时不显示日期框", (await page.locator(".act-date").count()) === 0);
  await page.locator(".act-filter .chip:has-text('指定范围')").click();
  await sleep(250);
  check(
    "选中后出现两个日期框，且默认是今天",
    (await page.locator(".act-date").count()) === 2 &&
      ((await reportRangeText()) ?? "").trim().split(" ")[0] ===
        new Date().toISOString().slice(0, 10),
    `${await page.locator(".act-date").count()} 个 · ${(await reportRangeText())?.trim()}`,
  );

  await page.locator(".act-date").first().fill("2026-09-08");
  await page.locator(".act-date").nth(1).fill("2026-09-09");
  await sleep(300);
  check(
    "指定范围能过滤报告",
    ((await reportRangeText()) ?? "").trim().startsWith("2026-09-08 – 2026-09-09"),
    (await reportRangeText())?.trim(),
  );

  await page.locator(".act-filter .chip:has-text('全年')").click();
  await sleep(250);
  const yearCount = await reportCountText();
  await page.locator(".hm-mo:nth-child(9) .hc.h2").first().click();
  await sleep(300);
  const dayCount = await reportCountText();
  check(
    "点热力图上的一天，报告切到那一天",
    ((await reportRangeText()) ?? "").includes("2026-09-") &&
      !((await reportRangeText()) ?? "").includes(" – ") &&
      (await page.locator(".act-filter .chip.on").textContent()) === "指定范围",
    `${yearCount} → ${dayCount} · ${(await reportRangeText())?.trim()}`,
  );
  // 范围一缩小，标签列表和报告的标签切换必须同步：两边都只保留「这个范围里有
  // 活动」的标签。曾经左边列着 0 条的标签（没活动），右边 ▶ 还能翻到它、报告一片
  // 空白 —— 两边单看都没错，摆在一起就是不一致。
  await page.locator(".act-filter .chip:has-text('今天')").click();
  await sleep(300);
  const tagSync = await page.evaluate(() => {
    const card = document.querySelector("#page-activity .split-filter .card");
    const rows = [...card.querySelectorAll(".tagrow")].filter((r) => r.children.length >= 3);
    return {
      tags: rows.map((r) => r.children[1].textContent),
      counts: rows.map((r) => Number(r.children[2].textContent.replace(/\D/g, ""))),
      hint: card.querySelector(".tagrow.dim")?.textContent ?? "",
    };
  });
  check(
    "标签列表只留当前范围有活动的标签，且不解释被隐藏的",
    tagSync.counts.length > 0 && tagSync.counts.every((n) => n >= 1) && tagSync.hint === "",
    `${tagSync.tags.join(" ")} · ${tagSync.hint || "无额外提示"}`,
  );

  await page.locator("#page-activity .split-filter .card .btn:has-text('全选')").click();
  await sleep(300);
  const reportCardSel = "#page-activity .split-filter .card:nth-child(2)";
  const visited = [];
  for (let i = 0; i < tagSync.tags.length; i += 1) {
    visited.push({
      tag: await page.locator(`${reportCardSel} .card-h .mono`).textContent(),
      empty: await page.locator(`${reportCardSel} .empty`).count(),
    });
    await page.locator(`${reportCardSel} .navbtn`).nth(1).click();
    await sleep(200);
  }
  check(
    "报告的标签切换不会翻到没活动的标签",
    visited.length === tagSync.tags.length && visited.every((v) => v.empty === 0),
    visited.map((v) => `${v.tag}${v.empty ? "(空)" : ""}`).join(" "),
  );

  await page.locator(".act-filter .chip:has-text('全年')").click();
  await sleep(250);

  // 换配色：色阶变量 --h0..--h4 挂在 data-scheme 上，按钮得真的改到它
  const schemeBefore = await page.evaluate(() => {
    const cell = document.querySelector(".hm .hc.h1, .hm .hc.h2, .hm .hc.h3, .hm .hc.h4");
    return {
      scheme: document.documentElement.dataset.scheme,
      color: cell ? getComputedStyle(cell).backgroundColor : "",
    };
  });
  await page.locator(".hmsw").nth(1).click();
  await sleep(200);
  const schemeAfter = await page.evaluate(() => {
    const cell = document.querySelector(".hm .hc.h1, .hm .hc.h2, .hm .hc.h3, .hm .hc.h4");
    return {
      scheme: document.documentElement.dataset.scheme,
      color: cell ? getComputedStyle(cell).backgroundColor : "",
      onIndex: [...document.querySelectorAll(".hmsw")].findIndex((n) => n.classList.contains("on")),
    };
  });
  check(
    "色板能换配色且选中态跟着走",
    schemeBefore.scheme !== schemeAfter.scheme &&
      schemeBefore.color !== schemeAfter.color &&
      schemeAfter.onIndex === 1,
    `${schemeBefore.scheme}/${schemeBefore.color} → ${schemeAfter.scheme}/${schemeAfter.color}`,
  );
  await page.locator(".hmsw").nth(0).click();
  await sleep(150);

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

  // 标题栏左上角只留软件名：图标在任务栏 / 托盘 / 安装包上已经见过一遍，标题栏里
  // 再来一张是同一句话重复三遍；版本号挪去设置 → 关于，那里读的是真实版本
  const bar = await page.evaluate(() => ({
    brand: document.querySelector(".brand")?.textContent?.trim() ?? "",
    logo: document.querySelectorAll(".titlebar .logo").length,
    ver: document.querySelectorAll(".titlebar .ver").length,
  }));
  check(
    "标题栏左上角只有软件名",
    bar.brand === "Tadado2" && bar.logo === 0 && bar.ver === 0,
    JSON.stringify(bar),
  );

  // 设置一页到底（2026-09-17 撤掉页签）：分三页时每页只剩两三行，翻页成本比滚动
  // 高，还得记住「口令在哪一页」。整页从上到下：外观 → 窗口 → 分区 → 关于
  await page.click("#set-btn");
  await page.waitForSelector("#set-drawer.open");
  const shape = await page.evaluate(() => ({
    tabs: document.querySelectorAll("#set-tabs").length,
    titles: [...document.querySelectorAll("#set-body .set-sec-t")].map((n) =>
      (n.textContent ?? "").trim(),
    ),
  }));
  check(
    "设置不再分页签，一页到底",
    shape.tabs === 0 && ["外观", "启动", "分区", "关于"].every((t) => shape.titles.includes(t)),
    `页签 ${shape.tabs} 个 · ${shape.titles.join("/")}`,
  );

  // 「关于」是按实际功能写的介绍：应用名 / 一句话定位 / 功能与特色两份清单 /
  // 版本号（浏览器预览拿不到 Tauri 的版本，这里显示的是兜底值，同样带 v）
  const about = await page.evaluate(() => {
    const sec = [...document.querySelectorAll("#set-body .set-sec")].find((node) =>
      node.querySelector(".about"),
    );
    return {
      name: sec?.querySelector(".about-name")?.textContent?.trim() ?? "",
      lead: sec?.querySelector(".about-lead")?.textContent?.trim() ?? "",
      groups: [...(sec?.querySelectorAll(".about-h") ?? [])].map((n) => n.textContent?.trim()),
      items: sec?.querySelectorAll(".about-list li").length ?? 0,
      ver: document.getElementById("set-ver")?.textContent?.trim() ?? "",
    };
  });
  check(
    "关于：应用名 / 定位 / 功能与特色清单都在",
    about.name === "Tadado2" &&
      about.lead.length > 10 &&
      about.groups.join("/") === "功能/特色" &&
      about.items >= 8 &&
      /^v\d/.test(about.ver),
    JSON.stringify(about),
  );

  // 开机自启动：浏览器预览里问不到系统（autostart 插件不在），那一行要标成不可用 ——
  // 而不是摆一个点了没反应的开关
  const autostart = await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-body .set-row")].find((r) =>
      (r.textContent ?? "").includes("开机自启动"),
    );
    const sw = row?.querySelector(".sw") ?? null;
    return { exists: sw !== null, disabled: sw?.classList.contains("disabled") === true };
  });
  check("设置里有「开机自启动」，浏览器里标成不可用", autostart.exists && autostart.disabled, JSON.stringify(autostart));

  // 窗口置顶只留标题栏图钉一个入口：它是「现在就要这个窗口浮上来」的动作，不是
  // 一条要翻两层菜单去改的偏好 —— 设置里那一行是图钉的第二个入口，撤了
  const pinEntry = await page.evaluate(() => ({
    inSettings: [...document.querySelectorAll("#set-body .set-row")].some((r) =>
      (r.textContent ?? "").includes("置顶"),
    ),
    inTitlebar: document.querySelectorAll("#tb-pin").length,
  }));
  check(
    "窗口置顶只留标题栏图钉一个入口",
    !pinEntry.inSettings && pinEntry.inTitlebar === 1,
    JSON.stringify(pinEntry),
  );

  // 切到别的模块就收起 —— 和「编辑任务」抽屉一样：设置讲的是外壳与分区，翻页后
  // 还挂在这儿，看上去像新页面里长出来的一层，也说不清它属于谁
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(300);
  check(
    "切到别的模块自动收起设置",
    (await page.locator("#set-drawer.open").count()) === 0,
    await page.evaluate(
      () => document.querySelector("#set-drawer")?.className ?? "?",
    ),
  );

  await page.click("#set-btn");
  await page.waitForSelector("#set-drawer.open");

  // 分区能增删：新建的分区必须**同时**出现在 rail 底部那个切换器里 ——
  // 那个菜单若只在启动时画一次，新分区就永远切不过去
  await page.click("#set-part button:has-text('新建分区')");
  await page.waitForSelector(".mask .pr-input");
  await page.fill(".mask .pr-input", "临时区");
  await page.click(".modal-actions button:has-text('创建')");
  await sleep(350);
  const added = await page.evaluate(() => ({
    panel: [...document.querySelectorAll("#set-part .set-row")].some((r) =>
      (r.textContent ?? "").includes("临时区"),
    ),
    menu: [...document.querySelectorAll(".part-item")].some(
      (n) => (n.textContent ?? "").includes("临时区"),
    ),
  }));
  check("新建分区后切换器里也有它", added.panel && added.menu, JSON.stringify(added));

  // 有任务的分区不给删：删了那批任务就跟着没了，而往哪儿迁用户没得选 —— 所以
  // 按钮直接置灰并写明还剩几条。
  // 挑「演示空间」：演示数据现在只有这一个分区有，另外三个是空的（删得掉）
  const busyDrop = await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("演示空间"),
    );
    const del = [...(row?.querySelectorAll("button") ?? [])].find(
      (b) => (b.textContent ?? "").trim() === "删除",
    );
    return { disabled: del?.disabled ?? null, title: del?.title ?? "" };
  });
  check(
    "有任务的分区删除按钮是灰的",
    busyDrop.disabled === true && busyDrop.title.includes("先移走"),
    JSON.stringify(busyDrop),
  );

  // 空的分区能删：面板和切换器要一起少一个 —— 只从面板里消失的话，切换器还留着
  // 一个点了就跳去空分区的入口
  await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("临时区"),
    );
    [...(row?.querySelectorAll("button") ?? [])]
      .find((b) => (b.textContent ?? "").trim() === "删除")
      ?.click();
  });
  await page.waitForSelector(".modal-actions button:has-text('删除')");
  await page.click(".modal-actions button:has-text('删除')");
  await sleep(350);
  const removed = await page.evaluate(() => ({
    panel: [...document.querySelectorAll("#set-part .set-row")].some((r) =>
      (r.textContent ?? "").includes("临时区"),
    ),
    menu: [...document.querySelectorAll(".part-item")].some(
      (n) => (n.textContent ?? "").includes("临时区"),
    ),
  }));
  check("删掉的分区两处一起消失", !removed.panel && !removed.menu, JSON.stringify(removed));

  // 默认分区：**启动时进哪个区**，和「现在在哪个区」是两回事 —— 切分区是随时都在
  // 做的事，默认不跟着切。一组分区里只能有一个，所以画成单选点
  const defaultState = async () =>
    page.evaluate(() => {
      const rows = [...document.querySelectorAll("#set-part .set-row")].filter((r) =>
        r.querySelector(".part-dot"),
      );
      return {
        count: rows.length,
        on: rows
          .filter((r) => r.querySelector(".part-dot.on"))
          .map((r) => (r.textContent ?? "").trim()),
      };
    });
  const pickDefault = async (name) => {
    await page.evaluate((text) => {
      const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
        (r.textContent ?? "").trim().startsWith(text),
      );
      row?.querySelector(".part-dot")?.click();
    }, name);
    await sleep(300);
  };
  await pickDefault("学习");
  const defaultAfter = await defaultState();
  check(
    "默认分区只有一个、能改",
    defaultAfter.count >= 3 &&
      defaultAfter.on.length === 1 &&
      defaultAfter.on[0].startsWith("学习"),
    JSON.stringify(defaultAfter),
  );

  // 自动归档 / 空闲锁定默认关、是少数人用得着的那类设置，所以收在分区行尾
  // 「自动 ▾」里：四项分区各挂两个常年不动的 seg，. 一页就全被挤没了
  const collapsed = await page.evaluate(() =>
    [...document.querySelectorAll("#set-part .part-more")].every((n) => n.hidden === true),
  );
  check("分区的自动归档 / 空闲锁定默认收起", collapsed);

  await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("工作"),
    );
    [...(row?.querySelectorAll("button") ?? [])]
      .find((b) => (b.textContent ?? "").includes("自动"))
      ?.click();
  });
  await sleep(250);

  // 自动归档是**按分区**设的：改「工作」这一档，别的分区不受影响。
  // 摆成全局值时 —— 工作区的东西该收走，个人区那几条想留着翻，
  // 一个值只能取折中，两头都不对
  const archiveValue = async () =>
    page.evaluate(() => {
      const row = [...document.querySelectorAll("#set-part .part-more .set-row")].find((r) =>
        (r.textContent ?? "").includes("自动归档"),
      );
      return row?.querySelector(".seg button.on")?.textContent?.trim() ?? "";
    });
  const archiveBefore = await archiveValue();
  const pickArchive = async (label) => {
    await page.evaluate((text) => {
      const row = [...document.querySelectorAll("#set-part .part-more .set-row")].find((r) =>
        (r.textContent ?? "").includes("自动归档"),
      );
      [...(row?.querySelectorAll(".seg button") ?? [])]
        .find((b) => (b.textContent ?? "").trim() === text)
        ?.click();
    }, label);
    await sleep(300);
  };
  await pickArchive("7 天");
  const archiveAfter = await archiveValue();
  check(
    "自动归档默认关、能改",
    archiveBefore === "关" && archiveAfter === "7 天",
    `${archiveBefore} → ${archiveAfter}`,
  );
  // 拨回去：后面的用例还在数任务条数
  await pickArchive("关");
  check("自动归档能拨回关", (await archiveValue()) === "关", await archiveValue());

  // 分区口令 → 切过去被挡 → 错口令不放行 → 对口令解锁。
  // 给「工作」上锁（当前停在「学习」）：给正在看的分区上锁会立刻把设置面板
  // 自己挡住 —— 那是缺陷，不是这里要测的场景。
  // 口令是**某个分区**的属性，所以跟着分区那一行。
  await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("工作"),
    );
    [...(row?.querySelectorAll("button") ?? [])]
      .find((b) => (b.textContent ?? "").trim() === "设口令")
      ?.click();
  });
  await page.waitForSelector(".mask .pr-input");
  await page.fill(".mask .pr-input", "1234");
  await page.click(".modal-actions button:has-text('设置')");
  await sleep(400);

  // 设 / 改 / 清是**同一个入口**：按钮文字始终是「设口令」，设没设用点亮表示 ——
  // 拆成三个按钮，用户每次都得先判断自己处在哪种状态
  const passState = await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("工作"),
    );
    const pass = [...(row?.querySelectorAll("button") ?? [])].find(
      (b) => (b.textContent ?? "").trim() === "设口令",
    );
    return { text: pass?.textContent?.trim() ?? "", on: pass?.classList.contains("on") ?? null };
  });
  check(
    "设过口令后「设口令」点亮，不换成别的按钮",
    passState.text === "设口令" && passState.on === true,
    JSON.stringify(passState),
  );

  // 再点开它：里面既能改（填新口令）也能清（那个 danger 按钮），
  // 不需要旧口令 —— 它挡的是路过的人，没有「证明你是你」的必要
  await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("工作"),
    );
    [...(row?.querySelectorAll("button") ?? [])]
      .find((b) => (b.textContent ?? "").trim() === "设口令")
      ?.click();
  });
  await page.waitForSelector(".mask .pr-input");
  const passDialog = await page.evaluate(() => ({
    title: document.querySelector(".mask .modal-title")?.textContent?.trim() ?? "",
    actions: [...document.querySelectorAll(".mask .modal-actions button")].map((b) =>
      (b.textContent ?? "").trim(),
    ),
  }));
  check(
    "同一个口令弹窗里能改也能清",
    passDialog.title.includes("工作") &&
      passDialog.actions.includes("清除") &&
      passDialog.actions.includes("保存"),
    JSON.stringify(passDialog),
  );
  await page.keyboard.press("Escape");
  await sleep(300);

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
    (await page.locator(".lock-screen.show").count()) === 1 && hint.includes("错误"),
    hint.trim(),
  );

  await page.fill(".lock-screen .pr-input", "1234");
  await page.keyboard.press("Enter");
  await sleep(400);
  check("正确口令解锁", (await page.locator(".lock-screen.show").count()) === 0);

  // 默认分区说的是**下次启动进哪个区**，不重启就验不到：上面把默认改成了「学习」，
  // reload 之后 rail 底部那个切换器应当停在「学习」，而不是列表第一个「工作」
  await page.reload();
  await page.waitForSelector("#part-btn");
  await sleep(700);
  const bootedInto = await page.evaluate(() => document.querySelector("#part-btn")?.title ?? "");
  check("重启后进入默认分区", bootedInto.includes("学习"), bootedInto);

  // 忘了口令的出口：**锁屏上能直接开设置**。锁屏盖住整个应用，而重设口令不需要
  // 旧口令（它只挡路过的人）—— 没有这个入口就是死循环：想改口令先得进得去，
  // 进得去又得先知道口令。重启后切到「工作」（上面那条用例给它设过口令）
  await page.click("#part-btn");
  await sleep(200);
  await page.click(".part-item[data-part='work']");
  await sleep(400);
  check("重启后切到上锁分区照样挡一层", (await page.locator(".lock-screen.show").count()) === 1);

  await page.click(".lock-screen .modal-actions button:has-text('设置')");
  await page.waitForSelector("#set-drawer.open");
  const stack = await page.evaluate(() => {
    const z = (selector) => {
      const node = document.querySelector(selector);
      return node ? Number(getComputedStyle(node).zIndex) : null;
    };
    return { drawer: z("#set-drawer"), lock: z(".lock-screen"), rail: z(".rail") };
  });
  check(
    "锁屏上能打开设置：抽屉压在锁屏之上，侧栏仍被盖着",
    stack.drawer > stack.lock && stack.lock > (stack.rail ?? 0),
    JSON.stringify(stack),
  );

  // 在设置里清掉它：弹窗（.mask）也得浮在锁屏之上，否则点不到「清除」
  await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("工作"),
    );
    [...(row?.querySelectorAll("button") ?? [])]
      .find((b) => (b.textContent ?? "").trim() === "设口令")
      ?.click();
  });
  await page.waitForSelector(".mask .pr-input");
  const maskStack = await page.evaluate(() => {
    const z = (selector) => {
      const node = document.querySelector(selector);
      return node ? Number(getComputedStyle(node).zIndex) : null;
    };
    return { mask: z(".mask"), lock: z(".lock-screen") };
  });
  check(
    "口令弹窗也压在锁屏之上",
    (maskStack.mask ?? 0) > (maskStack.lock ?? 0),
    JSON.stringify(maskStack),
  );
  await page.click(".mask .modal-actions button:has-text('清除')");
  await sleep(450);
  check("清掉口令后锁屏自己收起", (await page.locator(".lock-screen.show").count()) === 0);
  await page.click("#set-close");
  await sleep(250);

  // 报告卡头那个计数说的是**当前标签**有多少条，所以它得挨着标签名 ——
  // 挂在标题旁边会被读成「整份报告共几条」（报告是按标签翻页的，两个数不是一回事）
  const countSpot = await page.evaluate(() => {
    const head = document
      .querySelectorAll("#page-activity .split-filter .card")[1]
      ?.querySelector(".card-h");
    const kids = [...(head?.children ?? [])];
    const title = head?.querySelector(".t") ?? null;
    const label = head?.querySelector(".mono") ?? null;
    const count = head?.querySelector(".d") ?? null;
    // 头部的两个按钮就是 ◀ ▶（导出已经挪到范围条了）
    const next = head?.querySelectorAll("button")[1] ?? null;
    return {
      found: count !== null,
      // 在标签切换组的**外面**：紧跟 ▶ 之后，不在 ◀ #标签 ▶ 中间
      outsideToggle: next && count ? kids.indexOf(count) === kids.indexOf(next) + 1 : false,
      // 更不能被当成标签名的一部分
      afterLabel: label && count ? kids.indexOf(count) === kids.indexOf(label) + 1 : false,
      notByTitle: title && count ? kids.indexOf(count) - kids.indexOf(title) > 1 : false,
      text: count?.textContent?.trim() ?? "",
    };
  });
  check(
    "活动报告：条数在标签切换组外面、也不挂在标题旁",
    countSpot.found &&
      countSpot.outsideToggle &&
      !countSpot.afterLabel &&
      countSpot.notByTitle,
    JSON.stringify(countSpot),
  );

  // ── 导出：md / txt / xlsx，两个页面同一套 ───────────────────────────────────
  // 以前两个页面各导出各的（管理页 .md 方言、活动页 .csv），「导出」在同一个应用
  // 里是两种互不相干的东西。现在统一：md 与 txt 内容一致（与 python 版同一份
  // 排版），xlsx 是同一批数据的表格形态。
  // 回到演示空间：导出这两段要有数据可导（锁屏那一段把自己切到了「工作」，
  // 而它是空的）
  await page.click("#part-btn");
  await sleep(150);
  await page.click(".part-item[data-part='demo']");
  await sleep(350);
  await page.locator('.rail-btn[data-page="activity"]').click();
  // 限定在活动页里等：全局的 `.empty` 先匹配到任务页那个（display:none）
  await page.waitForSelector("#page-activity .act-item, #page-activity .empty");
  await sleep(250);

  const openExport = async (scope) => {
    await page.locator(`${scope} button:has-text('导出')`).first().click();
    await page.waitForSelector(".ctx-menu");
  };
  const grab = async (scope, label) => {
    await openExport(scope);
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.locator(".ctx-menu .menu-item", { hasText: label }).click(),
    ]);
    const file = join(TMP, download.suggestedFilename());
    await download.saveAs(file);
    return { name: download.suggestedFilename(), file };
  };

  // 导出与「范围」同一行：范围（含它的区间说明）从左排起，导出是一个**独立的
  // 按钮**钉在这行最右 —— 两者之间由弹性空白分开。它不属于报告卡，也不属于页头
  const spot = await page.evaluate(() => {
    const bar = document.querySelector("#page-activity .act-filter");
    const kids = [...(bar?.children ?? [])];
    const button =
      [...(bar?.querySelectorAll("button") ?? [])].find((b) =>
        (b.textContent ?? "").includes("导出"),
      ) ?? null;
    const chips = bar?.querySelector(".chips") ?? null;
    const barBox = bar?.getBoundingClientRect() ?? null;
    const btnBox = button?.getBoundingClientRect() ?? null;
    return {
      inBar: button !== null,
      // 最右：这一行最后一个元素，且前面是一段弹性空白（不是紧跟档位）
      last: button !== null && kids.indexOf(button) === kids.length - 1,
      afterSpacer: button?.previousElementSibling?.classList.contains("grow") === true,
      // 光有 grow 类不够：它的样式是按容器作用域写的，漏一条就是宽 0、按钮纹丝不动
      // （出过这个 bug：类名在、位置没变）。所以这里量真几何：按钮右边缘要贴着
      // 范围条的右内边距
      flushRight:
        barBox && btnBox ? Math.round(barBox.right - btnBox.right) <= 18 : false,
      rightOfChips: chips && button ? kids.indexOf(button) > kids.indexOf(chips) : false,
      inReport: [...document.querySelectorAll("#page-activity .split-filter button")].filter(
        (b) => (b.textContent ?? "").includes("导出"),
      ).length,
      inPageHead: document.querySelectorAll("#page-activity .ph button").length,
    };
  });
  check(
    "活动分析：导出与范围同行、独立按钮置最右",
    spot.inBar &&
      spot.last &&
      spot.afterSpacer &&
      spot.flushRight &&
      spot.rightOfChips &&
      spot.inReport === 0 &&
      spot.inPageHead === 0,
    JSON.stringify(spot),
  );

  await openExport(".act-filter");
  const formats = await page.evaluate(() =>
    [...document.querySelectorAll(".ctx-menu .menu-item")].map((n) => (n.textContent ?? "").trim()),
  );
  check(
    "导出菜单给出 md / txt / xlsx 三种格式",
    formats.length === 3 &&
      formats.some((t) => t.includes(".md")) &&
      formats.some((t) => t.includes(".txt")) &&
      formats.some((t) => t.includes(".xlsx")),
    formats.join(" / "),
  );
  await page.keyboard.press("Escape");
  await sleep(150);

  const actMd = await grab(".act-filter", "Markdown");
  const actTxt = await grab(".act-filter", "文本");
  const actXlsx = await grab(".act-filter", "表格");

  const actMdText = readFileSync(actMd.file, "utf8");
  const actTxtText = readFileSync(actTxt.file, "utf8");

  // md：三层结构（标签分块 / `1.` 有序任务 / 缩进 3 格的 `-` 活动），文件头那行
  // `<!-- … -->` 元信息已经去掉。标签行是 `#后端` —— **`#` 后不留空格**，
  // 留了 md 就把它当一级标题渲染成一行大号字，比任务本身还抢眼
  check(
    "导出的 md 是三层结构、标签行不是一级标题、且不含文件头",
    /^#\S/m.test(actMdText) &&
      !/^# \S/m.test(actMdText) &&
      /^\d+\. /m.test(actMdText) &&
      /^ {3}- /m.test(actMdText) &&
      !actMdText.includes("<!--") &&
      actMd.name.endsWith(".md"),
    actMdText.split("\n").slice(0, 3).join(" ⏎ "),
  );

  // txt：层次一样，但一个 md 语法符号都不许出现 —— 它的用途就是丢给不认 markdown
  // 的地方（记事本、工单），在那里 `# 后端` 会被原样显示、`- ` 会变成一串小横杠
  const mdSyntaxInTxt = actTxtText
    .split("\n")
    .filter((line) => /^#|^- |^\d+\. |^ {3}- /.test(line));
  check(
    "导出的 txt 用中性符号（【】/ 1)/ ·），不含 md 语法",
    /^【.+】$/m.test(actTxtText) &&
      /^ {2}\d+\) /m.test(actTxtText) &&
      /^ {5}· /m.test(actTxtText) &&
      mdSyntaxInTxt.length === 0 &&
      !actTxtText.includes("<!--") &&
      actTxt.name.endsWith(".txt"),
    mdSyntaxInTxt.length > 0
      ? `混进 md 语法的行：${mdSyntaxInTxt.slice(0, 2).join(" / ")}`
      : actTxtText.split("\n").slice(0, 3).join(" ⏎ "),
  );

  // 时间统一成绝对日期：界面上写「今天 / 昨天」更好读，但那是**会变**的 ——
  // 同一个活动今天导出写「昨天」、明天导出写「前天」，而文件要存档、要发给别人
  const relativeWords = [actMdText, actTxtText].map(
    (text) => (text.match(/(?:今天|昨天|刚刚)/g) ?? []).length,
  );
  check(
    "导出的时间戳一律是绝对日期（今天 / 昨天 / 刚刚 都已换算）",
    relativeWords.every((count) => count === 0) &&
      /^ {3}- \d{2}-\d{2} \d{2}:\d{2} /m.test(actMdText) &&
      /^ {5}· \d{2}-\d{2} \d{2}:\d{2} /m.test(actTxtText),
    relativeWords.join(" / "),
  );

  // 活动记的是**已经发生的事**，所以导出里不该出现比今天还晚的时间。
  // 压测数据曾经把「创建任务」记在 `min(截止日, 昨天)` 上，于是截止日已过的任务
  // 那条活动恰好等于截止日（连钟点都一样）—— 看着就像「创建于截止日」
  const todayMD = (() => {
    const now = new Date();
    return `${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  })();
  const futureActs = [...actMdText.matchAll(/^ {3}- (\d{2}-\d{2}) \d{2}:\d{2} /gm)]
    .map((match) => match[1])
    .filter((monthDay) => monthDay > todayMD);
  check(
    "导出的活动时间都不晚于今天",
    futureActs.length === 0,
    futureActs.length > 0 ? futureActs.slice(0, 3).join(", ") : `今天 ${todayMD}`,
  );

  // 两份内容不再逐字相同（符号不同），但**标签、任务、活动要一一对应**
  const shapeOf = (text) => ({
    tags: (text.match(/^(?:#\S|【).*$/gm) ?? []).length,
    tasks: (text.match(/^(?: {0,2})\d+[.)] /gm) ?? []).length,
    acts: (text.match(/^(?: {3}- | {5}· )/gm) ?? []).length,
  });
  check(
    "md 与 txt 的三层数量一一对应",
    JSON.stringify(shapeOf(actMdText)) === JSON.stringify(shapeOf(actTxtText)),
    `${JSON.stringify(shapeOf(actMdText))} vs ${JSON.stringify(shapeOf(actTxtText))}`,
  );


  const xlsxBytes = readFileSync(actXlsx.file);
  check(
    "导出的 xlsx 是结构完整的 zip（逐项 CRC 校验）",
    zipProblem(xlsxBytes) === "" &&
      xlsxBytes.includes(Buffer.from("xl/worksheets/sheet1.xml")),
    `${actXlsx.name} · ${zipProblem(xlsxBytes) || "5 个条目 · CRC 全对"}`,
  );

  await page.locator('.rail-btn[data-page="manage"]').click();
  await page.waitForSelector("#page-manage .mrow");
  await sleep(250);
  check(
    "任务管理不再有「导入」按钮",
    (await page.locator("#page-manage button:has-text('导入')").count()) === 0,
    `找到 ${await page.locator("#page-manage button:has-text('导入')").count()} 个`,
  );

  // 每页几条：**入口就在分页器上**（不进设置）—— 它只影响眼前这张表
  const rowsInPage = () => page.locator("#page-manage .mrow").count();
  const pageRowsBefore = await rowsInPage();
  await page.locator("#page-manage .pager .dd-btn").click();
  await page.locator("#page-manage .pager .menu-item", { hasText: "30 条/页" }).click();
  await sleep(400);
  const pageRowsAfter = await rowsInPage();
  check(
    "管理页每页条数可调（分页器上的下拉）",
    pageRowsBefore <= 20 && pageRowsAfter > pageRowsBefore,
    `${pageRowsBefore} → ${pageRowsAfter}`,
  );

  // 管理页与活动分析**同一套三层结构**：导入撤了之后，「必须保持 md 方言才能导回来」
  // 这个约束就没有了，两处统一之后用户不用再记「哪个页面给的是哪种格式」
  const manageMd = await grab("#page-manage", "Markdown");
  const manageText = readFileSync(manageMd.file, "utf8");
  check(
    "任务管理导出与活动分析同一套三层结构（md）",
    /^#\S+/m.test(manageText) &&
      /^\d+\. /m.test(manageText) &&
      /^ {3}- \d{2}-\d{2} \d{2}:\d{2} /m.test(manageText) &&
      !manageText.includes("<!--") &&
      !manageText.includes("- [ ]"),
    manageText.split("\n").slice(0, 4).join(" ⏎ "),
  );

  const manageTxt = await grab("#page-manage", "文本");
  const manageTxtText = readFileSync(manageTxt.file, "utf8");
  check(
    "任务管理的 txt 层次一致、且不含 md 语法",
    /^【.+】$/m.test(manageTxtText) &&
      /^ {2}\d+\) /m.test(manageTxtText) &&
      manageTxtText.split("\n").filter((line) => /^#|^- |^\d+\. /.test(line)).length === 0,
    manageTxtText.split("\n").slice(0, 4).join(" ⏎ "),
  );

  const manageXlsx = await grab("#page-manage", "表格");
  check(
    "管理页的 xlsx 同样是完整的 zip",
    zipProblem(readFileSync(manageXlsx.file)) === "",
    manageXlsx.name,
  );

  // 旧数据的迁移：改造前活动时刻存的是展示串（`"昨天 17:20"`），读进来必须先
  // 归一化成时间戳 —— 否则它会一路算成 `NaN-NaN 05:42` 送进导出的文件
  // （05:42 还是 new Date("09-16 13:42") 按本地时区解析、取 UTC 差 8 小时的结果）
  await page.evaluate(() => {
    const raw = JSON.parse(localStorage.getItem("tadado.tasks.v1") ?? "[]");
    if (raw[0]?.activities?.[0]) {
      raw[0].activities[0].at = "昨天 17:20";
      localStorage.setItem("tadado.tasks.v1", JSON.stringify(raw));
    }
  });
  await page.reload();
  await page.waitForSelector(".rail-btn", { timeout: 15000 });
  await sleep(700);

  const migrated = await page.evaluate(() => {
    const raw = JSON.parse(localStorage.getItem("tadado.tasks.v1") ?? "[]");
    const at = raw[0]?.activities?.[0]?.at;
    const shown = document.querySelector("#page-overview .feed-item .tm")?.textContent ?? "";
    return { at, finite: Number.isFinite(at), shown };
  });
  check(
    "旧格式的活动时刻（展示串）读入后被归一化成时间戳",
    migrated.finite && typeof migrated.at === "number" && !migrated.shown.includes("NaN"),
    JSON.stringify(migrated),
  );

  // ── 交付口径：演示空间 100 条，其他分区为空（2026-09-17）────────────────────
  // 样例数据的唯一去处是演示空间：其他三个分区留给用户自己建。100 这个数是
  // mock.ts 的 28（原型手写）+ 72（压测生成），也是性能验收的输入规模 ——
  // 100 条挤在一个分区里，任务页的窗口自适应 / 图谱的力导向 / 管理页的分页
  // 才压得出真实表现。
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(300);

  // 演示数据只在演示空间，另外三个分区是空的（待用户自己往里建）。
  // 不依赖前面几段留下的分区状态 —— 切分区、锁屏、导出各留下过不同的值
  const others = {};
  for (const [id, name] of [
    ["work", "工作"],
    ["study", "学习"],
    ["personal", "个人"],
  ]) {
    await page.click("#part-btn");
    await sleep(180);
    await page.click(`.part-item[data-part='${id}']`);
    await sleep(400);
    others[name] = await page.locator("#page-tasks .tt-row").count();
  }
  check(
    "其他分区为空（演示数据不再散落各分区）",
    Object.values(others).every((count) => count === 0),
    JSON.stringify(others),
  );

  // 回演示空间：下面的一屏断言要在这批数据上量
  await page.click("#part-btn");
  await sleep(180);
  await page.click(".part-item[data-part='demo']");
  await sleep(400);

  // ── 一屏到底（2026-09-17）───────────────────────────────────────────────────
  // 判据不是「没有滚动条」，而是**不用滚就能看到列表与翻页**：页面自身不出现
  // 滚动（scroll ≈ 0）、列表区真的吃到了剩余高度（listH）、工具行 / 分页器的
  // 下沿还在视口里（barBottom ≤ 视口高）。这三条缺一条，用户就还得滚。
  const oneScreen = async (id, listSel, barSel) => {
    await page.locator(`.rail-btn[data-page="${id}"]`).click();
    await sleep(320);
    return page.evaluate(
      ({ pageId, sel, bar }) => {
        const root = document.querySelector(`#page-${pageId}`);
        const list = document.querySelector(sel);
        const anchor = root?.querySelector(bar) ?? null;
        return {
          scroll: root ? root.scrollHeight - root.clientHeight : -1,
          listH: list ? Math.round(list.getBoundingClientRect().height) : 0,
          barBottom: anchor ? Math.round(anchor.getBoundingClientRect().bottom) : 0,
          view: window.innerHeight,
        };
      },
      { pageId: id, sel: listSel, bar: barSel },
    );
  };

  const screens = {
    overview: await oneScreen("overview", "#page-overview .feed", ".card .pager"),
    tasks: await oneScreen("tasks", "#page-tasks .tt-scroll", ".tools"),
    activity: await oneScreen("activity", "#page-activity .act-list", ".pager"),
    manage: await oneScreen("manage", "#page-manage .tabwrap", ".pager"),
  };
  for (const [id, shape] of Object.entries(screens)) {
    check(
      `${id}：一屏装下（页面不滚 · 列表吃满 · 翻页在视口内）`,
      shape.scroll <= 1 &&
        shape.listH > 60 &&
        shape.barBottom > 0 &&
        shape.barBottom <= shape.view,
      JSON.stringify(shape),
    );
  }

  const graphFit = await oneScreen("graph", "#page-graph .gwrap", ".gbar");
  check(
    "graph：舞台吃掉主区剩余高度",
    graphFit.scroll <= 1 && graphFit.listH > 320,
    JSON.stringify(graphFit),
  );

  check("无 console 报错", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));

  // ── 存储版本与读入口归位（2026-09-17）──────────────────────────────────────
  // 放在**最后**：下面几步故意往存储里塞旧结构和坏数据，控制台会出现预期的
  // 警告 —— 那是设计好的行为，不该让上面那条「无 console 报错」变红。
  //
  // 浏览器后端没有 `PRAGMA user_version`（那是 SQLite 文件头里的东西），版本号
  // 落在 kv 的一个 key 上；但**迁移链是同一条**（见 data/schema.ts），
  // 所以 e2e 在浏览器里也能真的验一遍迁移与归位。
  const TASK_KEY = "tadado.tasks.v1";
  const VERSION_KEY = "tadado.schema.version";

  const bootVersion = await page.evaluate((key) => localStorage.getItem(key), VERSION_KEY);
  check("schema 版本号已写进存储", bootVersion === "1", `${VERSION_KEY} = ${bootVersion}`);

  // 老结构的存档：缺后面才加的字段、早期枚举、活动时刻还是展示串，
  // 外加一条连标题都没有的垃圾记录
  const legacy = [
    {
      id: "legacy-1",
      title: "上个版本留下的任务",
      status: "WAITING",
      due: "09-20",
      at: null,
      start: [9, 18],
      end: [9, 20],
      created: [9, 10],
      archived: false,
      activities: [{ at: "昨天 17:20", text: "写了一版", kind: "log" }],
    },
    { id: "legacy-junk", junk: true },
  ];
  await page.evaluate(
    ({ tasks, taskKey, versionKey }) => {
      localStorage.setItem(taskKey, JSON.stringify(tasks));
      // 把版本号抹掉 = 模拟「还没有版本号的老库」：迁移链应当从 0 跑起来
      localStorage.removeItem(versionKey);
    },
    { tasks: legacy, taskKey: TASK_KEY, versionKey: VERSION_KEY },
  );
  await page.reload();
  await page.waitForSelector(".rail-btn");
  // 落盘有 400ms 防抖，等它写完再读
  await sleep(800);

  const afterMigrate = await page.evaluate(
    ({ taskKey, versionKey }) => {
      const raw = localStorage.getItem(taskKey);
      return { version: localStorage.getItem(versionKey), tasks: raw ? JSON.parse(raw) : [] };
    },
    { taskKey: TASK_KEY, versionKey: VERSION_KEY },
  );
  const keptTask = afterMigrate.tasks.find((task) => task.id === "legacy-1");
  // 不比总条数：压测模式下启动会把种子里缺的补进来（见 store.ts 的 bootStore），
  // 库里本该有 legacy-1 加那 100 条种子。这里只关心两件事 —— 这条被救回来了、
  // 那条没有标题的垃圾没被写进去
  check(
    "老结构的存档被归位：缺字段补默认、旧时刻换时间戳、垃圾条丢弃",
    keptTask !== undefined &&
      !afterMigrate.tasks.some((task) => task.id === "legacy-junk") &&
      keptTask.status === "todo" &&
      Array.isArray(keptTask.tags) &&
      keptTask.related.length === 0 &&
      keptTask.urgency === 3 &&
      keptTask.partition === "work" &&
      typeof keptTask.activities[0]?.at === "number",
    JSON.stringify({ version: afterMigrate.version, task: keptTask }),
  );
  check("归位后补上版本号", afterMigrate.version === "1", `version = ${afterMigrate.version}`);

  // 存档彻底坏掉：不能当空库处理（那等于拿演示数据把用户的存档盖掉），
  // 要原样留着 + 给一句人话提示
  await page.evaluate((key) => localStorage.setItem(key, "{ 这不是 JSON"), TASK_KEY);
  await page.reload();
  await page.waitForSelector(".rail-btn");
  await sleep(800);

  const brokenState = await page.evaluate(
    ({ taskKey, versionKey }) => ({
      raw: localStorage.getItem(taskKey),
      toast: document.querySelector("#toast")?.textContent?.trim() ?? "",
      // 内存里也应当没有任务：种子数据**不能**顶上来
      rows: document.querySelectorAll(".tt-row").length,
    }),
    { taskKey: TASK_KEY, versionKey: VERSION_KEY },
  );
  check(
    "存档读不出来时不静默变空库：原样留着 + 明确提示 + 不拿种子顶替",
    brokenState.raw === "{ 这不是 JSON" &&
      brokenState.toast.includes("解析失败") &&
      brokenState.rows === 0,
    JSON.stringify(brokenState),
  );
} finally {
  await browser.close();
  server.kill();
  rmSync(TMP, { recursive: true, force: true });
}

console.log(failures.length === 0 ? "\n全部通过" : `\n失败：${failures.join("、")}`);
process.exit(failures.length === 0 ? 0 : 1);

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
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

const PORT = 4173;
// vite preview 默认只监听 ::1，写 127.0.0.1 会连不上
//
// 别叫 `URL`：模块作用域里的 const 会把全局 `URL` 顶掉，以后谁写一句 `new URL(...)`
// 就会撞上暂时性死区（`Cannot access 'URL' before initialization`）——
// resources/screenshots.mjs 上已经栽过一次，那次是一行看不出毛病的 `new URL`
const PREVIEW = `http://localhost:${PORT}/`;

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

// ─── 日期助手 ────────────────────────────────────────────────────────────────
//
// 这一组是为了掐掉同一类隐患：**测试里的「今天」与真实时钟不一致**。
// 这个仓库已经炸过三次，每次的样子都像被测代码坏了：
//
//   · **写死日期** —— 曾经把 `2026-09-18` 当成「今天」写进测试，两天后它变成了过去，
//     任务按设计被自动标成逾期，于是一条「状态不该被 md 改掉」的断言跟着红。
//   · **UTC 与本地混用** —— `new Date().toISOString().slice(0, 10)` 给的是 **UTC** 日期。
//     东八区每天 00:00–08:00 它都是**昨天**，那条断言于是每天早红八小时。
//   · **跨边界** —— 页面在 10:59 装载、断言在 11:00 求值，问候语差了整整一个整点。
//
// 规矩三条：要「今天」就**现算**；跟本地日历日对齐就**别用 `toISOString`**；
// 任何挨着日期边界的断言都**容许「上一步的值」**（上一分钟 / 上一小时 / 前一天）。
//
// 判据是「将来还会不会自己红」，不是「今天跑不跑得过」：一条只在某些钟点红的断言，
// 红的时候没人会想到是测试自己的问题。

/** 本地日历日 → `YYYY-MM-DD`。 */
const localIso = (date = new Date()) => {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};

/** 今天（**本地**日历日）对应的绝对天数，与数据层 `time.ts` 的 `TODAY` 同一坐标。 */
const todayDay = () => {
  const now = new Date();
  return Math.floor(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / 86400000);
};

/**
 * `[月, 日]` → 绝对天数，年份按「离今天最近的那一年」补。
 *
 * 与 `data/time.ts` 的 `dayNumber` 同一套规则。数据里**不存年**（见 `MonthDay`），
 * 所以比较日期时也不能假设同一年 —— 直接拿 `"MM-DD"` 比字符串，1 月里 12 月的活动
 * 会显得「比今天晚」（跨年倒挂），而它其实是去年 12 月的、早就发生了。
 */
const nearestDay = (month, day) => {
  const today = todayDay();
  const year = new Date(today * 86400000).getUTCFullYear();
  let best = Math.floor(Date.UTC(year, month - 1, day) / 86400000);
  for (const other of [year - 1, year + 1]) {
    const value = Math.floor(Date.UTC(other, month - 1, day) / 86400000);
    if (Math.abs(value - today) < Math.abs(best - today)) best = value;
  }
  return best;
};

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
    ready = (await fetch(PREVIEW)).ok;
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
  await page.goto(PREVIEW, { waitUntil: "networkidle" });
  await page.waitForSelector(".rail-btn", { timeout: 15000 });

  /**
   * 打开「数据迁入」对话框。
   *
   * 入口在**任务管理页**（与「导出 ▾」并排）—— 2026-09-18 从任务页页头搬过来的：
   * 它是「一批一批地处置」，和那页的性格一致，而页头的位置该留给每天都用的「＋ 新建任务」。
   */
  const openImport = async () => {
    await page.locator('.rail-btn[data-page="manage"]').click();
    await sleep(320);
    await page.click('#page-manage button:has-text("数据迁入")');
    await page.waitForSelector(".modal-card .batch-file");
  };

  /**
   * 造一个临时 md 文件并选进「数据迁入」—— 相当于用户点「选择文件…」。
   *
   * 对话框**只吃文件**（没有粘贴框），所以这里必须真写一个文件：
   * `setInputFiles` 对 `display:none` 的 input 同样有效，不需要把它显示出来。
   */
  let fixtureSeq = 0;
  const pickImportFile = async (content) => {
    fixtureSeq += 1;
    const file = join(TMP, `import-${fixtureSeq}.md`);
    writeFileSync(file, content, "utf8");
    await page.setInputFiles(".modal-card input[type=file]", file);
    await sleep(280);
  };

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
  // 容许「上一小时的那个问候」：页面装载与这里算 want 之间可能正好跨过整点
  // （10:59 装载、11:00 断言 —— 页面停在「早上好」是对的，不该判红）。
  // 它真正要抓的是**写死的问候语**：晚上八点说「早上好」，既不是当前值也不是上一小时的值。
  const greetState = await page.evaluate(() => {
    const hour = new Date().getHours();
    const at = (h) =>
      h < 5 ? "夜深了" : h < 11 ? "早上好" : h < 13 ? "中午好" : h < 18 ? "下午好" : "晚上好";
    return {
      hour,
      greet: document.querySelector(".greet .g1")?.textContent ?? "",
      allowed: [at(hour), at((hour + 23) % 24)],
    };
  });
  check(
    "问候语按真实时钟",
    greetState.allowed.includes(greetState.greet),
    `「${greetState.greet}」· 现在 ${greetState.hour} 点 · 合法值 ${greetState.allowed.join(" / ")}`,
  );
  check("问候语里没有占位人名", !greetState.greet.includes("HananxR"), greetState.greet);

  // 焦点时间轴的「现在」也必须指向真实时刻：它以前读 mock 里写死的 09:30
  // （DEMO_NOW_MINUTES），晚上打开也停在上午九点半 —— 这块界面上唯一能证明
  // 「知道现在几点」的地方在说谎。轴的范围是 6:00–24:00
  const nowMark = await page.evaluate(() => {
    const node = document.querySelector("#page-overview .tdt-now");
    return node ? { left: Number.parseFloat(node.style.left), title: node.title } : null;
  });
  const clock = new Date();
  // 与 pages/overview.ts 的 axisPct 同一套：轴只覆盖 06:00–24:00，结果**钳在 0–100**
  // （凌晨的「现在」贴在左端，而不是画到轴外面去）
  const pctAt = (minutes) =>
    Math.max(0, Math.min(100, ((minutes - 6 * 60) / ((24 - 6) * 60)) * 100));
  const dayMinutes = clock.getHours() * 60 + clock.getMinutes();
  // 容许「上一分钟」。两条理由：
  //   ① 标记每分钟才重画一次（且只在总览可见时），这里读的是上一次重画留下的值；
  //   ② 跨午夜时它整段跨过去 —— 23:59 是 99.9%，00:00 是 -27.8%（轴从 6:00 起，
  //      凌晨的「现在」在轴的左边之外）。差一个量级，1.5% 的容差兜不住。
  const expectedPct = [pctAt(dayMinutes), pctAt((dayMinutes + 1439) % 1440)];
  check(
    "焦点时间轴的「现在」指向真实时刻",
    nowMark !== null && expectedPct.some((pct) => Math.abs(nowMark.left - pct) <= 1.5),
    `标记 ${nowMark?.left?.toFixed(1)}% · 应 ${expectedPct.map((p) => p.toFixed(1)).join(" / ")}% · ${nowMark?.title}`,
  );

  // ── 四张表都能翻页、档位一致（100 条数据下才看得出）────────────────────────
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(300);
  const feedBar = await page.evaluate(() => {
    const bar = document.querySelector("#page-overview .ov-right .card .pager");
    return bar
      ? {
          has: true,
          text: bar.textContent ?? "",
          // 卡片头那句后缀（排序口径 + 窗口）
          head: document
            .querySelector("#page-overview .ov-right .card .card-h .d")
            ?.textContent?.trim() ?? "",
          // 分页器第一句（范围那句）
          range: bar.querySelector("span")?.textContent?.trim() ?? "",
          sizes: [...bar.querySelectorAll(".menu-item")].map((n) => n.textContent?.trim()),
          // 当前选中的档位（下拉按钮上的字）：默认值就写在这儿
          pick: bar.querySelector(".dd-btn")?.textContent?.trim() ?? "",
          // 翻页件的个数（一页时应当是 0）
          nav: bar.querySelectorAll(".navbtn").length,
          // 一屏真正摆出来的行数
          rows: document.querySelectorAll("#page-overview .feed-item").length,
        }
      : { has: false, text: "", head: "", range: "", sizes: [], pick: "", nav: -1, rows: -1 };
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

  // 这张卡**只显示最近 50 条**（2026-09-20 用户定的：不想显示太多）。上限做法是
  // 取排序后的前 FEED_LIMIT 条，所以种子的 88 个「动过的任务」到这里只剩 50：
  // 范围正好是 1–50、一屏摆满，而且**只有一页**（一页时不摆翻页箭头）。
  // 88 → 50 这件事必须真的发生，所以这里比的是确认值而不是 \d+
  check(
    "总览近期活动：上限 50 条、默认一屏摆满、只有一页（档位 20/30/50/100）",
    feedBar.has &&
      // 档位只写数（单位由旁边那句范围说明给，说两遍只会更挤）
      feedBar.sizes.join("/") === "20/页/30/页/50/页/100/页" &&
      // 默认 = 上限，一屏看完
      feedBar.pick === "50/页" &&
      // 单位是「个任务」（不是「条」，那是某个任务的活动条数）
      feedBar.range === "第 1–50 个任务" &&
      feedBar.rows === 50 &&
      // 只有一页：一个能按的箭头都没有
      feedBar.nav === 0 &&
      // 卡片头那句后缀给的是**窗口**：`按最近活动倒序 · 前 50 个任务`。
      // 以前写「共 88 个任务」—— 88 是聚合后的任务总数，会被读成「这一屏显示了 88 条」，
      // 跟每屏行数（20/50）不是一回事（2026-09-20 用户报的）
      feedBar.head === "按最近活动倒序 · 前 50 个任务" &&
      !feedBar.text.includes("共"),
    `${feedBar.sizes.join(" / ")} · 当前 ${feedBar.pick} · 头「${feedBar.head}」 · 范围「${feedBar.range}」 · ${feedBar.rows} 行 · 翻页件 ${feedBar.nav}`,
  );

  // 档位下拉必须**真的能选**（2026-09-20 用户报的）：分页器贴在卡片底部，而这几张卡
  // 的正文是 `overflow: hidden`（撑满场景的硬要求）—— 菜单默认向下展开，落在卡外那条
  // 裁切线以下：看得见一截、点不到任何一项。修法是装不下就向上翻（menu.ts 的 openPanel）。
  // 这里量两件事：① 展开后整块菜单在卡片**以内**（没被裁）；② 点一项真的生效
  await page.locator("#page-overview .ov-right .card .pager .dd-btn").click();
  await sleep(220);
  const sizeMenu = await page.evaluate(() => {
    const card = document.querySelector("#page-overview .ov-right .card");
    const menu = card?.querySelector(".pager .menu.open");
    const box = menu?.getBoundingClientRect();
    const cardBox = card?.getBoundingClientRect();
    return {
      open: Boolean(menu),
      up: menu?.classList.contains("up") ?? false,
      inside:
        box && cardBox ? box.bottom <= cardBox.bottom + 1 && box.top >= cardBox.top - 1 : false,
      items: menu?.querySelectorAll(".menu-item").length ?? 0,
    };
  });
  await page.locator("#page-overview .pager .menu-item", { hasText: "20/页" }).click();
  await sleep(320);
  const sizeAfterPick = await page.evaluate(() => ({
    pick: document
      .querySelector("#page-overview .ov-right .card .pager .dd-btn")
      ?.textContent?.trim() ?? "",
    rows: document.querySelectorAll("#page-overview .feed-item").length,
  }));
  check(
    "分页器的档位下拉向上翻（不被卡片裁掉，且选得动）",
    sizeMenu.open &&
      sizeMenu.up &&
      sizeMenu.inside &&
      sizeMenu.items === 4 &&
      sizeAfterPick.pick === "20/页" &&
      sizeAfterPick.rows <= 20,
    `${JSON.stringify(sizeMenu)} → 选中后 ${sizeAfterPick.pick} · ${sizeAfterPick.rows} 行`,
  );
  // 恢复默认档位：后面的断言都按默认 50 看这张卡
  await page.locator("#page-overview .ov-right .card .pager .dd-btn").click();
  await sleep(220);
  await page.locator("#page-overview .pager .menu-item", { hasText: "50/页" }).click();
  await sleep(280);

  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(300);

  // ── 交付口径：启动状态就是「演示空间 100 条，其他分区为空」─────────────────
  // 100 = mock.ts 的 28（原型手写）+ 72（压测生成），也是性能验收的输入规模：
  // 100 条挤在同一个分区里，任务页的窗口自适应 / 图谱的力导向 / 管理页的分页
  // 才压得出真实表现。这条必须放在**早期** —— 后面几段测试会自己建任务，
  // 等到末尾再数就不是启动状态了（那时是 103）
  //
  // 任务页只列**未归档**的，两处一起数才算真的验了 100。
  //
  // 数从工具行那句「筛出 X · 共 N」里的**总数**取，不读分页器上那个数：分页器数的是
  // **筛出来的**，而默认档位是「本周」—— 它会远小于总数，那是筛选的口径，不是数据少了。
  //
  // ⚠️ 两个数都**不写死**（2026-09-21 改口径之后）：默认「完成后归档＝立即」（见 store
  // 的 archiveDays），所以种子一写进库，**所有已完成的任务当场就被收进归档了** ——
  // 「未归档 99 + 归档 1」那个组合不会再出现。到底多少条已完成由生成那 72 条的生成器
  // 决定，写死就会一改生成逻辑就红；这里只钉**恒等式**与「归档明显不止样例那 1 条」。
  const bootTotal = await page.evaluate(() => {
    const tools = document.querySelector("#page-tasks .tools")?.textContent ?? "";
    return Number.parseInt(/共 (\d+)/.exec(tools)?.[1] ?? "-1", 10);
  });

  await page.locator('.rail-btn[data-page="manage"]').click();
  await sleep(350);

  // 管理页页头是一条**单选**：全部状态 / 逾期 / 进行中 / 已完成 / 未归档 / 已归档
  // （2026-09-21 用户定的）。以前是「状态 × 归档」两组 chip，各自「只亮一枚」又挨在一起 ——
  // 看起来像一条单选行里亮了两枚，于是「默认怎么不是全部状态」这个问题才冒出来。
  // 「待办」那枚同一天撤了（状态本身删掉，见 types.ts 的 TaskStatus）
  const viewChips = () =>
    page.evaluate(() => {
      const exportBtn = [...document.querySelectorAll("#page-manage button")].find((node) =>
        (node.textContent ?? "").trim().startsWith("导出"),
      );
      const chips = [...(exportBtn?.parentElement?.querySelectorAll(".chip") ?? [])];
      return {
        all: chips.map((chip) => (chip.textContent ?? "").trim()),
        on: chips
          .filter((chip) => chip.classList.contains("on"))
          .map((chip) => (chip.textContent ?? "").trim()),
      };
    });
  const defaultChips = await viewChips();
  check(
    "管理页筛选是一条单选：6 枚、默认只亮「全部状态」",
    defaultChips.all.join("/") === "全部状态/逾期/进行中/已完成/未归档/已归档" &&
      defaultChips.on.join() === "全部状态",
    JSON.stringify(defaultChips),
  );

  await page.locator("#page-manage .chip:has-text('已归档')").click();
  await sleep(300);
  // 比**总数**（分页器上那句），不是这一页的行数：归档之后必翻页，行数只反映当前页
  const bootArchived = await page.evaluate(() => {
    const bar = document.querySelector("#page-manage .pager")?.textContent ?? "";
    return Number.parseInt(/共 (\d+) 条/.exec(bar)?.[1] ?? "-1", 10);
  });
  check(
    "启动即演示空间 100 条：未归档 + 归档 = 100（默认「立即」已把已完成的收进归档）",
    bootTotal + bootArchived === 100 && bootArchived > 1 && bootTotal < 99,
    `未归档 ${bootTotal} · 归档 ${bootArchived} · 合计 ${bootTotal + bootArchived}`,
  );

  // 把归档筛选拨回默认那档（「未归档」）再回任务页：上面那段动的筛选别留给
  // 后面的用例。归档那排只有两档：未归档 / 已归档（2026-09-21 去掉了「含归档」——
  // 它把两档混着看，而批量归档是按档位执行的动作）
  await page.locator("#page-manage .chip:has-text('未归档')").click();
  await sleep(200);

  // 单选行为：切到「未归档」之后，**仍然只有一枚亮着**（合单之前这里是两枚，
  // 于是「默认怎么不是全部状态」这个问题才冒出来）
  const afterPick = await viewChips();
  check(
    "筛选是一条单选：切到「未归档」之后仍只有它一枚亮着",
    afterPick.all.join("/") === "全部状态/逾期/进行中/已完成/未归档/已归档" &&
      afterPick.on.join() === "未归档",
    JSON.stringify(afterPick),
  );
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(300);

  // 任务页现在默认就列**全部未归档任务**（工具行那排档位 2026-09-21 撤了），80 条天然
  // 就有好几页；而分页器在只有一页时不摆翻页件（`◀ 1 / 1 ▶` 一个都按不动，2026-09-21 减负）
  const tasksPaged = await page.evaluate(() => {
    const bar = document.querySelector("#page-tasks .pager");
    if (!bar) return { has: false, pages: 0, first: "", text: "" };
    return {
      has: true,
      // 分页器那句「1 / 5」里的总页数
      pages: Number(/1 \/ (\d+)/.exec(bar.textContent ?? "")?.[1] ?? 0),
      first: document.querySelector("#page-tasks .tt-row .lt1 .t")?.textContent ?? "",
      text: bar.textContent ?? "",
    };
  });
  check(
    "任务页：任务多于一页时才摆翻页件",
    tasksPaged.pages >= 2,
    `共 ${tasksPaged.pages} 页 · ${tasksPaged.text.trim().slice(0, 44)}`,
  );
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
    // 档位下拉只写数（`20/页`）：单位由紧挨着的那句范围说明给，说两遍更挤（2026-09-21 减负）
    reportPager.has && /\d+\/页/.test(reportPager.text),
    reportPager.text.trim(),
  );

  // ── 总览的数字必须点得开、且对得上 ─────────────────────────────────────────
  // 以前任务页先按档位定窗口、再拿窗口砍任务：总览写「逾期 4」，点进来只有 3 条
  // —— 第 4 条的起止落在窗口外，它没丢，只是没被画出来。现在窗口固定 32 天、
  // **不参与筛选**（档位按「这段时间动过」筛，见 poolTasks）：列表里的行一定画得出来。
  //
  // 名单**从界面上取**（有几张卡就验几张），不再写死一个清单：这条原来列的是
  // 「逾期 / 进行中 / 已完成」三张，「今日到期」是第四张 —— 它的 onClick 漏传了
  // （`tile()` 是「有 onClick 才可点」），卡片上写着 1 条、点上去没反应，
  // 而这条断言因为只盯着那三张，一直没有发现。
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(300);
  const tiles = await page.evaluate(() =>
    [...document.querySelectorAll("#page-overview .tile")].map((node) => ({
      label: node.querySelector(".lbl")?.textContent?.trim() ?? "",
      value: Number.parseInt(node.querySelector(".num")?.textContent ?? "", 10),
      sub: node.querySelector(".delta")?.textContent?.trim() ?? "",
      // tile() 只在给了 onClick 时才加这个类（可点、悬停提示、监听三件事同源）
      clickable: node.classList.contains("clickable"),
    })),
  );
  check(
    "总览的指标卡都点得开（少一张，那张就成了「点了没反应」）",
    // 五张：今日到期 / 逾期 / 进行中 / 已完成 / 归档（2026-09-21 加的第五张）
    tiles.length === 5 && tiles.every((tile) => tile.clickable && tile.label !== ""),
    tiles.map((tile) => `${tile.label}:${tile.clickable ? "可点" : "✗不可点"}`).join(" · "),
  );

  // 五个数的关系（数据模型，2026-09-21 用户问的）：`status` 与 `archived` 是两个**正交**的
  // 字段 —— 三张状态卡把**未归档**那批干净切开（逾期 / 进行中 / 已完成，互不重叠），
  // 而「归档」是它们的**补集**。于是有两条恒等式，一起量：
  //   ① 逾期 + 进行中 + 已完成 = 未归档
  //   ② 未归档 + 归档 = 本分区全部
  // 「今日到期」不参与：它是**截止日**维度的卡，与状态卡有交集（今天到期的可能也是逾期的）。
  // 数字直接跟 localStorage 对 —— 这样哪怕「四张卡口径漂移」也不会漏（各自看都对、加起来对不上）
  const relation = await page.evaluate(() => {
    const numOf = (label) =>
      Number.parseInt(
        [...document.querySelectorAll("#page-overview .tile")]
          .find((node) => (node.querySelector(".lbl")?.textContent ?? "").trim() === label)
          ?.querySelector(".num")?.textContent ?? "-1",
        10,
      );
    const mine = JSON.parse(localStorage.getItem("tadado.tasks.v1") ?? "[]").filter(
      (task) => task.partition === "demo",
    );
    return {
      overdue: numOf("逾期"),
      ongoing: numOf("进行中"),
      done: numOf("已完成"),
      archived: numOf("已归档"),
      active: mine.filter((task) => task.archived !== true).length,
      total: mine.length,
    };
  });
  check(
    "三张状态卡之和 = 未归档；未归档 + 归档 = 本分区全部",
    relation.overdue + relation.ongoing + relation.done === relation.active &&
      relation.active + relation.archived === relation.total,
    JSON.stringify(relation),
  );

  // ── 副标里那个「其中 N」必须真是这批里的 ────────────────────────────────────
  // 「进行中 N，其中 M 个今日更新」：以前 M 数的是**全部未归档任务**，而 N 只数
  // `status === "doing"` —— 于是 M 可以大于 N，点进去看到的 N 条里根本找不到那
  // M 个（它们多半是逾期的）。用户看到的就是「今天更新过的那条凭空消失了」。
  // 这条断言验的是那个「其中」成立：**子集不会比全集大**。
  const doingTile = tiles.find((tile) => tile.label === "进行中");
  const claimedToday = Number.parseInt(/其中 (\d+) 个今日更新/.exec(doingTile?.sub ?? "")?.[1] ?? "0", 10);
  check(
    "「进行中」副标里的「其中 N 个今日更新」确实是这批里的（N ≤ 卡上的数字）",
    doingTile !== undefined && claimedToday <= doingTile.value,
    `卡上 ${doingTile?.value} · 副标「${doingTile?.sub}」`,
  );


  for (const [index, tile] of tiles.entries()) {
    await page.locator('.rail-btn[data-page="overview"]').click();
    await sleep(250);
    await page.locator("#page-overview .tile").nth(index).click();
    await sleep(350);
    // 「已归档」是唯一**不落在任务页**的数字卡：已归档的任务在任务页根本不列（归档的
    // 意思就是「从「任务」界面收走」），所以它去任务管理页的「已归档」—— 那页是唯一能
    // 看见这批的地方。判据同其他卡：卡上的数 = 那页筛出来的**总数**（不是这一页的行数）
    if (tile.label === "已归档") {
      const inManage = await page.evaluate(() => ({
        // 管理页有两组 chip（状态 / 归档），两组都各有一个 .on —— 取全部再认标签
        on: [...document.querySelectorAll("#page-manage .chip.on")].map((chip) =>
          (chip.textContent ?? "").trim(),
        ),
        total: Number.parseInt(
          /共 (\d+) 条/.exec(document.querySelector("#page-manage .pager")?.textContent ?? "")?.[1] ??
            "-1",
          10,
        ),
      }));
      check(
        "总览「已归档」点开后是任务管理的「已归档」，数字也对得上",
        inManage.on.includes("已归档") && inManage.total === tile.value,
        `卡上 ${tile.value} · 落点 ${inManage.on.join("+")} · 共 ${inManage.total} 条`,
      );
      continue;
    }

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
      `总览「${tile.label}」的数字 = 点开后筛出的总数`,
      // 0 条时没有分页器，`firstPage` 无从谈起（「共 0 条」本身已经把数字对上了）
      tile.value === opened.total && (tile.value === 0 || (opened.firstPage && opened.rows > 0)),
      `${tile.value} vs 共 ${opened.total} 条（本页 ${opened.rows} 行 · 第一页 ${opened.firstPage}）`,
    );

    // 「今日到期」这类**不是状态**的筛选，页面上得有个地方说出「现在只看这几条」，
    // 也要有出口 —— 否则点进来看到 1 条，没人知道为什么、也不知道怎么退回去
    if (tile.label === "今日到期") {
      const dueChip = await page.evaluate(() => {
        const chip = [...document.querySelectorAll("#page-tasks .chips .chip")].find((node) =>
          (node.textContent ?? "").startsWith("今日到期"),
        );
        return { has: chip !== undefined, on: chip?.classList.contains("on") ?? false };
      });
      check(
        "任务页有「今日到期」这枚筛选且已点亮（能看出为什么只剩这几条，也能再点一下退回全部）",
        dueChip.has && dueChip.on,
        JSON.stringify(dueChip),
      );
    }
  }

  // （这里原来是一条「任务页『进行中』≥『待办』」的断言，钉的是「进行中 = 待办 + 进行中」
  //   那个合并口径。**「待办」2026-09-21 删掉之后两者是同一档**，这条没有内容了。）

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
  // 标签写「名字 + 编号」（`紧急(P0)`）。只写名字的话，用户得自己记住「紧急对应 P0」，
  // 而列表里那枚徽标写的是 `P0` —— 两边各说各话，对不上就得靠猜
  check(
    "优先级分布的标签是「名字(Px)」",
    buckets.map((item) => item.label).join(" ") === "紧急(P0) 重要(P1) 关注(P2) 普通(P3)",
    buckets.map((item) => item.label).join(" / "),
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

  // 页头说明只回答「这里能看到什么」（2026-09-21 用户报的一处 Py 版口径：原来写
  // 「单击选中 · 双击打开维护抽屉 · 右键处置 · 批量迁入在任务管理页」—— 既没说清这一页
  // 是什么，还把别页的入口写进来）。断言只钉**性质**：提到甘特、不提别的页面的入口名、
  // 不写操作手势（手势交给悬浮提示）
  const tasksDesc = ((await page.locator("#page-tasks .ph-d").textContent()) ?? "").trim();
  check(
    "任务页页头说明说的是「这一页是什么」，不是操作说明书",
    tasksDesc.includes("甘特") &&
      !tasksDesc.includes("管理页") &&
      !tasksDesc.includes("右键") &&
      !tasksDesc.includes("单击"),
    tasksDesc,
  );

  // 排序下拉：默认「按优先级」，而且**点了必须切得动**（2026-09-21 用户报的两个问题）。
  // 切不动的根因在控件层：`dropdown` 原来只在 `setValue` 里改显示，菜单行自己点了**不同步**
  // —— 值确实换了、行也重排了，按钮上却还写着旧的那一项、勾也还在旧项上，看着就是
  // 「切不过去」。现在控件自己同步（见 shell/menu.ts），所以这里量按钮文案**和勾选**都跟着走
  const sortBtn = page.locator("#page-tasks .tools .dd-btn", { hasText: "按" });
  const sortLabel = async () => ((await sortBtn.textContent()) ?? "").trim();
  check("任务页默认排序是「按优先级」", (await sortLabel()).startsWith("按优先级"), await sortLabel());

  const pickSort = async (label) => {
    await sortBtn.click();
    await sleep(200);
    await page.locator("#page-tasks .tools .menu-item", { hasText: label }).click();
    await sleep(320);
    // 菜单里被勾上的那一项（切完之后再打开看一眼）
    await sortBtn.click();
    await sleep(180);
    const checked = await page.evaluate(
      () =>
        // 只看**展开着**的那个菜单：`.menu-item.on` 在每个下拉里都有一份（收起时也在 DOM 里，
        // 只是不可见），不限定就只会读到优先级那个下拉的勾选
        document.querySelector("#page-tasks .tools .menu.open .menu-item.on span")
          ?.textContent?.trim() ?? "",
    );
    await sortBtn.click(); // 收回菜单
    await sleep(150);
    return { label: await sortLabel(), checked };
  };
  const sortCreated = await pickSort("按创建时间");
  const sortProgress = await pickSort("按进度");
  check(
    "排序下拉切得动：按钮文案与勾选都跟着换",
    sortCreated.label.startsWith("按创建时间") &&
      sortCreated.checked.startsWith("按创建时间") &&
      sortProgress.label.startsWith("按进度") &&
      sortProgress.checked.startsWith("按进度"),
    `${sortCreated.label}（勾 ${sortCreated.checked}）→ ${sortProgress.label}（勾 ${sortProgress.checked}）`,
  );
  await pickSort("按优先级"); // 切回默认，后面的用例按默认排序走

  // ── 甘特：固定 32 天窗口 · 拖动平移（2026-09-20 改的模型）────────────────────
  // 以前窗口跟着档位走：「今天」= 1 天（一屏挤成一根线）、「全部」= 撑到装下所有任务的
  // 跨度（几百天，列宽被压成十几像素），两头都不好看。现在窗口**固定 32 天**
  // （前 16 天 + 今天 + 后 15 天），看别的时间段靠拖动 —— 那排档位 2026-09-21 撤了。
  const ganttToday = Math.floor(
    Date.UTC(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()) / 86400000,
  );
  const ganttShape = () =>
    page.evaluate(() => {
      const dates = [...document.querySelectorAll("#page-tasks .tt-date")];
      const grid = document.querySelector("#page-tasks .tt-grid");
      const rangeText = document.querySelector("#page-tasks .tt-range");
      return {
        days: dates.length,
        first: Number(dates[0]?.getAttribute("data-day") ?? NaN),
        last: Number(dates[dates.length - 1]?.getAttribute("data-day") ?? NaN),
        todayAt: dates.findIndex((node) => node.classList.contains("today")),
        colW: grid ? Number.parseFloat(getComputedStyle(grid).getPropertyValue("--tt-col")) : 0,
        // 标准甘特（2026-09-21）：条上**不画进度、也不按档位切段** —— 这两类段一个都不该有
        segSplit: document.querySelectorAll(
          "#page-tasks .tt-bar .seg-h, #page-tasks .tt-bar .seg-d",
        ).length,
        // 「今天」那条竖线（只在今天落在窗口里时才该有）
        todayLine: document.querySelectorAll("#page-tasks .tt-today").length,
        rangeText: rangeText?.textContent?.trim() ?? "",
        rangeOff: rangeText?.classList.contains("off") ?? false,
      };
    });
  const ganttStart = await ganttShape();
  // 窗口恒 32 天、首尾接得上，且**今天落在这 32 天里**（默认窗口就是「今天前 16 天」）。
  // 档位撤了之后，「窗口对准哪批任务」只在跨页请求进来时发生（另有断言守着那一条）
  check(
    "甘特窗口固定 32 天（今天在这一屏里，竖线在）",
    ganttStart.days === 32 &&
      ganttStart.last === ganttStart.first + 31 &&
      // 标准甘特：条上不画进度/范围分段
      ganttStart.segSplit === 0 &&
      // 今天在这 32 天里 → 有那条竖线（2026-09-21：今天不在窗口里时**不该**画它）
      ganttStart.todayAt >= 0 &&
      ganttStart.todayLine === 1,
    `${ganttStart.days} 天 · ${ganttStart.first}–${ganttStart.last} · 今天第 ${ganttStart.todayAt} 格 · 条上分段 ${ganttStart.segSplit}`,
  );

  // 拖动平移：按**天**吸附（拖两格 = 往过去挪两天）。窗口固定之后，「看别的时间段」
  // 就只剩拖动这一条路 —— 拖不动的话这 32 天就是死的
  const dragOn = async (days) => {
    const box = await page.locator("#page-tasks .tt-scroll").boundingBox();
    const y = box.y + Math.min(60, box.height / 2);
    const x = box.x + 40;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + ganttStart.colW * days, y, { steps: 8 });
    await page.mouse.up();
    await sleep(320);
  };
  await dragOn(2);
  const afterDrag = await ganttShape();
  check(
    "在表格上拖动可以平移窗口（拖两格 = 往过去挪两天，按天吸附）",
    afterDrag.first === ganttStart.first - 2 && afterDrag.days === 32,
    `${ganttStart.first} → ${afterDrag.first} · 列宽 ${ganttStart.colW}px`,
  );

  // 标准甘特（2026-09-21 用户定的）：条上**不画进度、也不按档位切段** —— 它只回答
  // 「这条任务占着哪段时间」。所以「范围之前」那段（`.seg-h`）与「范围内到今天」那段
  // （`.seg-d`）**一个都不该有**（出现就是回到了「一条上叠两个量」的老路）；进度有它
  // 自己的家（行首那枚进度饼，另有断言守着）
  const barShape = await page.evaluate(() => ({
    bars: document.querySelectorAll("#page-tasks .tt-bar").length,
    hist: document.querySelectorAll("#page-tasks .tt-bar .seg-h").length,
    solid: document.querySelectorAll("#page-tasks .tt-bar .seg-d").length,
  }));
  check(
    "条上不画进度与范围分段（标准甘特：一条 = 一段时间）",
    barShape.bars > 0 && barShape.hist === 0 && barShape.solid === 0,
    JSON.stringify(barShape),
  );

  // 条内白字**只写进度**（2026-09-21 用户提的「没必要再显示任务名称」）：标题在左边任务列里
  // 已经占了一整行，条上再写一遍是同一句话说两遍。判据用格式而不是「不含标题」—— 标题是
  // 中文长文本，`N%` 这个形状它匹配不上，不必再依赖「左边那一格的选择器还是不是那个」
  const captions = await page.evaluate(() =>
    [...document.querySelectorAll("#page-tasks .tt-bar b")].map((node) =>
      (node.textContent ?? "").trim(),
    ),
  );
  check(
    "条内白字只写进度（不再重复任务名）",
    captions.length > 0 && captions.every((text) => /^\d{1,3}%$/.test(text)),
    `${captions.length} 条 · 例 ${captions.slice(0, 3).join(" / ")}`,
  );

  // 进度数字贴**条右端**（2026-09-21 用户提的「标到右侧，标识向右前进」）：量真几何 ——
  // 挑一条够宽的（窄条本来就不写这个字，拿它量等于空跑），看文字右缘离条右缘有多远
  const captionSide = await page.evaluate(() => {
    const bar = [...document.querySelectorAll("#page-tasks .tt-bar")].find(
      (node) => node.querySelector("b") !== null && node.getBoundingClientRect().width > 90,
    );
    if (!bar) return null;
    const barBox = bar.getBoundingClientRect();
    const textBox = bar.querySelector("b").getBoundingClientRect();
    return { width: Math.round(barBox.width), gap: Math.round(barBox.right - textBox.right) };
  });
  check(
    "进度数字贴条右端（向右推进的读法）",
    captionSide !== null && captionSide.gap >= 2 && captionSide.gap <= 14,
    captionSide ? `条宽 ${captionSide.width}px · 距右端 ${captionSide.gap}px` : "没有够宽的条",
  );

  // 逾期：条的右端**渲染**延长到「今天」，数据里的结束日不动（2026-09-21 用户提的）
  const overdueBar = await page.evaluate(() => {
    const bar = document.querySelector("#page-tasks .tt-bar.st-overdue");
    if (!bar) return null;
    const today = document.querySelector("#page-tasks .tt-date.today");
    return {
      status: "overdue",
      late: bar.querySelectorAll(".seg-late").length,
      mark: bar.querySelectorAll(".late-mark").length,
      // 条右端越过了「今天」那一格的左边界 = 已经延到今天
      reachesToday: today
        ? bar.getBoundingClientRect().right > today.getBoundingClientRect().left + 1
        : null,
    };
  });
  check(
    "逾期的条渲染延长到今天（警示段 + 原结束日竖记），数据里的结束日不动",
    overdueBar !== null &&
      overdueBar.late === 1 &&
      overdueBar.mark === 1 &&
      overdueBar.reachesToday === true,
    JSON.stringify(overdueBar),
  );

  // 拖远了必须**有出口**：今天不在窗口里时，表头那句区间变成强调色的「↺ 回到今天」，
  // 点它回到默认窗口 —— 没有出口的话，昨天那批数据可能在屏幕外好几星期
  await dragOn(18);
  const away = await ganttShape();
  await page.locator("#page-tasks .tt-range").click();
  await sleep(320);
  const home = await ganttShape();
  check(
    "拖远之后能一键回到今天（表头那句区间就是入口）",
    away.rangeOff &&
      // 今天被拖出窗口 → 那条竖线**不画**（线在屏幕外、或被夹在边上，只会误导）
      away.todayLine === 0 &&
      !home.rangeOff &&
      home.todayLine === 1 &&
      home.first === ganttToday - 16,
    `拖远到 ${away.first}（off=${away.rangeOff}，线 ${away.todayLine}）→ 回到 ${home.first}（线 ${home.todayLine}）`,
  );

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
  // 挑一条**未完成**的：已完成的任务按设计不会被标成逾期（`refreshOverdue` 只豁免它），
  // 拿它测逾期等于测了个空。压测数据下先筛出「进行中」—— 排序默认按优先级，
  // 最前面那批未必是未完成的，得先把它筛出来才看得见
  await page.click("#page-tasks .tools .chip:has-text('进行中')");
  await sleep(300);
  const todoRow = page
    .locator(".tt-row")
    .filter({ has: page.locator(".tt-bar.st-doing") })
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
  // 恢复「全部」：下面要测「截止挪到过去 → 自动逾期」，而逾期在「进行中」筛选下看不见
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

  // 清除结束 → 退回「进行中」（没有截止就谈不上过期，`refreshOverdue` 把它放回去）
  await page.click("#task-drawer .dt:has(.dt-time) .dt-quick button:has-text('清除')");
  await sleep(350);
  const badge2 = (await page.locator("#task-drawer .dr-h .st").textContent()) ?? "";
  check("清除结束后退回进行中", !badge2.includes("逾期"), badge2.trim());

  // 结束时间能填时分。列表行上的「⏰ …」显示的正是这个时刻 ——
  // 以前这里只有一个日期框，列表上却写着「今天 15:00」，没有地方能改它
  // 用**今天**，别写死。这里原来写的是 `2026-09-18` —— 写这条测试的那天正好是它，
  // 两天后它就变成了过去：任务按设计被自动标成**逾期**，于是下面那条「状态不被 md
  // 改掉」跟着红（md 把截止挪到未来，而逾期会按设计退回「进行中」，见 store 的 refreshOverdue）。
  // 写死「今天」的测试就是定时炸弹 —— 而且它炸的时候看起来像是被测代码坏了。
  const todayIso = localIso();
  await endDate.fill(todayIso);
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

  // 进度控件就在**活动时间线**里（2026-09-20 用户提的）：写一句进展、顺手把进度挪到哪，
  // 本来是同一次动作的两半；分在「任务定义」和「时间线」两处，漏维护一处是常态。
  // 这里量「只此一处」—— 两处都留着的话，改哪处都像没改，数字还会各说各话
  const progPlaces = await page.evaluate(() => ({
    timeline: document.querySelectorAll("#task-drawer .dr-tl .tl-prog .pct-input").length,
    def: document.querySelectorAll("#task-drawer .dr-def .pct-input").length,
  }));
  check(
    "进度控件在活动时间线里，任务定义里不再重复一份",
    progPlaces.timeline === 1 && progPlaces.def === 0,
    `时间线 ${progPlaces.timeline} 处 · 任务定义 ${progPlaces.def} 处`,
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
  // 两个判据分开量：一个是「标题真写进列表了」，一个是「状态没被 md 改掉」。
  // 合在一个 && 里，失败时看不出是哪半边 —— 这条测试曾经就是这么误报的。
  const renamedRows = await page.locator(".tt-label", { hasText: "md 改过的名字" }).count();
  const badgeAfterMd = (await page.locator("#task-drawer .dr-h .st").first().textContent()) ?? "";
  check(
    "按 md 更新写入，且状态不被 md 改掉",
    renamedRows === 1 && badgeAfterMd === badgeBeforeMd,
    `列表里 ${renamedRows} 行 · 徽标 ${badgeBeforeMd}→${badgeAfterMd}`,
  );

  await page.keyboard.press("Escape");
  await sleep(300);

  // ── 行首那枚「进度饼」 ─────────────────────────────────────────────────────
  // 它取代了原来那个 8px 的状态圆点：圆点只有颜色一个通道，挂在任务名前面谁都会以为
  // 那是进度。现在**形状说进度、颜色说状态**，两端还各有一个更好认的记号
  // （▶ 还没开始 / ✓ 做完）。断三件事：
  //   ① 每枚都带着一个 0–100 的百分比；
  //   ② 记号与进度对得上（满格的必须是 ✓ —— 那是「已做完」的意思，不是装饰）；
  //   ③ 它与悬停提示里那个数是**同一个**（两处各算一遍的话，改了其中一处就会出现
  //      「提示说 45%、饼说 60%」）。
  const dots = await page.evaluate(() =>
    [...document.querySelectorAll("#page-tasks .tt-row")].map((row) => {
      const dot = row.querySelector(".tt-label .pdot");
      return {
        pct: Number.parseInt(dot?.getAttribute("data-pct") ?? "-1", 10),
        mark: dot?.getAttribute("data-mark") ?? "",
      };
    }),
  );
  await page.locator("#page-tasks .tt-row").first().locator(".tt-bar").hover();
  await sleep(250);
  const tipPct = await page.evaluate(
    () => /进度 (\d+)%/.exec(document.querySelector(".tt-tip")?.textContent ?? "")?.[1] ?? "",
  );
  check(
    "行首的进度饼：百分比是真的，记号与进度对得上，且与悬停提示同一个数",
    dots.length > 0 &&
      dots.every((dot) => dot.pct >= 0 && dot.pct <= 100) &&
      dots.every((dot) => (dot.pct >= 100 ? dot.mark === "check" : dot.mark !== "check")) &&
      dots[0].pct === Number.parseInt(tipPct, 10),
    `首行 ${dots[0].pct}% ${dots[0].mark} · 提示 ${tipPct}% · 共 ${dots.length} 枚 · 记号 ${
      [...new Set(dots.map((dot) => dot.mark))].join("/")
    }`,
  );

  // 右键菜单
  await page.locator(".tt-row").first().click({ button: "right" });
  await sleep(200);
  const items = await page.locator(".ctx-menu .menu-item").allTextContents();
  check("右键菜单出现", items.length === 3, items.join(" / "));
  await page.keyboard.press("Escape");

  // 新建任务：页头按钮 → 对话框，一次把状态、优先级、起止时间填全。
  // 原来那个「快速新建」输入框只能填名称和标签，建出来的永远是「待办 + 普通 +
  // 无起止」，必须再开抽屉补一遍 —— 那正是它被撤掉的原因。
  await page.click('#page-tasks .ph button:has-text("＋ 新建任务")');
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
  // 看**整页**（这张卡上限 50 条，不切页时就在这一页里），而不是只看头三条
  const feedTop = await page.evaluate(() =>
    [...document.querySelectorAll("#page-overview .feed-item")].map(
      (node) => node.textContent ?? "",
    ),
  );
  // ⚠️ 判据不能用「它排第一条」：种子里的「今天」活动带**固定时刻**（06:20 / 08:30 / 15:00…），
  // 在凌晨跑这套测试时那些时刻还没到，新建的这条（真实时钟）本来就该排在它们后面 ——
  // 那是数据的时刻问题，不是「总览没刷新」。要量的是**事件驱动重画**：它不用切页就出现在
  // 这一页里（不重画的话它压根不在这一页上）
  check(
    "新建的任务出现在总览近期活动的第一页（不必切页刷新）",
    feedTop.some((text) => text.includes("冒烟新建的任务")),
    feedTop.slice(0, 3).join(" ⟂ "),
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

  // 时间线是**正序（追加模式）**（2026-09-20 用户提的：倒序读起来别扭）：新写的一条
  // 追加在**最下面**（贴着输入框），而不是最上面。**存储仍是「最新在前」**（md 里写明
  // 的约定，导出 / 统计 / 进度上界都依赖它），只有渲染反着铺 —— 所以这条断言是它与
  // 存储约定的分界线：只改存储顺序、或只改渲染顺序，都会让它红
  await page.fill("#task-drawer .tl-compose input", "正序检查用的最后一条");
  await page.locator("#task-drawer .tl-compose input").press("Enter");
  await sleep(320);
  const timelineOrder = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#task-drawer .tl-entry")];
    const textOf = (node) => (node?.textContent ?? "").replace(/\s+/g, " ").trim();
    return {
      count: rows.length,
      first: textOf(rows[0]).slice(0, 26),
      last: textOf(rows[rows.length - 1]).slice(0, 26),
    };
  });
  check(
    "时间线正序显示：新的一条追加在最下面",
    timelineOrder.count > 1 &&
      timelineOrder.last.includes("正序检查用的最后一条") &&
      !timelineOrder.first.includes("正序检查用的最后一条"),
    `${timelineOrder.count} 条 · 首「${timelineOrder.first}」· 末「${timelineOrder.last}」`,
  );

  // （这里原来是「写一条进展 → 把待办推到进行中」。**「待办」那档 2026-09-21 删了** ——
  //   新建任务就是「进行中」，没有可推的起点，这条断言连同那段逻辑一起撤。
  //   活动记录里那些历史上的「待办 → 进行中」仍照原样显示，另有断言守着时间线的渲染。）

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

  // 进度与优先级也要留痕 —— 「关于」面板里那句「状态、进度、优先级的每一次改动都写进
  // 活动时间线」是给用户的承诺，少一条它就是假的。
  //
  // 但抽屉里的进度是**草稿式**的（2026-09-20 用户报的 bug：「进度条调整后，还没来得及
  // 编辑信息，已经被提交了」）：拖 / 填只产生「待保存」，写一句说明按回车**才落库**，
  // 说明与进度落在**同一条**记录上（信息与进度不分家）。
  // 先把进度压到一个**已知的低值**（30），并让它落成一条记录：这样下面那条「进度到 55」
  // 的 `from` 就是确定的 30，于是「改到 65」一定落在 [30, 70] 里。
  // 不这么做的话，`from` 取决于前面几步用例留下的进度（可能就是 70）—— 而 from 与上界
  // 相等时那条记录**根本没有可改的值**，用例会以「被下界拦下」的形式假红（2026-09-21 修）
  await page.fill("#task-drawer .pct-input", "30");
  await page.locator("#task-drawer .pct-input").blur();
  await sleep(180);
  await page.fill("#task-drawer .tl-compose input", "把进度压到 30（用例的起点）");
  await page.locator("#task-drawer .tl-compose input").press("Enter");
  await sleep(320);

  // 先量「拖着不落库」这一步 —— 少了它，后面那条断言在「拖完即提交」的实现下也是绿的
  const beforeDraft = await page.evaluate(
    () => document.querySelectorAll("#task-drawer .tl-entry").length,
  );
  await page.fill("#task-drawer .pct-input", "55");
  await page.locator("#task-drawer .pct-input").blur();
  await sleep(300);
  const draftState = await page.evaluate(() => ({
    entries: document.querySelectorAll("#task-drawer .tl-entry").length,
    pending: document.querySelector("#task-drawer .prog-pending")?.textContent?.trim() ?? "",
  }));
  check(
    "改进度只产生「待保存」，不落库",
    draftState.entries === beforeDraft && /^待保存 \d+% → 55%$/.test(draftState.pending),
    `${beforeDraft} → ${draftState.entries} 条 · 「${draftState.pending}」`,
  );

  // 写说明 + 回车 = 一次提交：**恰好一条**记录，且那条里既有说明也有落差。
  // 「恰好一条」还顺带钉住 from 的抓取位置（滑杆 input 连发，拿上一次的值当起点会刷出
  // 「50→51、51→52……」一串噪声）
  await page.fill("#task-drawer .tl-compose input", "进度到 55 的一句话");
  await page.locator("#task-drawer .tl-compose input").press("Enter");
  await sleep(320);
  const afterProgress = await page.evaluate(() =>
    [...document.querySelectorAll("#task-drawer .tl-entry")].map((n) =>
      (n.textContent ?? "").trim(),
    ),
  );
  const progressHits = afterProgress.filter(
    (text) => text.includes("进度到 55 的一句话") && /% → 55%/.test(text),
  );
  check(
    "写说明后回车：说明与进度落在同一条记录上，且只有一条",
    progressHits.length === 1,
    progressHits[0]?.slice(0, 80) ?? "（没找到那条记录）",
  );

  // 「保存好的进度」可以**再次编辑**（2026-09-20 用户报的第二个 bug：带说明的进度记录
  // 长得像 log，却是 kind=progress，当时根本没有编辑入口）；但值**不能超过后面那条
  // 记录** —— 时间线是单调的，把老记录改到超过后来的值，页面上就出现「倒着走」的进度。
  // 先再造一条更新的进度记录，好让被编辑的那条有上界
  await page.fill("#task-drawer .pct-input", "70");
  await page.locator("#task-drawer .pct-input").blur();
  await sleep(200);
  await page.fill("#task-drawer .tl-compose input", "第二条进度");
  await page.locator("#task-drawer .tl-compose input").press("Enter");
  await sleep(320);

  const older = page
    .locator("#task-drawer .tl-entry", { hasText: "进度到 55 的一句话" })
    .first();
  await older.hover();
  await older.locator(".tl-op:has-text('编辑')").click();
  await sleep(220);
  // 改到 90：上界是后面那条的 70 → 应被拦下（编辑框仍在，值没被吞）
  await page.fill("#task-drawer .tl-card .pct-input", "90");
  await page.locator("#task-drawer .tl-card .tl-op:has-text('保存')").click();
  await sleep(260);
  const blocked = await page.evaluate(() => ({
    value:
      (document.querySelector("#task-drawer .tl-card .pct-input"))?.value ?? "（编辑框已关闭）",
    // toast 会说清走了哪一支（拦下的理由 / 已更新 / 内容不能为空…）
    toast: document.querySelector("#toast")?.textContent?.trim() ?? "",
  }));
  // 改到 65（在它自己的起点 60 和后面的 70 之间）→ 允许，且后面那条的起点跟着挪
  await page.fill("#task-drawer .tl-card .pct-input", "65");
  await page.locator("#task-drawer .tl-card .tl-op:has-text('保存')").click();
  await sleep(320);
  const applied = await page.evaluate(() => ({
    toast: document.querySelector("#toast")?.textContent?.trim() ?? "",
    // 存下去之后编辑器应当关掉（这一行回到普通的记录卡）
    editing: document.querySelectorAll("#task-drawer .tl-card .tl-edit").length,
    entries: [...document.querySelectorAll("#task-drawer .tl-entry")].map((n) =>
      (n.textContent ?? "").trim(),
    ),
  }));
  check(
    "进度记录可再编辑，但改不过后面那条（改完前后两条接得上）",
    blocked.value === "90" &&
      /最多改到 70%/.test(blocked.toast) &&
      applied.editing === 0 &&
      // 起点不写死：那条记录的 `from` 取决于前面几步之后任务当时的进度（本用例只保证
      // 「改到了 65」以及「后面那条接上」这两件事）
      applied.entries.some(
        (text) => text.includes("进度到 55 的一句话") && /→ 65%/.test(text),
      ) &&
      applied.entries.some((text) => text.includes("第二条进度") && /65% → 70%/.test(text)),
    `超界「${blocked.toast}」/ 编辑框 ${blocked.value} · 保存后「${applied.toast}」（编辑器 ${applied.editing}）· ${applied.entries
      .filter((text) => text.includes("进度") || text.includes("第二条"))
      .join(" | ")
      .slice(0, 140)}`,
  );

  // 点当前那一档算「没改」，按设计不留记录 —— 所以挑一个**不是**当前档的来点
  const altUrgency = await page.evaluate(() => {
    const all = [...document.querySelectorAll("#task-drawer .urg-pick")];
    const index = all.findIndex((node) => !node.classList.contains("on"));
    const label = (all[index]?.textContent ?? "").replace(/^P\d\s*/, "").trim();
    return { index, label };
  });
  await page.locator("#task-drawer .urg-pick").nth(altUrgency.index).click();
  await sleep(300);
  const afterUrgency = await page.evaluate(() =>
    [...document.querySelectorAll("#task-drawer .tl-entry")].map((n) =>
      (n.textContent ?? "").trim(),
    ),
  );
  check(
    "改优先级会留一条活动记录",
    afterUrgency.some((text) => text.includes(`→ ${altUrgency.label}`)),
    `${altUrgency.label} · ${afterUrgency.slice(0, 3).join(" / ").slice(0, 70)}`,
  );

  // 底部那两个按钮随即时保存一起撤了：所有字段本来就是改完即存，
  // 「保存」按钮只是把抽屉收起来 —— 名字在骗人
  check(
    "抽屉底部不再有删除 / 保存",
    (await page.locator("#task-drawer .dr-f").count()) === 0,
  );
  await page.keyboard.press("Escape");
  await sleep(300);

  // 近期活动按**任务**聚合（一个任务一行），不是按活动一条条摊开：同一个任务连着
  // 记三条进展就占三行、标题重复三遍，扫一眼看见的其实只是「有个任务动了很多次」。
  //
  // 样本不能钉在某一条固定任务上：上面「改状态」那步把样本标成了「已完成」，默认
  // 「立即」档位下它当场就被收进归档了，而这张卡只列未归档的（见 overview 的
  // activeTasks）—— 于是「拿它当样本」的前提落空。这里改成量**这张卡本身**的性质：
  // 每行都有标题、标题不重复（聚合）、且被折叠的多数要有「共 N 条」报数。
  // 总览是事件驱动重画的、页面一直挂在 DOM 里，所以站在任务页也读得到
  const feedGrouped = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#page-overview .feed-item")];
    const read = rows.map((row) => ({
      title: row.querySelector(".tx b")?.textContent?.trim() ?? "",
      count: row.querySelector(".cn")?.textContent?.trim() ?? "",
    }));
    const titles = read.map((item) => item.title);
    return {
      rows: rows.length,
      // 没有标题的行 = 这一行渲染漏了东西
      untitled: titles.filter((title) => title === "").length,
      // 同一页里出现两次的标题：聚合之后不该有
      dupes: titles.filter((title, index) => title !== "" && titles.indexOf(title) !== index),
      // 折叠了多条的：行尾必须写清它**一共**有几条 —— 只给最新一条而不报数的话，
      // 「动过一次」和「动过八次」在这一行上长得一模一样，折叠就成了丢信息
      counted: read.filter((item) => /^共 [2-9]\d* 条$/.test(item.count)).length,
      sample: read.find((item) => item.count !== "")?.count ?? "",
    };
  });
  check(
    "近期活动按任务聚合：同一个任务只占一行（多条的标出「共 N 条」）",
    feedGrouped.rows > 0 &&
      feedGrouped.untitled === 0 &&
      feedGrouped.dupes.length === 0 &&
      feedGrouped.counted > 0,
    JSON.stringify(feedGrouped),
  );

  // ── 标签：带不带 # 都认，最多 3 个，标签不是固定集合 ──
  // 以前解析只认带 `#` 的写法，「学习 新标签」会被解析成空数组，再被兜底成单个
  // #工作 —— 用户看到的就是「我维护了好几个标签，列表里只剩一个」
  await page.click('#page-tasks .ph button:has-text("＋ 新建任务")');
  await page.waitForSelector(".modal-card.wide");
  await page.fill(".modal-card .dr-title", "多标签任务");
  await page.fill(".modal-card .dr-tags", "学习 新标签 生活 多余的");
  await page.click(".modal-card .dt:has(.dt-time) .dt-quick button:has-text('今天')");
  await sleep(200);
  await page.click(".modal-card .modal-actions button:has-text('创建')");
  await sleep(450);

  // 先搜出来再断言：100 条数据下，刚建的任务未必落在当前这一页上（排序 + 分页都会
  // 把它挤出去）—— 直接 locator 一行都匹配不到，表现就是「(没有标签)」这种看不出
  // 所以然的失败（曾经当成 flaky 放过去两次）
  await page.fill("#page-tasks .searchbox input", "多标签任务");
  // **等这一行出现**再断言，而不是睡一个固定时长：建任务 → 数据广播 → 重画 是异步的，
  // 睡 350ms 在稍慢的机器上就落在重画之前，于是 `multi` 匹配不到任何行，报出来的是
  // 「(没有标签)」—— 看不出所以然，曾经被当成 flaky 放过两次。等不到就算失败，
  // 但失败信息仍然由下面那两条断言给出（那时 rowTags 是空的）
  try {
    await page.waitForSelector(".tt-row:has-text('多标签任务')", { timeout: 5000 });
  } catch {
    // 等不到就把**现场**打出来：只报「(没有标签)」时看不出是没建成、还是建了没画出来，
    // 这两种失败要改的地方完全不同（曾经被当成 flaky 放过两次）
    const why = await page.evaluate(() => ({
      rows: document.querySelectorAll("#page-tasks .tt-row").length,
      toast: document.querySelector("#toast")?.textContent?.trim() ?? "",
      stored: (JSON.parse(localStorage.getItem("tadado.tasks.v1") ?? "[]")).filter(
        (task) => (task.title ?? "").includes("多标签"),
      ).length,
      query: document.querySelector("#page-tasks .searchbox input")?.value ?? "",
    }));
    console.log(`  ⚠ 没等到「多标签任务」这一行：${JSON.stringify(why)}`);
  }
  const multi = page.locator(".tt-row", { hasText: "多标签任务" }).first();
  const rowTags = await multi.locator(".lt2 .tag").allTextContents();
  check(
    "不带 # 的多个标签能入库，最多 3 个",
    rowTags.length === 3 && rowTags.join(" ") === "#学习 #新标签 #生活",
    rowTags.join(" ") || "(没有标签)",
  );
  // 任务列两行的分工：**第一行只有标题**（截止 / 优先级以前和它同行，标题被挤成
  // 省略号，列表里看不出这是哪条任务），第二行是标签 + 截止 + 优先级。
  // 只数 `.lt1 .dlt === 0` 还不够 —— 哪天又往第一行塞个别的（比如优先级徽标），
  // 它照样会绿，所以连「第一行只有标题一个子节点」一起量
  const lt1Kids = await multi.locator(".lt1 > *").count();
  check(
    "标题独占第一行，截止与优先级都在标签那一排",
    lt1Kids === 1 &&
      (await multi.locator(".lt1 .dlt").count()) === 0 &&
      (await multi.locator(".lt2 .dlt").count()) === 1 &&
      (await multi.locator(".lt2 .urg").count()) === 1,
    `第一行 ${lt1Kids} 个子节点`,
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
  // 轴上放的是**任务**（2026-09-20）：只列这一天动过的任务，气泡写「任务名 · 更新了
  // N 条记录」，没动过的任务不占位置。以前这里列的是任务本身，于是「今天到期但没排
  // 时刻」和「今天根本没动过」混在一处 —— 后者压根不该出现在这条轴上。
  // 同一个任务今天记好几笔也只占一个位置（气泡报条数，不给明细）；
  // 同一时段里好几个任务挨太近则合成一簇 —— 那时任务名收在簇里，所以「独立气泡」
  // 与「在某一簇里」两种形态都算出现在今天的轴上
  check(
    "新建的任务出现在今天的轴上",
    axis.bubbles.some(
      (text) => text.includes("冒烟新建的任务") || /\d{2}:\d{2}–\d{2}:\d{2}/.test(text),
    ),
    axis.bubbles.join(" | ").slice(0, 120),
  );
  // 气泡用「任务名 +N」报条数，**不铺活动明细**（明细在抽屉的时间线里）。
  // 最早这里写的是活动原文（「首屏 1.2s → 0.6s」）；后来改成「任务名 · 更新了 N 条
  // 记录」，又嫌太长 —— 气泡是轴上的**标记**，一句完整的话会把整条轴挤满，
  // 所以现在是「任务名 +N」（绿字，见 .tdt-cn）。
  // ⚠️ 这个形状放到**簇展开之后**再量（见后面「点开簇看得到里面每一条」那一步）：
  // 凌晨跑的时候今天只有一条 06:20 的记录，它会合成一个簇（`.st-plain`）——
  // 此刻一个独立气泡都没有，在这里数 `.tdt-cn` 只会数到 0，等于空跑

  // 今天**没动过**的任务不占轴：轴上（含簇）和「时刻在轴外」那条里都不该有它。
  // 它**可以**出现在「已过期未完成」里 —— 那是另一个维度的提示（任务过没过期），
  // 跟「今天动没动过」不是一回事，所以只看前两处。
  //
  // 样本要挑得能挡住那个老 bug：**今天到期、填了时刻、但今天一条活动都没有**
  // （种子里的「评审团队 PR」：due 今天 15:00、at 15:00、活动只有昨天 17:20）。
  // 旧写法正是按「今天到期 + 时刻」把任务本身摆到轴上，于是它会在 15:00 那儿
  // 写着一个「今天根本没发生过」的位置。反过来，只挑一条**起止都不盖今天**的
  // （比如「图标统一」）就什么也挡不住 —— 那种任务在旧写法里本来也不会出现。
  // 以前这一条拿刚建的任务来判，而那时气泡上写的是活动原文、不含任务名，
  // 怎么搜都搜不到 —— 怎么跑都绿，等于没量
  const idle = await page.evaluate(() => {
    const card = [...document.querySelectorAll("#page-overview .card")].find(
      (node) => node.querySelector(".t")?.textContent === "焦点时间轴",
    );
    const rowOf = (label) =>
      [...(card?.querySelectorAll(".tdt-untimed") ?? [])].find(
        (node) => node.querySelector(".lbl")?.textContent === label,
      );
    const has = (nodes, title) =>
      [...nodes].some((node) => (node.textContent ?? "").includes(title));
    // 「今天」按**应用的约定**算：TODAY 是**本地日历日**的 anchor（date/time.ts 顶部），
    // 取本地 Y/M/D 再折成天数。**不能**用 `utcDay(Date.now())` —— 那是真实 UTC 时刻的天号，
    // 本地 00:24（UTC+8）时它还是前一天，于是「昨天 17:20 的活动」会被判成今天（这条断言
    // 就是这么假红过一次）
    const now = new Date();
    const todayAnchor = Math.floor(
      Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / 86400000,
    );
    const dayOf = (t) => Math.floor(t / 86400000);
    const TITLE = "评审团队 PR";
    const stored = (JSON.parse(localStorage.getItem("tadado.tasks.v1") ?? "[]")).find(
      (task) => task.title === TITLE,
    );
    return {
      onAxis: has(card?.querySelectorAll(".tdt-p") ?? [], TITLE),
      offAxis: has(rowOf("时刻在轴外")?.querySelectorAll(".tdt-chip") ?? [], TITLE),
      // 反证：样本确实具备「旧写法会列出来」的属性，且今天没有活动
      // （否则上面两条都空跑，绿了也不说明什么）
      dueToday: /今天/.test(stored?.due ?? ""),
      hasTime: Boolean(stored?.at),
      noActivityToday: (stored?.activities ?? []).every(
        (item) => dayOf(item.at) !== todayAnchor,
      ),
      acts: (stored?.activities ?? []).map((item) => `${item.at} ${item.text}`),
    };
  });
  check(
    "今天没动过的任务不占轴（但仍可在「已过期未完成」里）",
    idle.dueToday &&
      idle.hasTime &&
      idle.noActivityToday &&
      !idle.onAxis &&
      !idle.offAxis,
    JSON.stringify(idle),
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

  // 「已过期未完成」只摆前 3 条，其余折成「等 N 个」（2026-09-20）：
  // 那一栏是**提示**，不是清单 —— 逾期一多就撑成第二张表，把上面的轴挤没了。
  // 折叠必须满足三件事，否则就是丢信息，所以一起量：
  //   1. 总数还在（卡片头那个「过期 N 项未清」），折的是位置不是数；
  //   2. 「等 N 个」的 N 就是**总数**（中文「A、B、C 等 N 个」的 N 含前面摆出的），
  //      不是减出来的剩余数；
  //   3. 折掉的那部分**有去处** —— 「等 N 个」本身可点，点了去逾期清单。
  // 口径（2026-09-20 收紧）：这一栏的判据与「逾期」**同一个谓词**（status ===
  // "overdue"）。以前写 `未完成 && end < 今天`，把「进行中但已过期」也算进去
  // （refreshOverdue 故意不动 doing），于是栏上 47、点过去清单只有 40 —— 两个数
  // 都没算错，摆在一起就像坏了。现在三处（栏 / 逾期指标卡 / 筛选清单）同一个数，
  // 下面第 4 条断言就是量这个等式。
  // 反证：种子里逾期的不止 3 条（否则「≤3」怎么都成立，等于没量）
  const lateRow = await page.evaluate(() => {
    const card = [...document.querySelectorAll("#page-overview .card")].find(
      (node) => node.querySelector(".t")?.textContent === "焦点时间轴",
    );
    const row = [...(card?.querySelectorAll(".tdt-untimed") ?? [])].find(
      (node) => node.querySelector(".lbl")?.textContent === "已过期未完成",
    );
    return {
      head: card?.querySelector(".dim.mono")?.textContent ?? "",
      chips: row?.querySelectorAll(".tdt-chip").length ?? 0,
      more: row?.querySelector(".tdt-more")?.textContent?.trim() ?? "",
      // 折叠掉的部分得能点出去（有去处，折叠才不等于丢信息）
      clickable: row?.querySelector(".tdt-more") instanceof HTMLElement,
    };
  });
  const lateTotal = Number(/过期 (\d+) 项未清/.exec(lateRow.head)?.[1] ?? -1);
  check(
    "「已过期未完成」最多摆 3 条，折成「等 N 个」（N=总数，仍报、可点）",
    lateTotal > 3 &&
      lateRow.chips === 3 &&
      lateRow.more === `等 ${lateTotal} 个` &&
      lateRow.clickable,
    `${lateRow.head.trim()} · 摆 ${lateRow.chips} 条 + ${lateRow.more || "（无）"} · 可点 ${lateRow.clickable}`,
  );
  // 点「等 N 个」要真的到逾期清单，而且**数要对上**（否则就是 47 对 40 那种
  // 「各自都对、摆在一起像坏了」）。只比行数会被聚焦窗口带偏：窗口外的任务不进表，
  // 那时候行数为 0 跟这个入口没关系 —— 所以比的是那枚亮着的筛选 chip 上的数
  await page.locator("#page-overview .tdt-more").click();
  await sleep(350);
  const overdueJump = await page.evaluate(() => {
    const on = [...document.querySelectorAll("#page-tasks .chip")].find((chip) =>
      chip.classList.contains("on"),
    );
    return {
      chip: on?.textContent?.trim() ?? "",
      rows: document.querySelectorAll("#page-tasks .tt-row").length,
    };
  });
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(250);
  const overdueChipCount = Number(/\d+$/.exec(overdueJump.chip)?.[0] ?? -1);
  check(
    "点「等 N 个」到任务页的逾期清单，且与栏上的总数一致",
    /^逾期/.test(overdueJump.chip) && overdueChipCount === lateTotal,
    `${overdueJump.chip || "（无亮的筛选）"} vs 栏上 ${lateTotal}`,
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

  // 种子里下午那一段是刻意造的密集数据：perf 一个任务 7 条（合成一个气泡、报条数），
  // deploy / mentor 各再动一次（14:55 / 14:58 / 15:03 三个任务挨在一起）——
  // 轴上必须把这三个合成一簇，而不是靠加道把轴撑高；点开簇要能看全里面每一个任务。
  // 簇里装的是**任务**，所以气泡上写的是「N 个任务」，不是「N 条」
  const clusterText = await page.evaluate(() => {
    const pill = [...document.querySelectorAll("#page-overview .tdt-p.st-plain")].find((n) =>
      /\d+ 个任务$/.test((n.textContent ?? "").trim()),
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

  // 「+N」记号的形状在这里量（簇已展开，`.tdt-chip` 就在 DOM 里）：
  //   ① 记号必须是 `+N`，不是「更新了 N 条记录」那种整句 —— 气泡是轴上的标记；
  //   ② 整条轴上（气泡 / 展开的簇）都不许再出现「更新了」。
  // 放在这里而不是刚进总览时：凌晨跑的时候今天只有一条 06:20 的记录，会合成一个簇，
  // 独立气泡一个都没有 —— 那会儿数 `.tdt-cn` 只会数到 0
  const pillShape = await page.evaluate(() => {
    const counters = [...document.querySelectorAll("#page-overview .tdt-cn")].map((node) =>
      (node.textContent ?? "").trim(),
    );
    const nodes = [...document.querySelectorAll("#page-overview .tdt-p, #page-overview .tdt-chip")];
    return {
      counters: counters.length,
      bad: counters.filter((text) => !/^\+\d+$/.test(text)),
      legacy: nodes.filter((node) => (node.textContent ?? "").includes("更新了")).length,
    };
  });
  check(
    "焦点时间轴用「任务名 +N」报条数（不铺明细、也不再写「更新了 N 条记录」）",
    pillShape.counters > 0 && pillShape.bad.length === 0 && pillShape.legacy === 0,
    `+N 记号 ${pillShape.counters} 个 · 不合形 ${pillShape.bad.join(",")} · 「更新了」${pillShape.legacy} 处`,
  );

  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(250);

  // 新建对话框的「结束」默认值本身也是一条断言（2026-09-21 用户提的：时分原本是空的，
  // 得手动挑）：**今天 + 当前时刻**。日期框以前就显示着今天（draftTask 的 end 是今天），
  // 但模型里的 `due` 是 null —— 字段看着填好了、点创建却说「还差：结束时间」。
  await page.click('#page-tasks .ph button:has-text("＋ 新建任务")');
  await page.waitForSelector(".modal-card.wide");
  const dialEnd = await page.evaluate(() => {
    const dt = document.querySelector(".modal-card .dt:has(.dt-time)");
    return {
      date: dt?.querySelector(".dt-date")?.value ?? "",
      time: dt?.querySelector(".dt-time")?.value ?? "",
      hint: dt?.querySelector(".dt-hint")?.textContent?.trim() ?? "",
    };
  });
  const clockNow = new Date();
  const hhmmOf = (date) =>
    `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  // 差一分钟都算过：填完对话框到读值之间可能正好跨过一分钟
  const nowHM = hhmmOf(clockNow);
  const prevHM = hhmmOf(new Date(clockNow.getTime() - 60000));
  check(
    "新建任务的「结束」默认今天 + 当前时刻（不必再挑一次时分）",
    dialEnd.date !== "" &&
      [nowHM, prevHM].includes(dialEnd.time) &&
      dialEnd.hint.includes(dialEnd.time),
    `日期 ${dialEnd.date} · 时刻 ${dialEnd.time}（现在 ${nowHM}）· 提示「${dialEnd.hint}」`,
  );

  // 必填：任务名 / 标签 / 结束时间，缺一个都不落库
  await page.fill(".modal-card .dr-title", "缺东西的任务");
  await page.click(".modal-card .modal-actions button:has-text('创建')");
  await sleep(350);
  check(
    "缺标签时拒绝创建并提示",
    (await page.locator(".modal-card.wide").count()) === 1 &&
      ((await page.locator("#toast").textContent()) ?? "").includes("还差") &&
      (await page.locator(".tt-label", { hasText: "缺东西的任务" }).count()) === 0,
    (await page.locator("#toast").textContent())?.trim(),
  );

  // 补齐标签，但把结束**清掉**：给了默认值不等于这条规矩没了
  await page.fill(".modal-card .dr-tags", "#工作");
  await page.click(".modal-card .dt:has(.dt-time) .dt-quick button:has-text('清除')");
  await sleep(220);
  await page.click(".modal-card .modal-actions button:has-text('创建')");
  await sleep(350);
  check(
    "清掉结束之后同样拦下来（结束时间是必填）",
    (await page.locator(".modal-card.wide").count()) === 1 &&
      ((await page.locator("#toast").textContent()) ?? "").includes("结束时间") &&
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

  // 迁入对话框是「选文件 → 看结果 → 导入」，没有打字框，所以**草稿这个概念也不存在了**
  // （原来这两条测的是批量框的草稿，连同 `shell/draft.ts` 一起删掉了）。
  // 这里改成锁新行为：没选文件时导不了，而且重开不会记着上一次选的文件。
  await page.reload({ waitUntil: "networkidle" });
  await page.locator(".rail-btn").nth(1).click();
  await page.waitForSelector(".tt-row");
  await openImport();
  const emptyNote = ((await page.locator(".batch-n").textContent()) ?? "").trim();
  check(
    "迁入：没选文件时导不了，重开也不记着上次的文件",
    emptyNote.includes("还没选择文件") &&
      // 精确匹配「导入」两个字：`跳过重复，导入 0 条` 也含「导入」，用 has-text 会撞上
      (await page.locator('.modal-actions button:text-is("导入")').isDisabled()),
    emptyNote,
  );
  await page.keyboard.press("Escape");
  await sleep(300);

  // 数据迁入：选一个文件（对话框只吃文件，没有粘贴框）
  await openImport();
  await pickImportFile(
    "- [ ] 批量一 #工作 ⏰09-20 14:30 :: 20%\n- [x] 批量二 #工作\n这句不是任务",
  );
  const preview = await page.locator(".batch-n").textContent();
  check("迁入条数预览", preview.includes("共 2 条"), preview.trim());

  // 认不出的行不再静默跳过：以前它只体现为「条数少了一个」，粘 30 行的人看不出
  // 少的是哪几行、为什么少。迁移工具那套「先对账」在这里同样成立
  const skipNote = (await page.locator(".batch-skip").textContent()) ?? "";
  check(
    "批量：认不出的行逐条列出来（不再只是条数少一个）",
    skipNote.includes("1 行没能识别") &&
      skipNote.includes("这句不是任务") &&
      skipNote.includes("第 3 行"),
    skipNote.trim(),
  );
  await page.click(".modal-actions .btn.primary");
  await sleep(400);
  // 迁入是在任务管理页做的，就地看结果。**不能回任务页数**：迁进来的「批量二」是
  // `[x]`（已完成），默认「立即」档位下当场被收进归档 —— 而任务页不列已归档的，
  // 在那边只会数到一条，看着像「迁入吞了一条」。管理页两侧都能看见，在这儿查
  // 「两条都入库了」才是这条断言的意思（归档与否由下面那几条单独管）
  await page.locator("#page-manage .chip:has-text('全部状态')").click();
  await sleep(300);
  const importedRows = {
    first: await page.locator("#page-manage .mrow", { hasText: "批量一" }).count(),
    second: await page.locator("#page-manage .mrow", { hasText: "批量二" }).count(),
  };
  check(
    "批量建出两条（非任务行被跳过）",
    importedRows.first === 1 && importedRows.second === 1,
    JSON.stringify(importedRows),
  );
  // 回任务页把搜索框清干净（下面几条断言还站在这一页上做）
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(320);
  await page.fill("#page-tasks .searchbox input", "");
  await sleep(300);

  // 导入成功后重开，不该还带着上一次选的文件
  await openImport();
  await sleep(350);
  check(
    "导入后重开：不带着上一次的文件",
    ((await page.locator(".batch-n").textContent()) ?? "").includes("还没选择文件"),
  );
  await page.keyboard.press("Escape");
  await sleep(250);

  // 重复：**只提示、不替用户决定** —— 同名不一定同一条，所以给「跳过 / 全部」两个
  // 按钮由他挑。判重规则只有一条：标题在当前分区里已存在（旧版里改过标题的认不出，
  // 这一点界面上也写了）
  await openImport();
  await pickImportFile("- [ ] 批量一 #工作\n- [ ] 迁入去重的新任务 #工作 ⏰09-30");
  const dupNote = (await page.locator(".batch-dup").textContent()) ?? "";
  const dupButtons = await page.locator(".modal-actions button").allTextContents();
  check(
    "迁入：同名的会被列出来，并给出「跳过 / 全部」两个选择",
    dupNote.includes("1 条在当前分区里已有同名任务") &&
      dupButtons.some((text) => text.includes("跳过重复")) &&
      dupButtons.some((text) => text.includes("全部导入")),
    `${dupNote.trim()} · ${dupButtons.join(" | ")}`,
  );
  await page.click(".modal-actions .btn.primary"); // 默认走「跳过重复」
  await sleep(400);
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(320);
  await page.fill("#page-tasks .searchbox input", "批量一");
  await sleep(350);
  const dupRows = await page.locator(".tt-row").count();
  check("跳过重复：同名的那条没有被再建一遍", dupRows === 1, `匹配到 ${dupRows} 行`);
  await page.fill("#page-tasks .searchbox input", "");
  await sleep(300);

  // ── 写法里的「活动行」：任务下面缩进的一行，属于它的活动时间线 ──────────────
  // 活动分析导出的清单就是这个形状（标签 → 任务 → 活动三层），迁移旧数据时它是
  // 唯一带着**活动历史**的载体 —— 不带这一条，导进来就只剩标题
  await openImport();
  await pickImportFile(
    "- [~] 带活动历史的任务 #迁移 ⏰09-30 :: 60%\n" +
      "   - 08-25 16:50 记一条进展\n" +
      "   - 09-09 08:47 记第二条进展",
  );
  const withActivity = await page.locator(".batch-n").textContent();
  check("带活动行的文件按「一条任务」预览", withActivity.includes("共 1 条"), withActivity.trim());
  await page.click(".modal-actions .btn.primary");
  await sleep(450);

  // 回任务页看结果
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(320);
  await page.fill("#page-tasks .searchbox input", "带活动历史");
  await sleep(350);
  await page.locator(".tt-row", { hasText: "带活动历史" }).first().dblclick();
  await page.waitForSelector("#task-drawer.open");
  await sleep(300);
  // 只读**时间线那一块**。以前读的是整张抽屉的文字，于是「比顺序」这件事会被抽屉里
  // 别处的日期带偏 —— 加了「创建于 08-25」之后它就假红过一次（抽屉头部也有 08-25，
  // 位置比时间线里的 09-09 还靠前）
  const timelineEntries = await page.evaluate(() =>
    [...document.querySelectorAll("#task-drawer .tl-entry")]
      .map((node) => (node.textContent ?? "").replace(/\s+/g, " "))
      .join(" | "),
  );
  check(
    "导入的活动行进了时间线，且按**正序**排（早的在上，与时间线的读法一致）",
    timelineEntries.includes("记一条进展") &&
      timelineEntries.includes("记第二条进展") &&
      timelineEntries.indexOf("08-25") < timelineEntries.indexOf("09-09"),
    timelineEntries.slice(0, 160),
  );
  check(
    "带了活动行就不再补一条「导入任务」",
    !timelineEntries.includes("导入任务"),
    timelineEntries.slice(0, 160),
  );

  // 创建日取**最早一条活动**的日期（08-25），不是导入日：迁进来的任务历史全在活动行
  // 里，一律落导入日会把「创建于」和「按创建日排序」一起抹平 —— 而创建日是这次迁移里
  // 唯一会被整个抹平的时间维度
  const createdText = ((await page.locator("#task-drawer .dr-sub").textContent()) ?? "").trim();
  check("导入的任务：创建日取最早一条活动的日期", createdText.includes("08-25"), createdText);
  await page.keyboard.press("Escape");
  await sleep(300);
  await page.fill("#page-tasks .searchbox input", "");
  await sleep(300);

  // 当前分区要在 rail 上看得见，**不用悬浮**：那个入口原先只有一个文件夹图标，名字只
  // 在它的 title 里。rail 有 64px，图标下面那一行放得下四五个汉字
  const capBefore = await page.evaluate(() => ({
    cap: document.querySelector("#part-cap")?.textContent ?? "",
    // 页头那枚分区章已经撤掉了（夹在标题与按钮之间像贴上去的），顺手守着别再回来
    anyChip: document.querySelectorAll(".pchip").length,
  }));
  check(
    "rail 底部的分区入口写着当前分区名（不用悬浮）",
    capBefore.cap === "演示空间" && capBefore.anyChip === 0,
    `「${capBefore.cap}」· 页头残留 ${capBefore.anyChip} 处`,
  );

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

  // 那个名字要跟着切。它订阅的是 onPartitionChange —— 漏了订阅的话，切完分区 rail 上
  // 还写着上一个区的名字，比不显示更糟
  const capAfter = await page.evaluate(
    () => document.querySelector("#part-cap")?.textContent ?? "",
  );
  check("切分区后 rail 上的分区名跟着变", capAfter === "学习", capAfter);

  // 总览问候条那一行也写分区名（日期 · 星期 · 分区 · 条数 连起来是一句话）。口径同样
  // 是**当前分区**：这里正在「学习」区，所以它必须写「学习」——写死的名字过不了这一条
  await page.locator('.rail-btn[data-page="overview"]').click();
  await sleep(430);
  const greetLine = await page.evaluate(
    () => document.querySelector("#page-overview .greet .g2")?.textContent ?? "",
  );
  check("总览问候条按当前分区显示", greetLine.includes("学习 分区"), greetLine.trim());

  // 弹层里当前项要有**勾选标记**（不能只靠底色：底色同时被 :hover 用着，扫一眼分不出
  // 「当前项」和「鼠标正停在这一项上」），每项还要带条数
  await page.click("#part-btn");
  await sleep(250);
  const partList = await page.evaluate(() => ({
    ticked: [...document.querySelectorAll(".part-item")]
      .filter((node) => (node.querySelector(".pt-tick")?.innerHTML ?? "") !== "")
      .map((node) => node.dataset.part ?? ""),
    counts: [...document.querySelectorAll(".part-item .cnt")].map(
      (node) => node.textContent ?? "",
    ),
  }));
  await page.keyboard.press("Escape");
  await sleep(150);
  check(
    "分区弹层：当前项带勾选标记，每项带条数",
    partList.ticked.length === 1 &&
      partList.ticked[0] === "study" &&
      partList.counts.length === 4 &&
      partList.counts.every((text) => /^\d+$/.test(text)),
    `勾选 ${partList.ticked.join()} · 条数 ${partList.counts.join("/")}`,
  );

  // **五个页面都要跟着空**。这条断言原来只覆盖任务页（上面那条），于是
  // 「管理页直接读 TASKS」和「活动分析直接读 TASKS」两处漏洞都从它手底下溜过去了 ——
  // 现象就是「切到空分区，总览 / 任务 / 图谱都空了，管理页却还列着别区的任务」。
  //
  // 口径：每一页量**它自己那批内容的行数**，而不是量某个共用的数字。各页的内容元素
  // 不一样（活动流 / 甘特行 / 图节点 / 表格行 / 活动条目），各量各的才不会互相掩护。
  const readPage = async (pageId, fn) => {
    await page.locator(`.rail-btn[data-page="${pageId}"]`).click();
    await sleep(430);
    return page.evaluate(fn);
  };

  const empty = {
    // 总览：近期活动流 + 焦点时间轴上的气泡，两者都按「任务的活动」铺出来
    overview: await readPage("overview", () => ({
      feed: document.querySelectorAll("#page-overview .feed-item").length,
      bubbles: document.querySelectorAll("#page-overview .tdt-p").length,
    })),
    tasks: await readPage("tasks", () => document.querySelectorAll(".tt-row").length),
    // 图谱：剩下的应该只有「分区」那一个根节点。节点是 .gcanvas 的子元素（另有一个 svg 画连线）
    graph: await readPage("graph", () => {
      const canvas = document.querySelector("#page-graph .gcanvas");
      const total = canvas ? canvas.children.length : 0;
      const svg = canvas?.querySelector(":scope > svg") ? 1 : 0;
      return total - svg;
    }),
    // 任务管理：表格 + 标签卡。它曾经直接读 TASKS（为了放开「显示已归档」），
    // 结果把分区过滤一起放开了 —— 分区口令那道屏风也被绕过去
    manage: await readPage("manage", () => ({
      rows: document.querySelectorAll("#page-manage .mrow").length,
      tags: document.querySelectorAll("#page-manage .tagrow").length,
    })),
    // 活动分析：活动条目 + 左侧标签列表。后者是**另一处** TASKS.flatMap
    // （tagStatsNow），只查活动列表会漏掉它
    activity: await readPage("activity", () => ({
      items: document.querySelectorAll("#page-activity .act-item").length,
      tags: document.querySelectorAll("#page-activity .split-filter .card .tagrow").length,
    })),
  };

  check(
    "空分区：五个页面都空（总览 / 任务 / 图谱 / 任务管理 / 活动分析）",
    empty.overview.feed === 0 &&
      empty.overview.bubbles === 0 &&
      empty.tasks === 0 &&
      empty.graph <= 1 &&
      empty.manage.rows === 0 &&
      empty.manage.tags === 0 &&
      empty.activity.items === 0 &&
      empty.activity.tags === 0,
    JSON.stringify(empty),
  );

  // 下面几条（活动报告搜索、图谱）都要有数据可看，切回演示空间再跑
  await page.click("#part-btn");
  await sleep(150);
  await page.click(".part-item[data-part='demo']");
  await sleep(400);

  // 切回来**要有数据**。这条守着活动分析的另一半：它的标签勾选集（checked）只在
  // 同一个分区里延续，换分区必须重算 —— 不然从空分区切回来会是一个空报告，
  // 看着像「这个分区的活动没了」（e2e 上一轮就是这样发现它的）
  await page.locator('.rail-btn[data-page="activity"]').click();
  await sleep(430);
  const backItems = await page.locator("#page-activity .act-item").count();
  check("切回演示空间：活动分析又有数据了", backItems > 0, `${backItems} 条`);

  // （这里原来有两条「任务页档位 = 进度透镜」的断言：选了范围就只列该范围里动过的任务、
  //   刷新回到默认档位。那排档位 2026-09-21 撤了，两条一起删 —— 这一页现在没有会自己变
  //   的视图状态，刷新后看到的就是「这个分区全部未归档任务」。）
  //
  // 刷新一次：让下面几条用例从一个干净的启动状态开始
  await page.reload({ waitUntil: "networkidle" });
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(500);

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

      // 月份天数按**格子自己带的年份**算。这里原来写死 `2026` —— 「全年」热力图画的是
      // 当前年份，2027 年再跑这条就会拿 2026 去比（闰年更糟），报的还是「月错位」
      const cellYear = Number((dates[0] ?? localIso()).slice(0, 4));
      const daysInMonth = new Date(Date.UTC(cellYear, index + 1, 0)).getUTCDate();
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
      // 用 localIso()，**不要** `toISOString().slice(0, 10)`：那是 UTC 日期，
      // 东八区每天 00:00–08:00 都算成昨天，这条断言曾经每天早红八小时
      ((await reportRangeText()) ?? "").trim().split(" ")[0] === localIso(),
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
  // 点哪一天就断言哪一天：原来断言的是写死的 `"2026-09-"`（第 9 个月块 = 9 月），
  // 年份一翻就假红。改成从被点那格自己的 `title` 里取日期 —— 这样它验的是
  // 「报告切到了我点的那一天」，而不是「今天是 2026 年」
  const dayCell = page.locator(".hm-mo:nth-child(9) .hc.h2").first();
  const clickedDay = ((await dayCell.getAttribute("title")) ?? "").slice(0, 10);
  await dayCell.click();
  await sleep(300);
  const dayCount = await reportCountText();
  check(
    "点热力图上的一天，报告切到那一天",
    clickedDay !== "" &&
      ((await reportRangeText()) ?? "").includes(clickedDay) &&
      !((await reportRangeText()) ?? "").includes(" – ") &&
      (await page.locator(".act-filter .chip.on").textContent()) === "指定范围",
    `${yearCount} → ${dayCount} · 点的是 ${clickedDay} · ${(await reportRangeText())?.trim()}`,
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

  // 「全选」是**一枚开关**，不是「全选 + 清空」两个单向按钮（2026-09-20 定稿）：
  // 默认全选 → 再点 = 取消全选 → 再点 = 全选。
  //
  // 起因是一句反馈「清空好像没用，全选再点一次就取消全选了」：实测「全选」当时**不会**
  // 取消勾选（它只 add、不 delete），但它在默认状态下**永远是空操作** —— 默认勾选集
  // 本来就等于列表里那几个标签。点了没反应的按钮，只能引出两种结论：「它坏了」或者
  // 「它和旁边那个是一回事」。开关没有这个问题：**两边都有活儿干，点下去一定有变化**。
  //
  // 这条就是照着开关的语义验的：默认全选（按钮是亮的）→ 点一次全清（报告跟着空）→
  // 再点一次全回来。原来那条「在默认状态点一下全选」是空操作，**什么都没验到**。
  const tagBtn = "#page-activity .split-filter .card .btn:has-text('全选')";
  const tagState = () =>
    page.evaluate(() => {
      const card = document.querySelector("#page-activity .split-filter .card");
      const all = [...card.querySelectorAll(".btn")].find((b) => b.textContent?.trim() === "全选");
      return {
        rows: card.querySelectorAll(".tagrow:has(.tcb)").length,
        checked: card.querySelectorAll(".tagrow .tcb.on").length,
        // 全勾着时按钮带 .on（强调色）—— 那一亮就是「现在是全选状态」的说明
        on: all?.classList.contains("on") ?? false,
        // 「清空」已经撤掉：一个开关就把两件事都说了
        clears: [...card.querySelectorAll(".btn")].filter(
          (b) => b.textContent?.trim() === "清空",
        ).length,
        report: document.querySelectorAll("#page-activity .act-item").length,
      };
    });

  const allOn = await tagState();
  await page.locator(tagBtn).click();
  await sleep(350);
  const allOff = await tagState();
  await page.locator(tagBtn).click();
  await sleep(350);
  const backOn = await tagState();
  check(
    "标签筛选只有一枚「全选」开关：默认全选 → 再点取消 → 再点全选",
    allOn.rows > 0 &&
      allOn.clears === 0 &&
      allOn.checked === allOn.rows &&
      allOn.on === true &&
      allOff.checked === 0 &&
      allOff.on === false &&
      // 取消全选后报告是真空的（不是「看起来没勾、其实还在筛」）
      allOff.report === 0 &&
      backOn.checked === backOn.rows &&
      backOn.on === true,
    `默认 ${allOn.checked}/${allOn.rows}(on) → 取消 ${allOff.checked}(报告 ${allOff.report}) → 全选 ${backOn.checked}/${backOn.rows}(on) · 清空按钮 ${allOn.clears} 个`,
  );
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
      list: [...(sec?.querySelectorAll(".about-list li") ?? [])].map((n) =>
        (n.textContent ?? "").trim(),
      ),
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

  // 清单里的功能名要对得上**界面现状**（2026-09-21 小字审计）：这行原来写
  // 「色条为起止区间、填充为进度，档位从今天到全年」—— 条形早已改成创建 → 截止，
  // 而档位根本没有「全年」这一档（是 昨天/今天/上周/本周/上月/本月 + 全部）
  check(
    "「关于」的功能清单与界面一致（没有不存在的档位 / 过期的条形口径）",
    about.list.every((text) => !text.includes("全年")) &&
      about.list.some((text) => text.includes("创建 → 截止")) &&
      about.list.some((text) => text.includes("数据迁入")),
    about.list.join(" | ").slice(0, 160),
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

  // 完成后归档 / 空闲锁定是少数人用得着的那类设置，所以收在分区行尾
  // 「自动 ▾」里：四项分区各挂两个常年不动的 seg，一页就全被挤没了
  const collapsed = await page.evaluate(() =>
    [...document.querySelectorAll("#set-part .part-more")].every((n) => n.hidden === true),
  );
  check("分区的完成后归档 / 空闲锁定默认收起", collapsed);

  await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("工作"),
    );
    [...(row?.querySelectorAll("button") ?? [])]
      .find((b) => (b.textContent ?? "").includes("自动"))
      ?.click();
  });
  await sleep(250);

  // 完成后归档是**按分区**设的：改「工作」这一档，别的分区不受影响。
  // 摆成全局值时 —— 工作区的东西该收走，个人区那几条想留着翻，
  // 一个值只能取折中，两头都不对。
  // 档位的**读数**与**点选**分开两个小helper：三处（这里、演示空间那段、收尾复位）都用同一套选择器
  const archiveValue = async () =>
    page.evaluate(() => {
      const row = [...document.querySelectorAll("#set-part .part-more .set-row")].find((r) =>
        (r.textContent ?? "").includes("完成后归档"),
      );
      return row?.querySelector(".seg button.on")?.textContent?.trim() ?? "";
    });
  const archiveBefore = await archiveValue();
  const pickArchive = async (label) => {
    await page.evaluate((text) => {
      const row = [...document.querySelectorAll("#set-part .part-more .set-row")].find((r) =>
        (r.textContent ?? "").includes("完成后归档"),
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
    "完成后归档：默认「立即」，能改成别的档",
    archiveBefore === "立即" && archiveAfter === "7 天",
    `${archiveBefore} → ${archiveAfter}`,
  );
  // 拨回去（默认档）：后面的用例还在数任务条数
  await pickArchive("立即");
  check("完成后归档能拨回「立即」", (await archiveValue()) === "立即", await archiveValue());

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
  // 以前两个页面各导出各的（管理页 .md 任务行、活动页 .csv），「导出」在同一个应用
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
  // 那条活动恰好等于截止日（连钟点都一样）—— 看着就像「创建于截止日」。
  //
  // 比较按**绝对天数**，不拿 `"MM-DD"` 直接比字符串：1 月里 12 月的活动会显得
  // 「比今天晚」（跨年倒挂），而它其实是去年 12 月的、早就发生了 —— 整个 1 月假红
  const futureActs = [...actMdText.matchAll(/^ {3}- (\d{2}-\d{2}) \d{2}:\d{2} /gm)]
    .map((match) => match[1])
    .filter((monthDay) => {
      const [month, day] = monthDay.split("-").map(Number);
      return nearestDay(month, day) > todayDay();
    });
  check(
    "导出的活动时间都不晚于今天",
    futureActs.length === 0,
    futureActs.length > 0 ? futureActs.slice(0, 3).join(", ") : `今天 ${localIso().slice(5)}`,
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
  await page.locator("#page-manage .pager .menu-item", { hasText: "30/页" }).click();
  await sleep(400);
  const pageRowsAfter = await rowsInPage();
  check(
    "管理页每页条数可调（分页器上的下拉）",
    pageRowsBefore <= 20 && pageRowsAfter > pageRowsBefore,
    `${pageRowsBefore} → ${pageRowsAfter}`,
  );

  // 管理页与活动分析**同一套三层结构**：导入撤了之后，「必须保持任务行才能导回来」
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
  const manageXlsxBytes = readFileSync(manageXlsx.file);
  check(
    "管理页的 xlsx 同样是完整的 zip",
    zipProblem(manageXlsxBytes) === "",
    manageXlsx.name,
  );

  // 截止那一列必须是**绝对日期**。表格上写「今天 15:00 / 昨天」是对的（界面上更好读），
  // 但它是**会变**的：今天导出的「今天」，明天打开就指错了日子，而文件要存档、要发给别人。
  // 活动分析那边早就量了（时间戳一律绝对日期），管理页这一列一直没量 —— 而它是唯一把
  // 界面文案直接写进文件的格子，于是「今天」就这么进了文件。
  // xlsx 用 `inlineStr` 存字符串、zip 又不压缩（见 data/xlsx.ts），所以单元格原文
  // 就躺在字节里：不用解压也能逐格读出来（D 列 = 截止，表头 `# / 创建 / 任务内容 / 截止`）
  const sheetText = manageXlsxBytes.toString("utf8");
  const dueCells = [
    ...sheetText.matchAll(/<c r="D(\d+)"[^>]*><is><t[^>]*>([^<]*)<\/t><\/is><\/c>/g),
  ]
    .filter((match) => Number(match[1]) > 1)
    .map((match) => match[2]);
  const badDue = dueCells.filter(
    (cell) => cell !== "" && !/^\d{2}-\d{2}( \d{2}:\d{2})?$/.test(cell),
  );
  check(
    "管理页导出的「截止」列是绝对日期（今天 / 明天 / 昨天 都已换算）",
    dueCells.length > 0 && badDue.length === 0,
    badDue.length > 0
      ? badDue.slice(0, 3).join(" / ")
      : `${dueCells.length} 格 · 例 ${dueCells.find((cell) => cell !== "") ?? "（都是无截止）"}`,
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

  // ── 端到端：转换工具的输出必须能被应用**直接导入**（2026-09-18）───────────────
  // 「可以直接导入」是三句可验收的话：① 应用**解析得出**（0 行认不出）；② **条数对得上**；
  // ③ **活动历史没丢**（这是这条通道存在的全部理由）。
  //
  // 以前这三条只靠人眼比一遍 —— 工具用自己那套正则，应用用自己那份解析器，两者只在
  // 「看一眼」这一层碰过。现在拿工具的**真输出**喂进「数据迁入」跑一遍：解析走的是
  // `parseTasksDetailed`（应用自己的那份），不是在工具里再写一份副本。
  const converted = join(TMP, "from-tool.md");
  await new Promise((done) => {
    const child = spawn(
      process.execPath,
      [
        join("..", "resources", "skill", "tadado-activity-import", "scripts", "migrate-activity.mjs"),
        join("..", "resources", "skill", "tadado-activity-import", "sample-input.md"),
        "--apply",
        "--force",
        "--out",
        converted,
      ],
      { stdio: "ignore" },
    );
    child.on("close", done);
  });

  await openImport();
  await page.setInputFiles(".modal-card input[type=file]", converted);
  await sleep(320);
  const toolCount = ((await page.locator(".batch-n").textContent()) ?? "").trim();
  const toolSkipped = ((await page.locator(".batch-skip").textContent()) ?? "").trim();
  check(
    "转换工具的输出：应用能直接解析（3 条 · 0 行认不出）",
    toolCount.includes("共 3 条") && toolSkipped === "",
    `${toolCount} · 未识别：${toolSkipped || "无"}`,
  );
  await page.click(".modal-actions .btn.primary");
  await sleep(450);

  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(320);
  await page.fill("#page-tasks .searchbox input", "示例任务");
  await sleep(350);
  const toolRows = await page.locator(".tt-row").count();
  check("转换工具的输出：导入后 3 条都在", toolRows === 3, `匹配到 ${toolRows} 行`);

  // 活动历史也一起过来了：这条任务在源清单里横跨两个标签组、共 4 行活动，
  // 其中 2 行是旧版自动写下的系统记录（延后处理 / 状态变更）—— 滤掉后剩 2 行人写的
  await page.locator(".tt-row", { hasText: "示例任务三" }).first().dblclick();
  await page.waitForSelector("#task-drawer.open");
  await sleep(320);
  const toolHistory = await page.locator("#task-drawer .tl-entry").count();
  check(
    "转换工具的输出：留下的只有人写的进展（系统记录已滤掉）",
    toolHistory === 2,
    `${toolHistory} 条`,
  );
  await page.keyboard.press("Escape");
  await sleep(250);
  await page.fill("#page-tasks .searchbox input", "");
  await sleep(300);

  // ── 完成后归档：默认「立即」＝勾完即离开任务页；改成「N 天」＝在任务页存活 N 天 ──
  // （2026-09-21 定的口径：判据从「结束日 + N」改成「**完成日** + N」，档位也从
  //   关/7/30/90 变成 不归档/立即/7 天/30 天/90 天、默认「立即」——见 store 的 archiveDays）
  await page.click("#part-btn");
  await sleep(200);
  await page.click(".part-item[data-part='demo']");
  await sleep(400);

  /** 打开设置、展开「演示空间」那一行的「自动 ▾」、点一个档位、再关掉。 */
  const setArchiveFor = async (label) => {
    await page.click("#set-btn");
    await page.waitForSelector("#set-drawer.open");
    await page.evaluate(() => {
      const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
        (r.textContent ?? "").trim().startsWith("演示空间"),
      );
      [...(row?.querySelectorAll("button") ?? [])]
        .find((b) => (b.textContent ?? "").includes("自动"))
        ?.click();
    });
    await sleep(300);
    await page.evaluate((text) => {
      const row = [...document.querySelectorAll("#set-part .part-more .set-row")].find((r) =>
        (r.textContent ?? "").includes("完成后归档"),
      );
      [...(row?.querySelectorAll(".seg button") ?? [])]
        .find((b) => (b.textContent ?? "").trim() === text)
        ?.click();
    }, label);
    await sleep(350);
    await page.click("#set-close");
    await sleep(250);
  };

  // ① 「默认＝立即」这句话本身要有个判据：演示空间那一档（= 新装的默认）就该停在「立即」
  await page.click("#set-btn");
  await page.waitForSelector("#set-drawer.open");
  await page.evaluate(() => {
    const row = [...document.querySelectorAll("#set-part .set-row")].find((r) =>
      (r.textContent ?? "").trim().startsWith("演示空间"),
    );
    [...(row?.querySelectorAll("button") ?? [])]
      .find((b) => (b.textContent ?? "").includes("自动"))
      ?.click();
  });
  await sleep(300);
  const archiveDefault = await page.evaluate(
    () =>
      [...document.querySelectorAll("#set-part .part-more .set-row")]
        .find((r) => (r.textContent ?? "").includes("完成后归档"))
        ?.querySelector(".seg button.on")?.textContent?.trim() ?? "",
  );
  await page.click("#set-close");
  await sleep(250);
  check(
    "「完成后归档」的默认档是「立即」（新装分区）",
    archiveDefault === "立即",
    `演示空间 = ${archiveDefault || "（没读到）"}`,
  );

  const archivedCount = () =>
    page.evaluate(
      () =>
        (JSON.parse(localStorage.getItem("tadado.tasks.v1") ?? "[]")).filter(
          (task) => task.archived === true,
        ).length,
    );
  const archivedBase = await archivedCount();

  // ② 样本从库里挑一条**未完成**的（归档只认完成：拿一条已完成的去测，是空跑）
  const pickUndone = (skip) =>
    page.evaluate((skipTitle) => {
      const tasks = JSON.parse(localStorage.getItem("tadado.tasks.v1") ?? "[]");
      const hit = tasks.find(
        (task) =>
          task.partition === "demo" &&
          task.archived !== true &&
          task.status !== "done" &&
          task.title !== skipTitle,
      );
      return hit ? { title: hit.title, status: hit.status } : null;
    }, skip ?? "");

  /** 到任务页搜出这条、打开抽屉点「已完成」，返回搜到几行。 */
  const completeViaDrawer = async (title) => {
    await page.locator('.rail-btn[data-page="tasks"]').click();
    await sleep(320);
    await page.fill("#page-tasks .searchbox input", title);
    await sleep(400);
    const row = page.locator("#page-tasks .tt-row").filter({ hasText: title }).first();
    const found = await row.count();
    await row.dblclick();
    await page.waitForSelector("#task-drawer.open");
    await sleep(330);
    await page.click("#task-drawer .tf-row .chip:has-text('已完成')");
    await sleep(400);
    await page.keyboard.press("Escape");
    await sleep(400);
    return found;
  };

  const listedRows = (title) =>
    page.locator("#page-tasks .tt-row").filter({ hasText: title }).count();

  // ③ 「立即」：勾完**当场**离开任务页（这就是「存活 0 天」），存储里也真的归档了
  const first = await pickUndone("");
  check(
    "样本：演示空间里有一条未完成的任务（否则下面两条空跑）",
    first !== null,
    first ? `${first.title}（${first.status}）` : "没找到",
  );
  const foundFirst = await completeViaDrawer(first?.title ?? "");
  const listedFirst = await listedRows(first?.title ?? "");
  const archivedFirst = await archivedCount();
  check(
    "「立即」：标记完成即离开任务页，存储里 archived = true",
    foundFirst === 1 && listedFirst === 0 && archivedFirst === archivedBase + 1,
    `完成前 ${foundFirst} 行 → 完成后 ${listedFirst} 行 · 已归档 ${archivedBase} → ${archivedFirst}`,
  );

  // ④ 「7 天」：完成之后**还留在**任务页（「存活 N 天」的字面意思），存储里没归档。
  //    这是**反向断言**：少了它，「把判据写成做完就收」也能让上面那条绿
  await setArchiveFor("7 天");
  const second = await pickUndone(first?.title ?? "");
  const foundSecond = await completeViaDrawer(second?.title ?? "");
  const listedSecond = await listedRows(second?.title ?? "");
  const archivedSecond = await archivedCount();
  check(
    "「7 天」：标记完成之后仍留在任务页（存活 N 天），没被归档",
    foundSecond === 1 && listedSecond === 1 && archivedSecond === archivedFirst,
    `完成前 ${foundSecond} 行 → 完成后 ${listedSecond} 行 · 已归档 ${archivedSecond}（未增）`,
  );

  // ⑤ 管理页（唯一显示已归档的视图）认这总数：比**总数**而不是行数 ——
  //    归档一批之后必然翻页，行数只反映这一页
  await page.locator('.rail-btn[data-page="manage"]').click();
  await sleep(350);
  await page.locator("#page-manage .chip:has-text('已归档')").click();
  await sleep(320);
  const archivedTotal = await page.evaluate(() => {
    const bar = document.querySelector("#page-manage .pager")?.textContent ?? "";
    return Number.parseInt(/共 (\d+) 条/.exec(bar)?.[1] ?? "-1", 10);
  });
  check(
    "任务管理页的「已归档」总数 = 存储里的归档数",
    archivedTotal === archivedSecond,
    `表格共 ${archivedTotal} 条 · 存储里 ${archivedSecond} 条`,
  );

  // ⑥ 「归档」那一列是**只读**的（与「状态」「标签」两列同性质）：只摆标 —— 已归档 / —
  //    （2026-09-21 用户定的：那一列不摆按钮）。动手的地方是页头那枚按筛选的按钮，
  //    以及勾选之后的批量栏
  const archivedTotalNow = () =>
    page.evaluate(() => {
      const bar = document.querySelector("#page-manage .pager")?.textContent ?? "";
      return Number.parseInt(/共 (\d+) 条/.exec(bar)?.[1] ?? "-1", 10);
    });
  const archiveColumn = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#page-manage .mrow")];
    return {
      buttons: document.querySelectorAll("#page-manage .mrow .arch-toggle").length,
      // 这一档（「已归档」）里每一行都该带着那枚标
      tagged: rows.filter((row) => (row.textContent ?? "").includes("已归档")).length,
      rows: rows.length,
    };
  });
  check(
    "「归档」列只显示标（已归档 / —），不摆按钮",
    archiveColumn.buttons === 0 &&
      archiveColumn.tagged === archiveColumn.rows &&
      archiveColumn.rows > 0,
    JSON.stringify(archiveColumn),
  );

  // 单条恢复改走**勾选 + 批量栏**那条路（那一列不摆按钮之后，它是单条处置的入口）：
  // 勾一行 → 批量栏「取消归档」→ 「已归档」总数少 1
  const beforeRestore = await archivedTotalNow();
  await page.locator("#page-manage .mrow").first().locator(".ckb").click();
  await sleep(280);
  await page.locator("#page-manage .batchbar button:has-text('取消归档')").click();
  await sleep(440);
  const afterRestore = await archivedTotalNow();
  check(
    "单条恢复：勾选 + 批量栏「取消归档」（「已归档」总数少 1）",
    afterRestore === beforeRestore - 1,
    `${beforeRestore} → ${afterRestore}`,
  );
  // ⑦ 页头那枚**批量归档**按钮（2026-09-21 用户提的「在导出之后增加一个归档按钮即可」）。
  //    它跟着**筛选条件**做事 —— 筛选已经把「哪一批」讲清楚了（状态 × 归档），按钮只负责
  //    执行，所以标签里**不写条数**；标签只跟着**归档档位**换：看「未归档」时是「归档」、
  //    看「已归档」时是「取消归档」（一次只可能做对该做的那件事）
  // 位置与标签：**导出** 与 **归档** 是页头最后两枚（选择器用类名定位 —— 页头里还有
  // 「未归档 / 已归档」两枚 chip，按文字找会撞上它们）
  const headerTail = () =>
    page.evaluate(() => {
      const exportBtn = [...document.querySelectorAll("#page-manage button")].find((node) =>
        (node.textContent ?? "").trim().startsWith("导出"),
      );
      const buttons = [
        ...(exportBtn?.parentElement?.querySelectorAll("button") ?? []),
      ].map((node) => (node.textContent ?? "").trim());
      return buttons.slice(-2);
    });
  const archiveBtnLabel = () =>
    page.evaluate(
      () =>
        (document.querySelector("#page-manage .archive-batch")?.textContent ?? "").trim(),
    );
  const tail = await headerTail();
  check(
    "页头的批量归档按钮紧跟在「导出」之后",
    (tail[0] ?? "").startsWith("导出") && tail[1] === "取消归档",
    `尾部按钮 ${JSON.stringify(tail)}`,
  );
  // 动作真的生效：在「已归档」这一档按它（= 取消归档），再在「已完成」那一档收回来 ——
  // 来回一趟，结束时状态与开头一致。（合单之后「已完成 × 已归档」这种组合不再能表达，
  // 所以用「已完成」那一档收回：默认「立即」下，归档里的正好就是那批已完成的）
  const beforeRelease = await archivedTotalNow();
  await page.click("#page-manage .archive-batch");
  await sleep(320);
  await page.click('.modal-actions button:has-text("恢复")');
  await sleep(520);
  const afterRelease = await archivedTotalNow();
  check(
    "「取消归档」按当前筛选生效（这一档放回了 N 条）",
    afterRelease === 0 && beforeRelease > 0,
    `${beforeRelease} → ${afterRelease}`,
  );
  // 这一档已经空了：再按应当给一句提示，不静默无反应
  await page.click("#page-manage .archive-batch");
  await sleep(260);
  const emptyHint = await page.evaluate(
    () => document.querySelector("#toast")?.textContent?.trim() ?? "",
  );
  check("空筛选下按归档给提示，不静默无反应", emptyHint.includes("没有任务"), emptyHint);
  // 换到「已完成」那一档：刚放回来的就是它们，按钮也应当换回「归档」
  await page.locator("#page-manage .chip:has-text('已完成')").click();
  await sleep(340);
  check(
    "换到「已完成」档，按钮标签跟着换回「归档」",
    (await archiveBtnLabel()) === "归档",
    await archiveBtnLabel(),
  );
  // 基准是**这一档的条数**，不是「刚才放回的那 N 条」：放回的是「已归档」那一批
  // （里面可能混着非已完成的手动归档），而这里是「已完成 × 两侧」—— 两批人不一样，
  // 拿前者的数去比后者的结果只会得到一个假红
  const beforeReclaim = await archivedCount();
  const reclaimRows = await archivedTotalNow();
  await page.click("#page-manage .archive-batch");
  await sleep(320);
  await page.click('.modal-actions button:has-text("归档")');
  await sleep(520);
  const afterReclaim = await archivedCount();
  check(
    "「归档」按当前筛选生效（这一档的条数加了进去）",
    reclaimRows > 0 && afterReclaim === beforeReclaim + reclaimRows,
    `${beforeReclaim} → ${afterReclaim}（这一档 ${reclaimRows} 条）`,
  );
  // 复位：状态回「全部状态」、归档回「未归档」，并确认按钮又变成「归档」
  await page.locator("#page-manage .chip:has-text('全部状态')").click();
  await sleep(300);

  // 收尾：筛选与档位复位，归档档位拨回「立即」（= 默认）—— 后面的用例（含重启）不该被这段影响
  await page.locator("#page-manage .chip:has-text('未归档')").click();
  await sleep(200);
  await page.locator('.rail-btn[data-page="tasks"]').click();
  await sleep(300);
  await page.fill("#page-tasks .searchbox input", "");
  await setArchiveFor("立即");

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
  // 外加一条连标题都没有的垃圾记录。
  // 日期取**相对今天**（写死 09-18/09-20 的话，跑的日子一过 09-20，这条被迁移出来的
  // 任务就会被 bootStore 的 refreshOverdue 标成「逾期」，而断言期望的是迁移补上的默认值
  // 「进行中」—— 那是日期的锅，不是迁移坏了，2026-09-21 修）
  //
  // 两条样本各管一件事：`legacy-1` 的状态是**认不出的枚举**（`WAITING`），`legacy-2` 写的
  // 是**已经删掉的那一档** `todo` —— 两者都该落到「进行中」，而后者正是真实老库的形态
  // （2026-09-21 删掉待办时，库里的 todo 就是这么被归一的）
  const legacyDay = (offset) => {
    const date = new Date(Date.now() + offset * 86400000);
    return [date.getMonth() + 1, date.getDate()];
  };
  const legacy = [
    {
      id: "legacy-1",
      title: "上个版本留下的任务",
      status: "WAITING",
      due: "09-20",
      at: null,
      start: legacyDay(-2),
      end: legacyDay(7),
      created: legacyDay(-8),
      archived: false,
      activities: [{ at: "昨天 17:20", text: "写了一版", kind: "log" }],
    },
    {
      id: "legacy-2",
      title: "老库里那档「待办」",
      status: "todo",
      due: null,
      at: null,
      start: legacyDay(-1),
      end: legacyDay(3),
      created: legacyDay(-1),
      archived: false,
      activities: [],
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
  const todoTask = afterMigrate.tasks.find((task) => task.id === "legacy-2");
  // 不比总条数：压测模式下启动会把种子里缺的补进来（见 store.ts 的 bootStore），
  // 库里本该有 legacy-1 加那 100 条种子。这里只关心两件事 —— 这条被救回来了、
  // 那条没有标题的垃圾没被写进去
  check(
    "老结构的存档被归位：缺字段补默认、旧时刻换时间戳、垃圾条丢弃",
    keptTask !== undefined &&
      !afterMigrate.tasks.some((task) => task.id === "legacy-junk") &&
      keptTask.status === "doing" &&
      // 老库里写着 `todo` 的（那档 2026-09-21 删了）也落到「进行中」
      todoTask?.status === "doing" &&
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

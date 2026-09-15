// ─────────────────────────────────────────────────────────────────────────────
// 分区密码与空闲锁定。
//
// 定位：这是**隐私屏风**，不是加密保险箱。密码只用来挡住路过的人看一眼，
// 不防拿到数据文件的人 —— 真要防那种场景，得做的是磁盘加密，不是应用层口令。
// 所以口令存的是哈希（不是为了安全强度，是为了不把原文摆在配置里），
// 而且**忘了就没法找回**：不做安全问题、不做邮箱找回，那种东西在单机应用里
// 只会把「防君子」变成「防自己」。
//
// 空闲锁定：一段时间没有任何输入就把已解锁的分区全部重新锁上。
// 计时只看真实的用户输入（键鼠），不动页面自己的重绘。
// ─────────────────────────────────────────────────────────────────────────────

import { loadSetting, saveSetting } from "../data/db";
import { activePartitionId, onPartitionChange } from "../data/partitions";
import { el } from "./dom";

const KEY_PASSWORDS = "lock.passwords";
const KEY_IDLE = "lock.idleMinutes";

type Listener = () => void;

const listeners = new Set<Listener>();

/** 分区 id → 口令哈希。空串表示未设密码。 */
let passwords: Record<string, string> = {};
/** 本次运行里已经解锁的分区。关掉应用即失效。 */
const unlocked = new Set<string>();
/** 空闲多少分钟后自动上锁，0 = 不自动锁。 */
let idleMinutes = 0;

let idleTimer: number | undefined;
let screen: HTMLElement | null = null;

/**
 * 口令哈希。刻意用一个非加密哈希（FNV-1a）：
 * 这里要挡的是「配置文件被人瞄一眼」，不是离线爆破 ——
 * 而真需要抗爆破时，缺的是密钥派生与加盐，换更花哨的哈希只是自我安慰。
 */
function hash(input: string): string {
  let value = 0x811c9dc5;
  for (let index = 0; index < input.length; index += 1) {
    value ^= input.charCodeAt(index);
    value = Math.imul(value, 0x01000193) >>> 0;
  }
  return value.toString(36);
}

const notify = (): void => {
  for (const listener of listeners) listener();
};

export const onLockChange = (listener: Listener): void => {
  listeners.add(listener);
};

export const hasPassword = (id: string): boolean => Boolean(passwords[id]);
export const isUnlocked = (id: string): boolean => !hasPassword(id) || unlocked.has(id);
export const idleLimit = (): number => idleMinutes;

export async function setPassword(id: string, password: string): Promise<void> {
  if (password) {
    passwords[id] = hash(password);
    // 只在你**正看着**这个分区时保持解锁：刚亲手输完口令的人显然知道口令，
    // 设完立刻把当前分区锁上，表现是「设置面板被一层锁屏整块盖住」——
    // 像被自己刚设的锁踢出去。但给别的分区设口令不在此列：那不是「你在里面」，
    // 照常上锁，下次切过去才要口令。
    if (activePartitionId() === id) unlocked.add(id);
    else unlocked.delete(id);
  } else {
    delete passwords[id];
    unlocked.delete(id);
  }
  await saveSetting(KEY_PASSWORDS, passwords);
  notify();
  syncScreen();
}

export async function setIdleMinutes(minutes: number): Promise<void> {
  idleMinutes = minutes;
  await saveSetting(KEY_IDLE, minutes);
  armIdle();
}

export function unlock(id: string, password: string): boolean {
  if (hash(password) !== passwords[id]) return false;
  unlocked.add(id);
  notify();
  syncScreen();
  return true;
}

/** 全部重新上锁（空闲超时、或用户手动上锁）。 */
export function lockAll(): void {
  if (unlocked.size === 0) return;
  unlocked.clear();
  notify();
  syncScreen();
}

/** 切到某个分区是否要先过口令这一关。 */
export function canEnter(id: string): boolean {
  return !hasPassword(id) || unlocked.has(id);
}

// ─── 空闲计时 ────────────────────────────────────────────────────────────────

function armIdle(): void {
  window.clearTimeout(idleTimer);
  if (idleMinutes <= 0) return;
  idleTimer = window.setTimeout(() => {
    lockAll();
  }, idleMinutes * 60_000);
}

function trackActivity(): void {
  // 只听这几类：页面自己的重绘、定时器都不算「有人在」
  for (const type of ["pointerdown", "keydown", "wheel"]) {
    window.addEventListener(type, () => armIdle(), { passive: true });
  }
}

// ─── 锁屏 ────────────────────────────────────────────────────────────────────

/**
 * 锁屏。它不是对话框而是**盖住整个应用的一层**：
 * 对话框能被人 Esc 掉、点遮罩关掉，那就不是锁了。
 */
function buildScreen(): HTMLElement {
  const input = el("input", { class: "pr-input", type: "password", placeholder: "分区口令" });
  const hint = el("div", { class: "lock-hint", text: "" });
  const button = el("button", { class: "btn primary", type: "button", text: "解锁" });

  const submit = (): void => {
    const id = activePartitionId();
    if (!input.value) return;
    if (unlock(id, input.value)) {
      input.value = "";
      return;
    }
    hint.textContent = "口令不对";
    input.value = "";
    input.focus();
  };

  button.addEventListener("click", submit);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") submit();
  });

  const node = el("div", { class: "lock-screen" }, [
    el("div", { class: "lock-card" }, [
      el("div", { class: "modal-title", text: "分区已锁定" }),
      el("div", { class: "modal-detail", text: "输入该分区的口令以继续" }),
      input,
      hint,
      el("div", { class: "modal-actions" }, [button]),
    ]),
  ]);

  document.body.append(node);
  return node;
}

/**
 * 重新判断当前分区该不该上锁（切分区、改密码、空闲超时后都要调）。
 * 对外暴露：切分区这件事发生在 shell/partition.ts，锁屏得跟着走。
 */
export function syncScreen(): void {
  const locked = !canEnter(activePartitionId());
  if (locked && !screen) screen = buildScreen();
  if (!locked && screen) {
    screen.remove();
    screen = null;
  }
  if (screen) {
    screen.classList.toggle("show", locked);
    if (locked) screen.querySelector("input")?.focus();
  }
}

// ─── 启动 ────────────────────────────────────────────────────────────────────

export async function bootLock(): Promise<void> {
  const [savedPasswords, savedIdle] = await Promise.all([
    loadSetting<Record<string, string>>(KEY_PASSWORDS),
    loadSetting<number>(KEY_IDLE),
  ]);
  passwords = savedPasswords ?? {};
  idleMinutes = savedIdle ?? 0;

  trackActivity();
  armIdle();
  syncScreen();
  // 切到上了锁的分区时立刻挡一层；切回来（已解锁或未设密码）则收起
  onPartitionChange(() => syncScreen());
}

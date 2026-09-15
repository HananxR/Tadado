// ─────────────────────────────────────────────────────────────────────────────
// 「保存后自动收起抽屉」偏好。
//
// DESIGN.md 规定「保存后自动收起」，但连着整理好几个任务时，每改一条就被弹回
// 表格是很烦的 —— 所以它做成开关，而不是照着规范写死。默认值仍跟着规范走。
//
// 状态放在外壳而不是抽屉里：设置面板要用这个值，而设置面板不该反过来去
// import 页面。
// ─────────────────────────────────────────────────────────────────────────────

import { loadSetting, saveSetting } from "../data/db";

const KEY = "behavior.closeOnSave";
let enabled = true;

export async function bootDrawerPref(): Promise<void> {
  const saved = await loadSetting<boolean>(KEY);
  if (saved !== null) enabled = saved;
}

export const shouldCloseOnSave = (): boolean => enabled;

export async function setCloseOnSave(next: boolean): Promise<void> {
  enabled = next;
  await saveSetting(KEY, next);
}

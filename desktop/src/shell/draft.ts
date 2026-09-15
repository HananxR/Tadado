// ─────────────────────────────────────────────────────────────────────────────
// 草稿：写了一半、还没变成任务的字。
//
// 任务数据是改完即存的（data/db.ts），唯独「还没建出来的」不在里面 ——
// 快速新建框打了三段字、批量框粘了十行，切个页面或者关掉窗口就全没了。
//
// 所以草稿跟设置一起落在 kv 里，而不是内存里：重开之后它还在，才叫草稿。
// ─────────────────────────────────────────────────────────────────────────────

import { loadSetting, saveSetting } from "../data/db";

const KEY = (name: string): string => `draft.${name}`;
const DEBOUNCE_MS = 500;
const timers = new Map<string, number>();

export async function loadDraft(name: string): Promise<string> {
  return (await loadSetting<string>(KEY(name))) ?? "";
}

/** 打字途中连续保存 —— 每敲一个字写一次库没必要，边打字边写也容易卡。 */
export function saveDraft(name: string, value: string): void {
  window.clearTimeout(timers.get(name));
  timers.set(
    name,
    window.setTimeout(() => void saveSetting(KEY(name), value), DEBOUNCE_MS),
  );
}

/** 提交成功了就不再是草稿。留着会在下次打开时又冒出来一次。 */
export async function dropDraft(name: string): Promise<void> {
  window.clearTimeout(timers.get(name));
  timers.delete(name);
  await saveSetting(KEY(name), "");
}

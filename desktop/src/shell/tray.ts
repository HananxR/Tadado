// ─────────────────────────────────────────────────────────────────────────────
// 系统托盘。常驻应用的第二入口：左键切换窗口显隐，右键出菜单。
//
// 窗口不再是「贴屏幕右缘的抽屉」，所以这里只做显隐，不做位置适配 ——
// 尺寸与位置交给窗口管理器（以及用户自己的拖动）。
// ─────────────────────────────────────────────────────────────────────────────

import { defaultWindowIcon } from "@tauri-apps/api/app";
import { invoke } from "@tauri-apps/api/core";
import { Menu, MenuItem } from "@tauri-apps/api/menu";
import { TrayIcon } from "@tauri-apps/api/tray";
import { hideWindow, showWindow, toggleWindow } from "./window";

// 句柄必须存在模块级变量上，否则会被 GC 回收、托盘图标随之消失
let tray: TrayIcon | null = null;

export async function setupTray(): Promise<string> {
  const showItem = await MenuItem.new({
    id: "show",
    text: "显示窗口",
    action: () => void showWindow(),
  });
  const hideItem = await MenuItem.new({
    id: "hide",
    text: "收起窗口",
    action: () => void hideWindow(),
  });
  const quitItem = await MenuItem.new({
    id: "quit",
    text: "退出 Tadado",
    action: () => void invoke("app_exit"),
  });

  const menu = await Menu.new({ items: [showItem, hideItem, quitItem] });

  const icon = await defaultWindowIcon();
  if (!icon) throw new Error("defaultWindowIcon() 返回空，无法设置托盘图标");

  tray = await TrayIcon.new({
    icon,
    tooltip: "Tadado",
    menu,
    showMenuOnLeftClick: false,
    action: (event) => {
      if (event.type === "Click" && event.button === "Left") void toggleWindow();
    },
  });

  return tray.id;
}

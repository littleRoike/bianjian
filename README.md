# 极简悬浮便笺 (Sticky Note)

一款使用 Python + Tkinter 开发的 Windows 桌面悬浮便签工具。极致轻量、无后台、无广告、无边框，风格对标 Windows 11 便笺 / 苹果备忘录。

## 功能特性

- 极简纯白无边框 UI，顶栏 + 大编辑区 + 底部格式栏
- 回车自动生成交互式复选框任务，点击勾选自动打上删除线
- 右键删除单条任务，支持批量清空
- 文本格式：加粗 / 斜体 / 下划线 / 删除线 / 高亮（可自定义高亮色）
- 快捷键：`Ctrl+B`、`Ctrl+I`、`Ctrl+U`、`Ctrl+H`、`Ctrl+S`
- 支持插入图片（PNG/GIF 原生；JPG 需安装 Pillow）
- 一键置顶切换、窗口自由拖拽、透明度滑块调节
- 自由缩放（右下角手柄）、最小尺寸限制
- 贴屏幕左侧自动缩进隐藏，鼠标划入自动弹出
- 实时自动持久化，保存为**标准 Markdown**（`- [ ] / - [x]`）
- 关闭/重启完整还原（含文本格式）

## 目录结构

```
bianjian/
├── main.py            # 主程序
├── requirements.txt   # 依赖声明
├── README.md
├── build.ps1          # 一键打包脚本（Windows PowerShell）
└── venv/              # 虚拟环境（由下方命令创建）
```

运行/打包后会在同目录生成：

```
notes.md        # 标准 Markdown 任务清单，可用任意笔记软件打开
notes.json      # 带完整格式元数据的备份（保证格式无损还原）
config.json     # 窗口位置、置顶、透明度等偏好
```

## 开发与运行

### 1. 创建虚拟环境

```powershell
cd E:\code\bianjian
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
# 可选：如需 JPG 图片支持
# pip install pillow
```

### 3. 直接运行

```powershell
python main.py
```

## 打包为单 EXE

推荐使用 `build.ps1`：

```powershell
.\venv\Scripts\Activate.ps1
.\build.ps1
```

或手动执行：

```powershell
pyinstaller -w -F --name "便笺" main.py
```

参数说明：

- `-w`：隐藏黑色控制台窗口
- `-F`：打包为单一 EXE 文件

打包产物位于 `dist\便笺.exe`，复制到任意 Windows 电脑双击即可使用（免安装 Python 环境）。

## 数据格式

保存为标准 Markdown 任务列表，兼容 VSCode / Obsidian / Typora 等主流编辑器：

```markdown
- [ ] 未完成任务
- [x] 已完成任务
- [ ] **加粗** *斜体* <u>下划线</u> ~~删除线~~ ==高亮==
```

若同目录存在 `notes.json`（带完整格式），加载时将优先使用它以完美还原所有格式；否则将从 `notes.md` 解析。两份文件同步写入。

## 快捷键一览

| 功能 | 快捷键 |
| ---- | ---- |
| 加粗 | `Ctrl + B` |
| 斜体 | `Ctrl + I` |
| 下划线 | `Ctrl + U` |
| 高亮 | `Ctrl + H` |
| 切换任务（增/删复选框） | `Ctrl + L` |
| 手动保存 | `Ctrl + S` |
| 撤销 / 重做 | `Ctrl + Z` / `Ctrl + Y` |

### 复选框增删说明

- **新增**：回车自动生成；或光标在普通文字行上按 `Ctrl+L` / 点击底部 `≡` 按钮转为任务；或框选多行后 `Ctrl+L` 批量加复选框
- **取消**：在已是任务的行按 `Ctrl+L` / 点 `≡` 即可去掉复选框变普通文字；也可把光标放到文字前按 `Backspace`（或放到行首按 `Delete`）整体删掉复选框
- **勾选**：鼠标点一下复选框切换 ☐/☑，文字自动打上删除线
- **整行删除**：右键 → 删除此行

## 常见问题

- **窗口贴到屏幕最左侧"消失"了？** 这是"贴边自动隐藏"特性，将鼠标移到屏幕最左边 3~5 像素即可唤出。
- **字体太小/太大？** 编辑 `main.py` 顶部的 `FONT_SIZE` 常量后重新打包。
- **打开后看不到光标？** 请点击编辑区内部使其获得焦点。

## License

MIT

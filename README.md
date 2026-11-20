# 暗黑重铸（Darkforge）

《艾尔登法环》（ELDEN RING）的整合模组：在原版游戏上加入暗黑类刷宝玩法——随机词条、分稀有度的新装备、装备工坊、
局内难度，以及可选的敌人随机。不改游戏目录里的任何文件，靠注入式加载器在启动时把改动叠上去。

> 非官方模组，与 FromSoftware、Bandai Namco 没有任何关系。启动后游戏以离线模式运行。

## 主要内容

- **新装备系统**：武器、防具、护符按稀有度（普通 / 稀有 / 史诗 / 传说）生成，带随机词条和数值；未鉴定物品、一键 / 定向鉴定、许愿石。
- **装备工坊**：游戏内界面，继承词条、提取护符、武器重铸、超限锻造、词条百科、搜索和筛选。
- **词条**：一百多种词条，包括数值类、命中 / 附近触发类，以及由运行时 DLL 实现的机制类词条（见切、猎印、霜铠等）；骨灰也有稀有度和词条。
- **局内难度**：多档难度，敌人血量、攻击、异常抗性、掉落随难度变化；「死亡」以上难度有改版头目、魇化精英、咒痕。
- **其他玩法**：斗技场试炼与无尽试炼、暗黑商店、卢恩银行、死亡惩罚、唤声船、蹬墙跳等。
- **敌人随机（可选）**：配合 thefifthmatt 的 EldenRingRandomizer 使用。随机器不随本项目分发，要自己下载。
- **启动器**：Python 写的图形界面（WebView2），负责生成每一局的游戏数据、启动游戏、存档定时备份、在线更新、导出诊断包。

玩家用的说明在 [`说明/启动说明.md`](说明/启动说明.md)，版本变化见 [`更新日志.txt`](更新日志.txt)。

## 目录结构

| 位置 | 内容 |
|---|---|
| `启动.bat` | 启动器入口 |
| `launcher/dfl/`、`launcher/ui/` | 启动器（Python 后端 + 网页界面） |
| `launcher/reroll/` | 每次启动时生成游戏数据的脚本：`reroll.py`（参数）、`scripts.py`（事件、对话、动作脚本），`rr/`、`sc/` 是各个功能模块，`data/` 是生成用的数据 |
| `dev/dark_core/` | 运行时主 DLL：新装备、词条机制、难度、斗技场等，一个功能一个模块 |
| `dev/dark_ui/` | 游戏内界面（装备工坊、词条百科），基于 hudhook + Dear ImGui |
| `dev/dark_lock/`、`dark_sell/`、`dark_slot/`、`dark_wings/` | 物品锁定、一键出售、第五个护符槽、熔炉百相之羽飞行 |
| `dev/dark_dev/` | 开发测试用的 F9 面板（不随整合包发布） |
| `dev/item_system/` | 词条库的提取、生成工具和设计文档 |
| `dev/vendor/` | 第三方源码的本地副本（见下面「许可」） |
| `dev/tools/` | 打包、离线更新包、发布用的工具 |

仓库里不包含：游戏文件、随机器（`randomizer/`）、加载器（`yafsml/`）、启动器自带的 Python / .NET / WebView2 运行库、
编译好的 DLL（`dll/`），以及每次启动生成的 `out/`。完整的整合包从发布页下载。

## 编译

各 DLL 是独立的 Rust crate（`dev/<名字>/`），用 `stable-x86_64-pc-windows-gnu` 工具链编译：

```powershell
cd dev\dark_core
cargo test --release
cargo build --release      # 生成 target\release\dark_core.dll，复制到 dll\dark_core\
```

需要的工具：

- Rust 的 `llvm-tools` 组件：GNU 工具链自带的 dlltool 缺汇编器，把 llvm-tools 里的 `llvm-ar.exe` 复制一份改名成 `dlltool.exe` 当 llvm-dlltool 用；
  链接用工具链自带的 `rust-lld`（已在各 crate 的 `.cargo/config.toml` 里设好）。
- `dark_ui`、`dark_dev` 要编译 Dear ImGui（C++）：用 [llvm-mingw](https://github.com/mstorsjo/llvm-mingw)（ucrt-x86_64）。

这两样工具的位置因机器而异，不写在仓库里。放到仓库**外面**、上级目录里的 `.cargo/config.toml`（例如仓库放在游戏的 `Game\` 下面时用
`Game\.cargo\config.toml`），cargo 会和各 crate 自己的配置合并：

```toml
[target.x86_64-pc-windows-gnu]
rustflags = [
  "-C", "dlltool=<工具目录>/dlltool.exe",
  # 可选：编进 DLL 的源码路径（panic 日志里会出现）不带本机目录
  "--remap-path-prefix=<仓库的上级目录>=game",
  "--remap-path-prefix=<CARGO_HOME>\\registry\\src=cargo",
]

[env]
CC_x86_64_pc_windows_gnu = "<llvm-mingw>/bin/x86_64-w64-mingw32-clang.exe"
CXX_x86_64_pc_windows_gnu = "<llvm-mingw>/bin/x86_64-w64-mingw32-clang++.exe"
AR_x86_64_pc_windows_gnu = "<llvm-mingw>/bin/llvm-ar.exe"
```

`dev/` 下的开发脚本按自己所在的位置找仓库和游戏目录（假定仓库放在游戏的 `Game\` 下面）。用到外部工具的脚本读这两个环境变量：

- `SMITHBOX_DIR`：Smithbox 的解压目录（要它的 paramdef 和行名表）；
- `ER_NEW_EXE`：另一个版本的 `eldenring.exe`（核对两个游戏版本的地址时用）。

打包：`python dev\tools\make_package.py <输出.zip>`（`--dry` 只检查不写）。

## 许可

本项目自己的代码和数据按 **GNU 通用公共许可证第 3 版（GPL-3.0）** 发布，全文见 [`LICENSE`](LICENSE)。

下面这些不是本项目的作品，各自保留原来的许可和权利，GPL-3.0 不覆盖它们：

- `dev/vendor/fromsoftware-rs/`：[fromsoftware-rs](https://github.com/vswarte/fromsoftware-rs)（Vincent Swarte），MIT / Apache-2.0。
  其中 `crates/eldenring/src/rva/rva_ww_2720.rs`、`rva_jp_2721.rs` 取自上游较新的提交，许可是 MIT NON-AI / Apache-2.0 NON-AI，
  附加了「不得用于训练机器学习」的限制（`LICENSE-*-NON-AI`）。改动见 `dev/vendor/README-dark_reforged.txt`。
- `dev/vendor/hudhook/`：[hudhook](https://github.com/veeenu/hudhook)，MIT；其中的 MinHook 按它自己的许可（`vendor/minhook/LICENSE.txt`）。
- `launcher/reroll/bin/` 里的 zstd：见 `LICENSE-zstd.txt`。
- `launcher/ui/` 的界面框架：tamikip，MIT（`LICENSE-launcher-ui-shell.txt`）。
- `dev/dark_ui/sounds/kenney/`：Kenney，CC0（`License.txt`）。
- `launcher/reroll/data/player/c0000.hks`：在社区整理的反编译脚本（[EldenRingHKS](https://github.com/ividyon/EldenRingHKS)，Vawser 等）基础上修改。
- `launcher/reroll/data/bossmods/`：整合的头目模组（来源写在各自的 `mod.json`）的改动描述，权利归原作者。
- 词条库最初从 RNG Lands 模组提取，权利归原作者。
- 从游戏里读出或改出来的数据和素材（参数布局、文本、图标、特效、`dev/item_system/sfx/`、存档包的公钥等）版权属于 FromSoftware / Bandai Namco，
  只为制作模组使用。
- 运行时用到但不在仓库里的：EldenRingRandomizer（thefifthmatt，不许转发，要自己下载）、YAFSML 加载器、Seamless Co-op 以及 `dll/` 里的其他模组。

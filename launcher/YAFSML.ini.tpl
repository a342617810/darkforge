; =====================================================================
;  Dark Reforged 启动器 · YAFSML 配置模板
;  ---------------------------------------------------------------------
;  这个文件是模板，启动器每次启动前会把 [dll] / [mod] 两段分别填进去，
;  生成真正的 yafsml\YAFSML.ini（每次启动都重新生成，改了会被覆盖）。
;  玩家要加 mod / 改设置：把 mod 放进整合包根目录的 mods 文件夹（DLL 放 dll 文件夹），
;  或者改整合包根目录的 YAFSML自定义.ini（启动器的「模组」里有按钮）。这两样整合包更新不会动。
;
;  [mod] 规则：后声明的 mod 覆盖先声明的 mod 的同名文件
;             （所以“随机器输出”永远放在最后）
; =====================================================================
game=eldenring


; 各游戏通用补丁
[patch]
skip_intro=1

; 阻止 mod 里的 regulation.bin 往存档写“已修改”标记
prevent_regulation_save_write=1

; 1 = 用 mimalloc 替换游戏的分配器。必须开：2026-10-24 试过 0，进游戏就崩（原版的堆不够用）
patch_mem=1
; 1 = 给游戏单独划一块高地址的 mimalloc 内存区（YAFSML 0.10.3 起作者的默认值，0.10.4 自带配置也是 1）。
; 2026-11-01 试过开 1（想减少偶发的内存崩溃），用户说开了反而卡游戏，关回 0
patch_mem_dedicated_heap=0
patch_mem_heap_size=0
boot_boost=1
disable_arxan=0

; 独立存档：ER0000.sl2 -> ER0000.rng（Dark Reforged 专用，和原版 .sl2、法魂 .cnv 都分开；dll\ErdTools 的 save_extension 启动器按启动方式写：单机 rng、联机 co2）
replace_save_filename=.rng
; 联机启动（Seamless Co-op 把扩展名换成 co2）：ER0000.co2 -> ER0000.rngcoop（和单机存档、法魂的联机存档都分开）。
; 换完的名字不能还以 .co2 结尾：以前是 .rng.co2，联机时有组件按真名再打开它，YAFSML 又当成联机存档改一次、复制一份，
; 套出 ER0000.rng.rng.co2、.rng.rng.rng.co2……（2026-11-17 玩家诊断包）。旧的 ER0000.rng.co2 由启动器联机启动前复制过来（launcher\dfl\backup.py move_coop_save_name）
replace_seamless_coop_save_filename=.rngcoop

enable_ime=0


; 通用优化
[tweak]
cpu_affinity=0


; 日志（每次启动重写 yafsml\log\YAFSML.log）
[log]
console=0
log_file=1
log_level=info


; 游戏启动时加载的外部 DLL
; 条件：early / data_ready / delay,毫秒 / after,名字（互斥）；不写 = SteamAPI_Init 之后
[dll]
@DLL_LINES@
; 独立存档 dll（可选，默认不用）：本机 alt-saves.log 显示它在游戏 1.17 上 panic，
; 且独立存档已由上面的 replace_save_filename=.rng 实现。要试就删掉行首分号：
;eldenring_alt_saves=dll\eldenring_alt_saves.dll


; 扫描并覆盖游戏数据的 mod 目录（后声明覆盖先声明）
[mod]
@MOD_LINES@

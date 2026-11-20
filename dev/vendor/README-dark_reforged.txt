fromsoftware-rs 本地副本（dark_sell / dark_lock 用）

来源：https://github.com/vswarte/fromsoftware-rs
- 代码：提交 29fd1381ce458d5748c1fd2d188a808471f11972（适配 ELDEN RING 1.17.1，eldenring.exe 2.7.1.0），MIT / Apache-2.0（LICENSE-MIT、LICENSE-ASL2）。
- 加进来的：crates/eldenring/src/rva/rva_ww_2720.rs、rva_jp_2721.rs，取自提交 b7263368e97a（适配 1.17.2，2.7.2.0 / 日版 2.7.2.1），
  那个版本的许可证是 LICENSE-MIT-NON-AI / LICENSE-ASL2-NON-AI（也放在这里）。
- 改动：crates/eldenring/src/rva.rs 的版本识别同时认 2.7.1.0 / 2.7.1.1 / 2.7.2.0 / 2.7.2.1，按版本选地址表；
  crates/eldenring/src/cs/chr_ins/module/physics.rs 的 root_motion 改成 pub（dark_wings 用）。别的没改。

游戏再更新时：从上游取对应版本的 rva_ww.rs / rva_jp.rs，照同样的办法加一组。

----------------------------------------------------------------
hudhook 本地副本（dark_ui / dark_dev 用，2026-11-19 加）

来源：crates.io 的 hudhook 0.9.3（https://github.com/veeenu/hudhook 提交 72e1cc062c35），MIT（hudhook\LICENSE），整包照拷。
改动（都在注释里标了 dark_reforged）：
- src/renderer/input.rs：WM_CHAR 收到半个 UTF-16 代理字符（emoji、扩展区生僻字）时丢掉，不再 unwrap 失败 abort。
- src/renderer/backend/dx12.rs：
  - 贴图数到 8/16/32… 要换更大的 SRV 堆时，先等前几帧的命令列表跑完再换（旧堆马上释放，GPU 可能还在读）；
  - 上传贴图不再每次漏一块 upload buffer：最近 4 块先留着，再往后上传时才释放；等 GPU 失败时才故意留着；
  - 画的时候遇到不在贴图表里的编号（管线重建前留下的）跳过，不越界 panic；replace_texture 同样返回错误。
- src/util.rs：Fence 释放时关掉事件句柄（每次管线重建原来漏两个）。
升级 hudhook 时：换成新版本的源码，再把上面几处补回去（或者确认上游已经修了）。

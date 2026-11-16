// RNG Lands 地图工具（离线用：做 data\dummy 里的固定地图；运行时不需要它，也就不需要 .NET）：
// 用随机器自带的 SoulsFormats 改 MSB（部件之间按名字引用，加部件后编号自动重排）。
//   msbtool add   <输入msb> <输出msb> <部件名> <模型> <NpcParam> <ThinkParam> <x> <y> <z> <朝向> <实体ID> [碰撞部件名]
//       加一个敌人（照抄地图里第一个普通敌人的其余设置）
//   msbtool clone <输入msb> <输出msb> <原部件名> <新部件名> <实体ID> <x> <y> <z> <朝向> [碰撞部件名]
//       复制一个现成部件（敌人 / 资产 / 玩家部件都行）到新位置，换名字和实体 ID
//   msbtool resave <输入msb> <输出msb>
//       原样读进来再写出去（运行时同步随机器改动用的对照底子：和随机器输出一样经过 SoulsFormats 重写）
//   msbtool talk <输入msb> <输出msb> <部件名> <对话编号> [敌人参数]
//       改敌人部件的对话编号（TalkID → 对话包里的 t<编号>.esd），给了敌人参数就一起改（对话时显示的名字跟着敌人参数走）
//   msbtool import <输入msb> <输出msb> <来源msb> <模型名> <新部件名> <实体ID> <x> <y> <z> <朝向>
//       从别的地图照抄第一个用这个模型的部件（资产 / 敌人），模型表里没有就把来源的模型条目一起抄过来；部件名引用清空
//   msbtool cloneregion <输入msb> <输出msb> <原区域实体ID> <新区域名> <x> <y> <z>
//       复制一个区域（比如赐福光的特效区域）到新位置，实体 ID 清零、部件名引用清空
//   msbtool bndadd <输入bnd> <输出bnd> <新文件名> <照抄的文件名>
//       往 BND4（对话包）里加一个文件，内容先照抄包里的另一个文件（运行时 Python 再换成真正的内容；文件名哈希表由 SoulsFormats 重建）
//   msbtool batch <输入msb> <输出msb> <清单>
//       一次读写做一批（竞技场试炼 2026-11-10，sc/arena.py）。清单每行 Tab 分隔，# 开头是注释：
//         drawfrom <部件名>        之后导入的敌人照这个部件（地面碰撞）的显示 / 绘制分组；其余未知字段照本图第一个敌人（模板）
//         import <来源msb> <来源部件名> <新部件名> <实体ID> <x> <y> <z> <朝向> <敌人参数> <思考参数|-1> <碰撞部件名> <分组实体|0>
//             从别的地图照抄指定的敌人部件（模型条目没有就一起抄），部件名引用清空、换参数和碰撞
//         clone <原部件名> <新部件名> <实体ID> <x> <y> <z> <朝向>
//             同 clone 命令（玩家部件 = 传送落点）
//         player <来源msb> <来源玩家部件名> <新部件名> <实体ID> <x> <y> <z> <朝向>
//             从别的地图照抄一个玩家部件（这张图没有玩家部件时用，比如野外小格子），模型条目没有就一起抄
//         region <来源msb|-> <来源区域实体ID> <新区域名> <实体ID> <x> <y> <z> <朝向>
//             照抄一个区域（- = 本图；比如 SpawnPoint 当复活点），部件名引用清空
//       实体 ID 已经被本图的部件 / 区域用了就失败（不重复加）
// 需要 .NET 8；SoulsFormats.dll / oo2core 放在本程序旁边，并在本程序目录下运行（SoulsFormats 按工作目录找 oo2core）。
// 成功最后一行输出 ok。
using System;
using System.Globalization;
using System.Numerics;
using SoulsFormats;

class MsbTool {
    static float F(string s) { return float.Parse(s, CultureInfo.InvariantCulture); }

    // 部件的实例编号（SoulsFormats 里叫 Unk08）要和名字末尾的数字一致：游戏按「模型 + 实例编号」认部件，
    // 复制出来的部件编号不改的话会被当成原来那个（新赐福被认成圆桌大赐福）
    static void SetInstance(MSBE.Part p) {
        int k = p.Name.LastIndexOf('_');
        p.Unk08 = int.Parse(p.Name.Substring(k + 1), CultureInfo.InvariantCulture);
    }

    static int Add(string[] a) {
        var m = MSBE.Read(a[1]);
        string name = a[3], model = a[4];
        if (m.Models.Enemies.Find(x => x.Name == model) == null)
            m.Models.Enemies.Add(new MSBE.Model.Enemy { Name = model, SibPath = @"N:\GR\data\Model\chr\" + model + @"\sib\" + model + ".sib" });
        m.Parts.Enemies.RemoveAll(x => x.Name == name);       // 重复运行时替换
        var tpl = m.Parts.Enemies.Find(x => x.ModelName != "c1000" && x.ModelName != "c0000" && x.ModelName != "c0100");
        if (tpl == null) { Console.WriteLine("no template enemy"); return 1; }
        var e = (MSBE.Part.Enemy)tpl.DeepCopy();
        e.Name = name;
        SetInstance(e);
        e.ModelName = model;
        e.NPCParamID = int.Parse(a[5]);
        e.ThinkParamID = int.Parse(a[6]);
        e.Position = new Vector3(F(a[7]), F(a[8]), F(a[9]));
        e.Rotation = new Vector3(0, F(a[10]), 0);
        e.EntityID = uint.Parse(a[11]);
        for (int i = 0; i < e.EntityGroupIDs.Length; i++) e.EntityGroupIDs[i] = 0;
        e.WalkRouteName = "";
        e.CollisionPartName = a.Length > 12 ? a[12] : "";
        m.Parts.Enemies.Add(e);
        m.Write(a[2]);
        return MSBE.Read(a[2]).Parts.Enemies.Find(x => x.Name == name) == null ? 1 : 0;
    }

    static int Clone(string[] a) {
        var m = MSBE.Read(a[1]);
        string src = a[3], name = a[4];
        foreach (var p in m.Parts.GetEntries())
            if (p.Name == name) { Console.WriteLine("part exists: " + name); return 1; }
        MSBE.Part found = null;
        foreach (var p in m.Parts.GetEntries())
            if (p.Name == src) found = p;
        if (found == null) { Console.WriteLine("no part: " + src); return 1; }
        var c = found.DeepCopy();
        c.Name = name;
        SetInstance(c);
        c.EntityID = uint.Parse(a[5]);
        c.Position = new Vector3(F(a[6]), F(a[7]), F(a[8]));
        c.Rotation = new Vector3(0, F(a[9]), 0);
        for (int i = 0; i < c.EntityGroupIDs.Length; i++) c.EntityGroupIDs[i] = 0;
        var en = c as MSBE.Part.Enemy;
        if (en != null) {
            en.WalkRouteName = "";
            if (a.Length > 10) en.CollisionPartName = a[10];
            m.Parts.Enemies.Add(en);
        } else if (c is MSBE.Part.Player) {
            // 玩家部件 = 赐福的传送落点 / 复活点（实体 ID 照「赐福资产 - 970」，比如资产 14001954 → 14000984），没有它传送会落到地图默认位置
            m.Parts.Players.Add((MSBE.Part.Player)c);
        } else {
            var asset = c as MSBE.Part.Asset;
            if (asset == null) { Console.WriteLine("only enemies / assets / players"); return 1; }
            m.Parts.Assets.Add(asset);
        }
        m.Write(a[2]);
        foreach (var p in MSBE.Read(a[2]).Parts.GetEntries())
            if (p.Name == name) return 0;
        return 1;
    }

    static int Talk(string[] a) {
        var m = MSBE.Read(a[1]);
        var e = m.Parts.Enemies.Find(x => x.Name == a[3]);
        if (e == null) { Console.WriteLine("no enemy part: " + a[3]); return 1; }
        e.TalkID = int.Parse(a[4]);
        if (a.Length > 5) e.NPCParamID = int.Parse(a[5]);
        m.Write(a[2]);
        return 0;
    }

    static void ClearPartRefs(object o) {
        foreach (var p in o.GetType().GetProperties()) {
            if (!p.CanWrite) continue;
            if (p.PropertyType == typeof(string) && p.Name.EndsWith("PartName")) p.SetValue(o, null);
            else if (p.PropertyType == typeof(string[]) && p.Name.EndsWith("PartNames")) p.SetValue(o, new string[((string[])p.GetValue(o)).Length]);
        }
    }

    static int Import(string[] a) {
        var m = MSBE.Read(a[1]);
        var src = MSBE.Read(a[3]);
        string model = a[4], name = a[5];
        MSBE.Part found = null;
        foreach (var p in src.Parts.GetEntries())
            if (found == null && p.ModelName == model && (p is MSBE.Part.Asset || p is MSBE.Part.Enemy)) found = p;
        if (found == null) { Console.WriteLine("no part with model " + model); return 1; }
        var c = found.DeepCopy();
        c.Name = name;
        SetInstance(c);
        c.EntityID = uint.Parse(a[6]);
        c.Position = new Vector3(F(a[7]), F(a[8]), F(a[9]));
        c.Rotation = new Vector3(0, F(a[10]), 0);
        for (int i = 0; i < c.EntityGroupIDs.Length; i++) c.EntityGroupIDs[i] = 0;
        ClearPartRefs(c);
        if (c is MSBE.Part.Asset) {
            if (m.Models.Assets.Find(x => x.Name == model) == null) m.Models.Assets.Add((MSBE.Model.Asset)src.Models.Assets.Find(x => x.Name == model).DeepCopy());
            m.Parts.Assets.Add((MSBE.Part.Asset)c);
        } else {
            if (m.Models.Enemies.Find(x => x.Name == model) == null) m.Models.Enemies.Add((MSBE.Model.Enemy)src.Models.Enemies.Find(x => x.Name == model).DeepCopy());
            m.Parts.Enemies.Add((MSBE.Part.Enemy)c);
        }
        m.Write(a[2]);
        foreach (var p in MSBE.Read(a[2]).Parts.GetEntries())
            if (p.Name == name) return 0;
        return 1;
    }

    static int CloneRegion(string[] a) {
        var m = MSBE.Read(a[1]);
        uint ent = uint.Parse(a[3]);
        MSBE.Region src = null;
        foreach (var r in m.Regions.GetEntries())
            if (r.EntityID == ent) src = r;
        if (src == null) { Console.WriteLine("no region with entity " + ent); return 1; }
        var c = src.DeepCopy();
        c.Name = a[4];
        c.EntityID = 0;
        c.Position = new Vector3(F(a[5]), F(a[6]), F(a[7]));
        ClearPartRefs(c);
        m.Regions.Add(c);
        m.Write(a[2]);
        foreach (var r in MSBE.Read(a[2]).Regions.GetEntries())
            if (r.Name == a[4]) return 0;
        return 1;
    }

    static int BndAdd(string[] a) {
        var b = BND4.Read(a[1]);
        BinderFile src = null;
        int maxId = -1;
        foreach (var f in b.Files) {
            if (f.Name.EndsWith("\\" + a[4])) src = f;
            if (f.Name.EndsWith("\\" + a[3])) { Console.WriteLine("exists: " + a[3]); return 1; }
            if (f.ID > maxId) maxId = f.ID;
        }
        if (src == null) { Console.WriteLine("no file: " + a[4]); return 1; }
        string name = src.Name.Substring(0, src.Name.LastIndexOf('\\') + 1) + a[3];
        b.Files.Add(new BinderFile(src.Flags, maxId + 1, name, src.Bytes));
        b.Write(a[2]);
        return 0;
    }

    // 显示 / 绘制分组、碰撞遮罩（各类部件的 Unk1，基类上没有，按名字反射取）
    static void CopyGroups(MSBE.Part from, MSBE.Part to) {
        var uf = from.GetType().GetProperty("Unk1");
        var ut = to.GetType().GetProperty("Unk1");
        if (uf == null || ut == null) return;
        object a = uf.GetValue(from), b = ut.GetValue(to);
        foreach (var n in new string[] { "DisplayGroups", "DrawGroups", "CollisionMask" }) {
            var pa = a.GetType().GetProperty(n);
            var pb = b.GetType().GetProperty(n);
            if (pa == null || pb == null) continue;
            var src = (Array)pa.GetValue(a);
            var dst = (Array)pb.GetValue(b);
            Array.Copy(src, dst, Math.Min(src.Length, dst.Length));
        }
    }

    static bool EntityUsed(MSBE m, uint ent) {
        if (ent == 0) return false;
        foreach (var p in m.Parts.GetEntries()) if (p.EntityID == ent) return true;
        foreach (var r in m.Regions.GetEntries()) if (r.EntityID == ent) return true;
        return false;
    }

    static int Batch(string[] a) {
        var m = MSBE.Read(a[1]);
        var srcs = new System.Collections.Generic.Dictionary<string, MSBE>();
        MSBE.Part.Enemy tpl = m.Parts.Enemies.Count > 0 ? m.Parts.Enemies[0] : null;
        MSBE.Part groups = null;
        var names = new System.Collections.Generic.List<string>();
        int no = 0;
        foreach (var raw in System.IO.File.ReadAllLines(a[3])) {
            no++;
            if (raw.Length == 0 || raw.StartsWith("#")) continue;
            var f = raw.Split('\t');
            uint want = 0;
            if (f[0] == "import" && f.Length >= 13) want = uint.Parse(f[4]);
            else if (f[0] == "clone" && f.Length >= 8) want = uint.Parse(f[3]);
            else if (f[0] == "player" && f.Length >= 9) want = uint.Parse(f[4]);
            else if (f[0] == "region" && f.Length >= 9) want = uint.Parse(f[4]);
            if (EntityUsed(m, want)) { Console.WriteLine("line " + no + ": entity used " + want); return 1; }
            if (f[0] == "region" && f.Length >= 9) {
                MSBE src = m;
                if (f[1] != "-" && !srcs.TryGetValue(f[1], out src)) { src = MSBE.Read(f[1]); srcs[f[1]] = src; }
                uint from = uint.Parse(f[2]);
                MSBE.Region found = null;
                foreach (var r in src.Regions.GetEntries()) if (r.EntityID == from) found = r;
                if (found == null) { Console.WriteLine("line " + no + ": no region with entity " + from); return 1; }
                foreach (var r in m.Regions.GetEntries()) if (r.Name == f[3]) { Console.WriteLine("line " + no + ": region exists " + f[3]); return 1; }
                var c = found.DeepCopy();
                c.Name = f[3];
                c.EntityID = want;
                c.Position = new Vector3(F(f[5]), F(f[6]), F(f[7]));
                c.Rotation = new Vector3(0, F(f[8]), 0);
                ClearPartRefs(c);
                m.Regions.Add(c);
                continue;
            }
            if (f[0] == "player" && f.Length >= 9) {
                MSBE src;
                if (!srcs.TryGetValue(f[1], out src)) { src = MSBE.Read(f[1]); srcs[f[1]] = src; }
                var found = src.Parts.Players.Find(x => x.Name == f[2]);
                if (found == null) { Console.WriteLine("line " + no + ": no player part " + f[2] + " in " + f[1]); return 1; }
                foreach (var p in m.Parts.GetEntries()) if (p.Name == f[3]) { Console.WriteLine("line " + no + ": part exists " + f[3]); return 1; }
                var c = (MSBE.Part.Player)found.DeepCopy();
                c.Name = f[3];
                SetInstance(c);
                c.EntityID = want;
                c.Position = new Vector3(F(f[5]), F(f[6]), F(f[7]));
                c.Rotation = new Vector3(0, F(f[8]), 0);
                for (int i = 0; i < c.EntityGroupIDs.Length; i++) c.EntityGroupIDs[i] = 0;
                ClearPartRefs(c);
                if (m.Models.Players.Find(x => x.Name == c.ModelName) == null) {
                    var mod = src.Models.Players.Find(x => x.Name == c.ModelName);
                    if (mod == null) { Console.WriteLine("line " + no + ": no player model " + c.ModelName); return 1; }
                    m.Models.Players.Add((MSBE.Model.Player)mod.DeepCopy());
                }
                m.Parts.Players.Add(c);
                names.Add(c.Name);
                continue;
            }
            if (f[0] == "drawfrom" && f.Length >= 2) {
                groups = null;
                foreach (var p in m.Parts.GetEntries()) if (p.Name == f[1]) groups = p;
                if (groups == null) { Console.WriteLine("line " + no + ": no part " + f[1]); return 1; }
            } else if (f[0] == "import" && f.Length >= 13) {
                MSBE src;
                if (!srcs.TryGetValue(f[1], out src)) { src = MSBE.Read(f[1]); srcs[f[1]] = src; }
                var found = src.Parts.Enemies.Find(x => x.Name == f[2]);
                if (found == null) { Console.WriteLine("line " + no + ": no enemy " + f[2] + " in " + f[1]); return 1; }
                var e = (MSBE.Part.Enemy)found.DeepCopy();
                e.Name = f[3];
                SetInstance(e);
                e.EntityID = uint.Parse(f[4]);
                e.Position = new Vector3(F(f[5]), F(f[6]), F(f[7]));
                e.Rotation = new Vector3(0, F(f[8]), 0);
                for (int i = 0; i < e.EntityGroupIDs.Length; i++) e.EntityGroupIDs[i] = 0;
                e.EntityGroupIDs[0] = uint.Parse(f[12]);
                ClearPartRefs(e);
                e.WalkRouteName = "";
                e.CollisionPartName = f[11];
                e.NPCParamID = int.Parse(f[9]);
                int think = int.Parse(f[10]);
                if (think >= 0) e.ThinkParamID = think;
                if (tpl != null) {
                    e.Unk10.MapID = tpl.Unk10.MapID;
                    e.Unk10.Unk04 = tpl.Unk10.Unk04;
                    e.Unk10.Unk0C = tpl.Unk10.Unk0C;
                    e.Unk10.Unk10 = tpl.Unk10.Unk10;
                    e.Unk10.Unk14 = tpl.Unk10.Unk14;
                    e.Gparam.LightSetID = tpl.Gparam.LightSetID;
                    e.Gparam.FogParamID = tpl.Gparam.FogParamID;
                    e.Gparam.LightScatteringID = tpl.Gparam.LightScatteringID;
                    e.Gparam.EnvMapID = tpl.Gparam.EnvMapID;
                    e.MapStudioLayer = tpl.MapStudioLayer;
                }
                if (groups != null) CopyGroups(groups, e);
                // 模型条目：人形敌人（c0000）的模型在玩家模型表里，本图有同名的哪一类都行
                bool have = false;
                foreach (var x in m.Models.GetEntries()) if (x.Name == e.ModelName) have = true;
                if (!have) {
                    var mod = src.Models.Enemies.Find(x => x.Name == e.ModelName);
                    var pmod = src.Models.Players.Find(x => x.Name == e.ModelName);
                    if (mod != null) m.Models.Enemies.Add((MSBE.Model.Enemy)mod.DeepCopy());
                    else if (pmod != null) m.Models.Players.Add((MSBE.Model.Player)pmod.DeepCopy());
                    else { Console.WriteLine("line " + no + ": no model " + e.ModelName); return 1; }
                }
                m.Parts.Enemies.RemoveAll(x => x.Name == e.Name);
                m.Parts.Enemies.Add(e);
                names.Add(e.Name);
            } else if (f[0] == "clone" && f.Length >= 8) {
                MSBE.Part found = null;
                foreach (var p in m.Parts.GetEntries()) if (p.Name == f[1]) found = p;
                if (found == null) { Console.WriteLine("line " + no + ": no part " + f[1]); return 1; }
                foreach (var p in m.Parts.GetEntries()) if (p.Name == f[2]) { Console.WriteLine("line " + no + ": part exists " + f[2]); return 1; }
                var c = found.DeepCopy();
                c.Name = f[2];
                SetInstance(c);
                c.EntityID = uint.Parse(f[3]);
                c.Position = new Vector3(F(f[4]), F(f[5]), F(f[6]));
                c.Rotation = new Vector3(0, F(f[7]), 0);
                for (int i = 0; i < c.EntityGroupIDs.Length; i++) c.EntityGroupIDs[i] = 0;
                if (c is MSBE.Part.Player) m.Parts.Players.Add((MSBE.Part.Player)c);
                else if (c is MSBE.Part.Enemy) m.Parts.Enemies.Add((MSBE.Part.Enemy)c);
                else if (c is MSBE.Part.Asset) m.Parts.Assets.Add((MSBE.Part.Asset)c);
                else { Console.WriteLine("line " + no + ": only enemies / assets / players"); return 1; }
                names.Add(c.Name);
            } else { Console.WriteLine("line " + no + ": bad line"); return 1; }
        }
        m.Write(a[2]);
        var back = MSBE.Read(a[2]);
        foreach (var n in names) {
            bool ok = false;
            foreach (var p in back.Parts.GetEntries()) if (p.Name == n) ok = true;
            if (!ok) { Console.WriteLine("missing after write: " + n); return 1; }
        }
        Console.WriteLine("parts " + names.Count);
        return 0;
    }

    static int Main(string[] a) {
        int r;
        if (a.Length == 4 && a[0] == "batch") r = Batch(a);
        else if (a.Length == 3 && a[0] == "resave") { MSBE.Read(a[1]).Write(a[2]); r = 0; }
        else if ((a.Length == 5 || a.Length == 6) && a[0] == "talk") r = Talk(a);
        else if (a.Length == 5 && a[0] == "bndadd") r = BndAdd(a);
        else if (a.Length == 11 && a[0] == "import") r = Import(a);
        else if (a.Length == 8 && a[0] == "cloneregion") r = CloneRegion(a);
        else if (a.Length >= 12 && a[0] == "add") r = Add(a);
        else if (a.Length >= 10 && a[0] == "clone") r = Clone(a);
        else { Console.WriteLine("usage: msbtool add in out name model npc think x y z yaw entity [collision] | clone in out src name entity x y z yaw [collision]"); return 2; }
        Console.WriteLine(r == 0 ? "ok" : "failed");
        return r;
    }
}

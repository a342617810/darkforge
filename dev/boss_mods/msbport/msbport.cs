// Boss 模组的地图移植（dev\boss_mods\build.py 离线跑；敌人随机的高难度世界里 sc/bossarena.py 启动时也跑）：
//   msbport <原版msb> <模组msb> <输出msb> <部件> [...]
//   部件写法：
//     名字[@敌人参数@思考参数]   把模组地图里的这个部件拷进来（原版里已经有同名的就报错）；带 @ 的敌人部件换成这两个参数编号
//                                （模组新加的参数行换过编号，免得和随机器新建的行撞）
//     =名字[@敌人参数@思考参数]  用模组的同名部件替换（原版里没有就当新加）
//     -名字                      删掉原版里的这个部件（没有就跳过：敌人随机的世界里可能已经被换掉；
//                                还有别的部件 / 区域 / 事件（宝箱等）按名字引用它就留着，免得写不出来或丢东西）
//     模组名>新名字[@…]          拷模组的这个部件，改成新名字加进来（模组拿原版部件改作他用时，原版那个保留）
//     模组名~实体>新名字[@…]     模组地图里有同名的几个部件时，按实体编号挑（一般再改个名字，免得重名）
//     ^名字                      区域：拷模组的这个区域（原版里有同名的就替换）
//     %名字                      事件表：拷模组的这个条目（敌人生成器等，原版里有同名的就替换）
//     :名字                      部件：只把位置和朝向改成模组的，别的不动（敌人随机的世界里敌人参数是随机器 / 重随配的，要留着）
// 删部件（-）支持任何类型（敌人 / 物件 / 地图块 / 碰撞…），按类型找它在哪张表里。
// 写出前：拷 / 换进来的部件和区域按名字引用的部件（*PartName / *PartNames）在这张图里没有了（敌人随机的世界里随机器删掉的），
// 就把那个引用清掉，免得写不出来。
// 模型表里没有的模型条目一起拷。部件之间按名字引用，SoulsFormats 写出时自己重排编号。
// 输入输出都用解压后的 .msb（DCX 由 Python 处理，免得找 oo2core）。成功最后一行输出 ok。
using System;
using SoulsFormats;

class MsbPort {
    static MSBE.Part Find(MSBE m, string name) {
        foreach (var p in m.Parts.GetEntries())
            if (p.Name == name) return p;
        return null;
    }

    // 别的部件 / 区域 / 事件里有没有按名字引用它（字符串属性、字符串数组属性，反射找）
    static string RefBy(MSBE m, MSBE.Part target) {
        var lists = new System.Collections.Generic.List<object>();
        foreach (var x in m.Parts.GetEntries()) if (x != target) lists.Add(x);
        foreach (var x in m.Regions.GetEntries()) lists.Add(x);
        foreach (var x in m.Events.GetEntries()) lists.Add(x);
        foreach (var o in lists) {
            foreach (var pr in o.GetType().GetProperties()) {
                if (pr.GetIndexParameters().Length > 0 || pr.Name == "Name") continue;
                object v;
                try { v = pr.GetValue(o, null); } catch { continue; }
                var sv = v as string;
                if (sv != null && sv == target.Name) return o.GetType().Name + " " + ((MSBE.Entry)o).Name;
                var arr = v as string[];
                if (arr != null) foreach (var a in arr) if (a == target.Name) return o.GetType().Name + " " + ((MSBE.Entry)o).Name;
            }
        }
        return null;
    }

    // 表（PartsParam / RegionParam 里的 List<具体类型>）里按对象删 / 加：用反射找元素类型正好是它的那张表
    static System.Collections.IList ListFor(object param, Type t) {
        foreach (var pr in param.GetType().GetProperties()) {
            if (!pr.PropertyType.IsGenericType) continue;
            var args = pr.PropertyType.GetGenericArguments();
            if (args.Length == 1 && args[0] == t) return pr.GetValue(param, null) as System.Collections.IList;
        }
        return null;
    }

    // 拷进来的对象（部件 / 区域）：引用的部件名这张图里没有就清空
    static void FixRefs(MSBE m, object o, string owner) {
        var names = new System.Collections.Generic.HashSet<string>();
        foreach (var x in m.Parts.GetEntries()) names.Add(x.Name);
        FixRefs(names, o, owner, 0);
    }

    static void FixRefs(System.Collections.Generic.HashSet<string> names, object o, string owner, int depth) {
        foreach (var pr in o.GetType().GetProperties()) {
            if (pr.GetIndexParameters().Length > 0 || !pr.CanRead) continue;
            object v;
            try { v = pr.GetValue(o, null); } catch { continue; }
            if (v == null) continue;
            var sv = v as string;
            var arr = v as string[];
            if (sv != null && pr.Name.EndsWith("PartName") && pr.CanWrite && sv != "" && !names.Contains(sv)) {
                pr.SetValue(o, null, null);
                Console.WriteLine("unlinked " + owner + "." + pr.Name + " -> " + sv);
            } else if (arr != null && pr.Name.EndsWith("PartNames")) {
                for (int i = 0; i < arr.Length; i++)
                    if (arr[i] != null && arr[i] != "" && !names.Contains(arr[i])) {
                        Console.WriteLine("unlinked " + owner + "." + pr.Name + "[" + i + "] -> " + arr[i]);
                        arr[i] = null;
                    }
            } else if (depth < 1 && !v.GetType().IsPrimitive && !(v is string) && !v.GetType().IsEnum && v.GetType().Namespace == "SoulsFormats") {
                FixRefs(names, v, owner, depth + 1);
            }
        }
    }

    static bool Remove(MSBE m, MSBE.Part p) {
        var l = ListFor(m.Parts, p.GetType());
        if (l == null || !l.Contains(p)) return false;
        l.Remove(p);
        return true;
    }

    static System.Collections.Generic.List<object> Added = new System.Collections.Generic.List<object>();

    static int CopyRegion(MSBE m, MSBE src, string name) {
        MSBE.Region r = null, old = null;
        foreach (var x in src.Regions.GetEntries()) if (x.Name == name) r = x;
        foreach (var x in m.Regions.GetEntries()) if (x.Name == name) old = x;
        if (r == null) { Console.WriteLine("no region in mod map: " + name); return 1; }
        var l = ListFor(m.Regions, r.GetType());
        if (l == null) { Console.WriteLine("no region list for " + r.GetType().Name); return 1; }
        if (old != null) ListFor(m.Regions, old.GetType()).Remove(old);
        var c = (MSBE.Region)r.GetType().GetMethod("DeepCopy").Invoke(r, null);
        l.Add(c);
        Added.Add(c);
        Console.WriteLine((old != null ? "replaced region " : "copied region ") + name + " (" + r.GetType().Name + ", entity " + r.EntityID + ")");
        return 0;
    }

    static int CopyEvent(MSBE m, MSBE src, string name) {
        MSBE.Event e = null, old = null;
        foreach (var x in src.Events.GetEntries()) if (x.Name == name) e = x;
        foreach (var x in m.Events.GetEntries()) if (x.Name == name) old = x;
        if (e == null) { Console.WriteLine("no event in mod map: " + name); return 1; }
        var l = ListFor(m.Events, e.GetType());
        if (l == null) { Console.WriteLine("no event list for " + e.GetType().Name); return 1; }
        if (old != null) ListFor(m.Events, old.GetType()).Remove(old);
        l.Add(e);                                 // src 用完就扔，不用复制
        Added.Add(e);
        Console.WriteLine((old != null ? "replaced event " : "copied event ") + name + " (" + e.GetType().Name + ", entity " + e.EntityID + ")");
        return 0;
    }

    static int Main(string[] a) {
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);      // 名字里有日文
        if (a.Length < 4) { Console.WriteLine("usage: msbport <vanilla.msb> <mod.msb> <out.msb> <[=|-]part> [...]"); return 2; }
        var m = MSBE.Read(a[0]);
        var src = MSBE.Read(a[1]);
        var kept = new System.Collections.Generic.HashSet<string>();
        var added = new System.Collections.Generic.List<object>();
        for (int i = 3; i < a.Length; i++) {
            string arg = a[i];
            if (arg[0] == '^') {
                if (CopyRegion(m, src, arg.Substring(1)) != 0) return 1;
                continue;
            }
            if (arg[0] == '%') {
                if (CopyEvent(m, src, arg.Substring(1)) != 0) return 1;
                continue;
            }
            if (arg[0] == ':') {
                var to = Find(m, arg.Substring(1));
                var from = Find(src, arg.Substring(1));
                if (from == null) { Console.WriteLine("no part in mod map: " + arg.Substring(1)); return 1; }
                if (to == null) { Console.WriteLine("absent " + arg.Substring(1)); continue; }
                to.Position = from.Position;
                to.Rotation = from.Rotation;
                Console.WriteLine("moved " + arg.Substring(1));
                continue;
            }
            char op = arg[0] == '=' || arg[0] == '-' ? arg[0] : '+';
            if (op != '+') arg = arg.Substring(1);
            string[] spec = arg.Split('@');
            string name = spec[0], srcName = spec[0];
            if (name.Contains(">")) {
                if (op != '+') { Console.WriteLine("rename only for plain copy: " + arg); return 1; }
                srcName = name.Substring(0, name.IndexOf('>'));
                name = name.Substring(name.IndexOf('>') + 1);
            }
            var old = Find(m, name);
            if (op == '+' && old != null) { Console.WriteLine("part exists in vanilla: " + name); return 1; }
            if (op == '-' && old == null) { Console.WriteLine("absent " + name); continue; }
            if (op == '-' && old != null) {
                string by = RefBy(m, old);
                if (by != null) { Console.WriteLine("kept " + name + " (referenced by " + by + ")"); kept.Add(name); continue; }
            }
            if (op != '+' && old != null) {
                if (!Remove(m, old)) { Console.WriteLine("cannot remove (type " + old.GetType().Name + "): " + name); return 1; }
                if (op == '-') { Console.WriteLine("deleted " + name + " (" + old.GetType().Name + ", entity " + old.EntityID + ")"); continue; }
            }
            MSBE.Part found = null;
            if (srcName.Contains("~")) {
                string sn = srcName.Substring(0, srcName.IndexOf('~'));
                int sel = int.Parse(srcName.Substring(srcName.IndexOf('~') + 1));
                foreach (var p in src.Parts.GetEntries())
                    if (p.Name == sn && p.EntityID == sel) found = p;
            } else {
                int n = 0;
                foreach (var p in src.Parts.GetEntries())
                    if (p.Name == srcName) n++;
                if (n > 1) { Console.WriteLine("several parts named " + srcName + " in mod map: pick one with ~entity"); return 1; }
                found = Find(src, srcName);
            }
            if (found == null) { Console.WriteLine("no part in mod map: " + srcName); return 1; }
            var c = found.DeepCopy();
            c.Name = name;
            Added.Add(c);
            var en = c as MSBE.Part.Enemy;
            var asset = c as MSBE.Part.Asset;
            var pl = c as MSBE.Part.Player;
            if (en != null && spec.Length == 3) {
                en.NPCParamID = int.Parse(spec[1]);
                en.ThinkParamID = int.Parse(spec[2]);
            }
            if (en != null) {
                // c0000（人形 NPC）的模型条目在玩家模型表里
                if (m.Models.Enemies.Find(x => x.Name == en.ModelName) == null && m.Models.Players.Find(x => x.Name == en.ModelName) == null) {
                    var mm = src.Models.Enemies.Find(x => x.Name == en.ModelName);
                    var mp = src.Models.Players.Find(x => x.Name == en.ModelName);
                    if (mm != null) m.Models.Enemies.Add((MSBE.Model.Enemy)mm.DeepCopy());
                    else if (mp != null) m.Models.Players.Add((MSBE.Model.Player)mp.DeepCopy());
                    else { Console.WriteLine("no model " + en.ModelName); return 1; }
                }
                m.Parts.Enemies.Add(en);
            } else if (asset != null) {
                if (m.Models.Assets.Find(x => x.Name == asset.ModelName) == null) {
                    var mm = src.Models.Assets.Find(x => x.Name == asset.ModelName);
                    if (mm == null) { Console.WriteLine("no model " + asset.ModelName); return 1; }
                    m.Models.Assets.Add((MSBE.Model.Asset)mm.DeepCopy());
                }
                m.Parts.Assets.Add(asset);
            } else if (pl != null) {
                m.Parts.Players.Add(pl);
            } else { Console.WriteLine("only enemies / assets / players: " + name); return 1; }
            Console.WriteLine((op == '=' ? "replaced " : "copied ") + name + " (" + c.GetType().Name + ", model " + c.ModelName + ", entity " + c.EntityID +
                              (en != null ? ", npc " + en.NPCParamID + ", think " + en.ThinkParamID : "") + ")");
        }
        foreach (var o in Added) FixRefs(m, o, ((MSBE.Entry)o).Name);
        m.Write(a[2]);
        var chk = MSBE.Read(a[2]);
        for (int i = 3; i < a.Length; i++) {
            string arg = a[i];
            if (arg[0] == '^') {
                bool hasR = false;
                foreach (var x in chk.Regions.GetEntries()) if (x.Name == arg.Substring(1)) hasR = true;
                if (!hasR) { Console.WriteLine("region missing after write: " + arg.Substring(1)); return 1; }
                continue;
            }
            if (arg[0] == '%') {
                bool hasE = false;
                foreach (var x in chk.Events.GetEntries()) if (x.Name == arg.Substring(1)) hasE = true;
                if (!hasE) { Console.WriteLine("event missing after write: " + arg.Substring(1)); return 1; }
                continue;
            }
            if (arg[0] == ':') continue;
            bool del = arg[0] == '-';
            string nm = (arg[0] == '=' || arg[0] == '-' ? arg.Substring(1) : arg).Split('@')[0];
            if (nm.Contains(">")) nm = nm.Substring(nm.IndexOf('>') + 1);
            bool have = Find(chk, nm) != null;
            if (del && kept.Contains(nm)) continue;
            if (have == del) { Console.WriteLine((del ? "still there after write: " : "missing after write: ") + nm); return 1; }
        }
        Console.WriteLine("ok");
        return 0;
    }
}

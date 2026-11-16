// 只读：把地图里指定部件 / 区域的全部属性（含嵌套的结构体，两层）打出来，用来比较模组改了部件的哪些字段。
//   msbprops <msb> <名字> [名字 ...]
using System;
using System.Collections;
using System.Reflection;
using SoulsFormats;

class MsbProps {
    static void Dump(object o, string pre, int depth) {
        foreach (var p in o.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)) {
            if (p.GetIndexParameters().Length > 0) continue;
            object v;
            try { v = p.GetValue(o, null); } catch { continue; }
            if (v == null) { Console.WriteLine(pre + p.Name + "=null"); continue; }
            var t = v.GetType();
            if (t.IsPrimitive || v is string || t.IsEnum || t.Name.StartsWith("Vector")) {
                Console.WriteLine(pre + p.Name + "=" + v);
            } else if (v is IEnumerable) {
                var parts = new System.Collections.Generic.List<string>();
                foreach (var x in (IEnumerable)v) parts.Add(x == null ? "null" : x.ToString());
                Console.WriteLine(pre + p.Name + "=[" + string.Join(",", parts.ToArray()) + "]");
            } else if (depth < 2) {
                Dump(v, pre + p.Name + ".", depth + 1);
            } else {
                Console.WriteLine(pre + p.Name + "=" + v);
            }
        }
    }

    static int Main(string[] a) {
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);      // 名字里有日文
        var m = MSBE.Read(a[0]);
        for (int i = 1; i < a.Length; i++) {
            bool hit = false;
            foreach (var p in m.Parts.GetEntries())
                if (p.Name == a[i]) { Console.WriteLine("== PART " + p.GetType().Name + " " + p.Name); Dump(p, "  ", 0); hit = true; }
            foreach (var r in m.Regions.GetEntries())
                if (r.Name == a[i]) { Console.WriteLine("== REGION " + r.GetType().Name + " " + r.Name); Dump(r, "  ", 0); hit = true; }
            if (!hit) Console.WriteLine("== missing " + a[i]);
        }
        return 0;
    }
}

// 只读：列出 MSB 里离某个坐标近的区域（类型、名字、实体 ID、坐标、引用的部件名）和部件
//   msbdump <msb> <x> <y> <z> <半径>
using System;
using System.Globalization;
using System.Numerics;
using SoulsFormats;

class MsbDump {
    static float F(string s) { return float.Parse(s, CultureInfo.InvariantCulture); }

    static string Refs(object o) {
        var s = "";
        foreach (var p in o.GetType().GetProperties()) {
            if (p.PropertyType == typeof(string) && p.Name.EndsWith("PartName")) {
                var v = (string)p.GetValue(o);
                if (!string.IsNullOrEmpty(v)) s += " " + p.Name + "=" + v;
            }
            if (p.PropertyType == typeof(int) && (p.Name.Contains("Entity") || p.Name.Contains("Warp") || p.Name.Contains("Map") || p.Name.Contains("Region") || p.Name.Contains("Bonfire"))) {
                s += " " + p.Name + "=" + p.GetValue(o);
            }
        }
        return s;
    }

    static int Main(string[] a) {
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);      // 名字里有日文
        var m = MSBE.Read(a[0]);
        var c = new Vector3(F(a[1]), F(a[2]), F(a[3]));
        float rad = F(a[4]);
        foreach (var r in m.Regions.GetEntries()) {
            if (Vector3.Distance(r.Position, c) > rad) continue;
            Console.WriteLine("REGION " + r.GetType().Name + " " + r.Name + " ent=" + r.EntityID + " pos=" + r.Position + " rot=" + r.Rotation + Refs(r));
        }
        foreach (var p in m.Parts.GetEntries()) {
            if (Vector3.Distance(p.Position, c) > rad) continue;
            Console.WriteLine("PART " + p.GetType().Name + " " + p.Name + " model=" + p.ModelName + " ent=" + p.EntityID + " pos=" + p.Position + Refs(p));
        }
        foreach (var p in m.Parts.Players)
            Console.WriteLine("PLAYER " + p.Name + " ent=" + p.EntityID + " pos=" + p.Position + " rot=" + p.Rotation + " inst=" + p.Unk08);
        foreach (var p in m.Parts.Assets)
            if (p.ModelName == "AEG099_060") Console.WriteLine("GRACE " + p.Name + " ent=" + p.EntityID + " pos=" + p.Position);
        return 0;
    }
}

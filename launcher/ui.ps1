# Dark Reforged · 启动器的界面控件和统一风格的弹窗（图形界面 gui.ps1 和启动器 launcher.ps1 的后台弹窗共用，用 . 引入）
# 用之前先 Import-UiTypes（同一进程里只编译 / 加载一次）；Show-DrDialog 自己会调
# 暗色 + 金色（艾尔登法环的配色）：按钮、标题栏、状态卡片、日志框都是自己画的（下面的 C#，第一次打开时编译一次，存在 %TEMP%）
$UiCs = @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace DarkReforgedUI
{
    public static class Theme
    {
        public static readonly Color Bg = Color.FromArgb(17, 16, 14);
        public static readonly Color Surface = Color.FromArgb(28, 26, 22);
        public static readonly Color SurfaceHi = Color.FromArgb(39, 36, 30);
        public static readonly Color SurfaceDown = Color.FromArgb(22, 20, 17);
        public static readonly Color Border = Color.FromArgb(54, 49, 39);
        public static readonly Color BorderHi = Color.FromArgb(128, 106, 64);
        public static readonly Color Gold = Color.FromArgb(200, 164, 94);
        public static readonly Color GoldHi = Color.FromArgb(221, 186, 117);
        public static readonly Color GoldDown = Color.FromArgb(170, 137, 75);
        public static readonly Color Ink = Color.FromArgb(28, 22, 14);
        public static readonly Color InkSub = Color.FromArgb(78, 60, 32);
        public static readonly Color Fg = Color.FromArgb(234, 226, 210);
        public static readonly Color FgDim = Color.FromArgb(162, 153, 136);
        public static readonly Color FgMuted = Color.FromArgb(112, 105, 93);
        public static readonly Color LogBg = Color.FromArgb(12, 11, 10);
        public static readonly Color Ok = Color.FromArgb(136, 178, 110);
        public static readonly Color Warn = Color.FromArgb(224, 168, 72);
        public static readonly Color Bad = Color.FromArgb(214, 100, 90);

        public static GraphicsPath Round(RectangleF r, float rad)
        {
            GraphicsPath p = new GraphicsPath();
            float d = Math.Min(rad * 2, Math.Min(r.Width, r.Height));
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        static string iconFamily, serifFamily;
        static string FindFamily(string[] names)
        {
            foreach (string n in names)
                foreach (FontFamily f in FontFamily.Families)
                    if (f.Name == n) return n;
            return "";
        }
        // Segoe MDL2 Assets（Win10）/ Segoe Fluent Icons（Win11）里的图标；都没有就不画图标
        public static Font IconFont(float size)
        {
            if (iconFamily == null) iconFamily = FindFamily(new string[] { "Segoe Fluent Icons", "Segoe MDL2 Assets" });
            return iconFamily == "" ? null : new Font(iconFamily, size, FontStyle.Regular, GraphicsUnit.Point);
        }
        public static Font SerifFont(float size)
        {
            if (serifFamily == null) serifFamily = FindFamily(new string[] { "Palatino Linotype", "Book Antiqua", "Georgia", "Times New Roman" });
            return new Font(serifFamily == "" ? FontFamily.GenericSerif.Name : serifFamily, size, FontStyle.Regular, GraphicsUnit.Point);
        }

        public const TextFormatFlags Flat = TextFormatFlags.NoPadding | TextFormatFlags.NoPrefix | TextFormatFlags.SingleLine;

        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
        [DllImport("uxtheme.dll", CharSet = CharSet.Unicode)] static extern int SetWindowTheme(IntPtr hwnd, string app, string idList);
        [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern int SetCurrentProcessExplicitAppUserModelID(string id);

        // 任务栏：这个进程的窗口用自己的 AppUserModelID，不和别的 PowerShell 窗口归成一组，按钮上显示窗口的图标（要在窗口显示之前调）
        public static void AppId(string id) { try { SetCurrentProcessExplicitAppUserModelID(id); } catch { } }

        static int Rgb(Color c) { return c.R | (c.G << 8) | (c.B << 16); }
        // 暗色标题栏（Win10 20H1+ / Win11；不支持的系统什么都不做）
        public static void DarkTitle(Form f)
        {
            try
            {
                int on = 1;
                if (DwmSetWindowAttribute(f.Handle, 20, ref on, 4) != 0) DwmSetWindowAttribute(f.Handle, 19, ref on, 4);
                int cap = Rgb(Bg), txt = Rgb(Fg), bd = Rgb(Border);
                DwmSetWindowAttribute(f.Handle, 35, ref cap, 4);
                DwmSetWindowAttribute(f.Handle, 36, ref txt, 4);
                DwmSetWindowAttribute(f.Handle, 34, ref bd, 4);
            }
            catch { }
        }
        // 文本框、列表的滚动条也换成暗色
        public static void DarkScroll(Control c) { try { SetWindowTheme(c.Handle, "DarkMode_Explorer", null); } catch { } }
    }

    public enum Kind { Primary, Secondary, Ghost }

    // 圆角按钮：Primary = 金色实心（启动），Secondary = 暗色卡片，Ghost = 工具按钮（鼠标移上去才显出底色）；Sub = 第二行小字
    public class DrButton : Button
    {
        public Kind Look = Kind.Secondary;
        public string Glyph = "";
        public string Sub = "";
        bool hover, down;

        public DrButton()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            Cursor = Cursors.Hand;
            ForeColor = Theme.Fg;
            BackColor = Theme.Bg;
        }
        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; down = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { if (e.Button == MouseButtons.Left) { down = true; Invalidate(); } base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { down = false; Invalidate(); base.OnMouseUp(e); }
        protected override void OnEnabledChanged(EventArgs e) { Invalidate(); base.OnEnabledChanged(e); }
        protected override void OnGotFocus(EventArgs e) { Invalidate(); base.OnGotFocus(e); }
        protected override void OnLostFocus(EventArgs e) { Invalidate(); base.OnLostFocus(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            Color outer = Parent != null ? Parent.BackColor : Theme.Bg;
            g.Clear(outer);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            bool en = Enabled, hot = en && hover, pressed = en && down;
            Color fill, border, fg, sub;
            if (Look == Kind.Primary)
            {
                fill = !en ? Color.FromArgb(58, 52, 40) : pressed ? Theme.GoldDown : hot ? Theme.GoldHi : Theme.Gold;
                border = fill;
                fg = en ? Theme.Ink : Theme.FgMuted;
                sub = en ? Theme.InkSub : Theme.FgMuted;
            }
            else if (Look == Kind.Secondary)
            {
                fill = pressed ? Theme.SurfaceDown : hot ? Theme.SurfaceHi : Theme.Surface;
                border = hot ? Theme.BorderHi : Theme.Border;
                fg = en ? Theme.Fg : Theme.FgMuted;
                sub = en ? Theme.FgDim : Theme.FgMuted;
            }
            else
            {
                fill = pressed ? Theme.SurfaceDown : hot ? Theme.SurfaceHi : outer;
                border = hot ? Theme.Border : Color.FromArgb(36, 33, 28);
                fg = !en ? Theme.FgMuted : hot ? Theme.Fg : Theme.FgDim;
                sub = Theme.FgMuted;
            }
            float rad = (Look == Kind.Primary ? 8f : 6f) * g.DpiX / 96f;
            using (GraphicsPath p = Theme.Round(new RectangleF(0.5f, 0.5f, Width - 1.5f, Height - 1.5f), rad))
            {
                using (SolidBrush b = new SolidBrush(fill)) g.FillPath(b, p);
                using (Pen pen = new Pen(border)) g.DrawPath(pen, p);
            }
            if (Focused && ShowFocusCues && en)
            {
                using (GraphicsPath p = Theme.Round(new RectangleF(3.5f, 3.5f, Width - 7.5f, Height - 7.5f), rad * 0.7f))
                using (Pen pen = new Pen(Look == Kind.Primary ? Color.FromArgb(150, Theme.Ink) : Color.FromArgb(150, Theme.Gold)))
                {
                    pen.DashStyle = DashStyle.Dot;
                    g.DrawPath(pen, p);
                }
            }

            bool two = Sub.Length > 0;
            Font subF = two ? new Font(Font.FontFamily, Font.Size * 0.74f, FontStyle.Regular) : null;
            Font iconF = Glyph.Length > 0 ? Theme.IconFont(Font.Size * (two ? 1.35f : 1.0f)) : null;
            Size big = new Size(int.MaxValue, int.MaxValue);
            Size ts = TextRenderer.MeasureText(g, Text, Font, big, Theme.Flat);
            Size ss = two ? TextRenderer.MeasureText(g, Sub, subF, big, Theme.Flat) : Size.Empty;
            Size isz = iconF != null ? TextRenderer.MeasureText(g, Glyph, iconF, big, Theme.Flat) : Size.Empty;
            int gap = iconF != null ? (int)(Font.Size * (two ? 1.1f : 0.8f) * g.DpiX / 72f * 0.75f) : 0;
            int textW = Math.Max(ts.Width, ss.Width);
            int textH = ts.Height + (two ? ss.Height + (int)(2 * g.DpiX / 96f) : 0);
            int x = (Width - (isz.Width + gap + textW)) / 2;
            if (iconF != null)
            {
                TextRenderer.DrawText(g, Glyph, iconF, new Point(x, (Height - isz.Height) / 2 + 1), fg, Theme.Flat);
                x += isz.Width + gap;
            }
            int y = (Height - textH) / 2;
            TextRenderer.DrawText(g, Text, Font, new Point(x, y), fg, Theme.Flat);
            if (two) TextRenderer.DrawText(g, Sub, subF, new Point(x, y + ts.Height + (int)(2 * g.DpiX / 96f)), sub, Theme.Flat);
            if (subF != null) subF.Dispose();
            if (iconF != null) iconF.Dispose();
        }
    }

    // 顶部标题：字距拉开的衬线字 DARKFORGE + 菱形和渐隐的金线 + 副标题；右上角一个状态标签（版本 / 运行中）
    public class DrHeader : Panel
    {
        public string Title = "DARKFORGE";
        public string Subtitle = "";
        public string Badge = "";
        public bool Busy = false;

        public DrHeader()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            BackColor = Theme.Bg;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            float s = g.DpiX / 96f;
            g.Clear(Theme.Bg);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            // 左上一团暖色的光
            Rectangle glow = new Rectangle((int)(-160 * s), (int)(-150 * s), (int)(720 * s), (int)(360 * s));
            using (GraphicsPath ep = new GraphicsPath())
            {
                ep.AddEllipse(glow);
                using (PathGradientBrush pb = new PathGradientBrush(ep))
                {
                    pb.CenterColor = Color.FromArgb(40, 200, 164, 94);
                    pb.SurroundColors = new Color[] { Color.FromArgb(0, 200, 164, 94) };
                    g.FillEllipse(pb, glow);
                }
            }
            // 标题字（逐字画，拉开字距）
            float x = 28 * s, y = 22 * s, h;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            using (Font wf = Theme.SerifFont(25f))
            using (SolidBrush gb = new SolidBrush(Theme.Gold))
            {
                h = wf.GetHeight(g);
                float sp = 5.5f * s;
                foreach (char ch in Title)
                {
                    string c = ch.ToString();
                    float w = ch == ' ' ? wf.Size * 0.5f * s : g.MeasureString(c, wf, PointF.Empty, StringFormat.GenericTypographic).Width;
                    g.DrawString(c, wf, gb, x, y, StringFormat.GenericTypographic);
                    x += w + sp;
                }
            }
            // 菱形 + 渐隐金线
            float ly = y + h + 6 * s, lx = 30 * s, lw = Math.Min(Width * 0.55f, x - lx + 60 * s);
            using (LinearGradientBrush lb = new LinearGradientBrush(new PointF(lx, ly), new PointF(lx + lw, ly), Color.FromArgb(200, Theme.Gold), Color.FromArgb(0, Theme.Gold)))
            using (Pen lp = new Pen(lb, 1f * s))
                g.DrawLine(lp, lx + 9 * s, ly, lx + lw, ly);
            using (SolidBrush db = new SolidBrush(Theme.Gold))
                g.FillPolygon(db, new PointF[] { new PointF(lx, ly), new PointF(lx + 4 * s, ly - 4 * s), new PointF(lx + 8 * s, ly), new PointF(lx + 4 * s, ly + 4 * s) });
            using (Font sf = new Font(Font.FontFamily, Font.Size * 0.9f))
                TextRenderer.DrawText(g, Subtitle, sf, new Point((int)(30 * s), (int)(ly + 9 * s)), Theme.FgDim, Theme.Flat);
            // 右上状态标签
            if (Badge.Length > 0)
            {
                using (Font bf = new Font(Font.FontFamily, Font.Size * 0.82f))
                {
                    Size bs = TextRenderer.MeasureText(g, Badge, bf, new Size(int.MaxValue, int.MaxValue), Theme.Flat);
                    int dot = Busy ? (int)(12 * s) : 0;
                    RectangleF br = new RectangleF(Width - 24 * s - bs.Width - 24 * s - dot, 24 * s, bs.Width + 24 * s + dot, bs.Height + 10 * s);
                    Color edge = Busy ? Theme.Gold : Theme.Border;
                    using (GraphicsPath bp = Theme.Round(br, br.Height / 2))
                    {
                        using (SolidBrush b = new SolidBrush(Busy ? Color.FromArgb(40, Theme.Gold) : Theme.Surface)) g.FillPath(b, bp);
                        using (Pen p = new Pen(edge)) g.DrawPath(p, bp);
                    }
                    if (Busy)
                        using (SolidBrush b = new SolidBrush(Theme.Gold))
                            g.FillEllipse(b, br.X + 11 * s, br.Y + br.Height / 2 - 3.5f * s, 7 * s, 7 * s);
                    TextRenderer.DrawText(g, Badge, bf, new Point((int)(br.X + 12 * s + dot), (int)(br.Y + 5 * s)), Busy ? Theme.GoldHi : Theme.FgDim, Theme.Flat);
                }
            }
            using (Pen p = new Pen(Color.FromArgb(40, 37, 31))) g.DrawLine(p, 0, Height - 1, Width, Height - 1);
        }
    }

    // 圆角卡片：状态卡（图标 + 小标题 + 一行内容，Accent 是图标颜色）；Header = true 时只在左上画小标题（日志框）
    public class DrCard : Panel
    {
        public string Caption = "";
        public string Value = "";
        public string Glyph = "";
        public Color Accent = Theme.Gold;
        public bool Header = false;

        public DrCard()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            BackColor = Theme.Surface;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            float s = g.DpiX / 96f;
            g.Clear(Parent != null ? Parent.BackColor : Theme.Bg);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (GraphicsPath p = Theme.Round(new RectangleF(0.5f, 0.5f, Width - 1.5f, Height - 1.5f), 8 * s))
            {
                using (SolidBrush b = new SolidBrush(BackColor)) g.FillPath(b, p);
                using (Pen pen = new Pen(Theme.Border)) g.DrawPath(pen, p);
            }
            int pad = (int)(14 * s);
            using (Font cf = new Font(Font.FontFamily, Font.Size * 0.8f))
            {
                if (Header)
                {
                    TextRenderer.DrawText(g, Caption, cf, new Point(pad, (int)(10 * s)), Theme.FgMuted, Theme.Flat);
                    return;
                }
                int tx = pad;
                using (Font iconF = Glyph.Length > 0 ? Theme.IconFont(Font.Size * 1.15f) : null)
                {
                    if (iconF != null)
                    {
                        TextRenderer.DrawText(g, Glyph, iconF, new Rectangle(pad, 0, (int)(22 * s), Height), Accent,
                            Theme.Flat | TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
                        tx = pad + (int)(34 * s);
                    }
                }
                using (Font vf = new Font(Font.FontFamily, Font.Size * 0.95f))
                {
                    Size big = new Size(int.MaxValue, int.MaxValue);
                    int ch = TextRenderer.MeasureText(g, "测", cf, big, Theme.Flat).Height;
                    int vh = TextRenderer.MeasureText(g, "测", vf, big, Theme.Flat).Height;
                    int y0 = (Height - ch - vh - (int)(3 * s)) / 2;
                    TextRenderer.DrawText(g, Caption, cf, new Point(tx, y0), Theme.FgMuted, Theme.Flat);
                    TextRenderer.DrawText(g, Value, vf, new Rectangle(tx, y0 + ch + (int)(3 * s), Width - tx - pad, vh), Theme.Fg,
                        Theme.Flat | TextFormatFlags.EndEllipsis);
                }
            }
        }
    }

    // 暗色提示框（鼠标停在按钮上时的说明）
    public class DarkTip : ToolTip
    {
        Font tipFont = new Font("Microsoft YaHei UI", 9f);
        const TextFormatFlags TF = TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix | TextFormatFlags.NoPadding;
        public DarkTip()
        {
            OwnerDraw = true;
            Popup += delegate(object s, PopupEventArgs e)
            {
                Size sz = TextRenderer.MeasureText(GetToolTip(e.AssociatedControl), tipFont, new Size(460, int.MaxValue), TF);
                e.ToolTipSize = new Size(sz.Width + 22, sz.Height + 16);
            };
            Draw += delegate(object s, DrawToolTipEventArgs e)
            {
                e.Graphics.Clear(Theme.SurfaceHi);
                using (Pen p = new Pen(Theme.BorderHi)) e.Graphics.DrawRectangle(p, 0, 0, e.Bounds.Width - 1, e.Bounds.Height - 1);
                TextRenderer.DrawText(e.Graphics, e.ToolTipText, tipFont, new Rectangle(11, 8, e.Bounds.Width - 22, e.Bounds.Height - 16), Theme.Fg, TF);
            };
        }
    }
}
'@

# 编译好的界面控件存在 %TEMP%（按代码的校验值命名，代码改了就重新编译；存不了就只在内存里编译）。同一进程里加载过就不再加载
function Import-UiTypes {
    if ('DarkReforgedUI.Theme' -as [type]) { return }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $sha = [Security.Cryptography.SHA1]::Create()
    $hash = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($UiCs))[0..5] | ForEach-Object { $_.ToString('x2') })
    $dll = Join-Path $env:TEMP ('DarkReforgedUI_' + $hash + '.dll')
    $refs = @('System.Windows.Forms', 'System.Drawing')
    try {
        if (-not (Test-Path -LiteralPath $dll)) { Add-Type -TypeDefinition $UiCs -ReferencedAssemblies $refs -OutputAssembly $dll -OutputType Library }
        Add-Type -LiteralPath $dll
    } catch {
        Add-Type -TypeDefinition $UiCs -ReferencedAssemblies $refs
    }
    [DarkReforgedUI.Theme]::AppId('Darkforge.Launcher')      # 启动器和它后台弹的窗口在任务栏归在一起、用整合包的图标
}


# 窗口图标（任务栏、标题栏）：launcher\darkforge.ico，普通难度封面上的四色重铸环（dev\title_menu\make_icon.py，用户 2026-11-11）
$DrIconPath = Join-Path $PSScriptRoot 'darkforge.ico'
$script:DrIcon = $null
function Get-DrIcon {
    if (-not $script:DrIcon -and (Test-Path -LiteralPath $DrIconPath)) {
        try { $script:DrIcon = New-Object System.Drawing.Icon($DrIconPath) } catch { }
    }
    return $script:DrIcon
}

# 暗色窗口：底色、字色，标题栏和滚动条在窗口句柄建好后换成暗色；图标用整合包的
function Set-DarkForm($f) {
    $f.BackColor = [DarkReforgedUI.Theme]::Bg
    $f.ForeColor = [DarkReforgedUI.Theme]::Fg
    $ic = Get-DrIcon
    if ($ic) { $f.Icon = $ic }
    $f.Add_HandleCreated({ param($s, $e) [DarkReforgedUI.Theme]::DarkTitle($s) })
}

function New-DarkText([bool]$Log = $false) {
    $tb = New-Object System.Windows.Forms.TextBox
    $tb.Multiline = $true
    $tb.ReadOnly = $true
    $tb.ScrollBars = 'Vertical'
    $tb.WordWrap = $true
    $tb.BorderStyle = 'None'
    $tb.BackColor = $(if ($Log) { [DarkReforgedUI.Theme]::LogBg } else { [DarkReforgedUI.Theme]::Surface })
    $tb.ForeColor = $(if ($Log) { [System.Drawing.Color]::FromArgb(206, 198, 182) } else { [DarkReforgedUI.Theme]::Fg })
    $tb.Add_HandleCreated({ param($s, $e) [DarkReforgedUI.Theme]::DarkScroll($s) })
    return $tb
}

# 对话框里的按钮（主要的一个用金色）
function New-DlgBtn([string]$Text, [int]$X, [int]$Y, [int]$W, [int]$H, [bool]$Primary = $false) {
    $b = New-Object DarkReforgedUI.DrButton
    $b.Look = $(if ($Primary) { [DarkReforgedUI.Kind]::Primary } else { [DarkReforgedUI.Kind]::Secondary })
    $b.Text = $Text
    $b.Location = New-Object System.Drawing.Point($X, $Y)
    $b.Size = New-Object System.Drawing.Size($W, $H)
    return $b
}

# 启动器后台进程（launcher.ps1、崩溃看守）要弹窗时，图形界面开着新界面就交给它显示在页面里（webui.ps1 的 Watch-HostDialogs，用户 2026-11-11）：
# 请求写进 $env:DARKFORGE_DLG_DIR\<id>.req.json，等 <id>.ans.json（选了第几个）。图形界面 5 秒内没接、或者已经关了，返回 $null（自己弹）
function Request-HostDialog([string]$Text, [string]$Title, [string[]]$Buttons, [int]$Default, [int]$Cancel, [string]$Icon) {
    $dir = $env:DARKFORGE_DLG_DIR
    $gp = 0
    if (-not $dir -or -not [int]::TryParse([string]$env:DARKFORGE_GUI_PID, [ref]$gp) -or $gp -eq $PID) { return $null }
    try {
        if (-not (Get-Process -Id $gp -ErrorAction SilentlyContinue)) { return $null }
        [void][System.IO.Directory]::CreateDirectory($dir)
        $id = [string]$PID + '_' + [DateTime]::Now.Ticks
        $req = Join-Path $dir ($id + '.req.json')
        $ans = Join-Path $dir ($id + '.ans.json')
        $j = @{ text = $Text; title = $Title; buttons = [string[]]$Buttons; def = $Default; cancel = $Cancel; icon = $Icon } | ConvertTo-Json -Compress
        [System.IO.File]::WriteAllText($req + '.tmp', $j, (New-Object System.Text.UTF8Encoding($false)))
        [System.IO.File]::Move($req + '.tmp', $req)
        $t0 = [DateTime]::Now
        while ($true) {
            if ([System.IO.File]::Exists($ans)) {
                $r = 0
                $ok = [int]::TryParse(([System.IO.File]::ReadAllText($ans)).Trim(), [ref]$r)
                try { [System.IO.File]::Delete($ans) } catch { }
                if ($ok) { return $r }
                return $null
            }
            if (-not (Get-Process -Id $gp -ErrorAction SilentlyContinue)) {
                try { [System.IO.File]::Delete($req) } catch { }
                return $null
            }
            if (([DateTime]::Now - $t0).TotalSeconds -gt 5 -and [System.IO.File]::Exists($req)) {
                $took = $false
                try { [System.IO.File]::Move($req, $req + '.x'); $took = $true } catch { }     # 改名成功 = 图形界面还没接，收回来自己弹
                if ($took) { try { [System.IO.File]::Delete($req + '.x') } catch { }; return $null }
            }
            Start-Sleep -Milliseconds 150
        }
    } catch { return $null }
}

# 统一风格的弹窗（代替系统白色的 MessageBox，用户 2026-11-01；图形界面和启动器后台进程都用）：暗色窗口、左边一个图标、正文自动换行
#（太长就换成带滚动条的文本框），底部深色条上从右往左排按钮，主要的那个是金色的。按实际 DPI 量字、排版。
#   $Buttons：按钮文字（从左到右）；$Default：主要按钮（金色，回车就是它）；$Cancel：按 Esc / 点标题栏的 × 算点了哪个
#   （-1 = Esc 不关窗口，× 关掉返回 -1：「没选」和「否」要分开的时候用）
#   $Icon：info / question / warn / error；$Owner：父窗口（图形界面的主窗口），不给就置顶显示在屏幕中间（启动器后台进程、崩溃看守）
# 返回点了第几个按钮（0 起）。自己画的窗口建不起来时退回系统的 MessageBox（一个按钮 = 确定，两个 = 是 / 否），保证玩家看得到
function Show-DrDialog {
    param([string]$Text, [string]$Title = '暗黑重铸', [string[]]$Buttons = @('确定'), [int]$Default = 0, [int]$Cancel = -1,
          [string]$Icon = 'info', $Owner = $null)
    if (-not $Owner) {
        $hr = Request-HostDialog $Text $Title $Buttons $Default $Cancel $Icon
        if ($null -ne $hr) { return $hr }
    }
    try {
        Import-UiTypes
        $th = [DarkReforgedUI.Theme]
        $dlg = New-Object System.Windows.Forms.Form
        $dlg.Text = $Title
        $dlg.FormBorderStyle = 'FixedDialog'
        $dlg.MaximizeBox = $false
        $dlg.MinimizeBox = $false
        $dlg.AutoScaleMode = 'None'
        $dlg.ShowInTaskbar = -not $Owner
        $dlg.TopMost = -not $Owner
        $dlg.StartPosition = $(if ($Owner) { 'CenterParent' } else { 'CenterScreen' })
        $dlg.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10)
        Set-DarkForm $dlg
        $g = $dlg.CreateGraphics()
        $s = $g.DpiX / 96.0
        $px = { param($v) [int][Math]::Round($v * $s) }
        $glyph, $accent = switch ($Icon) {
            'warn'     { [string][char]0xE7BA, $th::Warn }
            'error'    { [string][char]0xEA39, $th::Bad }
            'question' { [string][char]0xE9CE, $th::Gold }
            default    { [string][char]0xE946, $th::Gold }
        }
        $iconF = $th::IconFont(20)
        $m = & $px 24
        $left = $m + $(if ($iconF) { & $px 44 } else { 0 })
        $tw = & $px $(if ($Text.Length -gt 400) { 560 } else { 460 })
        $flags = [System.Windows.Forms.TextFormatFlags]'WordBreak, NoPrefix'
        $ts = [System.Windows.Forms.TextRenderer]::MeasureText($g, $Text, $dlg.Font, (New-Object System.Drawing.Size($tw, [int]::MaxValue)), $flags)
        $maxH = & $px 460
        if ($ts.Height -le $maxH) {
            $body = New-Object System.Windows.Forms.Label
            $body.AutoSize = $false
            $body.UseMnemonic = $false
            $body.UseCompatibleTextRendering = $false
            $body.Size = New-Object System.Drawing.Size(($tw + (& $px 4)), $ts.Height)
        } else {
            $body = New-DarkText
            $body.Size = New-Object System.Drawing.Size(($tw + (& $px 22)), $maxH)
        }
        $body.Text = $Text
        $body.ForeColor = $th::Fg
        $body.BackColor = $th::Bg
        $body.Location = New-Object System.Drawing.Point($left, $m)
        $dlg.Controls.Add($body)
        if ($iconF) {
            $ic = New-Object System.Windows.Forms.Label
            $ic.AutoSize = $false
            $ic.UseMnemonic = $false
            $ic.UseCompatibleTextRendering = $false
            $ic.Font = $iconF
            $ic.Text = $glyph
            $ic.ForeColor = $accent
            $ic.BackColor = $th::Bg
            $ic.Location = New-Object System.Drawing.Point($m, ($m - (& $px 3)))
            $ic.Size = New-Object System.Drawing.Size((& $px 36), (& $px 36))
            $dlg.Controls.Add($ic)
        }
        # 底部按钮条：按钮宽度按文字量，排不下就把窗口加宽
        $bh, $gap, $fh = (& $px 36), (& $px 10), (& $px 64)
        $widths = @($Buttons | ForEach-Object { [Math]::Max((& $px 96), [System.Windows.Forms.TextRenderer]::MeasureText($g, $_, $dlg.Font).Width + (& $px 40)) })
        $cw = [Math]::Max($left + $body.Width + $m, ($widths | Measure-Object -Sum).Sum + $gap * ($Buttons.Count - 1) + (& $px 40))
        $foot = New-Object System.Windows.Forms.Panel
        $foot.BackColor = $th::Surface
        $foot.Location = New-Object System.Drawing.Point(0, ($m + $body.Height + $m))
        $foot.Size = New-Object System.Drawing.Size($cw, $fh)
        $line = New-Object System.Windows.Forms.Panel
        $line.BackColor = $th::Border
        $line.Location = New-Object System.Drawing.Point(0, 0)
        $line.Size = New-Object System.Drawing.Size($cw, 1)
        $foot.Controls.Add($line)
        $btns = @{}
        $x = $cw - (& $px 20)
        for ($i = $Buttons.Count - 1; $i -ge 0; $i--) {
            $x -= $widths[$i]
            $b = New-DlgBtn $Buttons[$i] $x ([int](($fh - $bh) / 2)) $widths[$i] $bh ($i -eq $Default)
            $b.Font = $dlg.Font
            $b.Tag = $i
            $b.Add_Click({ $f = $this.FindForm(); $f.Tag = $this.Tag; $f.Close() })
            $foot.Controls.Add($b)
            $btns[$i] = $b
            $x -= $gap
        }
        $dlg.Controls.Add($foot)
        $dlg.ClientSize = New-Object System.Drawing.Size($cw, ($m + $body.Height + $m + $fh))
        if ($btns.ContainsKey($Default)) { $dlg.AcceptButton = $btns[$Default] }
        if ($btns.ContainsKey($Cancel)) { $dlg.CancelButton = $btns[$Cancel] }
        $dlg.Add_Shown({
            $this.Activate()
            if ($btns.ContainsKey($Default)) { $this.ActiveControl = $btns[$Default] }
            if ($body -is [System.Windows.Forms.TextBox]) { $body.SelectionLength = 0 }
        })
        $g.Dispose()
        if (-not $Owner) {
            # 隐藏窗口启动的进程（崩溃看守是 -WindowStyle Hidden 开的）：Windows 把这个进程第一次显示窗口换成「隐藏」（启动参数里的 SW_HIDE），
            # 弹窗建出来了却看不见（2026-11-01 实测）。显示出来以后再自己调一次 ShowWindow（第二次不受影响），并拿到前台
            if (-not ('DrNative.Win' -as [type])) {
                Add-Type -Namespace DrNative -Name Win -MemberDefinition ('[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int c);' +
                    '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);')
            }
            $dlg.Add_Shown({ [void][DrNative.Win]::ShowWindow($this.Handle, 5); [void][DrNative.Win]::SetForegroundWindow($this.Handle) })
        }
        if ($Owner) { [void]$dlg.ShowDialog($Owner) } else { [void]$dlg.ShowDialog() }
        $r = $dlg.Tag
        $dlg.Dispose()
        if ($null -eq $r) { return $Cancel }
        return [int]$r
    } catch {
        Add-Type -AssemblyName System.Windows.Forms
        $ico = @{ warn = 'Warning'; error = 'Error'; question = 'Question' }[$Icon]
        if (-not $ico) { $ico = 'Information' }
        if ($Buttons.Count -ge 2) {
            $r = [System.Windows.Forms.MessageBox]::Show($Text, $Title, 'YesNo', $ico, $(if ($Default -eq 1) { 'Button2' } else { 'Button1' }))
            return $(if ($r -eq 'Yes') { 0 } else { 1 })
        }
        [void][System.Windows.Forms.MessageBox]::Show($Text, $Title, 'OK', $ico)
        return 0
    }
}

# 这台电脑的显卡（敌人信息 mod 的双显卡判断：启动器启动时、图形界面第一次打开时都用）。
# 只数真的显卡：PCI 设备、工作正常（远程桌面、虚拟显示器不算；在 BIOS / 设备管理器里停用的核显也不算）
function Get-GpuNames {
    if ($null -eq $script:GpuNames) {
        $script:GpuNames = @(try {
            Get-CimInstance Win32_VideoController -ErrorAction Stop |
                Where-Object { [string]$_.PNPDeviceID -like 'PCI\*' -and $_.ConfigManagerErrorCode -eq 0 } | ForEach-Object { [string]$_.Name }
        } catch { })
    }
    return $script:GpuNames
}

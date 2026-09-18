"""python -m app build: otto.png -> app/static/otto.ico (the window's icon) -> Otto.exe (the launcher under that icon).

Windows PowerShell with System.Drawing scales the logo; the .NET Framework C# compiler every Windows ships compiles the exe.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 16, 32 and 48 as 32-bit bitmaps with a mask, 256 as PNG: the sizes Explorer, the taskbar and Chrome ask for
ICON_PS = r"""
Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Image]::FromFile($Source)

function Frame([int]$size) {
    $bmp = New-Object System.Drawing.Bitmap $size, $size, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $g.DrawImage($src, 0, 0, $size, $size)
    $g.Dispose()
    return $bmp
}

function Dib([System.Drawing.Bitmap]$bmp) {
    $w = $bmp.Width; $h = $bmp.Height
    $maskRow = [int]([math]::Ceiling($w / 32.0) * 4)
    $ms = New-Object System.IO.MemoryStream
    $bw = New-Object System.IO.BinaryWriter $ms
    $bw.Write([int32]40); $bw.Write([int32]$w); $bw.Write([int32]($h * 2)); $bw.Write([int16]1); $bw.Write([int16]32)
    $bw.Write([int32]0); $bw.Write([int32]($w * $h * 4 + $maskRow * $h)); $bw.Write([int32]0); $bw.Write([int32]0); $bw.Write([int32]0); $bw.Write([int32]0)
    for ($y = $h - 1; $y -ge 0; $y--) {
        for ($x = 0; $x -lt $w; $x++) {
            $c = $bmp.GetPixel($x, $y)
            $bw.Write([byte]$c.B); $bw.Write([byte]$c.G); $bw.Write([byte]$c.R); $bw.Write([byte]$c.A)
        }
    }
    for ($y = $h - 1; $y -ge 0; $y--) {
        $row = New-Object byte[] $maskRow
        for ($x = 0; $x -lt $w; $x++) {
            if ($bmp.GetPixel($x, $y).A -eq 0) { $row[[int][math]::Floor($x / 8)] = $row[[int][math]::Floor($x / 8)] -bor (0x80 -shr ($x % 8)) }
        }
        $bw.Write($row)
    }
    $bw.Flush()
    return ,$ms.ToArray()
}

function Png([System.Drawing.Bitmap]$bmp) {
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    return ,$ms.ToArray()
}

$frames = New-Object System.Collections.ArrayList
foreach ($s in 16, 32, 48) { [void]$frames.Add(@($s, (Dib (Frame $s)))) }
[void]$frames.Add(@(256, (Png (Frame 256))))

$ms = New-Object System.IO.MemoryStream
$bw = New-Object System.IO.BinaryWriter $ms
$bw.Write([int16]0); $bw.Write([int16]1); $bw.Write([int16]$frames.Count)
$offset = 6 + 16 * $frames.Count
foreach ($f in $frames) {
    [int]$s = $f[0]; [byte[]]$d = $f[1]
    $bw.Write([byte]($s % 256)); $bw.Write([byte]($s % 256)); $bw.Write([byte]0); $bw.Write([byte]0)
    $bw.Write([int16]1); $bw.Write([int16]32); $bw.Write([int32]$d.Length); $bw.Write([int32]$offset)
    $offset += $d.Length
}
foreach ($f in $frames) { [byte[]]$d = $f[1]; $bw.Write($d) }
$bw.Flush()
[System.IO.File]::WriteAllBytes($Out, $ms.ToArray())
$src.Dispose()
"""

# The exe runs `.venv/Scripts/python.exe -m app` from its own directory with no console; a failure's output shows in a box.
LAUNCHER_CS = r"""
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

static class Otto
{
    [STAThread]
    static int Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        var info = new ProcessStartInfo(Path.Combine(root, ".venv", "Scripts", "python.exe"), "-m app")
        {
            WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
        };
        var output = new StringBuilder();
        try
        {
            using (var p = Process.Start(info))
            {
                p.ErrorDataReceived += (s, e) => { if (e.Data != null) output.AppendLine(e.Data); };
                p.BeginErrorReadLine();
                output.Append(p.StandardOutput.ReadToEnd());
                p.WaitForExit();
                if (p.ExitCode != 0)
                    MessageBox.Show(output.ToString().Trim(), "Otto", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return p.ExitCode;
            }
        }
        catch (Exception e)
        {
            MessageBox.Show(e.Message, "Otto", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
"""


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def icon(source: Path, out: Path) -> None:
    script = f"$Source = {_q(str(source))}\n$Out = {_q(str(out))}\n{ICON_PS}"
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True)


def exe(ico: Path, out: Path) -> None:
    csc = Path(os.environ["SystemRoot"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if not csc.exists():
        sys.exit(f"C# compiler not found at {csc}")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "Otto.cs"
        src.write_text(LAUNCHER_CS, "utf-8")
        subprocess.run(
            [str(csc), "/nologo", "/target:winexe", "/optimize", f"/win32icon:{ico}", "/r:System.Windows.Forms.dll", f"/out:{out}", str(src)],
            check=True,
        )


def main(root: Path) -> None:
    ico = root / "app" / "static" / "otto.ico"
    icon(root / "otto.png", ico)
    exe(ico, root / "Otto.exe")
    print(f"wrote {ico}\nwrote {root / 'Otto.exe'}")

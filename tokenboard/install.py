"""安装/卸载辅助：复制文件、建快捷方式、写卸载注册表。

只用标准库 + PowerShell（系统自带）建快捷方式，不引入额外依赖。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "TokenBoard"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TokenBoard"
START_MENU = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
DESKTOP = Path(os.environ.get("USERPROFILE", "")) / "Desktop"


def default_install_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP_NAME


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME


def _shortcut_script(link: Path, target: Path, workdir: Path, icon: Path,
                     desc: str) -> str:
    return f"""$ErrorActionPreference = 'Stop'
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut('{link}')
$lnk.TargetPath = '{target}'
$lnk.WorkingDirectory = '{workdir}'
$lnk.IconLocation = '{icon},0'
$lnk.Description = '{desc}'
$lnk.Save()
"""


def create_shortcuts(install_dir: Path, with_desktop: bool = True) -> list[Path]:
    """在开始菜单和桌面创建快捷方式。"""
    exe = install_dir / f"{APP_NAME}.exe"
    if not exe.exists():
        return []
    START_MENU.mkdir(parents=True, exist_ok=True)
    made = []

    script = install_dir / "_mklink.ps1"
    # WScript.Shell.CreateShortcut 要求路径以 .lnk 结尾
    links = [START_MENU / f"{APP_NAME}.lnk"]
    if with_desktop:
        DESKTOP.mkdir(parents=True, exist_ok=True)
        links.append(DESKTOP / f"{APP_NAME}.lnk")
    body = "\n".join(
        _shortcut_script(l, exe, install_dir, exe, f"{APP_NAME} - AI IDE Token 消耗看板")
        for l in links
    )
    script.write_text(body, encoding="utf-8-sig")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script)],
            check=True, capture_output=True, timeout=60)
        if r.stderr.strip():
            import sys as _s
            print("[快捷方式] PowerShell 输出:", r.stderr.decode("utf-8", "replace")[:400],
                  file=_s.stderr)
    except Exception as e:  # noqa: BLE001
        import sys as _s
        print(f"[快捷方式] 创建失败: {e}", file=_s.stderr)
        try:
            print("[快捷方式] 脚本内容:\n" + body[:800], file=_s.stderr)
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            script.unlink()
        except OSError:
            pass
    made.extend(links)
    return made


def write_uninstall_registry(install_dir: Path, version: str = "1.0.0") -> None:
    """写「应用和功能」里的卸载项。"""
    import winreg

    exe = install_dir / f"{APP_NAME}.exe"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, f"{exe},0")
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,
                          f'"{exe}" --uninstall')
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, 0)


def delete_uninstall_registry() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY,
                            0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                winreg.DeleteKey(k, sub)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def install(payload_dir: Path, install_dir: Path, with_desktop: bool = True,
            version: str = "1.0.0") -> Path:
    """把 payload 目录复制到 install_dir。"""
    install_dir.mkdir(parents=True, exist_ok=True)
    for src in payload_dir.iterdir():
        dst = install_dir / src.name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    create_shortcuts(install_dir, with_desktop=with_desktop)
    write_uninstall_registry(install_dir, version=version)
    return install_dir


def uninstall(install_dir: Path | None = None, remove_data: bool = False) -> None:
    """卸载：删快捷方式、注册表、安装目录。"""
    install_dir = install_dir or default_install_dir()
    for link in (START_MENU / f"{APP_NAME}.lnk", DESKTOP / f"{APP_NAME}.lnk"):
        try:
            if link.exists():
                link.unlink()
        except OSError:
            pass
    delete_uninstall_registry()
    if install_dir.exists():
        shutil.rmtree(install_dir, ignore_errors=True)
    if remove_data:
        shutil.rmtree(data_dir(), ignore_errors=True)


if __name__ == "__main__":
    # 直接运行：python -m tokenboard.install --uninstall
    if "--uninstall" in sys.argv:
        uninstall(remove_data="--purge" in sys.argv)
        print("已卸载 TokenBoard")
    else:
        print("这个模块是给安装器用的，请运行 TokenBoard-Setup.exe")

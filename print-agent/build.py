import subprocess
import sys
import platform
import os
import shutil

os_name = platform.system().lower()

def find_libusb_windows():
    """Find libusb-1.0.dll from various possible locations."""
    import glob

    search_paths = [
        # pip installed libusb package
        os.path.join(sys.prefix, "Lib", "site-packages", "libusb", "_platform", "_windows", "x64", "libusb-1.0.dll"),
        os.path.join(sys.prefix, "Lib", "site-packages", "libusb", "_platform", "_windows", "x86", "libusb-1.0.dll"),
        # manually placed in project root
        os.path.join(os.path.dirname(__file__), "libusb-1.0.dll"),
        # system PATH
        shutil.which("libusb-1.0.dll"),
        # common install locations
        r"C:\Windows\System32\libusb-1.0.dll",
        r"C:\Windows\SysWOW64\libusb-1.0.dll",
    ]

    # Also search site-packages recursively
    site_packages = os.path.join(sys.prefix, "Lib", "site-packages")
    for found in glob.glob(os.path.join(site_packages, "**", "libusb-1.0.dll"), recursive=True):
        search_paths.append(found)

    for path in search_paths:
        if path and os.path.exists(path):
            print(f"  Found libusb at: {path}")
            return path

    return None


def install_requirements():
    print("[1/3] Installing requirements...")
    packages = [
        "flask",
        "flask-cors",
        "python-escpos",
        "pyusb",
        "pyserial",
        "pyinstaller",
    ]
    if os_name == "windows":
        packages.append("libusb")  # bundles the DLL on Windows

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade"] + packages,
        check=True
    )


def build():
    print(f"\n[2/3] Building for {platform.system()}...")

    if os_name == "windows":
        output_name = "shekel-agent"
        extra = ["--windowed"]

        # Find and bundle libusb DLL
        dll_path = find_libusb_windows()
        if dll_path:
            print(f"  Bundling libusb: {dll_path}")
            add_binary = [
                "--add-binary", f"{dll_path};.",
                "--collect-binaries", "libusb",
            ]
        else:
            print("  WARNING: libusb-1.0.dll not found.")
            print("  Download from libusb.info and place in this folder.")
            print("  Continuing without it — may cause 'No backend' error.")
            add_binary = []

        # Also collect usb binaries
        collect = [
            "--collect-all", "usb",
            "--collect-all", "escpos",
        ]

    elif os_name == "darwin":
        output_name = "shekel-agent-macos"
        extra = ["--windowed"]
        add_binary = []
        collect = [
            "--collect-all", "usb",
            "--collect-all", "escpos",
        ]

    else:  # linux
        output_name = "shekel-agent"
        extra = []
        add_binary = []
        collect = [
            "--collect-all", "usb",
            "--collect-all", "escpos",
        ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--clean",
        "--name", output_name,
        *extra,
        *add_binary,
        *collect,
        "agent.py",
    ]

    print(f"  Command: {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)


def verify():
    print("\n[3/3] Verifying build...")
    if os_name == "windows":
        binary = os.path.join("dist", "shekel-agent.exe")
    elif os_name == "darwin":
        binary = os.path.join("dist", "shekel-agent-macos")
    else:
        binary = os.path.join("dist", "shekel-agent")

    if os.path.exists(binary):
        size = os.path.getsize(binary) / (1024 * 1024)
        print(f"  Built: {binary} ({size:.1f} MB)")
        print("\n  Done. Distribute this file to users.")
    else:
        print(f"  ERROR: Expected binary not found at {binary}")
        sys.exit(1)


if __name__ == "__main__":
    install_requirements()
    build()
    verify()
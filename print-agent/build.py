import subprocess
import sys
import platform
import os

os_name = platform.system().lower()


def build():
    print(f"Building for {platform.system()}...")

    if os_name == "windows":
        output_name = "shekel-agent"
        extra = []
        collect = [
            "--collect-all", "escpos",
            "--hidden-import", "win32print",
            "--hidden-import", "win32api",
            "--hidden-import", "pywintypes",
        ]

    elif os_name == "darwin":
        output_name = "shekel-agent-macos"
        extra = []
        collect = [
            "--collect-all", "usb",
            "--collect-all", "escpos",
        ]

    else:  # linux
        output_name = "shekel-agent"
        extra = []
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
        *collect,
        "agent.py",
    ]

    subprocess.run(cmd, check=True)
    print(f"\nDone → dist/{output_name}")


if __name__ == "__main__":
    # Install deps first
    packages = [
        "flask",
        "flask-cors",
        "python-escpos",
        "pyusb",
        "pyserial",
        "pyinstaller",
    ]
    if os_name == "windows":
        packages.append("pywin32")  # replaces libusb on Windows

    subprocess.run(
        [sys.executable, "-m", "pip", "install"] + packages,
        check=True
    )

    build()
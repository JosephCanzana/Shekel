# build.py — run this to produce the executable
# Usage:
#   Windows  →  python build.py
#   macOS    →  python build.py
#   Linux    →  python build.py

import subprocess
import sys
import platform

os_name = platform.system().lower()

if os_name == "windows":
    output_name = "shekel-agent"
    extra = ["--windowed"]   # hides the terminal window on Windows
elif os_name == "darwin":
    output_name = "shekel-agent"
    extra = ["--windowed"]
else:
    output_name = "shekel-agent"
    extra = []               # Linux keeps the terminal (useful for debugging)

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--clean",
    "--name", output_name,
    "--add-binary", "libusb-1.0.dll;.",   # ← add this line (Windows only)
    *extra,
    "agent.py",
]

print(f"Building for {platform.system()}...")
print(f"Command: {' '.join(cmd)}\n")
subprocess.run(cmd, check=True)
print(f"\nDone. Find your binary in: dist/{output_name}")
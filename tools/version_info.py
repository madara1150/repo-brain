"""Write build/version_info.txt (Windows version resource) for APP_VERSION (default 1.0.0)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
version = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("APP_VERSION") or "1.0.0").lstrip("v")
a, b, c = (version.split(".") + ["0", "0"])[:3]
with open(os.path.join(ROOT, "build_tools", "version_info.template.txt"), encoding="utf-8") as fh:
    text = fh.read()
text = text.replace("@A@", a).replace("@B@", b).replace("@C@", c).replace("@V@", f"{a}.{b}.{c}")
os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
with open(os.path.join(ROOT, "build", "version_info.txt"), "w", encoding="utf-8") as fh:
    fh.write(text)

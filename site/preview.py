"""Start the complete local demo with the CRM environment."""
from argparse import ArgumentParser
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    port = parser.parse_args().port
    crm = Path(__file__).resolve().parents[1] / "crm"
    python = next((path for path in (crm / ".venv/Scripts/python.exe", crm / ".venv/bin/python")
                   if path.is_file()), sys.executable)
    commands = (["migrate", "--noinput"], ["seed_demo"], ["runserver", f"127.0.0.1:{port}", "--noreload"])
    for args in commands:
        subprocess.run([python, "manage.py", *args], cwd=crm, check=True)

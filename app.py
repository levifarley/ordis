import os
import sys
import subprocess
import time
import httpx

# Add both root directory and frontend directory to sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(root_dir, "frontend")

if frontend_dir not in sys.path:
    sys.path.insert(0, frontend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

_backend_process = None

def ensure_embedded_backend_running():
    """Starts FastAPI backend in a background subprocess if not already running on port 8000."""
    global _backend_process
    try:
        res = httpx.get("http://127.0.0.1:8000/api/health", timeout=0.8)
        if res.status_code == 200:
            return
    except Exception:
        pass

    if _backend_process is not None and _backend_process.poll() is None:
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = root_dir

    try:
        _backend_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=root_dir,
            env=env
        )
        time.sleep(1.5)
    except Exception as e:
        print(f"Failed to start embedded backend process: {e}", flush=True)

ensure_embedded_backend_running()

# Execute frontend Streamlit application
frontend_app_path = os.path.join(frontend_dir, "app.py")
with open(frontend_app_path, "r", encoding="utf-8") as f:
    code = compile(f.read(), frontend_app_path, "exec")
    exec(code, {"__name__": "__main__", "__file__": frontend_app_path, "__builtins__": __builtins__})

import os
import sys
import threading
import time
import httpx

# Add both root directory and frontend directory to sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(root_dir, "frontend")

if frontend_dir not in sys.path:
    sys.path.insert(0, frontend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

def ensure_embedded_backend_running():
    """Starts FastAPI backend in a background thread if not already running on port 8000."""
    try:
        res = httpx.get("http://127.0.0.1:8000/api/health", timeout=0.8)
        if res.status_code == 200:
            return
    except Exception:
        pass

    def run_uvicorn():
        try:
            import uvicorn
            uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, log_level="info")
        except Exception as e:
            print(f"Embedded uvicorn start exception: {e}", flush=True)

    thread = threading.Thread(target=run_uvicorn, daemon=True)
    thread.start()
    time.sleep(2.0)

ensure_embedded_backend_running()

# Execute frontend Streamlit application
frontend_app_path = os.path.join(frontend_dir, "app.py")
with open(frontend_app_path, "r", encoding="utf-8") as f:
    code = compile(f.read(), frontend_app_path, "exec")
    exec(code, {"__name__": "__main__", "__file__": frontend_app_path, "__builtins__": __builtins__})

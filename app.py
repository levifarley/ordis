import os
import sys

# Add both root directory and frontend directory to sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(root_dir, "frontend")

if frontend_dir not in sys.path:
    sys.path.insert(0, frontend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Execute frontend Streamlit application
frontend_app_path = os.path.join(frontend_dir, "app.py")
with open(frontend_app_path, "r", encoding="utf-8") as f:
    code = compile(f.read(), frontend_app_path, "exec")
    exec(code, {"__name__": "__main__", "__file__": frontend_app_path, "__builtins__": __builtins__})

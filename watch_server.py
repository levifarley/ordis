import os
import sys
import time
import subprocess

def get_watched_files():
    watched = []
    # Watch config.py, requirements.txt, .env, and all .py files in current directory
    # Exclude virtual env, cache directories, git folders, etc.
    exclude_dirs = {'.venv', 'venv', '__pycache__', '.git', '.agents'}
    for root, dirs, files in os.walk('.'):
        # Modify dirs in-place to avoid descending into excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith('.py') or f == 'requirements.txt' or f == '.env':
                watched.append(os.path.join(root, f))
    return watched

def get_mtimes(files):
    mtimes = {}
    for f in files:
        try:
            mtimes[f] = os.path.getmtime(f)
        except OSError:
            pass
    return mtimes

def main():
    cmd = [
        ".venv/bin/streamlit", "run", "app.py",
        "--server.port=8080", "--server.address=0.0.0.0",
        "--server.fileWatcherType=none"  # disable streamlit's own watcher to prevent double-reloading
    ]
    
    print(f"Starting server watcher: {' '.join(cmd)}")
    
    process = None
    try:
        watched_files = get_watched_files()
        last_mtimes = get_mtimes(watched_files)
        
        # Start initial process
        process = subprocess.Popen(cmd)
        
        while True:
            time.sleep(1.0)
            
            # Check if streamlit exited unexpectedly
            if process.poll() is not None:
                print("Streamlit process exited. Restarting in 2 seconds...")
                time.sleep(2.0)
                process = subprocess.Popen(cmd)
                watched_files = get_watched_files()
                last_mtimes = get_mtimes(watched_files)
                continue
                
            current_files = get_watched_files()
            current_mtimes = get_mtimes(current_files)
            
            # Check for changes in file list or file modification times
            changed = False
            if set(current_files) != set(watched_files):
                changed = True
                print("Watched file list changed.")
            else:
                for f in current_files:
                    if current_mtimes.get(f) != last_mtimes.get(f):
                        changed = True
                        print(f"File modified: {f}")
                        break
            
            if changed:
                print("Change detected. Rebooting application server...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                
                print("Server stopped. Restarting...")
                process = subprocess.Popen(cmd)
                watched_files = current_files
                last_mtimes = current_mtimes
                
    except KeyboardInterrupt:
        if process:
            process.terminate()
            process.wait()
        sys.exit(0)

if __name__ == "__main__":
    main()

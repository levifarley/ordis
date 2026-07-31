import os
import sys
import time
import subprocess

def get_watched_files():
    watched = []
    exclude_dirs = {'.venv', 'venv', '__pycache__', '.git', '.agents'}
    for root, dirs, files in os.walk('.'):
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
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_bin = os.path.join(base_dir, ".venv", "bin")
    
    cmd_streamlit = [
        os.path.join(venv_bin, "streamlit"), "run", os.path.join(base_dir, "app.py"),
        "--server.port=8080", "--server.address=0.0.0.0",
        "--server.fileWatcherType=none"
    ]
    cmd_scheduler = [
        os.path.join(venv_bin, "python"), os.path.join(base_dir, "scheduler.py")
    ]
    
    print(f"Starting server watcher...")
    print(f"  Streamlit: {' '.join(cmd_streamlit)}")
    print(f"  Scheduler: {' '.join(cmd_scheduler)}")
    
    proc_streamlit = None
    proc_scheduler = None
    
    try:
        watched_files = get_watched_files()
        last_mtimes = get_mtimes(watched_files)
        
        # Start processes
        proc_streamlit = subprocess.Popen(cmd_streamlit)
        proc_scheduler = subprocess.Popen(cmd_scheduler)
        
        while True:
            time.sleep(1.0)
            
            # Check if streamlit exited unexpectedly
            if proc_streamlit.poll() is not None:
                print("Streamlit process exited. Restarting both processes in 2 seconds...")
                time.sleep(2.0)
                try:
                    proc_scheduler.terminate()
                    proc_scheduler.wait(timeout=2)
                except Exception:
                    pass
                proc_streamlit = subprocess.Popen(cmd_streamlit)
                proc_scheduler = subprocess.Popen(cmd_scheduler)
                watched_files = get_watched_files()
                last_mtimes = get_mtimes(watched_files)
                continue
                
            # Check if scheduler exited unexpectedly
            if proc_scheduler.poll() is not None:
                print("Scheduler process exited. Restarting scheduler...")
                proc_scheduler = subprocess.Popen(cmd_scheduler)
                continue
                
            current_files = get_watched_files()
            current_mtimes = get_mtimes(current_files)
            
            changed = False
            if set(current_files) != set(watched_files):
                changed = True
                print("Watched file list changed.")
            else:
                for f in current_files:
                    if current_mtimes.get(f) != last_mtimes.get(f):
                        changed = True
                        print(f"Code file modified: {f}")
                        break
            
            if changed:
                print("Code or environment change detected. Rebooting processes...")
                proc_streamlit.terminate()
                proc_scheduler.terminate()
                
                for p in (proc_streamlit, proc_scheduler):
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()
                
                print("Processes stopped. Restarting...")
                proc_streamlit = subprocess.Popen(cmd_streamlit)
                proc_scheduler = subprocess.Popen(cmd_scheduler)
                watched_files = current_files
                last_mtimes = current_mtimes
                
    except KeyboardInterrupt:
        print("Stopping watched processes...")
        for p in (proc_streamlit, proc_scheduler):
            if p:
                try:
                    p.terminate()
                    p.wait()
                except Exception:
                    pass
        sys.exit(0)

if __name__ == "__main__":
    main()

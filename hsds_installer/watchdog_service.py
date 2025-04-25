
import os
import subprocess
import threading
import time
import requests
from datetime import datetime, timedelta
from queue import Queue
import base64
import sys
import logging
import json

# ------------------ Logs ------------------
LOG_FILE = r"C:\Sioux\hsds_installer\logs\watchdog_runtime.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename=LOG_FILE,
    filemode='a'
)

class LoggerWriter:
    def __init__(self, level):
        self.level = level

    def write(self, message):
        message = message.strip()
        if message:  
            self.level(message)

    def flush(self):
        pass

sys.stdout = LoggerWriter(logging.info)
sys.stderr = LoggerWriter(logging.error)

# ===================== GLOBAL CONST =====================
DOMAIN_PREFIX = "/home/admin/"        
ADMIN_USERNAME = "admin"               
ADMIN_PASSWORD = "admin"               
TIME_SIGNAL_NAME = "@Time@"            
DEFAULT_SAMPLE_FREQUENCY = 4000        
GLOBAL_ENDPOINT = "http://localhost:5101"  # self-deployed hsds

TRACE_PATH = os.path.join(os.path.dirname(__file__), "trace_path.json")
def load_watchdog_dirs(trace_path=TRACE_PATH):
    try:
        with open(trace_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            dirs = data.get("watchdog_dirs", [])
            if not isinstance(dirs, list):
                raise ValueError("配置文件格式错误，'watchdog_dirs' 应为列表。")
            return dirs
    except Exception as e:
        print(f"ERROR 无法加载配置文件 '{trace_path}'：{e}")
        return []

WATCHDOG_DIRS = load_watchdog_dirs()

#=======================Background Upload Queue===========================
upload_queue = Queue()

def upload_worker():
    while True:
        file_path = upload_queue.get()
        if file_path is None:  
            break
        default_upload_callback(file_path)
        upload_queue.task_done()

worker_thread = threading.Thread(target=upload_worker, daemon=True)
worker_thread.start()



# -------------------------------------------------------------------------------
# Watchdog File Monitor
# -------------------------------------------------------------------------------

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

HSLOAD_PATH = r"C:\Sioux\hsds_installer\venv\Scripts\hsload.exe"
HSLS_PATH = r"C:\Sioux\hsds_installer\venv\Scripts\hsls.exe"

class HDF5UploadHandler(FileSystemEventHandler):
    def __init__(self, upload_callback, debounce_interval=1):

        self.upload_callback = upload_callback
        self.debounce_interval = debounce_interval
        self.pending_files = {}  # {file_path: last_modification_time}
        self._stop_event = threading.Event()
        self._checker_thread = threading.Thread(target=self._check_pending_files)
        self._checker_thread.daemon = True
        self._checker_thread.start()

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.lower().endswith('.strc'):
            print("Detected new file (created):", event.src_path)
            self.pending_files[event.src_path] = time.time()

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.lower().endswith('.strc'):
            if event.src_path not in self.pending_files:
                print("Detected file modification:", event.src_path)
            self.pending_files[event.src_path] = time.time()

    def _check_pending_files(self):
        while not self._stop_event.is_set():
            now = time.time()
            for file_path, last_mod in list(self.pending_files.items()):
                if now - last_mod >= self.debounce_interval:
                    print(f"File {file_path} is stable for {self.debounce_interval} seconds, uploading...")
                    upload_queue.put(file_path)  
                    del self.pending_files[file_path]
            time.sleep(1)

    def stop(self):
        self._stop_event.set()
        self._checker_thread.join()

def start_watchdog_for_dirs(dirs, upload_callback, debounce_interval=3):

    observers = []
    handler = HDF5UploadHandler(upload_callback, debounce_interval=debounce_interval)
    for path_to_watch in dirs:
        observer = Observer()
        observer.schedule(handler, path=path_to_watch, recursive=False)
        observer.start()
        observers.append((observer, handler))
        print(f"Started monitoring directory: {path_to_watch}")
    return observers

def domain_exists(domain):
    try:
        result = subprocess.run([
            HSLS_PATH,
            "-e", GLOBAL_ENDPOINT,
            "-u", ADMIN_USERNAME,
            "-p", ADMIN_PASSWORD,
            DOMAIN_PREFIX
        ],
                                capture_output=True, text=True, check=True)
        print(f"hsls output:\n{result.stdout}")
        return domain in result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running hsls: {e}")
        print(f"hsls stderr: {e.stderr}")
        return False

def default_upload_callback(file_path):
    filename = os.path.basename(file_path)
    domain = DOMAIN_PREFIX + filename

    if domain_exists(domain):
        print(f"Domain {domain} already exists (checked via hsls), skipping upload.")
        return domain

    print(f"Uploading file {filename} to domain {domain}...")
    try:
        result = subprocess.run(
    [
        HSLOAD_PATH,
        "-e", GLOBAL_ENDPOINT,
        "-u", ADMIN_USERNAME,
        "-p", ADMIN_PASSWORD,
        file_path,
        domain
    ],            capture_output=True, text=True, check=True
        )
        print(f"File {filename} has been successfully uploaded.")
        print(f"hsload stdout: {result.stdout}")
    except subprocess.CalledProcessError as err:
        error_message = err.stderr or err.stdout
        print(f"hsload stderr: {err.stderr}")
        print(f"hsload stdout: {err.stdout}")
        print(f"Upload failed with return code {err.returncode}")
        
        if "Unable to synchronously open file" in error_message:
            print("Detected error on file consistency, trying to reset the flag...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            h5clear_path = os.path.join(script_dir, "bin", "h5clear.exe")
            clear_cmd = [h5clear_path, "-s", file_path]
            subprocess.run(clear_cmd, capture_output=True, text=True)
            result = subprocess.run(
    [
        HSLOAD_PATH,
        "-e", GLOBAL_ENDPOINT,
        "-u", ADMIN_USERNAME,
        "-p", ADMIN_PASSWORD,
        file_path,
        domain
    ],                capture_output=True, text=True, check=True
            )
            print(f"File {filename} has been successfully uploaded.")
        else:
            raise
    return domain

def is_file_stable(file_path, debounce_interval=1): # 1s debounce interval

    try:
        initial_size = os.path.getsize(file_path)
        initial_mtime = os.path.getmtime(file_path)
    except Exception as e:
        print(f"Error accessing {file_path}: {e}")
        return False

    time.sleep(debounce_interval)

    try:
        new_size = os.path.getsize(file_path)
        new_mtime = os.path.getmtime(file_path)
    except Exception as e:
        print(f"Error accessing {file_path} after waiting: {e}")
        return False

    if initial_size == new_size and initial_mtime == new_mtime:
        return True
    else:
        return False

def scan_and_upload_all(dirs, debounce_interval=1):
    for path in dirs:
        if not os.path.exists(path):
            print(f"Directory {path} does not exist, skipping...")
            continue
        for file in os.listdir(path):
            if file.lower().endswith('.strc'):
                file_path = os.path.join(path, file)
                print(f"Found file {file_path}, checking stability...")
                if is_file_stable(file_path, debounce_interval):
                    print(f"File {file_path} is stable, adding to upload queue...")
                    upload_queue.put(file_path)
                else:
                    print(f"File {file_path} is not stable yet, skipping for now.")

def main():
    print("Starting Watchdog Service for HSDS file upload...")
    scan_and_upload_all(WATCHDOG_DIRS)
    observers = start_watchdog_for_dirs(WATCHDOG_DIRS, default_upload_callback)
    while True:
        time.sleep(10)

if __name__ == "__main__":
    main()

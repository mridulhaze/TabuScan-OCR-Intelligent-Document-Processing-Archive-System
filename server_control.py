import os
import sys
import subprocess
import threading
import webbrowser
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import scrolledtext

class ServerControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TabuScan Server Controller")
        self.root.geometry("600x480")
        self.root.configure(bg="#1a1c1a") # Dark forest background
        self.root.resizable(False, False)
        
        # Keep window on top on launch
        self.root.attributes("-topmost", True)
        self.root.after(1000, lambda: self.root.attributes("-topmost", False))
        
        self.process = None
        self.log_thread = None
        self.is_running = False

        # Fonts
        self.title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.status_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        self.btn_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.log_font = tkfont.Font(family="Consolas", size=9)

        self.setup_ui()
        
        # Handle close window event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        # Header Area
        header_frame = tk.Frame(self.root, bg="#242824", height=70)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        logo_label = tk.Label(header_frame, text="📄", font=("Segoe UI", 22), bg="#242824", fg="#2ecc71")
        logo_label.pack(side="left", padx=(20, 10))

        title_label = tk.Label(header_frame, text="TabuScan Service Console", font=self.title_font, bg="#242824", fg="#ffffff")
        title_label.pack(side="left")

        # Status and Controls Area
        ctrl_frame = tk.Frame(self.root, bg="#1a1c1a", pady=20)
        ctrl_frame.pack(fill="x")

        # Status Label
        status_container = tk.Frame(ctrl_frame, bg="#1a1c1a")
        status_container.pack(fill="x", padx=30, pady=(0, 15))
        
        tk.Label(status_container, text="Service Status:", font=self.btn_font, bg="#1a1c1a", fg="#a0a8a0").pack(side="left")
        self.status_val = tk.Label(status_container, text="OFFLINE", font=self.status_font, bg="#1a1c1a", fg="#e74c3c")
        self.status_val.pack(side="left", padx=10)

        self.ip_val = tk.Label(status_container, text="", font=("Segoe UI", 10), bg="#1a1c1a", fg="#2ecc71")
        self.ip_val.pack(side="right")

        # Action Buttons
        btn_container = tk.Frame(ctrl_frame, bg="#1a1c1a")
        btn_container.pack(fill="x", padx=30)

        self.toggle_btn = tk.Button(
            btn_container, 
            text="▶  Start Server", 
            font=self.btn_font, 
            bg="#2ecc71", 
            fg="#ffffff", 
            activebackground="#27ae60", 
            activeforeground="#ffffff",
            bd=0, 
            pady=8,
            cursor="hand2",
            command=self.toggle_server
        )
        self.toggle_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.web_btn = tk.Button(
            btn_container, 
            text="🌐  Open Web Portal", 
            font=self.btn_font, 
            bg="#34495e", 
            fg="#ffffff", 
            activebackground="#2c3e50", 
            activeforeground="#ffffff",
            bd=0, 
            pady=8,
            cursor="hand2",
            state="disabled",
            command=self.open_web
        )
        self.web_btn.pack(side="left", expand=True, fill="x", padx=6)

        self.dep_btn = tk.Button(
            btn_container, 
            text="🛠️  Install Dependencies", 
            font=self.btn_font, 
            bg="#7f8c8d", 
            fg="#ffffff", 
            activebackground="#95a5a6", 
            activeforeground="#ffffff",
            bd=0, 
            pady=8,
            cursor="hand2",
            command=self.run_install_dependencies
        )
        self.dep_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        # Footer Copyright (packed first at bottom to reserve space)
        footer_label = tk.Label(self.root, text="Developed by : Mridul Roy", font=("Segoe UI", 9, "italic"), bg="#1a1c1a", fg="#7a827a")
        footer_label.pack(side="bottom", pady=(5, 10))

        # Log Terminal Area
        log_label_frame = tk.Frame(self.root, bg="#1a1c1a", padx=30)
        log_label_frame.pack(fill="x", pady=(10, 2))
        tk.Label(log_label_frame, text="Activity Logs:", font=("Segoe UI", 10, "bold"), bg="#1a1c1a", fg="#a0a8a0").pack(side="left")
        
        clear_logs_btn = tk.Button(
            log_label_frame,
            text="Clear Log",
            font=("Segoe UI", 8),
            bg="#242824",
            fg="#a0a8a0",
            bd=0,
            cursor="hand2",
            padx=6,
            command=self.clear_logs
        )
        clear_logs_btn.pack(side="right")

        copy_logs_btn = tk.Button(
            log_label_frame,
            text="Copy Log",
            font=("Segoe UI", 8),
            bg="#242824",
            fg="#a0a8a0",
            bd=0,
            cursor="hand2",
            padx=6,
            command=self.copy_logs
        )
        copy_logs_btn.pack(side="right", padx=(0, 8))

        self.log_box = scrolledtext.ScrolledText(
            self.root, 
            font=self.log_font, 
            bg="#111211", 
            fg="#d0ffd0", 
            insertbackground="#ffffff",
            bd=0,
            highlightthickness=1,
            highlightcolor="#2ecc71"
        )
        self.log_box.pack(fill="both", expand=True, padx=30, pady=(0, 5))
        self.log_box.insert(tk.END, "[Console] TabuScan Console Ready.\n[Console] Click 'Start Server' to bind backend and listen.\n")
        self.log_box.configure(state="disabled")

    def toggle_server(self):
        if not self.is_running:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, "\n[Console] Starting background service...\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")
        
        # Verify app.py exists
        if not os.path.exists("app.py"):
            self.log_box.configure(state="normal")
            self.log_box.insert(tk.END, "[Error] Could not find app.py in current directory!\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state="disabled")
            return

        try:
            # Launch Python subprocess running app.py
            # Use sys.executable to run in same python environment
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            python_path = "python" if getattr(sys, 'frozen', False) else sys.executable
            self.process = subprocess.Popen(
                [python_path, "app.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding='utf-8',
                bufsize=1,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                env=env
            )
            
            self.is_running = True
            self.status_val.configure(text="RUNNING (ONLINE)", fg="#2ecc71")
            self.toggle_btn.configure(text="■  Stop Server", bg="#e74c3c", activebackground="#c0392b")
            self.web_btn.configure(state="normal")
            local_ip = self.get_local_ip()
            self.ip_val.configure(text=f"Portal: http://{local_ip}:5000")

            # Start thread to read logs asynchronously
            self.log_thread = threading.Thread(target=self.read_logs, daemon=True)
            self.log_thread.start()
            
        except Exception as e:
            self.log_box.configure(state="normal")
            self.log_box.insert(tk.END, f"[Error] Failed to spawn server: {str(e)}\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state="disabled")

    def stop_server(self):
        if not self.process:
            return

        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, "[Console] Stopping service...\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

        try:
            if sys.platform == "win32":
                # Clean process termination tree on Windows
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                self.process.terminate()
                self.process.wait()
        except Exception as e:
            print("Stop error:", e)

        self.process = None
        self.is_running = False
        self.status_val.configure(text="OFFLINE", fg="#e74c3c")
        self.toggle_btn.configure(text="▶  Start Server", bg="#2ecc71", activebackground="#27ae60")
        self.web_btn.configure(state="disabled")
        self.ip_val.configure(text="")
        
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, "[Console] Service Stopped.\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

    def read_logs(self):
        while self.is_running and self.process:
            line = self.process.stdout.readline()
            if not line:
                break
            
            # Safe GUI write from background thread
            self.root.after(0, self.append_log, line)
            
        # If output stops, service has exited
        self.root.after(0, self.handle_unexpected_exit)

    def append_log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, text)
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

    def handle_unexpected_exit(self):
        if self.is_running:
            self.is_running = False
            self.process = None
            self.status_val.configure(text="CRASHED / OFFLINE", fg="#e74c3c")
            self.toggle_btn.configure(text="▶  Start Server", bg="#2ecc71", activebackground="#27ae60")
            self.web_btn.configure(state="disabled")
            self.ip_val.configure(text="")
            
            self.log_box.configure(state="normal")
            self.log_box.insert(tk.END, "[Console] Service exited unexpectedly.\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state="disabled")

    def get_local_ip(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def open_web(self):
        local_ip = self.get_local_ip()
        webbrowser.open(f"http://{local_ip}:5000/")

    def copy_logs(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.log_box.get("1.0", tk.END).strip())
            self.log_box.configure(state="normal")
            self.log_box.insert(tk.END, "[Console] Logs copied to clipboard.\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state="disabled")
        except Exception as e:
            print("Error copying to clipboard:", e)

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")

    def run_install_dependencies(self):
        # Disable button during installation
        self.dep_btn.configure(state="disabled", bg="#95a5a6")
        
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, "\n[Console] Starting dependency check and install...\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")
        
        # Run checker in a background thread to keep GUI responsive
        threading.Thread(target=self.install_process, daemon=True).start()

    def install_process(self):
        libs = {
            "flask": "flask",
            "pyodbc": "pyodbc",
            "easyocr": "easyocr",
            "cv2": "opencv-python",
            "numpy": "numpy",
            "PIL": "pillow"
        }
        
        to_install = []
        for module_name, pip_name in libs.items():
            try:
                __import__(module_name)
                self.root.after(0, self.append_log, f"[Check] Module '{module_name}' is installed.\n")
            except ImportError:
                self.root.after(0, self.append_log, f"[Check] Module '{module_name}' is MISSING.\n")
                to_install.append(pip_name)
        
        if to_install:
            self.root.after(0, self.append_log, f"[Install] Installing missing packages: {', '.join(to_install)}...\n")
            
            # Spawn pip subprocess
            try:
                startupinfo = None
                if sys.platform == "win32":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE

                # We use sys.executable if running as normal script, but if we are frozen, we use "python"
                python_bin = "python" if getattr(sys, 'frozen', False) else sys.executable
                
                pip_proc = subprocess.Popen(
                    [python_bin, "-m", "pip", "install"] + to_install,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    startupinfo=startupinfo
                )
                
                while True:
                    line = pip_proc.stdout.readline()
                    if not line:
                        break
                    self.root.after(0, self.append_log, line)
                    
                pip_proc.wait()
                if pip_proc.returncode == 0:
                    self.root.after(0, self.append_log, "[Success] All packages installed successfully.\n")
                else:
                    self.root.after(0, self.append_log, f"[Error] Pip exited with code {pip_proc.returncode}.\n")
            except Exception as e:
                self.root.after(0, self.append_log, f"[Error] Installation failed: {str(e)}\n")
        else:
            self.root.after(0, self.append_log, "[Check] All Python library dependencies are present.\n")
            
        # Verify ODBC Driver 17 for SQL Server
        try:
            import pyodbc
            drivers = pyodbc.drivers()
            odbc_17_found = any("ODBC Driver 17 for SQL Server" in d for d in drivers)
            if odbc_17_found:
                self.root.after(0, self.append_log, "[Check] ODBC Driver 17 for SQL Server is installed.\n")
            else:
                self.root.after(0, self.append_log, "[Warning] 'ODBC Driver 17 for SQL Server' was not found in system drivers!\n")
                self.root.after(0, self.append_log, "[Warning] Please install Microsoft ODBC Driver 17 if connection fails.\n")
        except Exception:
            self.root.after(0, self.append_log, "[Warning] Could not verify system ODBC drivers.\n")
            
        self.root.after(0, self.enable_dep_btn)

    def enable_dep_btn(self):
        self.dep_btn.configure(state="normal", bg="#7f8c8d")

    def on_close(self):
        if self.is_running:
            self.stop_server()
        self.root.destroy()

if __name__ == "__main__":
    # Ensure working directory is set to script directory (handling PyInstaller frozen path)
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(sys.executable)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    root = tk.Tk()
    app = ServerControlApp(root)
    root.mainloop()

import os
import threading
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

def run_cmd(cmd, cwd=None, input_text=None, log_cb=None):
    line = " ".join(cmd)
    if log_cb:
        log_cb(f"> {line}\n")
    try:
        res = subprocess.run(cmd, cwd=cwd, input=input_text, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Command failed: {line}")
    except Exception as e:
        raise RuntimeError(str(e))

def run_cmd_capture(cmd, log_cb=None):
    line = " ".join(cmd)
    if log_cb:
        log_cb(f"> {line}\n")
    return subprocess.check_output(cmd, text=True).strip()

def windows_to_wsl_path(p):
    path = Path(p).resolve()
    drive = path.drive.replace(":", "").lower()
    rest = str(path).replace("\\", "/")
    if ":" in rest:
        rest = rest.split(":", 1)[1]
    return f"/mnt/{drive}{('/' + rest.lstrip('/')) if rest else ''}"

def docker_image_exists(tag):
    try:
        out = run_cmd_capture(["docker", "image", "ls", "-q", tag])
        return len(out.strip()) > 0
    except Exception:
        return False

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mendix v6 Build & Push to ECR")
        self.geometry("780x640")
        self.resizable(True, True)

        self.buildpack_dir = tk.StringVar(value=str(Path.cwd()))
        self.source_dir = tk.StringVar()
        self.context_dir = tk.StringVar()
        self.wsl_distro = tk.StringVar()
        self.wsl_choices = self._list_wsl_distros()
        if self.wsl_choices:
            self.wsl_distro.set(self.wsl_choices[0])
        self.image = tk.StringVar(value="ample2")
        self.tag = tk.StringVar(value="local")
        self.account_id = tk.StringVar()
        self.repo_name = tk.StringVar()
        self.region = tk.StringVar(value="ap-south-1")
        self.skip_rootfs = tk.BooleanVar(value=False)
        self.use_env_creds = tk.BooleanVar(value=True)
        self.aws_access_key_id = tk.StringVar()
        self.aws_secret_access_key = tk.StringVar()
        self.aws_session_token = tk.StringVar()

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def add_path_row(row, label, var, browse_cb):
            ttk.Label(frm, text=label).grid(column=0, row=row, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(frm, textvariable=var, width=70).grid(column=1, row=row, sticky=tk.W, padx=4, pady=4)
            ttk.Button(frm, text="Browse", command=browse_cb).grid(column=2, row=row, sticky=tk.W, padx=4, pady=4)

        add_path_row(0, "Buildpack directory", self.buildpack_dir, lambda: self._choose_dir(self.buildpack_dir))
        add_path_row(1, "Mendix source", self.source_dir, lambda: self._choose_dir(self.source_dir))
        add_path_row(2, "Docker context", self.context_dir, lambda: self._choose_dir(self.context_dir))

        ttk.Label(frm, text="WSL Distro").grid(column=0, row=3, sticky=tk.W, padx=4, pady=4)
        self.wsl_combo = ttk.Combobox(frm, textvariable=self.wsl_distro, values=self.wsl_choices or [""], state="readonly", width=30)
        self.wsl_combo.grid(column=1, row=3, sticky=tk.W, padx=4, pady=4)
        ttk.Button(frm, text="Refresh", command=self._refresh_wsl_choices).grid(column=2, row=3, sticky=tk.W, padx=4, pady=4)

        ttk.Label(frm, text="Image name").grid(column=0, row=4, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(frm, textvariable=self.image, width=30).grid(column=1, row=4, sticky=tk.W, padx=4, pady=4)

        ttk.Label(frm, text="Image tag").grid(column=0, row=5, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(frm, textvariable=self.tag, width=30).grid(column=1, row=5, sticky=tk.W, padx=4, pady=4)

        ttk.Label(frm, text="AWS Account ID").grid(column=0, row=6, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(frm, textvariable=self.account_id, width=30).grid(column=1, row=6, sticky=tk.W, padx=4, pady=4)

        ttk.Label(frm, text="ECR Repo Name").grid(column=0, row=7, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(frm, textvariable=self.repo_name, width=30).grid(column=1, row=7, sticky=tk.W, padx=4, pady=4)

        ttk.Label(frm, text="AWS Region").grid(column=0, row=8, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(frm, textvariable=self.region, width=30).grid(column=1, row=8, sticky=tk.W, padx=4, pady=4)

        ttk.Checkbutton(frm, text="Skip RootFS build", variable=self.skip_rootfs).grid(column=1, row=9, sticky=tk.W, padx=4, pady=4)
        ttk.Checkbutton(frm, text="Use AWS credentials from environment", variable=self.use_env_creds, command=self._toggle_creds_inputs).grid(column=1, row=10, sticky=tk.W, padx=4, pady=4)

        self.creds_frame = ttk.Frame(frm)
        self.creds_frame.grid(column=1, row=11, sticky=tk.W, padx=4, pady=4)
        ttk.Label(self.creds_frame, text="Access Key ID").grid(column=0, row=0, sticky=tk.W)
        ttk.Entry(self.creds_frame, textvariable=self.aws_access_key_id, width=40).grid(column=1, row=0, sticky=tk.W)
        ttk.Label(self.creds_frame, text="Secret Access Key").grid(column=0, row=1, sticky=tk.W)
        ttk.Entry(self.creds_frame, textvariable=self.aws_secret_access_key, width=40, show="*").grid(column=1, row=1, sticky=tk.W)
        ttk.Label(self.creds_frame, text="Session Token").grid(column=0, row=2, sticky=tk.W)
        ttk.Entry(self.creds_frame, textvariable=self.aws_session_token, width=40, show="*").grid(column=1, row=2, sticky=tk.W)

        self._toggle_creds_inputs()

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(column=1, row=12, sticky=tk.W, padx=4, pady=8)
        self.install_btn = ttk.Button(btn_frame, text="Install Basics", command=self._start_install_basics)
        self.install_btn.grid(column=0, row=0, padx=4)
        self.build_btn = ttk.Button(btn_frame, text="Start Build", command=self._start_build)
        self.build_btn.grid(column=1, row=0, padx=4)
        self.push_btn = ttk.Button(btn_frame, text="Push to ECR", command=self._start_push)
        self.push_btn.grid(column=2, row=0, padx=4)

        self.log = tk.Text(frm, height=18)
        self.log.grid(column=0, row=13, columnspan=3, sticky="nsew", padx=4, pady=4)
        scroll = ttk.Scrollbar(frm, orient="vertical", command=self.log.yview)
        scroll.grid(column=3, row=13, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(13, weight=1)

    def _toggle_creds_inputs(self):
        state = tk.DISABLED if self.use_env_creds.get() else tk.NORMAL
        for child in self.creds_frame.winfo_children():
            child.configure(state=state)

    def _choose_dir(self, var):
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def _append_log(self, text):
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def _start_install_basics(self):
        self.install_btn.configure(state=tk.DISABLED)
        t = threading.Thread(target=self._run_install_basics, daemon=True)
        t.start()

    def _start_build(self):
        self.build_btn.configure(state=tk.DISABLED)
        self.push_btn.configure(state=tk.DISABLED)
        t = threading.Thread(target=self._run_build_pipeline, daemon=True)
        t.start()

    def _start_push(self):
        self.build_btn.configure(state=tk.DISABLED)
        self.push_btn.configure(state=tk.DISABLED)
        t = threading.Thread(target=self._run_push_pipeline, daemon=True)
        t.start()

    def _run_install_basics(self):
        try:
            self._append_log("Installing basics in WSL\n")
            distros = self._list_wsl_distros()
            if self.wsl_distro.get() not in distros:
                raise RuntimeError("Selected WSL distro not found")
            distro = self._sanitize_distro(self.wsl_distro.get())
            run_cmd(["wsl", "-d", distro, "sh", "-lc", "sudo apt-get update"], log_cb=self._append_log)
            run_cmd(["wsl", "-d", distro, "sh", "-lc", "sudo apt-get install -y python3 python3-pip"], log_cb=self._append_log)
            run_cmd(["wsl", "-d", distro, "python3", "--version"], log_cb=self._append_log)
            self._append_log("Basics installed\n")
        except Exception as e:
            self._append_log(f"Error: {e}\n")
        finally:
            self.install_btn.configure(state=tk.NORMAL)

    def _run_build_pipeline(self):
        try:
            self._append_log("Validating prerequisites\n")
            for name in ["docker", "aws", "wsl"]:
                if not shutil.which(name):
                    raise RuntimeError(f"Missing required command: {name}")

            distros = self._list_wsl_distros()
            if self.wsl_distro.get() not in distros:
                raise RuntimeError("Selected WSL distro not found")
            distro = self._sanitize_distro(self.wsl_distro.get())
            res = subprocess.run(["wsl", "-d", distro, "python3", "--version"])
            if res.returncode != 0:
                raise RuntimeError("python3 not available in Ubuntu WSL")

            os.environ["AWS_DEFAULT_REGION"] = self.region.get().strip()

            if not self.skip_rootfs.get():
                self._append_log("Building rootfs images\n")
                if not docker_image_exists("mendix-rootfs:app"):
                    run_cmd(["docker", "build", "-t", "mendix-rootfs:app", "-f", "rootfs-app.dockerfile", "."], cwd=self.buildpack_dir.get(), log_cb=self._append_log)
                else:
                    self._append_log("mendix-rootfs:app present, skipping\n")
                if not docker_image_exists("mendix-rootfs:builder"):
                    run_cmd(["docker", "build", "-t", "mendix-rootfs:builder", "-f", "rootfs-builder.dockerfile", "."], cwd=self.buildpack_dir.get(), log_cb=self._append_log)
                else:
                    self._append_log("mendix-rootfs:builder present, skipping\n")

            self._append_log("Compiling Mendix app via build.py\n")
            wsl_buildpack = windows_to_wsl_path(self.buildpack_dir.get())
            wsl_source = windows_to_wsl_path(self.source_dir.get())
            wsl_context = windows_to_wsl_path(self.context_dir.get())
            shell_cmd = f"cd {wsl_buildpack} && python3 ./build.py --source {wsl_source} --destination {wsl_context} build-mda-dir"
            run_cmd(["wsl", "-d", distro, "sh", "-lc", shell_cmd], log_cb=self._append_log)

            self._append_log("Building final runtime image\n")
            run_cmd(["docker", "build", "-t", f"{self.image.get()}:{self.tag.get()}", self.context_dir.get()], log_cb=self._append_log)

            self._append_log("Build completed\n")
        except Exception as e:
            self._append_log(f"Error: {e}\n")
        finally:
            self.build_btn.configure(state=tk.NORMAL)
            self.push_btn.configure(state=tk.NORMAL)

    def _run_push_pipeline(self):
        try:
            self._append_log("Preparing for push\n")
            for name in ["docker", "aws"]:
                if not shutil.which(name):
                    raise RuntimeError(f"Missing required command: {name}")

            if not self.use_env_creds.get():
                os.environ["AWS_ACCESS_KEY_ID"] = self.aws_access_key_id.get().strip()
                os.environ["AWS_SECRET_ACCESS_KEY"] = self.aws_secret_access_key.get().strip()
                os.environ["AWS_SESSION_TOKEN"] = self.aws_session_token.get().strip()
            os.environ["AWS_DEFAULT_REGION"] = self.region.get().strip()

            local_tag = f"{self.image.get()}:{self.tag.get()}"
            if not docker_image_exists(local_tag):
                raise RuntimeError(f"Local image not found: {local_tag}. Build first.")

            run_cmd(["aws", "sts", "get-caller-identity"], log_cb=self._append_log)
            password = run_cmd_capture(["aws", "ecr", "get-login-password", "--region", self.region.get().strip()], self._append_log)
            registry = f"{self.account_id.get().strip()}.dkr.ecr.{self.region.get().strip()}.amazonaws.com"
            run_cmd(["docker", "login", "--username", "AWS", "--password-stdin", registry], input_text=password, log_cb=self._append_log)

            target = f"{registry}/{self.repo_name.get().strip()}:latest"
            run_cmd(["docker", "tag", local_tag, target], log_cb=self._append_log)
            run_cmd(["docker", "push", target], log_cb=self._append_log)

            self._append_log("Push completed\n")
        except Exception as e:
            self._append_log(f"Error: {e}\n")
        finally:
            self.build_btn.configure(state=tk.NORMAL)
            self.push_btn.configure(state=tk.NORMAL)

    def _list_wsl_distros(self):
        try:
            out = subprocess.check_output(["wsl", "-l", "-q"], text=True)
            lines = [l.replace("\x00", "").strip() for l in out.splitlines() if l.strip()]
            return lines
        except Exception:
            return []

    def _sanitize_distro(self, d):
        return (d or "").replace("\x00", "").strip()

    def _refresh_wsl_choices(self):
        self.wsl_choices = self._list_wsl_distros()
        self.wsl_combo.configure(values=self.wsl_choices or [""])
        if self.wsl_choices and self.wsl_distro.get() not in self.wsl_choices:
            self.wsl_distro.set(self.wsl_choices[0])

if __name__ == "__main__":
    try:
        import shutil
    except Exception:
        pass
    app = App()
    app.mainloop()

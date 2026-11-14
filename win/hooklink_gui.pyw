"""HookLinkWindows — Windows GUI for building iOS apps from supported NUP input.

Installs alongside the existing win/gui.pyw without replacing the build engine.
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import traceback

from hooklink_gui_core import (BuildConfig, PACKAGE_APP_ONLY, PACKAGE_FULL,
                               check_runtime_config, default_output_name,
                               export_app_only_ipa, find_transfer_sources,
                               make_build_environment, make_build_plan,
                               prepare_transfer_folder, shader_chain_from_ipa,
                               verify_build_config)
from hooklink_portable import (SettingsStore, check_project_installation, locate_engine_root,
                               DEFAULT_IPA_NAME)
from hooklink_prereqs import run_prerequisite_check

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
HOME = Path.home()
DEFAULT_WORK = HOME / 'HookLinkWindowsBuild'
DEFAULT_ENV = ROOT / 'config' / 'iphone-oot.env'
GUI_VERSION = '0.8.0'
DEFAULT_BUNDLE_ID = 'PhoenixNetwork.HookLinkWindows'


def build_python() -> str:
    """The GUI may be frozen, but compilation needs a real external Python."""
    if not getattr(sys, 'frozen', False):
        return sys.executable
    python = shutil.which('py.exe') or shutil.which('py') or shutil.which('python.exe') or shutil.which('python')
    if not python:
        raise ValueError('Python 3 is needed for the HookLinkWindows build toolchain. Install Python 3, then reopen the GUI.')
    return python



class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'HookLinkWindows — Ocarina of Time Builder (v{GUI_VERSION})')
        self.geometry('980x800')
        self.minsize(815, 680)
        self.proc: subprocess.Popen | None = None
        self.task_thread: threading.Thread | None = None
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.store = SettingsStore(ROOT)
        prefs, self.settings_warnings = self.store.load()
        work = prefs.get('work_dir') or str(DEFAULT_WORK)
        self.output_auto = prefs.get('output_auto', True)
        self.package_mode = tk.StringVar(value=prefs.get('package_mode', PACKAGE_APP_ONLY))
        self._updating_output = False
        self.input_var = tk.StringVar(value=prefs.get('input_path', ''))
        self.work_var = tk.StringVar(value=work)
        self.env_var = tk.StringVar(value=prefs.get('env_file') or str(DEFAULT_ENV))
        output_default = str(Path(work) / default_output_name(self.package_mode.get()))
        self.output_var = tk.StringVar(value=output_default if self.output_auto else (prefs.get('output_ipa') or output_default))
        saved_bundle = prefs.get('bundle_id') or DEFAULT_BUNDLE_ID
        if saved_bundle == 'org.example.hooklinkoot':
            saved_bundle = DEFAULT_BUNDLE_ID
        self.bundle_var = tk.StringVar(value=saved_bundle)
        self.workers_var = tk.StringVar(value=str(prefs.get('workers', min(61, max(1, os.cpu_count() or 4)))))
        self.allow_damaged = tk.BooleanVar(value=prefs.get('allow_damaged', True))
        self.allow_metal = tk.BooleanVar(value=prefs.get('allow_metal', True))
        self.entitlements = tk.BooleanVar(value=prefs.get('entitlements', True))
        self.state_var = tk.StringVar(value='Select a .nup file, then check prerequisites and build settings.')
        self._pending_package = None
        self._build_ui()
        self.package_mode.trace_add('write', self._mode_changed)
        self.work_var.trace_add('write', self._work_changed)
        self.output_var.trace_add('write', self._output_edited)
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self.after(100, self._drain)
        self._input_changed()
        self._append(f'HookLinkWindows Ocarina of Time Builder v{GUI_VERSION}\n')
        self._append('Choose a game .nup file, run Check prerequisites, and review the setup guide.\n')
        for warning in self.settings_warnings:
            self._append('Preferences: ' + warning + '\n')

    def _build_ui(self):
        self.configure(background='#f2f4f7')
        style = ttk.Style(self)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='HookLinkWindows', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Create an iOS app from your own Ocarina of Time .nup file.', foreground='#555').pack(anchor='w', pady=(2, 12))
        form = ttk.LabelFrame(outer, text='Build configuration', padding=12)
        form.pack(fill='x')
        self._field(form, 0, 'Game .nup file', self.input_var, self._browse_input)
        self._field(form, 1, 'Build directory', self.work_var, self._browse_work)
        self._field(form, 2, 'iOS runtime settings', self.env_var, self._browse_env)
        self._field(form, 3, 'Output IPA', self.output_var, self._browse_output)
        packaging = ttk.Frame(form)
        packaging.grid(row=4, column=1, columnspan=2, sticky='w', pady=(7, 1))
        ttk.Label(packaging, text='IPA packaging:').pack(side='left', padx=(0, 8))
        ttk.Radiobutton(packaging, text='App-only (recommended)', value=PACKAGE_APP_ONLY, variable=self.package_mode).pack(side='left')
        ttk.Radiobutton(packaging, text='Full (includes game data)', value=PACKAGE_FULL, variable=self.package_mode).pack(side='left', padx=(16, 0))
        row = ttk.Frame(form)
        row.grid(row=5, column=1, columnspan=2, sticky='w', pady=(7, 1))
        ttk.Label(row, text='Shader split workers (1–61):').pack(side='left')
        ttk.Spinbox(row, from_=1, to=61, width=5, textvariable=self.workers_var).pack(side='left', padx=(8, 20))
        ttk.Checkbutton(row, text='Request increased memory entitlement', variable=self.entitlements).pack(side='left')
        checkrow = ttk.Frame(form)
        checkrow.grid(row=6, column=1, columnspan=2, sticky='w', pady=(4, 1))
        ttk.Label(checkrow, text='Compatibility options:').pack(side='left', padx=(0, 8))
        ttk.Checkbutton(checkrow, text='Allow damaged assets', variable=self.allow_damaged).pack(side='left')
        ttk.Checkbutton(checkrow, text='Allow alternate Metal version', variable=self.allow_metal).pack(side='left', padx=16)
        self.advanced_btn = ttk.Button(form, text='Advanced settings  ▸', command=self._toggle_advanced)
        self.advanced_btn.grid(row=7, column=0, columnspan=3, sticky='w', pady=(9, 0))
        self.advanced_box = ttk.Frame(form)
        self.advanced_box.columnconfigure(1, weight=1)
        self._field(self.advanced_box, 0, 'iOS Bundle ID', self.bundle_var)
        ttk.Label(self.advanced_box, text='Default: PhoenixNetwork.HookLinkWindows. Changing this may create a separate app install.', foreground='#555').grid(row=1, column=0, columnspan=3, sticky='w', pady=(0, 4))
        self.advanced_visible = False
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=10)
        self.doctor_btn = ttk.Button(actions, text='Check prerequisites', command=self._doctor)
        self.preview_btn = ttk.Button(actions, text='Preview command', command=self._preview)
        self.build_btn = ttk.Button(actions, text='Build IPA', command=self._start_build)
        self.stop_btn = ttk.Button(actions, text='Stop', command=self._stop, state='disabled')
        self.guide_btn = ttk.Button(actions, text='Setup guide', command=self._open_setup_guide)
        for b in (self.doctor_btn, self.guide_btn, self.preview_btn, self.build_btn, self.stop_btn):
            b.pack(side='left', padx=(0, 8))

        ttk.Label(outer, textvariable=self.state_var, foreground='#163f75', wraplength=920).pack(fill='x', pady=(2, 7))
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 10))
        ttk.Label(outer, text='Build output and diagnostics', font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        logs = ttk.Frame(outer)
        logs.pack(fill='both', expand=True, pady=(5, 0))
        self.log = tk.Text(logs, wrap='word', height=12, font=('Consolas', 9), bg='#101720', fg='#e0e9f1', insertbackground='white')
        sc = ttk.Scrollbar(logs, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=sc.set)
        sc.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        footer = ttk.Frame(outer)
        footer.pack(fill='x', pady=(8, 0))
        ttk.Label(footer, text='Build locally from your own game files. App-only mode prepares a transfer folder.', foreground='#555').pack(side='left')
        ttk.Button(footer, text='Open work folder', command=self._open_work).pack(side='right')

    def _toggle_advanced(self):
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_box.grid(row=8, column=0, columnspan=3, sticky='ew', pady=(3, 0))
            self.advanced_btn.configure(text='Advanced settings  ▾')
        else:
            self.advanced_box.grid_remove()
            self.advanced_btn.configure(text='Advanced settings  ▸')

    def _field(self, parent, row, label, value, browse=None):
        ttk.Label(parent, text=label, width=23).grid(row=row, column=0, sticky='w', pady=4)
        entry = ttk.Entry(parent, textvariable=value)
        entry.grid(row=row, column=1, sticky='ew', padx=(5, 8), pady=4)
        if browse:
            ttk.Button(parent, text='Browse…', command=browse, width=12).grid(row=row, column=2, sticky='e', pady=4)
        if value is self.input_var:
            value.trace_add('write', lambda *_: self._input_changed())

    def _input_changed(self):
        selected = self.input_var.get().strip()
        if selected and Path(selected).suffix.lower() == '.nup':
            self.state_var.set('NUP file selected — review settings, then check prerequisites.')

    def _browse_input(self):
        f = filedialog.askopenfilename(title='Choose game .nup file', initialdir=str(HOME / 'Downloads'), filetypes=[('NUP game files', '*.nup')])
        if f:
            self.input_var.set(f)

    def _browse_work(self):
        f = filedialog.askdirectory(title='Select build work folder', initialdir=self.work_var.get())
        if f:
            self.work_var.set(f)

    def _browse_env(self):
        f = filedialog.askopenfilename(title='Choose runtime settings file', filetypes=[('Environment files', '*.txt *.env'), ('All files', '*.*')])
        if f:
            self.env_var.set(f)

    def _browse_output(self):
        f = filedialog.asksaveasfilename(title='IPA output', defaultextension='.ipa', filetypes=[('IPA', '*.ipa')], initialfile=Path(self.output_var.get()).name)
        if f:
            self.output_auto = False
            self.output_var.set(f)

    def _work_changed(self, *_):
        if self.output_auto:
            self._updating_output = True
            try:
                self.output_var.set(str(Path(self.work_var.get()) / default_output_name(self.package_mode.get())))
            finally:
                self._updating_output = False

    def _mode_changed(self, *_):
        if self.output_auto:
            self._updating_output = True
            try:
                self.output_var.set(str(Path(self.work_var.get()) / default_output_name(self.package_mode.get())))
            finally:
                self._updating_output = False
        self.state_var.set('App-only: builds and exports a smaller IPA plus an iPhone transfer folder.'
                           if self.package_mode.get() == PACKAGE_APP_ONLY else
                           'Full: builds one large IPA containing game resources.')

    def _output_edited(self, *_):
        if not self._updating_output:
            self.output_auto = False

    def _save_settings(self):
        try:
            workers = int(self.workers_var.get())
        except (ValueError, TypeError):
            workers = min(61, max(1, os.cpu_count() or 4))
        self.store.save({
            'input_path': self.input_var.get().strip(),
            'work_dir': self.work_var.get().strip(),
            'env_file': self.env_var.get().strip(),
            'output_ipa': self.output_var.get().strip(),
            'bundle_id': self.bundle_var.get().strip(),
            'workers': workers,
            'allow_damaged': self.allow_damaged.get(),
            'allow_metal': self.allow_metal.get(),
            'entitlements': self.entitlements.get(),
            'output_auto': self.output_auto,
            'package_mode': self.package_mode.get(),
        })

    def _on_close(self):
        if self.busy:
            messagebox.showinfo('Operation in progress', 'Finish or stop the active operation before closing the window.')
            return
        try:
            self._save_settings()
        except (OSError, ValueError) as exc:
            if not messagebox.askyesno('Could not save preferences', f'{exc}\n\nClose without saving?'):
                return
        self.destroy()

    def _config(self) -> BuildConfig:
        try:
            n = int(self.workers_var.get())
        except ValueError as exc:
            raise ValueError('Shader worker count is not a number') from exc
        return BuildConfig(root=locate_engine_root(ROOT), input_path=Path(self.input_var.get().strip()),
                           work_dir=Path(self.work_var.get().strip()), env_file=Path(self.env_var.get().strip()),
                           output_ipa=Path(self.output_var.get().strip()), bundle_id=self.bundle_var.get().strip(),
                           workers=n, allow_damaged=self.allow_damaged.get(),
                           allow_other_metal=self.allow_metal.get(), entitlements=self.entitlements.get())

    def _safe_config(self) -> BuildConfig | None:
        try:
            c = self._config()
            verify_build_config(c)
            return c
        except Exception as ex:
            messagebox.showerror('Invalid configuration', str(ex))
            return None

    def _append(self, text: str):
        self.log.insert('end', str(text))
        self.log.see('end')

    def _preview(self):
        c = self._safe_config()
        if c is None:
            return
        warnings = check_runtime_config(c.env_file)
        self._append('\n=== Planned build command ===\n')
        try:
            plan = make_build_plan(c, self.package_mode.get(), token='PREVIEW', python=build_python())
        except ValueError as exc:
            messagebox.showerror('Python required', str(exc))
            return
        self._append(subprocess.list2cmdline(plan.command) + '\n')
        self._append(f'Environment: J={c.workers}; DMSH_PROCS=0\n')
        if plan.mode == PACKAGE_APP_ONLY:
            self._append(f'After build: export app-only IPA to {plan.final_ipa}\n')
            self._append(f'Prepare iPhone transfer folder based on {plan.transfer_dir}\n')
            self._append('The temporary full IPA is removed after verified app-only export and transfer preparation.\n')
        else:
            self._append('Packaging: full IPA (large game resources included).\n')
        if warnings:
            self._append('Runtime warnings:\n' + '\n'.join(' - ' + x for x in warnings) + '\n')
        else:
            self._append('Runtime settings match the included compatibility preset.\n')

    def _set_busy(self, busy: bool):
        self.busy = busy
        for b in (self.doctor_btn, self.preview_btn, self.build_btn):
            b.configure(state='disabled' if busy else 'normal')
        self.stop_btn.configure(state='normal' if busy else 'disabled')
        if busy:
            self.progress.start(20)
        else:
            self.progress.stop()

    def _open_setup_guide(self):
        guide = ROOT / 'docs' / 'GETTING_STARTED.md'
        if not guide.is_file():
            messagebox.showerror('Setup guide missing', f'Expected documentation at: {guide}')
            return
        try:
            content = guide.read_text(encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('Cannot read setup guide', str(exc))
            return
        window = tk.Toplevel(self)
        window.title('HookLinkWindows — First-time setup guide')
        window.geometry('870x680')
        window.minsize(600, 420)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='First-time setup and prerequisites', font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(0, 6))
        ttk.Label(frame, text='Built-in guide (read-only). The full Markdown file is also in docs/GETTING_STARTED.md.', foreground='#555').pack(anchor='w', pady=(0, 8))
        area = ttk.Frame(frame)
        area.pack(fill='both', expand=True)
        scrollbar = ttk.Scrollbar(area)
        scrollbar.pack(side='right', fill='y')
        viewer = tk.Text(area, wrap='word', font=('Consolas', 10), yscrollcommand=scrollbar.set, padx=8, pady=8)
        viewer.insert('1.0', content)
        viewer.configure(state='disabled')
        scrollbar.configure(command=viewer.yview)
        viewer.pack(side='left', fill='both', expand=True)
        ttk.Button(frame, text='Close', command=window.destroy).pack(anchor='e', pady=(10, 0))

    def _doctor(self):
        if self.busy:
            return
        preflight = check_project_installation(ROOT)
        self._append('\n=== Prerequisite check: project layout ===\n' + preflight.summary() + '\n')
        if not preflight.ready_for_doctor:
            self.state_var.set(f'Repository incomplete: {len(preflight.blockers)} required file(s) missing. Use the complete source checkout; see diagnostics for the fix.')
            return
        try:
            interpreter = build_python()
        except ValueError as exc:
            self._append('[BLOCKED] ' + str(exc) + '\n')
            self.state_var.set('Python 3 required; see setup guide.')
            return
        self._set_busy(True)
        self.state_var.set('Checking Python, LLVM, .NET, Apple Metal, SDK and tools…')
        def worker():
            try:
                report = run_prerequisite_check(locate_engine_root(ROOT), interpreter)
                self.messages.put(('prereqs', report))
            except Exception:
                self.messages.put(('error', traceback.format_exc()))
        self.task_thread = threading.Thread(target=worker, daemon=True)
        self.task_thread.start()

    def _start_build(self):
        if self.busy:
            return
        preflight = check_project_installation(ROOT)
        if not preflight.ready_for_doctor:
            self._append('\n=== Prerequisite check: project layout ===\n' + preflight.summary() + '\n')
            messagebox.showerror('Incomplete checkout', 'Required build files are missing from this folder. Download or clone the complete HookLinkWindows source checkout, copy the GUI update into its root, and launch the EXE there. See diagnostics for missing paths.')
            return
        c = self._safe_config()
        if c is None:
            return
        warnings = check_runtime_config(c.env_file)
        mode = self.package_mode.get()
        try:
            plan = make_build_plan(c, mode, token=uuid.uuid4().hex[:12], python=build_python())
        except ValueError as exc:
            messagebox.showerror('Python required', str(exc))
            return
        msg = ('Start the HookLinkWindows build?\n\n'
               'The build can use significant CPU time and disk space. It may reuse or update files in the selected build directory.\n\n')
        if mode == PACKAGE_APP_ONLY:
            msg += 'App-only mode temporarily creates a large full IPA, then exports the smaller IPA and prepares separate iPhone files. The temporary IPA is deleted only after success.\n\n'
        if c.output_ipa.is_file():
            msg += f'Existing output IPA may be replaced: {c.output_ipa}\n\n'
        if warnings:
            msg += 'Configuration advisory:\n' + '\n'.join(warnings[:5]) + '\n\n'
        if c.allow_damaged or c.allow_other_metal:
            msg += 'Compatibility overrides are enabled; these bypass normal validation.\n\n'
        if not messagebox.askyesno('Confirm build', msg + 'Proceed?'):
            return
        c.work_dir.mkdir(parents=True, exist_ok=True)
        c.output_ipa.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._save_settings()
        except OSError as exc:
            self._append(f'Preferences not saved: {exc}\n')
        self._pending_package = (c, plan) if mode == PACKAGE_APP_ONLY else None
        plan.builder_ipa.parent.mkdir(parents=True, exist_ok=True)
        self._spawn(plan.command, c.root, make_build_environment(c), 'IPA compilation')

    def _spawn(self, cmd: list[str], cwd: Path, env: dict, title: str):
        self._set_busy(True)
        self.state_var.set(title + ' running…')
        self._append(f'\n=== {title} ===\n' + subprocess.list2cmdline(cmd) + '\n')
        def worker():
            try:
                kwargs = {'cwd': str(cwd), 'env': env, 'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT,
                          'text': True, 'errors': 'replace', 'bufsize': 1}
                if os.name == 'nt':
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                self.proc = subprocess.Popen(cmd, **kwargs)
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    self.messages.put(('text', line))
                exit_code = self.proc.wait()
                self.messages.put(('done', (title, exit_code)))
            except Exception:
                self.messages.put(('error', traceback.format_exc()))
            finally:
                self.proc = None
        self.task_thread = threading.Thread(target=worker, daemon=True)
        self.task_thread.start()

    def _post_build_export(self, c: BuildConfig, plan):
        self.state_var.set('Preparing app-only IPA and iPhone transfer files…')
        self._append(f'\n=== App-only packaging ===\nFull build: {plan.builder_ipa}\nFinal IPA: {plan.final_ipa}\n')
        def worker():
            try:
                chain = shader_chain_from_ipa(plan.builder_ipa)
                # Validate all three external files BEFORE creating an app-only IPA.
                find_transfer_sources(c.work_dir, c.env_file, chain)
                report = export_app_only_ipa(plan.builder_ipa, plan.final_ipa,
                                             lambda m: self.messages.put(('text', m + '\n')))
                folder = prepare_transfer_folder(c.work_dir, c.env_file, plan.transfer_dir, chain,
                                                 lambda m: self.messages.put(('text', m + '\n')))
                self.messages.put(('text', f"App-only IPA: {plan.final_ipa} ({report['size']/1024/1024:.1f} MiB)\n"
                                           f"iPhone files: {folder}\n"))
                plan.builder_ipa.unlink()
                try:
                    plan.builder_ipa.parent.rmdir()
                except OSError:
                    pass
                self.messages.put(('done', ('Build and app-only packaging', 0)))
            except Exception:
                self.messages.put(('text', 'App-only packaging failed. Full intermediate preserved for recovery: ' + str(plan.builder_ipa) + '\n'))
                self.messages.put(('error', traceback.format_exc()))
        self.task_thread = threading.Thread(target=worker, daemon=True)
        self.task_thread.start()

    def _stop(self):
        if not self.busy:
            return
        if self.proc is None:
            messagebox.showinfo('Operation', 'Packaging cannot be interrupted safely through the GUI.')
            return
        if messagebox.askyesno('Stop build?', 'Terminate the top-level builder? Child processes may require manual cleanup. Intermediate files may remain.'):
            self.proc.terminate()
            self._append('Stop requested for top-level builder.\n')

    def _drain(self):
        try:
            while True:
                typ, payload = self.messages.get_nowait()
                if typ == 'text':
                    self._append(str(payload))
                elif typ == 'prereqs':
                    self._append('\n' + payload.format() + '\n')
                    self._set_busy(False)
                    self.state_var.set('Prerequisites passed (build unverified).' if payload.ready else 'Prerequisites need attention; see diagnostics and Setup guide.')
                elif typ == 'done':
                    title, exit_code = payload
                    if title == 'IPA compilation' and exit_code == 0 and self._pending_package is not None:
                        c, plan = self._pending_package
                        self._pending_package = None
                        self._post_build_export(c, plan)
                        continue
                    self._pending_package = None
                    self._set_busy(False)
                    self.state_var.set(f'{title}: ' + ('completed' if exit_code == 0 else f'failed (exit code {exit_code})'))
                    self._append(f'=== Exit code: {exit_code} ===\n')
                    if exit_code == 0 and title == 'Build and app-only packaging':
                        messagebox.showinfo('App-only IPA created', 'Build complete. The app-only IPA and its iPhone transfer folder are ready. See the build log for their locations.')
                elif typ == 'error':
                    self._set_busy(False)
                    self.state_var.set('Operation failed — inspect log')
                    self._append('ERROR:\n' + str(payload) + '\n')
                    messagebox.showerror('Operation failed', 'An error occurred. See the GUI log for details.')
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _open_work(self):
        path = Path(self.work_var.get())
        if path.exists():
            if os.name == 'nt':
                os.startfile(str(path))
            else:
                messagebox.showinfo('Build folder', str(path))
        else:
            messagebox.showwarning('Missing folder', f'Folder does not yet exist:\n{path}')


if __name__ == '__main__':
    try:
        App().mainloop()
    except Exception:
        messagebox.showerror('HookLinkWindows failed to launch', traceback.format_exc())
        raise

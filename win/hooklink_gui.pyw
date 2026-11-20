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
import webbrowser

from hooklink_gui_core import (BuildConfig, PACKAGE_APP_ONLY, PACKAGE_FULL,
                               check_runtime_config, default_output_name,
                               export_app_only_ipa, find_transfer_sources,
                               make_build_environment, make_build_plan,
                               prepare_transfer_folder, shader_chain_from_ipa, verify_native_split_ipa,
                               verified_shader_chain_from_ipa, read_host_shader_chain, oot_runtime_errors,
                               verify_build_config)
from hooklink_portable import (SettingsStore, check_project_installation, locate_engine_root,
                               DEFAULT_IPA_NAME, DEFAULT_WORK_NAME, native_display_path)
from hooklink_prereqs import can_auto_prepare_translator, run_prerequisite_check
from shader_chain_flow import run_build_chain_preflight
from hooklink_progress import parse_build_progress
from auto_workers import logical_workers
from hooklink_toolchain_setup import configured_ios_sdk, save_ios_sdk
from hooklink_sdk_import import validate_xip_archive
from hooklink_dependency_manager import XCODE_XIP_DOWNLOAD_URL, dependency_statuses, missing_python_packages
from hooklink_engine_pin import read_engine_pin
from hooklink_iphone_logs import summarize_iphone_log
from hooklink_clean_build import new_clean_test_work_dir

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
DEFAULT_WORK = ROOT.parent / DEFAULT_WORK_NAME
DEFAULT_ENV = ROOT / 'config' / 'iphone-oot.env'
GUI_VERSION = 'Alpha V1.2.1'
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
        self.auto_workers_var = tk.BooleanVar(value=prefs.get('auto_workers', True))
        self.workers_var = tk.StringVar(value=str(logical_workers() if self.auto_workers_var.get() else prefs.get('workers', logical_workers())))
        self.allow_damaged = tk.BooleanVar(value=prefs.get('allow_damaged', True))
        self.allow_metal = tk.BooleanVar(value=prefs.get('allow_metal', True))
        self.entitlements = tk.BooleanVar(value=prefs.get('entitlements', True))
        self.reuse_var = tk.StringVar(value=prefs.get('reuse_shader_work', ''))
        self.native_var = tk.BooleanVar(value=prefs.get('native_app_only', False))
        self.state_var = tk.StringVar(value='Select a .nup file, then check prerequisites and build settings.')
        self.progress_var = tk.StringVar(value='')
        self._last_progress_stage = None
        self._last_progress_percent = None
        self._pending_package = None
        self._pending_build = None
        self._verified_shader_reuse = False
        self._auto_translator_attempted = False
        self._dependency_report = None
        self._deps_window = None
        self._deps_rows_frame = None
        self._deps_pip_button = None
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
        ttk.Label(outer, text='Create an iOS app from your own Ocarina of Time .nup file.', foreground='#555').pack(anchor='w', pady=(2, 5))
        self.engine_pin = read_engine_pin(ROOT)
        pin_row = ttk.Frame(outer)
        pin_row.pack(fill='x', pady=(0, 9))
        ttk.Label(pin_row, text='NXNative upstream base (pinned):', foreground='#555').pack(side='left', padx=(0, 8))
        self.upstream_sha_var = tk.StringVar(value=self.engine_pin.display)
        ttk.Entry(pin_row, textvariable=self.upstream_sha_var, width=45, state='readonly').pack(side='left', padx=(0, 8))
        upstream_button = ttk.Button(
            pin_row, text='View commit',
            command=lambda: webbrowser.open_new_tab(self.engine_pin.url) if self.engine_pin.url else None)
        upstream_button.pack(side='left', padx=(0, 8))
        if not self.engine_pin.url:
            upstream_button.configure(state='disabled')
        ttk.Label(pin_row, text='Windows engine modified', foreground='#555').pack(side='left')
        form = ttk.LabelFrame(outer, text='Build configuration', padding=12)
        form.pack(fill='x')
        self._field(form, 0, 'Game .nup file', self.input_var, self._browse_input)
        self._field(form, 1, 'Build directory', self.work_var, self._browse_work)
        ttk.Button(form, text='New clean…', command=self._new_clean_build, width=13).grid(row=1, column=3, sticky='w', pady=4)
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
        self.worker_spin = ttk.Spinbox(row, from_=1, to=61, width=5, textvariable=self.workers_var)
        self.worker_spin.pack(side='left', padx=(8, 8))
        ttk.Checkbutton(row, text='Auto (2x logical CPUs, max 61)', variable=self.auto_workers_var, command=self._update_auto_workers).pack(side='left', padx=(0, 16))
        self._update_auto_workers()
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
        self._field(self.advanced_box, 2, 'Previous shader work', self.reuse_var, self._browse_reuse)
        ttk.Label(self.advanced_box, text='Optional: reuse only after exact shader-package and library verification; never alters the previous build.', foreground='#555').grid(row=3, column=0, columnspan=3, sticky='w', pady=(0, 4))
        ttk.Checkbutton(self.advanced_box, text='Experimental native app-only packaging (avoids temporary full IPA)', variable=self.native_var).grid(row=4, column=0, columnspan=3, sticky='w', pady=(0, 4))
        self.advanced_visible = False
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=10)
        self.doctor_btn = ttk.Button(actions, text='Check prerequisites', command=self._doctor)
        self.preview_btn = ttk.Button(actions, text='Preview command', command=self._preview)
        self.build_btn = ttk.Button(actions, text='Build IPA', command=self._start_build)
        self.stop_btn = ttk.Button(actions, text='Stop', command=self._stop, state='disabled')
        self.guide_btn = ttk.Button(actions, text='Setup guide', command=self._open_setup_guide)
        self.device_log_btn = ttk.Button(actions, text='iPhone log…', command=self._analyze_iphone_log)
        self.toolchain_btn = ttk.Button(actions, text='Toolchain setup…', command=self._open_toolchain_setup)
        for b in (self.doctor_btn, self.toolchain_btn, self.guide_btn, self.device_log_btn, self.preview_btn, self.build_btn, self.stop_btn):
            b.pack(side='left', padx=(0, 8))

        ttk.Label(outer, textvariable=self.state_var, foreground='#163f75', wraplength=920).pack(fill='x', pady=(2, 4))
        ttk.Label(outer, textvariable=self.progress_var, foreground='#385a70', wraplength=920).pack(fill='x', pady=(0, 5))
        self.progress = ttk.Progressbar(outer, mode='indeterminate', maximum=100)
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
        f = filedialog.askopenfilename(title='Choose game .nup file', initialdir=str(Path(self.input_var.get()).parent if Path(self.input_var.get()).is_file() else ROOT.parent), filetypes=[('NUP game files', '*.nup')])
        if f:
            self.input_var.set(native_display_path(f))

    def _browse_work(self):
        f = filedialog.askdirectory(title='Select build work folder', initialdir=self.work_var.get())
        if f:
            self.work_var.set(native_display_path(f))

    def _new_clean_build(self):
        """Select a new empty work directory; never reuse previous shader files."""
        if self.busy:
            messagebox.showwarning('Build in progress', 'Stop or finish the current build before changing work directories.')
            return
        try:
            folder = new_clean_test_work_dir(Path(self.work_var.get().strip()))
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot create clean build directory', str(exc))
            return
        self.reuse_var.set('')
        self.output_auto = True
        self.work_var.set(native_display_path(folder))
        self.state_var.set('Fresh build directory selected — no shader or output reuse.')
        self._append(f'\n[CLEAN TEST] New empty work folder: {folder}\n')
        self._append('[CLEAN TEST] Existing build folders untouched; external shader reuse cleared.\n')
        self._save_settings()

    def _browse_env(self):
        f = filedialog.askopenfilename(title='Choose runtime settings file', filetypes=[('Environment files', '*.txt *.env'), ('All files', '*.*')], initialdir=str(DEFAULT_ENV.parent))
        if f:
            self.env_var.set(native_display_path(f))

    def _browse_output(self):
        f = filedialog.asksaveasfilename(title='IPA output', defaultextension='.ipa', filetypes=[('IPA', '*.ipa')], initialfile=Path(self.output_var.get()).name, initialdir=str(Path(self.output_var.get()).parent))
        if f:
            self.output_auto = False
            self.output_var.set(native_display_path(f))

    def _work_changed(self, *_):
        if self.output_auto:
            self._updating_output = True
            try:
                self.output_var.set(str(Path(self.work_var.get()) / default_output_name(self.package_mode.get())))
            finally:
                self._updating_output = False

    def _update_auto_workers(self):
        if self.auto_workers_var.get():
            self.workers_var.set(str(logical_workers()))
            self.worker_spin.configure(state='disabled')
        else:
            self.worker_spin.configure(state='normal')

    def _browse_reuse(self):
        folder = filedialog.askdirectory(title='Select an existing completed shader build directory', initialdir=self.reuse_var.get() or str(ROOT.parent))
        if folder: self.reuse_var.set(native_display_path(folder))

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
            workers = logical_workers()
        self.store.save({
            'input_path': self.input_var.get().strip(),
            'work_dir': self.work_var.get().strip(),
            'env_file': self.env_var.get().strip(),
            'output_ipa': self.output_var.get().strip(),
            'bundle_id': self.bundle_var.get().strip(),
            'workers': workers,
            'auto_workers': self.auto_workers_var.get(),
            'allow_damaged': self.allow_damaged.get(),
            'allow_metal': self.allow_metal.get(),
            'entitlements': self.entitlements.get(),
            'output_auto': self.output_auto,
            'package_mode': self.package_mode.get(),
            'reuse_shader_work': self.reuse_var.get().strip(),
            'native_app_only': self.native_var.get(),
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
            n = logical_workers() if self.auto_workers_var.get() else int(self.workers_var.get())
        except ValueError as exc:
            raise ValueError('Shader worker count is not a number') from exc
        return BuildConfig(root=locate_engine_root(ROOT), input_path=Path(self.input_var.get().strip()),
                           work_dir=Path(self.work_var.get().strip()), env_file=Path(self.env_var.get().strip()),
                           output_ipa=Path(self.output_var.get().strip()), bundle_id=self.bundle_var.get().strip(),
                           workers=n, allow_damaged=self.allow_damaged.get(),
                           allow_other_metal=self.allow_metal.get(), entitlements=self.entitlements.get(),
                           reuse_shader_work=Path(self.reuse_var.get().strip()) if self.reuse_var.get().strip() else None,
                           native_app_only=self.native_var.get())

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
        self._append(f'Environment: J={c.workers}; DMSH_PROCS=0; Windows rewrite x18 processes: up to 8 per module\n')
        if c.reuse_shader_work is not None:
            self._append(f'Reuse source (read-only; fail on mismatch): {c.reuse_shader_work}\n')
        self._append('Before compilation: validate shader-chain lock/header; synchronize locally with backups only if mismatched.\n')
        if plan.native_split:
            self._append('Native split-data: IPA and three-file transfer directory are created directly; no full intermediate IPA.\n')
        elif plan.mode == PACKAGE_APP_ONLY:
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
        for b in (self.doctor_btn, self.toolchain_btn, self.preview_btn, self.build_btn):
            b.configure(state='disabled' if busy else 'normal')
        self.stop_btn.configure(state='normal' if busy else 'disabled')
        if busy:
            self._last_progress_stage = None
            self._last_progress_percent = None
            self.progress.stop()
            self.progress.configure(mode='indeterminate', value=0)
            self.progress_var.set('Working — this step has not reported measurable progress yet')
            self.progress.start(20)
        else:
            self.progress.stop()

    def _update_progress_from_log(self, text: str):
        """Show measured progress within the CURRENT stage (never a guessed overall %)."""
        for line in text.splitlines():
            report = parse_build_progress(line)
            if report is None:
                continue
            stage_key = (report.stage, report.stages)
            changed = stage_key != self._last_progress_stage
            if changed:
                self._last_progress_stage = stage_key
                self._last_progress_percent = None
            if report.percent is not None:
                self._last_progress_percent = report.percent
                self.progress.stop()
                self.progress.configure(mode='determinate', maximum=100, value=report.percent)
            elif changed:
                self.progress.stop()
                self.progress.configure(mode='indeterminate', value=0)
                self.progress.start(20)
            self.state_var.set(f'Stage {report.stage} of {report.stages} — {report.label}')
            details = []
            if self._last_progress_percent is not None:
                details.append(f'{self._last_progress_percent:.1f}% of this stage')
            else:
                details.append('stage percentage not reported')
            if report.count:
                details.append(report.count)
            if report.eta:
                details.append(f'ETA {report.eta} (estimate)')
            self.progress_var.set('  ·  '.join(details))

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

    def _open_toolchain_setup(self):
        """Display a first-run dependency manager with vendor downloads and live statuses."""
        if self._deps_window is not None and self._deps_window.winfo_exists():
            self._deps_window.lift()
            self._render_dependency_rows()
            return
        window = tk.Toplevel(self)
        self._deps_window = window
        window.title('HookLinkWindows — Windows dependency manager')
        window.geometry('1050x810')
        window.minsize(800, 580)
        window.transient(self)
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Set up Windows build tools', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Install missing tools using their official download pages. Return here and choose Check again. Downloads and installers are never run without your action.', wraplength=980).pack(anchor='w', pady=(6, 10))
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill='x', pady=(0, 8))
        ttk.Button(toolbar, text='Check again', command=self._doctor).pack(side='left', padx=(0, 8))
        ttk.Label(toolbar, text='Results come from Check prerequisites; Not checked does not mean Missing.', foreground='#555').pack(side='left')
        listing = ttk.LabelFrame(frame, text='Required and optional dependencies', padding=(6, 5))
        listing.pack(fill='both', expand=True)
        canvas = tk.Canvas(listing, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(listing, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        rows = ttk.Frame(canvas)
        self._deps_rows_frame = rows
        inner_id = canvas.create_window((0, 0), window=rows, anchor='nw')
        rows.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(inner_id, width=e.width))
        self._render_dependency_rows()
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=(8, 4))
        self._deps_pip_button = ttk.Button(actions, text='Install missing Python packages', command=self._install_python_packages)
        self._deps_pip_button.pack(side='left')
        ttk.Label(actions, text='Uses the selected Python interpreter and public PyPI; confirmation required.', foreground='#555').pack(side='left', padx=8)
        self._render_dependency_rows()
        sdk_frame = ttk.LabelFrame(frame, text='iPhoneOS SDK (not bundled)', padding=9)
        sdk_frame.pack(fill='x', pady=(8, 5))
        ttk.Label(sdk_frame, text='Apple does not provide a Windows SDK installer. Import an archive you obtained yourself from Apple, or select an existing SDK folder. Review Apple licensing restrictions before use on non-Apple hardware.', wraplength=960, foreground='#555').pack(anchor='w', pady=(0, 6))
        try:
            current_sdk = configured_ios_sdk(ROOT)
        except ValueError as exc:
            messagebox.showerror('Toolchain settings error', str(exc), parent=window)
            current_sdk = ''
        sdk_var = tk.StringVar(value=current_sdk)
        sdk_row = ttk.Frame(sdk_frame)
        sdk_row.pack(fill='x')
        ttk.Label(sdk_row, text='Existing iPhoneOS 26+ SDK:').pack(side='left', padx=(0, 8))
        ttk.Entry(sdk_row, textvariable=sdk_var).pack(side='left', fill='x', expand=True, padx=(0, 6))

        def browse_sdk():
            initial = sdk_var.get()
            folder = filedialog.askdirectory(parent=window, title='Select the iPhoneOS.sdk directory',
                                             initialdir=initial if Path(initial).is_dir() else str(ROOT.parent))
            if folder:
                sdk_var.set(folder)

        def save_sdk():
            try:
                sdk = save_ios_sdk(ROOT, sdk_var.get())
            except (ValueError, OSError) as exc:
                messagebox.showerror('Invalid SDK directory', str(exc), parent=window)
                return
            self._append(f'[SETUP] Validated iPhoneOS SDK saved: {sdk}\n')
            if os.environ.get('NXW_IOS_SDK'):
                messagebox.showwarning('SDK environment override', 'NXW_IOS_SDK takes precedence over the saved directory.', parent=window)
            self._doctor()

        ttk.Button(sdk_row, text='Browse…', command=browse_sdk).pack(side='left', padx=(0, 5))
        ttk.Button(sdk_row, text='Save', command=save_sdk).pack(side='left')
        sdk_import_row = ttk.Frame(sdk_frame)
        sdk_import_row.pack(fill='x', pady=(8, 0))
        ttk.Button(sdk_import_row, text='Import SDK from Xcode .xip…', command=self._import_xcode_sdk).pack(side='left', padx=(0, 10))
        ttk.Button(sdk_import_row, text='Download .xip', command=lambda: webbrowser.open_new_tab(XCODE_XIP_DOWNLOAD_URL)).pack(side='left', padx=(0, 10))
        ttk.Button(sdk_import_row, text='Official Apple downloads', command=lambda: webbrowser.open_new_tab('https://developer.apple.com/download/all/')).pack(side='left')
        ttk.Label(sdk_frame, text='Download .xip opens Apple\'s Xcode 27.2 archive in your browser (Apple Developer sign-in may be required). If the direct link is unavailable, use Official Apple downloads. Then choose Import SDK from Xcode .xip… to extract and configure it.', wraplength=960, foreground='#555').pack(anchor='w', pady=(6, 0))
        ttk.Label(sdk_frame, text='Local import: reads your archive, extracts only the SDK, verifies version 26+, and saves its location. Allow several GB of free disk space; your archive is preserved.', wraplength=960, foreground='#555').pack(anchor='w', pady=(4, 0))
        graphics = ttk.Frame(frame)
        graphics.pack(fill='x', pady=(8, 0))
        ttk.Label(graphics, text='Graphics support is automatically prepared from bundled source when its tools are available.').pack(side='left')
        ttk.Button(graphics, text='Retry graphics setup', command=lambda: self._retry_graphics_setup(window)).pack(side='right')
        ttk.Button(frame, text='Close', command=window.destroy).pack(anchor='e', pady=(8, 0))

    def _import_xcode_sdk(self):
        """Import user-selected Xcode archive without a terminal or hidden downloads."""
        if self.busy:
            messagebox.showwarning('Operation in progress', 'Finish the current operation before importing an SDK.')
            return
        archive = filedialog.askopenfilename(
            parent=self._deps_window if self._deps_window is not None and self._deps_window.winfo_exists() else self,
            title='Choose your downloaded Xcode .xip archive',
            filetypes=[('Xcode XIP archives', '*.xip'), ('All files', '*.*')])
        if not archive:
            return
        try:
            checked = validate_xip_archive(Path(archive))
            interpreter = build_python()
        except (ValueError, OSError) as exc:
            messagebox.showerror('SDK import cannot start', str(exc))
            return
        if not messagebox.askyesno(
                'Import iPhoneOS SDK from archive?',
                'HookLinkWindows will extract only the iPhoneOS SDK from the selected Xcode archive and configure it automatically.\n\n'
                'Source: ' + str(checked) + '\n\n'
                'Apple SDK files are subject to Apple license restrictions, including restrictions on use on non-Apple-branded hardware. '
                'Confirm that you have the necessary rights before proceeding. This tool does not grant any license.\n\n'
                'Extraction requires substantial disk space and can take a while. The archive and existing SDKs will not be overwritten.\n\n'
                'Do you confirm that you are authorized to proceed?'):
            return
        self._append('[SDK] Beginning local import from the selected Xcode archive. No Apple files are downloaded or redistributed.\n')
        self._spawn([interpreter, '-u', '-B', str(ROOT / 'win' / 'hooklink_sdk_import.py'),
                     '--root', str(ROOT), '--archive', str(checked)],
                    ROOT, os.environ.copy(), 'iPhoneOS SDK import')

    def _render_dependency_rows(self):
        rows = self._deps_rows_frame
        if rows is None or not rows.winfo_exists():
            return
        for widget in rows.winfo_children():
            widget.destroy()
        rows.columnconfigure(0, weight=1)
        rows.columnconfigure(1, minsize=110)
        rows.columnconfigure(2, weight=2)
        rows.columnconfigure(3, minsize=105)
        for i, (dep, status, detail) in enumerate(dependency_statuses(self._dependency_report)):
            ttk.Label(rows, text=dep.label).grid(row=i, column=0, sticky='w', padx=(5, 8), pady=3)
            ttk.Label(rows, text=status).grid(row=i, column=1, sticky='w', padx=5, pady=3)
            ttk.Label(rows, text=detail, wraplength=365).grid(row=i, column=2, sticky='w', padx=5, pady=3)
            if dep.url:
                ttk.Button(rows, text='Download / info', command=lambda url=dep.url: webbrowser.open_new_tab(url)).grid(row=i, column=3, sticky='e', padx=5, pady=3)
            elif dep.key == 'shader translator DLLs':
                ttk.Label(rows, text='Automatic', foreground='#555').grid(row=i, column=3, sticky='e', padx=5, pady=3)
        if self._deps_pip_button is not None and self._deps_pip_button.winfo_exists():
            missing = missing_python_packages(self._dependency_report)
            self._deps_pip_button.configure(state='normal' if missing and not self.busy else 'disabled')

    def _install_python_packages(self):
        if self.busy:
            return
        packages = missing_python_packages(self._dependency_report)
        if not packages:
            messagebox.showinfo('Python packages', 'No required missing Python packages were detected. Click Check again if you recently installed Python.')
            return
        try:
            python = build_python()
        except ValueError as exc:
            messagebox.showerror('Python required', str(exc))
            return
        if not messagebox.askyesno('Install missing Python packages?',
                                   'Install the following packages from public PyPI into the active Python environment?\n\n'
                                   + ', '.join(packages)
                                   + '\n\nThis modifies that Python environment and may require network access. Nothing will be installed without this confirmation.'):
            return
        self._spawn([python, '-m', 'pip', '--disable-pip-version-check', '--no-input', 'install', *packages],
                    ROOT, os.environ.copy(), 'Python package setup')

    def _retry_graphics_setup(self, parent):
        if self.busy:
            messagebox.showwarning('Operation in progress', 'Finish the current operation first.', parent=parent)
            return
        if not messagebox.askyesno('Retry graphics setup?',
                                   'HookLinkWindows will prepare graphics support from bundled source. A new shader chain may require shader recompilation. Existing game files and shader archives will not be deleted, and chain metadata is backed up.\n\nContinue?',
                                   parent=parent):
            return
        self._start_graphics_setup(automatic=False)

    def _start_graphics_setup(self, *, automatic: bool):
        """Prepare local graphics support inside the GUI; never require shell commands."""
        if self.busy:
            return
        self._auto_translator_attempted = True
        try:
            interpreter = build_python()
        except ValueError as exc:
            self._append('[SETUP] Cannot prepare graphics support: ' + str(exc) + '\n')
            self.state_var.set('Graphics setup requires Python; see prerequisites.')
            return
        if automatic:
            self._append('[SETUP] Graphics support is missing; preparing it automatically. The existing game data and shader archives will be preserved.\n')
        else:
            self._append('[SETUP] Retrying graphics support setup from the GUI.\n')
        self._spawn([interpreter, '-B', str(ROOT / 'win' / 'bootstrap_translator.py'),
                     '--root', str(ROOT), '--install', '--accept-new-chain'],
                    ROOT, os.environ.copy(), 'Graphics support setup')

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
        runtime_errors = oot_runtime_errors(c.env_file)
        if runtime_errors:
            messagebox.showerror('Incompatible Ocarina of Time runtime settings',
                                 'Build blocked: this profile previously produced a black screen.\n\n' +
                                 '\n'.join(runtime_errors) +
                                 '\n\nSelect or update the tested config/iphone-oot.env preset.')
            self._append('[BLOCKED] OOT runtime settings:\n' + '\n'.join(runtime_errors) + '\n')
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
        if plan.native_split:
            msg += 'EXPERIMENTAL: Build app-only IPA and transfer files directly. This path is not yet proven by an end-to-end iPhone installation.\n\n'
        elif mode == PACKAGE_APP_ONLY:
            msg += 'App-only mode temporarily creates a large full IPA, then exports the smaller IPA and prepares separate iPhone files. The temporary IPA is deleted only after success.\n\n'
        if c.reuse_shader_work is not None:
            msg += f'EXTERNAL REUSE: {c.reuse_shader_work} is READ ONLY. The build will refuse to proceed if its shader package or library is incompatible.\n\n'
        if c.output_ipa.is_file():
            msg += f'Existing output IPA may be replaced: {c.output_ipa}\n\n'
        if plan.native_split and plan.transfer_dir.exists():
            msg += f'EXISTING transfer folder may be replaced after its data is checked: {plan.transfer_dir}\n\n'
        if warnings:
            msg += 'Configuration advisory:\n' + '\n'.join(warnings[:5]) + '\n\n'
        if c.allow_damaged or c.allow_other_metal:
            msg += 'Compatibility overrides are enabled; these bypass normal validation.\n\n'
        msg += 'Before compilation, shader-chain fingerprints will be checked. If needed, the local lock/header will be backed up and synchronized to the installed tools. Existing shader archives will not be deleted by this preflight.\n\n'
        if not messagebox.askyesno('Confirm build', msg + 'Proceed?'):
            return
        c.work_dir.mkdir(parents=True, exist_ok=True)
        c.output_ipa.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._save_settings()
        except OSError as exc:
            self._append(f'Preferences not saved: {exc}\n')
        self._pending_build = (c, plan)
        self._verified_shader_reuse = False
        self._set_busy(True)
        self.state_var.set('Checking local shader chain before IPA compilation…')
        self._append('\n=== Pre-build shader-chain validation ===\n')
        def worker():
            try:
                result = run_build_chain_preflight(ROOT, c.root, build_python(), make_build_environment(c))
                self.messages.put(('chain_ready', result))
            except Exception:
                self.messages.put(('error', traceback.format_exc()))
        self.task_thread = threading.Thread(target=worker, daemon=True)
        self.task_thread.start()

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
        self.progress.stop()
        self.progress.configure(mode='indeterminate', value=0)
        self.progress_var.set('Exporting app-only IPA — percentage not available')
        self.progress.start(20)
        self._append(f'\n=== App-only packaging ===\nFull build: {plan.builder_ipa}\nFinal IPA: {plan.final_ipa}\n')
        def worker():
            try:
                chain = verified_shader_chain_from_ipa(plan.builder_ipa, c.root / 'dm/gfx/nvn/dmsh_chain.h')
                # Donor is only allowed if the completed compiler explicitly confirmed
                # its exact CONTENT/toolchain/profile/pulling-policy/table equivalence.
                donor = c.reuse_shader_work if self._verified_shader_reuse else None
                find_transfer_sources(c.work_dir, c.env_file, chain,
                                      donor_shader_work=donor, donor_verified=self._verified_shader_reuse)
                report = export_app_only_ipa(plan.builder_ipa, plan.final_ipa,
                                             lambda m: self.messages.put(('text', m + '\n')))
                folder = prepare_transfer_folder(c.work_dir, c.env_file, plan.transfer_dir, chain,
                                                 lambda m: self.messages.put(('text', m + '\n')),
                                                 donor_shader_work=donor,
                                                 donor_verified=self._verified_shader_reuse)
                exported_errors = oot_runtime_errors(folder / 'env.txt')
                if exported_errors:
                    raise ValueError('Transfer folder has incompatible runtime settings: ' + ', '.join(exported_errors))
                verify_native_split_ipa(plan.final_ipa, folder, chain)
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
            messagebox.showinfo('Operation', 'Preflight or packaging is in progress. No IPA compiler is currently running.')
            return
        if messagebox.askyesno('Stop build?', 'Terminate the top-level builder? Child processes may require manual cleanup. Intermediate files may remain.'):
            self.proc.terminate()
            self._append('Stop requested for top-level builder.\n')

    def _drain(self):
        try:
            while True:
                typ, payload = self.messages.get_nowait()
                if typ == 'text':
                    if '[CACHE] Verified identical shader-package CONTENT' in str(payload):
                        self._verified_shader_reuse = True
                    self._update_progress_from_log(str(payload))
                    self._append(str(payload))
                elif typ == 'prereqs':
                    self._append('\n' + payload.format() + '\n')
                    self._dependency_report = payload
                    self._set_busy(False)
                    self._render_dependency_rows()
                    self.state_var.set('Prerequisites passed (build unverified).' if payload.ready else 'Prerequisites need attention; see diagnostics and Toolchain setup.')
                    if not self._auto_translator_attempted and can_auto_prepare_translator(payload):
                        self._start_graphics_setup(automatic=True)
                        continue
                    if not payload.ready:
                        missing_sdk = any('iPhoneOS SDK' in item['name'] and item['required'] and not item['ok']
                                          for item in payload.entries)
                        missing_graphics = any(item['name'] == 'shader translator DLLs' and item['required'] and not item['ok']
                                               for item in payload.entries)
                        if missing_sdk or missing_graphics:
                            detail = ('An iPhoneOS SDK is required. Open Toolchain setup to select an existing SDK folder.'
                                      if missing_sdk and not missing_graphics else
                                      'Graphics setup could not be completed automatically. Open Toolchain setup to retry or inspect the missing developer tools.'
                                      if missing_graphics and not missing_sdk else
                                      'An iPhoneOS SDK and graphics support are still missing. Open Toolchain setup for instructions or retry.')
                            if self._deps_window is None or not self._deps_window.winfo_exists():
                                if messagebox.askyesno('Build tools need setup', detail):
                                    self._open_toolchain_setup()
                elif typ == 'chain_ready':
                    self._append(payload.log)
                    if self._pending_build is None:
                        self._set_busy(False)
                        self._append('[BLOCKED] Build plan was lost before compilation.\n')
                        continue
                    c, plan = self._pending_build
                    self._pending_build = None
                    archive = c.work_dir / 'shader' / 'ios' / f'b-{payload.chain}.img'
                    if archive.is_file():
                        self._append(f'[CACHE] Matching shader archive exists: {archive}\n')
                    else:
                        self._append(f'[NOTE] No matching prebuilt shader archive at {archive}; shader compilation may be necessary.\n')
                    self._pending_package = (c, plan) if plan.mode == PACKAGE_APP_ONLY else None
                    plan.builder_ipa.parent.mkdir(parents=True, exist_ok=True)
                    self._spawn(plan.command, c.root, make_build_environment(c), 'IPA compilation')
                elif typ == 'done':
                    title, exit_code = payload
                    if title == 'IPA compilation' and exit_code == 0 and self._pending_package is not None:
                        c, plan = self._pending_package
                        self._pending_package = None
                        if plan.native_split:
                            try:
                                # Read the synchronized host header; the native IPA has no shader payload to inspect.
                                chain = read_host_shader_chain(c.root / 'dm/gfx/nvn/dmsh_chain.h')
                                verify_native_split_ipa(plan.final_ipa, plan.transfer_dir, chain)
                                errors = oot_runtime_errors(plan.transfer_dir / 'env.txt')
                                if errors:
                                    raise ValueError('Native output has incompatible runtime settings: ' + ', '.join(errors))
                                self._append(f'[VERIFIED] Native app-only IPA: {plan.final_ipa}\n[VERIFIED] iPhone files: {plan.transfer_dir}\n')
                                title = 'Build and native app-only packaging'
                            except Exception:
                                self._set_busy(False)
                                self._append('Native output verification FAILED. Do not sideload this result.\n' + traceback.format_exc() + '\n')
                                self.state_var.set('Native packaging failed verification')
                                continue
                        else:
                            self._post_build_export(c, plan)
                            continue
                    self._pending_package = None
                    self._set_busy(False)
                    self.state_var.set(f'{title}: ' + ('completed' if exit_code == 0 else f'failed (exit code {exit_code})'))
                    if exit_code == 0:
                        self.progress.configure(mode='determinate', maximum=100, value=100)
                        self.progress_var.set(f'{title} complete')
                    else:
                        self.progress.configure(mode='determinate', value=0)
                        self.progress_var.set('Build failed — inspect diagnostics')
                    self._append(f'=== Exit code: {exit_code} ===\n')
                    if title == 'iPhoneOS SDK import':
                        if exit_code == 0:
                            self._append('[SDK] SDK import completed; rechecking prerequisites.\n')
                            self._doctor()
                        else:
                            self._append('[SDK] Import failed or was interrupted. Existing SDK settings were not intentionally changed. Check diagnostics and retry through Toolchain setup.\n')
                    if title == 'Python package setup' and exit_code == 0:
                        self._append('[SETUP] Python packages installed; checking prerequisites again.\n')
                        self._doctor()
                    if title == 'Graphics support setup':
                        if exit_code == 0:
                            self._append('[SETUP] Graphics support is ready; checking prerequisites again.\n')
                            self._doctor()
                        else:
                            self._append('[SETUP] Graphics support could not be prepared. Check the diagnostics above; use Toolchain setup to retry after resolving missing tools.\n')
                    if exit_code == 0 and title in ('Build and app-only packaging', 'Build and native app-only packaging'):
                        messagebox.showinfo('App-only IPA created', 'Build complete. The app-only IPA and its iPhone transfer folder are ready. See the build log for their locations.')
                elif typ == 'error':
                    self._pending_build = None
                    self._pending_package = None
                    self._set_busy(False)
                    self.progress.configure(mode='determinate', value=0)
                    self.progress_var.set('Operation failed — inspect diagnostics')
                    self.state_var.set('Operation failed — inspect log')
                    self._append('ERROR:\n' + str(payload) + '\n')
                    messagebox.showerror('Operation failed', 'An error occurred. See the GUI log for details.')
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _analyze_iphone_log(self):
        """Inspect a game-session log downloaded from iPhone file sharing."""
        path = filedialog.askopenfilename(
            title='Open iPhone game log (log.prev.txt is the last game session)',
            filetypes=[('iPhone game logs', '*.txt'), ('All files', '*.*')])
        if not path:
            return
        try:
            report = summarize_iphone_log(Path(path))
        except (OSError, ValueError) as exc:
            messagebox.showerror('Unable to read iPhone log', str(exc))
            return
        self._append('\n' + report + '\n')
        self.state_var.set('iPhone game log inspected locally — review the highlighted messages below.')

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

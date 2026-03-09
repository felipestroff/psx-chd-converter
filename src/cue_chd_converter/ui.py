import queue
import shutil
import threading
import tempfile
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import winsound  # type: ignore
except ImportError:
    winsound = None  # type: ignore

from cue_chd_converter.archive_utils import (
    extract_archive_to_workspace,
    is_supported_archive,
)
from cue_chd_converter.converter import ChdConverter
from cue_chd_converter.models import CueGame, IgnoredEntry
from cue_chd_converter.paths import resolve_chdman_path, resolve_psxtract_path
from cue_chd_converter.pbp_utils import extract_pbp_to_workspace
from cue_chd_converter.scanner import scan_roms
from cue_chd_converter.settings import AppSettings, SettingsManager
from cue_chd_converter.size_estimator import estimate_conversion_size, format_estimate_summary


WorkerEvent = Tuple[object, ...]


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PSX CUE -> CHD Converter")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        default_w = min(1120, max(900, screen_w - 80))
        default_h = min(800, max(620, screen_h - 120))
        self.geometry("{0}x{1}".format(default_w, default_h))
        self.minsize(860, 560)

        self._apply_theme()
        self._configure_progress_style()

        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load()

        self.source_path_var = tk.StringVar(value=self.settings.last_source_path)
        self.destination_path_var = tk.StringVar(value=self.settings.destination_path)
        self.summary_var = tk.StringVar(value="No source selected.")
        self.estimate_var = tk.StringVar(value="Estimate: load ROMs to preview space savings.")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_percent_var = tk.StringVar(value="0%")
        self.progress_text_var = tk.StringVar(value="0/0 (0%) - Waiting for conversion...")
        self.same_folder_var = tk.BooleanVar(value=self.settings.same_folder)
        self.recursive_var = tk.BooleanVar(value=self.settings.recursive_scan)
        self.extract_archives_var = tk.BooleanVar(value=self.settings.extract_archives)
        self.overwrite_var = tk.BooleanVar(value=self.settings.overwrite_output)

        self.source_path: Optional[Path] = None
        self.compatible_games: List[CueGame] = []
        self.ignored_entries: List[IgnoredEntry] = []
        self.item_to_game: Dict[str, CueGame] = {}
        self.cue_to_item: Dict[str, str] = {}

        self.conversion_thread: Optional[threading.Thread] = None
        self.worker_queue: "queue.Queue[WorkerEvent]" = queue.Queue()
        self.cancel_event = threading.Event()
        self.is_converting = False
        self.log_lines: List[str] = []
        self.log_popup: Optional[tk.Toplevel] = None
        self.log_popup_text: Optional[tk.Text] = None
        self.progress_current_step = 0
        self.progress_total_steps = 0
        self.queue_drain_job: Optional[str] = None
        self.is_closing = False
        self.chdman_path = resolve_chdman_path()
        self.psxtract_path = resolve_psxtract_path()
        self.converter = ChdConverter(self.chdman_path)

        self._build_layout()
        self.bind("<Configure>", self._on_window_resize)
        self._force_fullscreen_start()

        self._update_destination_state()
        self._log("Expected chdman at: {0}".format(self.chdman_path))
        self._log("Expected psxtract at: {0}".format(self.psxtract_path))

        self._restore_source_from_settings()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_theme(self) -> None:
        self.style = ttk.Style(self)
        preferred = ["vista", "xpnative", "winnative", "clam", "default"]
        available = set(self.style.theme_names())
        for theme in preferred:
            if theme in available:
                self.style.theme_use(theme)
                break

    def _configure_progress_style(self) -> None:
        self.progress_style_name = "Text.Horizontal.TProgressbar"
        try:
            self.style.layout(
                self.progress_style_name,
                [
                    (
                        "Horizontal.Progressbar.trough",
                        {
                            "sticky": "nswe",
                            "children": [
                                ("Horizontal.Progressbar.pbar", {"side": "left", "sticky": "ns"}),
                                ("Horizontal.Progressbar.label", {"sticky": ""}),
                            ],
                        },
                    )
                ],
            )
        except tk.TclError:
            self.progress_style_name = "Horizontal.TProgressbar"

        self.style.configure(self.progress_style_name, text="0%", anchor="center")

    def _force_fullscreen_start(self) -> None:
        try:
            self.state("zoomed")
            return
        except tk.TclError:
            pass

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.geometry("{0}x{1}+0+0".format(screen_w, screen_h))

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        source_frame = ttk.LabelFrame(root, text="ROM Source (.cue, .pbp and archives)", padding=10)
        source_frame.pack(fill=tk.X, expand=False)

        ttk.Label(source_frame, text="Source:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.source_entry = ttk.Entry(source_frame, textvariable=self.source_path_var, state="readonly")
        self.source_entry.grid(row=0, column=1, sticky="ew")

        self.select_folder_btn = ttk.Button(source_frame, text="Select folder", command=self._select_folder)
        self.select_folder_btn.grid(row=0, column=2, padx=(8, 0))

        self.select_file_btn = ttk.Button(source_frame, text="Select file", command=self._select_file)
        self.select_file_btn.grid(row=0, column=3, padx=(8, 0))

        self.reload_btn = ttk.Button(source_frame, text="Reload", command=self._reload_source)
        self.reload_btn.grid(row=0, column=4, padx=(8, 0))

        self.recursive_check = ttk.Checkbutton(
            source_frame,
            text="Include subfolders",
            variable=self.recursive_var,
            command=self._on_recursive_toggle,
        )
        self.recursive_check.grid(row=1, column=1, sticky="w", pady=(8, 0))

        self.extract_archives_check = ttk.Checkbutton(
            source_frame,
            text="Extract archives before converting (.zip/.7z/.tar)",
            variable=self.extract_archives_var,
            command=self._on_extract_archives_toggle,
        )
        self.extract_archives_check.grid(row=2, column=1, sticky="w", pady=(4, 0))

        source_frame.columnconfigure(1, weight=1)

        destination_frame = ttk.LabelFrame(root, text="Destination", padding=10)
        destination_frame.pack(fill=tk.X, expand=False, pady=(10, 0))

        ttk.Label(destination_frame, text="Destination folder:").grid(row=0, column=0, sticky="w")
        self.destination_entry = ttk.Entry(destination_frame, textvariable=self.destination_path_var)
        self.destination_entry.grid(row=0, column=1, sticky="ew")

        self.select_destination_btn = ttk.Button(
            destination_frame, text="Choose destination", command=self._select_destination
        )
        self.select_destination_btn.grid(row=0, column=2, padx=(8, 0))

        self.same_folder_check = ttk.Checkbutton(
            destination_frame,
            text="Save in the ROM's source folder",
            variable=self.same_folder_var,
            command=self._on_same_folder_toggle,
        )
        self.same_folder_check.grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.overwrite_check = ttk.Checkbutton(
            destination_frame,
            text="Overwrite existing .chd",
            variable=self.overwrite_var,
            command=self._on_overwrite_toggle,
        )
        self.overwrite_check.grid(row=1, column=1, sticky="w", padx=(16, 0), pady=(8, 0))

        destination_frame.columnconfigure(1, weight=1)

        lists_frame = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
        lists_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        compatible_frame = ttk.LabelFrame(lists_frame, text="Compatible ROMs (.cue + .pbp + archives)", padding=10)
        ignored_frame = ttk.LabelFrame(lists_frame, text="Ignored / incompatible", padding=10)
        lists_frame.add(compatible_frame, weight=3)
        lists_frame.add(ignored_frame, weight=2)

        self.compatible_tree = ttk.Treeview(
            compatible_frame,
            columns=("name", "status", "path"),
            show="headings",
            selectmode="extended",
            height=8,
        )
        self.compatible_tree.heading("name", text="Game")
        self.compatible_tree.heading("status", text="Status")
        self.compatible_tree.heading("path", text="Source")
        self.compatible_tree.column("name", width=220, anchor="w")
        self.compatible_tree.column("status", width=110, anchor="center")
        self.compatible_tree.column("path", width=520, anchor="w")
        self.compatible_tree.tag_configure("pending", foreground="#003B8E")
        self.compatible_tree.tag_configure("running", foreground="#805100")
        self.compatible_tree.tag_configure("success", foreground="#0A6E0A")
        self.compatible_tree.tag_configure("failed", foreground="#8E0000")
        self.compatible_tree.tag_configure("canceled", foreground="#5F5F00")

        comp_scroll = ttk.Scrollbar(compatible_frame, orient=tk.VERTICAL, command=self.compatible_tree.yview)
        self.compatible_tree.configure(yscrollcommand=comp_scroll.set)
        self.compatible_tree.grid(row=0, column=0, sticky="nsew")
        comp_scroll.grid(row=0, column=1, sticky="ns")

        ignored_columns = ("file", "reason")
        self.ignored_tree = ttk.Treeview(
            ignored_frame, columns=ignored_columns, show="headings", selectmode="browse", height=8
        )
        self.ignored_tree.heading("file", text="File")
        self.ignored_tree.heading("reason", text="Reason")
        self.ignored_tree.column("file", width=300, anchor="w")
        self.ignored_tree.column("reason", width=320, anchor="w")
        ig_scroll = ttk.Scrollbar(ignored_frame, orient=tk.VERTICAL, command=self.ignored_tree.yview)
        self.ignored_tree.configure(yscrollcommand=ig_scroll.set)
        self.ignored_tree.grid(row=0, column=0, sticky="nsew")
        ig_scroll.grid(row=0, column=1, sticky="ns")

        compatible_frame.rowconfigure(0, weight=1)
        compatible_frame.columnconfigure(0, weight=1)
        ignored_frame.rowconfigure(0, weight=1)
        ignored_frame.columnconfigure(0, weight=1)

        summary_frame = ttk.Frame(root)
        summary_frame.pack(fill=tk.X, expand=False, pady=(8, 0))
        self.summary_label = tk.Label(summary_frame, textvariable=self.summary_var, fg="#8E0000", anchor="w")
        self.summary_label.pack(anchor="w", fill=tk.X)
        self.estimate_label = tk.Label(summary_frame, textvariable=self.estimate_var, fg="#004A99", anchor="w")
        self.estimate_label.pack(anchor="w", fill=tk.X, pady=(2, 0))

        actions_frame = ttk.Frame(root)
        actions_frame.pack(fill=tk.X, expand=False, pady=(8, 0))

        self.convert_selected_btn = ttk.Button(
            actions_frame, text="Convert selected", command=self._convert_selected
        )
        self.convert_selected_btn.pack(side=tk.LEFT)

        self.convert_all_btn = ttk.Button(actions_frame, text="Convert all", command=self._convert_all)
        self.convert_all_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.clear_status_btn = ttk.Button(actions_frame, text="Clear status", command=self._reset_statuses)
        self.clear_status_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.open_log_btn = ttk.Button(actions_frame, text="Open log", command=self._open_log_window)
        self.open_log_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.credits_btn = ttk.Button(actions_frame, text="Credits", command=self._show_credits)
        self.credits_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.stop_conversion_btn = ttk.Button(
            actions_frame, text="Cancel conversion", command=self._cancel_conversion, state=tk.DISABLED
        )
        self.stop_conversion_btn.pack(side=tk.LEFT, padx=(8, 0))

        progress_frame = ttk.LabelFrame(root, text="Progress", padding=10)
        progress_frame.pack(fill=tk.X, expand=False, pady=(10, 0))
        progress_frame.configure(height=92)
        progress_frame.pack_propagate(False)

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            variable=self.progress_var,
            maximum=1.0,
            style=self.progress_style_name,
        )
        self.progress_bar.pack(fill=tk.X, expand=True)
        self.progress_label = ttk.Label(
            progress_frame,
            textvariable=self.progress_text_var,
            justify=tk.LEFT,
            wraplength=780,
        )
        self.progress_label.pack(anchor="w", fill=tk.X, pady=(6, 0))

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget in [
            self.select_folder_btn,
            self.select_file_btn,
            self.reload_btn,
            self.recursive_check,
            self.extract_archives_check,
            self.same_folder_check,
            self.destination_entry,
            self.select_destination_btn,
            self.overwrite_check,
            self.convert_selected_btn,
            self.convert_all_btn,
            self.clear_status_btn,
        ]:
            widget.configure(state=state)

        self.stop_conversion_btn.configure(state=tk.NORMAL if self.is_converting else tk.DISABLED)
        self._update_destination_state()

    def _on_recursive_toggle(self) -> None:
        self._reload_source()
        self._save_settings()

    def _on_same_folder_toggle(self) -> None:
        self._update_destination_state()
        self._save_settings()

    def _on_extract_archives_toggle(self) -> None:
        self._refresh_overall_estimate_preview()
        self._save_settings()

    def _on_overwrite_toggle(self) -> None:
        self._save_settings()

    def _select_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose ROM folder")
        if not selected:
            return
        self._load_source(Path(selected))

    def _select_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose a CUE, PBP, or archive file",
            filetypes=[
                (
                    "Supported",
                    (
                        "*.cue",
                        "*.pbp",
                        "*.zip",
                        "*.7z",
                        "*.tar",
                        "*.tar.gz",
                        "*.tgz",
                        "*.tar.bz2",
                        "*.tbz2",
                        "*.tar.xz",
                        "*.txz",
                    ),
                ),
                ("CUE", "*.cue"),
                ("PBP", "*.pbp"),
                (
                    "Archives",
                    (
                        "*.zip",
                        "*.7z",
                        "*.tar",
                        "*.tar.gz",
                        "*.tgz",
                        "*.tar.bz2",
                        "*.tbz2",
                        "*.tar.xz",
                        "*.txz",
                    ),
                ),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        self._load_source(Path(selected))

    def _select_destination(self) -> None:
        selected = filedialog.askdirectory(title="Choose destination folder")
        if not selected:
            return
        self.destination_path_var.set(selected)
        self._save_settings()

    def _reload_source(self) -> None:
        if self.source_path:
            self._load_source(self.source_path)

    def _load_source(self, source: Path) -> None:
        if not source.exists():
            messagebox.showerror("Error", "Source path not found.")
            return

        self.source_path = source.resolve()
        self.source_path_var.set(str(self.source_path))

        recursive = self.recursive_var.get() if self.source_path.is_dir() else False
        self.compatible_games, self.ignored_entries = scan_roms(self.source_path, recursive=recursive)
        self._populate_compatible()
        self._populate_ignored()
        self._update_destination_state()

        compatible_count = len(self.compatible_games)
        ignored_count = len(self.ignored_entries)
        archive_count = len([game for game in self.compatible_games if game.is_archive])
        pbp_count = len([game for game in self.compatible_games if game.source_kind == "pbp"])
        self.summary_var.set(
            "{0} compatible item(s). {1} supported archive(s). {2} PBP file(s). {3} ignored file(s).".format(
                compatible_count, archive_count, pbp_count, ignored_count
            )
        )
        self._set_summary(self.summary_var.get(), color="#003B8E")
        self._log("Loaded source: {0}".format(self.source_path))
        self._log("Compatible: {0} | Ignored: {1}".format(compatible_count, ignored_count))
        self._refresh_overall_estimate_preview()
        self._save_settings()

    def _populate_compatible(self) -> None:
        self.compatible_tree.delete(*self.compatible_tree.get_children())
        self.item_to_game.clear()
        self.cue_to_item.clear()

        for game in self.compatible_games:
            self._insert_game_row(game, status=self._default_status_for_game(game))

    def _populate_ignored(self) -> None:
        self.ignored_tree.delete(*self.ignored_tree.get_children())
        for entry in self.ignored_entries:
            self.ignored_tree.insert("", tk.END, values=(str(entry.path.name), entry.reason))

    def _insert_game_row(self, game: CueGame, status: str) -> None:
        existing_item = self.cue_to_item.get(str(game.cue_path.resolve()))
        if existing_item:
            self.item_to_game[existing_item] = game
            self.compatible_tree.set(existing_item, "status", status)
            self.compatible_tree.set(existing_item, "path", self._display_path_for_game(game))
            return

        item = self.compatible_tree.insert(
            "",
            tk.END,
            values=(game.display_name, status, self._display_path_for_game(game)),
            tags=("pending",),
        )
        self.item_to_game[item] = game
        self.cue_to_item[str(game.cue_path.resolve())] = item

    def _display_path_for_game(self, game: CueGame) -> str:
        if game.archive_origin:
            return "{0} -> {1}".format(game.archive_origin.name, game.cue_path.name)
        if game.is_archive:
            return "[archive] {0}".format(game.cue_path)
        if game.source_kind == "pbp":
            return "[pbp] {0}".format(game.cue_path)
        return str(game.cue_path)

    def _default_status_for_game(self, game: Optional[CueGame]) -> str:
        if game and game.is_archive:
            return "Ready (archive)"
        if game and game.source_kind == "pbp":
            return "Ready (PBP)"
        return "Ready"

    def _reset_statuses(self) -> None:
        for item in self.compatible_tree.get_children():
            game = self.item_to_game.get(item)
            default_status = self._default_status_for_game(game)
            self.compatible_tree.set(item, "status", default_status)
            self.compatible_tree.item(item, tags=("pending",))
        self.progress_current_step = 0
        self.progress_total_steps = 0
        self._set_progress_values(current=0, total=0)
        self.progress_text_var.set("0/0 (0%) - Waiting for conversion...")

    def _convert_selected(self) -> None:
        selected_items = self.compatible_tree.selection()
        if not selected_items:
            messagebox.showinfo("Conversion", "Select at least one compatible ROM.")
            return
        selected_sources = [self.item_to_game[item] for item in selected_items]
        cue_games, archive_paths = self._split_conversion_sources(selected_sources, include_archives=True)
        if not cue_games and not archive_paths:
            messagebox.showinfo("Conversion", "No selected item to convert.")
            return
        self._start_conversion(cue_games, archive_paths=archive_paths)

    def _convert_all(self) -> None:
        include_archives = self.extract_archives_var.get()
        if self.source_path and self.source_path.is_file() and is_supported_archive(self.source_path):
            include_archives = True

        cue_games, archive_paths = self._split_conversion_sources(self.compatible_games, include_archives=include_archives)

        if not cue_games and not archive_paths:
            messagebox.showinfo("Conversion", "No compatible ROM or archive selected for conversion.")
            return
        self._start_conversion(cue_games, archive_paths=archive_paths)

    def _cancel_conversion(self) -> None:
        if not self.is_converting:
            return
        self.cancel_event.set()
        self.stop_conversion_btn.configure(state=tk.DISABLED)
        self._log("Cancel request received. Waiting for current task to finish...")

    def _start_conversion(self, games: Sequence[CueGame], archive_paths: Sequence[Path]) -> None:
        if self.is_converting:
            return

        if not self.chdman_path.exists():
            messagebox.showerror(
                "Missing chdman",
                "chdman.exe was not found at:\n{0}\n\nPlace the executable at tools\\mame\\chdman.exe".format(
                    self.chdman_path
                ),
            )
            return

        destination_root: Optional[Path] = None
        if not self.same_folder_var.get():
            destination_text = self.destination_path_var.get().strip()
            if not destination_text:
                messagebox.showerror("Invalid destination", "Select a destination folder.")
                return
            destination_root = Path(destination_text)
            destination_root.mkdir(parents=True, exist_ok=True)

        self._update_estimate_for_scope(
            scope_label="current task",
            games=games,
            archive_paths=archive_paths,
            write_log=True,
        )
        overwrite = self.overwrite_var.get()
        planned_total_steps = self._initial_total_steps(games=games, archive_paths=archive_paths)
        self.cancel_event.clear()
        self.is_converting = True
        self._set_controls_enabled(False)
        self.progress_current_step = 0
        self.progress_total_steps = planned_total_steps
        self._set_progress_values(current=0, total=planned_total_steps)
        if planned_total_steps > 0:
            self.progress_text_var.set("0/{0} (0%) - Preparing conversion...".format(planned_total_steps))
        else:
            self.progress_text_var.set("0/0 (0%) - Preparing conversion...")
        self._log("Planned progress steps: {0}".format(planned_total_steps))

        for game in games:
            self._set_game_status(game.cue_path, "Queued")
        for archive_path in archive_paths:
            self._set_game_status(archive_path, "Queued")

        pbp_count = len([game for game in games if game.source_kind == "pbp"])
        cue_count = len(games) - pbp_count
        if archive_paths or pbp_count:
            self._log(
                "Starting conversion of {0} CUE ROM(s) + {1} PBP file(s) + extraction of {2} archive(s).".format(
                    cue_count, pbp_count, len(archive_paths)
                )
            )
        else:
            self._log("Starting conversion of {0} ROM(s).".format(len(games)))
        self.conversion_thread = threading.Thread(
            target=self._worker_convert,
            args=(list(games), list(archive_paths), destination_root, overwrite),
            daemon=True,
        )
        self.conversion_thread.start()
        self.queue_drain_job = self.after(100, self._drain_worker_queue)

    def _worker_convert(
        self,
        games: List[CueGame],
        archive_paths: List[Path],
        destination_root: Optional[Path],
        overwrite: bool,
    ) -> None:
        extracted_workspaces: List[Path] = []
        extraction_fail_count = 0
        completed_steps = 0
        total_steps = self._initial_total_steps(games=games, archive_paths=archive_paths)
        self.worker_queue.put(("progress", completed_steps, total_steps, "Preparing conversion"))

        if archive_paths:
            self.worker_queue.put(
                (
                    "log",
                    "Extracting archives before conversion ({0} file(s))...".format(len(archive_paths)),
                    None,
                    None,
                )
            )

            workspace_root = Path(tempfile.mkdtemp(prefix="cue-chd-extract-"))
            extracted_workspaces.append(workspace_root)

            for archive_path in archive_paths:
                if self.cancel_event.is_set():
                    self.worker_queue.put(("status", str(archive_path), "Canceled"))
                    completed_steps += 1
                    self.worker_queue.put(("progress", completed_steps, total_steps, archive_path.name))
                    break

                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "Extracting {0}".format(archive_path.name))
                )
                self.worker_queue.put(("status", str(archive_path), "Extracting"))
                self.worker_queue.put(("log", "Extracting: {0}".format(archive_path), None, None))
                ok_extract, extracted_dir, message = extract_archive_to_workspace(
                    archive_path=archive_path,
                    workspace_root=workspace_root,
                )
                self.worker_queue.put(("log", message, None, None))
                if not ok_extract or not extracted_dir:
                    extraction_fail_count += 1
                    self.worker_queue.put(
                        (
                            "log",
                            "[DETAILED ERROR] Extraction failed\n"
                            "File: {0}\n"
                            "Cause: {1}\n"
                            "Suggestion: Check archive integrity, format support, and .7z extractor availability".format(
                                archive_path, message
                            ),
                            None,
                            None,
                        )
                    )
                    self.worker_queue.put(("status", str(archive_path), "Failed"))
                    completed_steps += 1
                    self.worker_queue.put(("progress", completed_steps, total_steps, archive_path.name))
                    continue

                extracted_games, ignored_inside = scan_roms(extracted_dir, recursive=True)
                extracted_games = [game for game in extracted_games if not game.is_archive]
                if not extracted_games:
                    extraction_fail_count += 1
                    ignored_preview = "; ".join(
                        "{0}: {1}".format(item.path.name, item.reason) for item in ignored_inside[:5]
                    )
                    if not ignored_preview:
                        ignored_preview = "No compatible item found"
                    self.worker_queue.put(
                        (
                            "log",
                            "[DETAILED ERROR] Incompatible content after extraction\n"
                            "File: {0}\n"
                            "Cause: No valid .cue found\n"
                            "Ignored items: {1}\n"
                            "Examples: {2}".format(
                                archive_path.name, len(ignored_inside), ignored_preview
                            ),
                            None,
                            None,
                        )
                    )
                    self.worker_queue.put(("status", str(archive_path), "Failed"))
                    completed_steps += 1
                    self.worker_queue.put(("progress", completed_steps, total_steps, archive_path.name))
                    continue

                for extracted_game in extracted_games:
                    extracted_game.archive_origin = archive_path.resolve()
                    extracted_game.extraction_dir = extracted_dir
                    games.append(extracted_game)
                total_steps += sum(self._steps_for_game(extracted_game) for extracted_game in extracted_games)

                self.worker_queue.put(("status", str(archive_path), "Extracted"))
                self.worker_queue.put(
                    (
                        "log",
                        "{0} ROM(s) extracted from {1}".format(len(extracted_games), archive_path.name),
                        None,
                        None,
                    )
                )
                completed_steps += 1
                self.worker_queue.put(("progress", completed_steps, total_steps, archive_path.name))

        success_count = 0
        fail_count = 0
        canceled_count = 0
        canceled = False

        prepared_games: List[CueGame] = []
        pbp_workspace_root: Optional[Path] = None
        pbp_sources = [game for game in games if game.source_kind == "pbp"]
        if pbp_sources:
            pbp_workspace_root = Path(tempfile.mkdtemp(prefix="cue-chd-pbp-"))
            extracted_workspaces.append(pbp_workspace_root)
            self.worker_queue.put(
                (
                    "log",
                    "Extracting PBP before conversion ({0} file(s))...".format(len(pbp_sources)),
                    None,
                    None,
                )
            )

        for game in games:
            if game.source_kind != "pbp":
                prepared_games.append(game)
                continue

            status_anchor = self._status_anchor_path(game)
            if self.cancel_event.is_set():
                canceled = True
                canceled_count += 1
                self.worker_queue.put(("status", str(status_anchor), "Canceled"))
                completed_steps += 3
                self.worker_queue.put(("progress", completed_steps, total_steps, game.display_name))
                continue

            self.worker_queue.put(
                ("progress", completed_steps, total_steps, "{0} (extracting PBP)".format(game.display_name))
            )
            self.worker_queue.put(("status", str(status_anchor), "Extracting"))
            self.worker_queue.put(("log", "Extracting PBP: {0}".format(game.cue_path), None, None))
            if pbp_workspace_root is None:
                fail_count += 1
                self.worker_queue.put(("status", str(status_anchor), "Failed"))
                completed_steps += 3
                self.worker_queue.put(("progress", completed_steps, total_steps, game.display_name))
                self.worker_queue.put(("log", "PBP extraction workspace was not initialized", None, None))
                continue

            ok_pbp, pbp_dir, pbp_message = extract_pbp_to_workspace(
                pbp_path=game.cue_path,
                workspace_root=pbp_workspace_root,
                psxtract_path=self.psxtract_path,
            )
            self.worker_queue.put(("log", pbp_message, None, None))
            if not ok_pbp or not pbp_dir:
                fail_count += 1
                self.worker_queue.put(
                    (
                        "log",
                        "[DETAILED ERROR] PBP extraction failed\n"
                        "File: {0}\n"
                        "Cause: {1}\n"
                        "Suggestion: {2}".format(
                            game.cue_path,
                            pbp_message,
                            self._pbp_failure_suggestion(pbp_message),
                        ),
                        None,
                        None,
                    )
                )
                self.worker_queue.put(("status", str(status_anchor), "Failed"))
                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (PBP extraction failed)".format(game.display_name))
                )
                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (conversion skipped)".format(game.display_name))
                )
                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (verification skipped)".format(game.display_name))
                )
                continue

            extracted_games, ignored_inside = scan_roms(pbp_dir, recursive=True)
            extracted_games = [
                extracted_game
                for extracted_game in extracted_games
                if not extracted_game.is_archive and extracted_game.source_kind == "cue"
            ]
            if not extracted_games:
                fail_count += 1
                ignored_preview = "; ".join(
                    "{0}: {1}".format(item.path.name, item.reason) for item in ignored_inside[:5]
                )
                if not ignored_preview:
                    ignored_preview = "No compatible item found"
                self.worker_queue.put(
                    (
                        "log",
                        "[DETAILED ERROR] Incompatible PBP extraction result\n"
                        "File: {0}\n"
                        "Cause: No valid .cue found after extraction\n"
                        "Ignored items: {1}\n"
                        "Examples: {2}".format(game.cue_path.name, len(ignored_inside), ignored_preview),
                        None,
                        None,
                    )
                )
                self.worker_queue.put(("status", str(status_anchor), "Failed"))
                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (PBP extraction invalid)".format(game.display_name))
                )
                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (conversion skipped)".format(game.display_name))
                )
                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (verification skipped)".format(game.display_name))
                )
                continue

            extracted_game = extracted_games[0]
            extracted_game.archive_origin = game.archive_origin.resolve() if game.archive_origin else game.cue_path.resolve()
            extracted_game.extraction_dir = pbp_dir
            prepared_games.append(extracted_game)
            completed_steps += 1
            self.worker_queue.put(("status", str(status_anchor), "Extracted"))
            self.worker_queue.put(
                (
                    "log",
                    "PBP extracted: {0} CUE file(s) found, using {1}".format(
                        len(extracted_games), extracted_game.cue_path.name
                    ),
                    None,
                    None,
                )
            )
            self.worker_queue.put(
                ("progress", completed_steps, total_steps, "{0} (PBP extracted)".format(game.display_name))
            )

        for game in prepared_games:
            status_anchor = self._status_anchor_path(game)
            if self.cancel_event.is_set():
                canceled = True
                canceled_count += 1
                self.worker_queue.put(("status", str(status_anchor), "Canceled"))
                completed_steps += 2
                self.worker_queue.put(("progress", completed_steps, total_steps, game.display_name))
                continue

            target_dir = self._resolve_output_dir(game, destination_root)
            output_path = (target_dir / self._output_name_for_game(game)).resolve()

            self.worker_queue.put(
                ("progress", completed_steps, total_steps, "{0} (converting)".format(game.display_name))
            )
            self.worker_queue.put(("status", str(status_anchor), "Converting"))
            self.worker_queue.put(
                (
                    "log",
                    "[{0}/{1}] {2} -> {3}".format(completed_steps + 1, total_steps, game.display_name, output_path),
                    None,
                    None,
                )
            )

            def log_callback(text: str) -> None:
                self.worker_queue.put(("log", text, None, None))

            create_ok, create_message = self.converter.create_cd(
                game=game,
                output_path=output_path,
                overwrite=overwrite,
                on_log=log_callback,
                cancel_event=self.cancel_event,
            )

            if create_ok:
                completed_steps += 1
                self.worker_queue.put(("progress", completed_steps, total_steps, "{0} (conversion)".format(game.display_name)))

                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (verifying)".format(game.display_name))
                )
                self.worker_queue.put(("status", str(status_anchor), "Verifying"))
                verify_ok, verify_message = self.converter.verify_chd(
                    game=game,
                    output_path=output_path,
                    on_log=log_callback,
                    cancel_event=self.cancel_event,
                )
                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (verification)".format(game.display_name))
                )

                if verify_ok:
                    success_count += 1
                    status = "Verified"
                    message = verify_message
                else:
                    if self.cancel_event.is_set() and "canceled" in verify_message.lower():
                        canceled = True
                        canceled_count += 1
                        status = "Canceled"
                    else:
                        fail_count += 1
                        status = "Failed"
                    message = verify_message
            else:
                if self.cancel_event.is_set() and "canceled" in create_message.lower():
                    canceled = True
                    canceled_count += 1
                    status = "Canceled"
                    message = create_message
                else:
                    fail_count += 1
                    status = "Failed"
                    message = "{0}\nVerification skipped due conversion failure.".format(create_message)

                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (conversion failed)".format(game.display_name))
                )
                completed_steps += 1
                self.worker_queue.put(
                    ("progress", completed_steps, total_steps, "{0} (verification skipped)".format(game.display_name))
                )

            self.worker_queue.put(("status", str(status_anchor), status))
            self.worker_queue.put(("log", message, None, None))

            if canceled:
                continue

        for workspace in extracted_workspaces:
            try:
                shutil.rmtree(workspace, ignore_errors=True)
            except OSError:
                self.worker_queue.put(("log", "Failed to clean temporary folder: {0}".format(workspace), None, None))

        self.worker_queue.put(
            (
                "done",
                success_count,
                fail_count,
                extraction_fail_count,
                canceled_count,
                completed_steps,
                total_steps,
                canceled,
            )
        )

    def _drain_worker_queue(self) -> None:
        self.queue_drain_job = None
        if self.is_closing:
            return

        done = False
        processed = 0
        max_events_per_tick = 250
        while processed < max_events_per_tick:
            try:
                event = self.worker_queue.get_nowait()
            except queue.Empty:
                break
            processed += 1

            try:
                event_type = event[0]
                if event_type == "log":
                    self._log(str(event[1]))
                elif event_type == "status":
                    cue_path = Path(str(event[1]))
                    status = str(event[2])
                    self._set_game_status(cue_path, status)
                elif event_type == "progress":
                    current = int(event[1])
                    total = int(event[2])
                    label = str(event[3])
                    self._update_progress(current, total, label)
                elif event_type == "done":
                    success = int(event[1])
                    failed = int(event[2])
                    extraction_failed = int(event[3])
                    canceled_count = int(event[4])
                    completed_steps = int(event[5])
                    total_steps = int(event[6])
                    canceled = bool(event[7])

                    self.progress_current_step = max(0, completed_steps)
                    self.progress_total_steps = max(0, total_steps)

                    self._set_progress_values(current=completed_steps, total=total_steps)
                    if canceled:
                        self.progress_text_var.set(
                            "Conversion canceled. {0}/{1} ({2:.0f}%) step(s) processed.".format(
                                completed_steps,
                                total_steps,
                                self._current_progress_percent(),
                            )
                        )
                        self._log(
                            "Canceled. Verified: {0} | Conversion failed: {1} | Extraction failed: {2} | Canceled: {3}".format(
                                success, failed, extraction_failed, canceled_count
                            )
                        )
                    else:
                        if total_steps:
                            self.progress_text_var.set(
                                "{0}/{1} ({2:.0f}%) step(s) completed.".format(
                                    completed_steps,
                                    total_steps,
                                    self._current_progress_percent(),
                                )
                            )
                        else:
                            self.progress_text_var.set("0/0 (0%) - No ROM was processed.")
                        self._log(
                            "Finished. Verified: {0} | Conversion failed: {1} | Extraction failed: {2}".format(
                                success, failed, extraction_failed
                            )
                        )
                    self._notify_process_end(
                        success=success,
                        failed=failed,
                        extraction_failed=extraction_failed,
                        canceled=canceled,
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    )
                    done = True
            except Exception as exc:
                self._log("[INTERNAL ERROR] Failed to process worker event: {0}".format(exc))

        if done:
            self.queue_drain_job = None
            self.is_converting = False
            if not self.is_closing and self._is_window_alive():
                self._set_controls_enabled(True)
            return

        if self.is_converting and not self.is_closing:
            interval_ms = 20 if not self.worker_queue.empty() else 100
            self.queue_drain_job = self.after(interval_ms, self._drain_worker_queue)

    def _update_progress(self, current: int, total: int, current_game: str) -> None:
        self.progress_current_step = max(0, int(current))
        self.progress_total_steps = max(0, int(total))

        percent = self._set_progress_values(current=self.progress_current_step, total=self.progress_total_steps)
        self.progress_text_var.set("{0}/{1} ({2:.0f}%) - {3}".format(current, total, percent, current_game))
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    def _on_window_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        wrap = max(280, self.winfo_width() - 260)
        self.progress_label.configure(wraplength=wrap)

    def _set_game_status(self, cue_path: Path, status: str) -> None:
        item = self.cue_to_item.get(str(cue_path.resolve()))
        if not item:
            return

        self.compatible_tree.set(item, "status", status)
        status_tag = {
            "Ready": "pending",
            "Ready (archive)": "pending",
            "Ready (PBP)": "pending",
            "Queued": "pending",
            "Converting": "running",
            "Verifying": "running",
            "Extracting": "running",
            "Converted": "success",
            "Verified": "success",
            "Extracted": "success",
            "Failed": "failed",
            "Canceled": "canceled",
        }.get(status, "pending")
        self.compatible_tree.item(item, tags=(status_tag,))

    def _notify_process_end(
        self,
        success: int,
        failed: int,
        extraction_failed: int,
        canceled: bool,
        completed_steps: int,
        total_steps: int,
    ) -> None:
        if self.is_closing or not self._is_window_alive():
            return

        if canceled:
            title = "Conversion canceled"
            message = (
                "Process canceled.\n\n"
                "Processed steps: {0}/{1}\n"
                "Verified: {2}\n"
                "Conversion failures: {3}\n"
                "Extraction failures: {4}".format(
                    completed_steps, total_steps, success, failed, extraction_failed
                )
            )
            self._set_summary(message.replace("\n", " "), color="#B36B00")
            self._play_system_sound(kind="warning")
            messagebox.showwarning(title, message, parent=self)
            return

        has_failure = failed > 0 or extraction_failed > 0
        if has_failure:
            title = "Conversion completed with failures"
            message = (
                "Process finished with failures.\n\n"
                "Processed steps: {0}/{1}\n"
                "Verified: {2}\n"
                "Conversion failures: {3}\n"
                "Extraction failures: {4}".format(
                    completed_steps, total_steps, success, failed, extraction_failed
                )
            )
            self._set_summary(message.replace("\n", " "), color="#8E0000")
            self._play_system_sound(kind="warning")
            messagebox.showwarning(title, message, parent=self)
            return

        title = "Conversion completed"
        message = (
            "Process finished successfully.\n\n"
            "Processed steps: {0}/{1}\n"
            "Verified ROM(s): {2}".format(completed_steps, total_steps, success)
        )
        self._set_summary(message.replace("\n", " "), color="#0A6E0A")
        self._play_system_sound(kind="info")
        messagebox.showinfo(title, message, parent=self)

    def _set_summary(self, text: str, color: str) -> None:
        self.summary_var.set(text)
        try:
            self.summary_label.configure(fg=color)
        except tk.TclError:
            pass

    def _set_estimate(self, text: str, color: str) -> None:
        self.estimate_var.set(text)
        try:
            self.estimate_label.configure(fg=color)
        except tk.TclError:
            pass

    def _set_progress_values(self, current: int, total: int) -> float:
        safe_total = max(0, int(total))
        safe_current = max(0, int(current))
        if safe_total > 0:
            safe_current = min(safe_current, safe_total)

        self.progress_bar.configure(maximum=float(max(1, safe_total)))
        self.progress_var.set(float(safe_current))

        percent = (float(safe_current) / float(safe_total)) * 100.0 if safe_total else 0.0
        percent_text = "{0:.0f}%".format(percent)
        self.progress_percent_var.set(percent_text)
        try:
            self.style.configure(self.progress_style_name, text=percent_text)
        except tk.TclError:
            pass
        return percent

    def _current_progress_percent(self) -> float:
        total = max(0, int(self.progress_total_steps))
        current = max(0, int(self.progress_current_step))
        if total <= 0:
            return 0.0
        return (float(min(current, total)) / float(total)) * 100.0

    def _refresh_overall_estimate_preview(self) -> None:
        if not self.compatible_games:
            self._set_estimate("Estimate: no compatible items to analyze.", color="#6F6F6F")
            return

        include_archives = self.extract_archives_var.get()
        if self.source_path and self.source_path.is_file() and is_supported_archive(self.source_path):
            include_archives = True

        cue_games, archive_paths = self._split_conversion_sources(
            self.compatible_games,
            include_archives=include_archives,
        )
        self._update_estimate_for_scope(
            scope_label="all compatible items",
            games=cue_games,
            archive_paths=archive_paths,
            write_log=False,
        )

    def _update_estimate_for_scope(
        self,
        scope_label: str,
        games: Sequence[CueGame],
        archive_paths: Sequence[Path],
        write_log: bool,
    ) -> None:
        estimate = estimate_conversion_size(games=games, archive_paths=archive_paths)
        contains_archives = len(archive_paths) > 0
        estimate_text = format_estimate_summary(
            estimate=estimate,
            scope_label=scope_label,
            contains_archives=contains_archives,
        )
        self._set_estimate(estimate_text, color="#004A99")
        if write_log:
            self._log(estimate_text)

    def _is_window_alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _play_system_sound(self, kind: str) -> None:
        if self.is_closing or not self._is_window_alive():
            return
        if winsound is not None:
            if kind == "warning":
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return
        self.bell()

    def _update_destination_state(self) -> None:
        same_folder = self.same_folder_var.get()
        state = tk.DISABLED if same_folder or self.is_converting else tk.NORMAL
        self.destination_entry.configure(state=state)
        self.select_destination_btn.configure(state=state)

        if same_folder:
            if self.source_path:
                folder = self.source_path if self.source_path.is_dir() else self.source_path.parent
                self.destination_path_var.set(str(folder))
            else:
                self.destination_path_var.set("")

    def _split_conversion_sources(
        self, sources: Sequence[CueGame], include_archives: bool
    ) -> Tuple[List[CueGame], List[Path]]:
        cue_games: List[CueGame] = []
        archive_paths: List[Path] = []
        seen_archives = set()

        for source in sources:
            if source.is_archive:
                if include_archives:
                    archive_path = source.cue_path.resolve()
                    archive_key = str(archive_path).lower()
                    if archive_key not in seen_archives:
                        seen_archives.add(archive_key)
                        archive_paths.append(archive_path)
                continue

            cue_games.append(source)

        return cue_games, archive_paths

    def _initial_total_steps(self, games: Sequence[CueGame], archive_paths: Sequence[Path]) -> int:
        # Base plan:
        # - archive: extraction (1 step)
        # - cue: conversion + verification (2 steps)
        # - pbp: extraction + conversion + verification (3 steps)
        total = len(archive_paths)
        for game in games:
            total += self._steps_for_game(game)
        return total

    def _steps_for_game(self, game: CueGame) -> int:
        if game.source_kind == "pbp":
            return 3
        return 2

    def _resolve_output_dir(self, game: CueGame, destination_root: Optional[Path]) -> Path:
        if destination_root:
            return destination_root
        if game.archive_origin:
            return game.archive_origin.parent
        return game.cue_path.parent

    def _output_name_for_game(self, game: CueGame) -> str:
        if game.archive_origin and game.archive_origin.suffix.lower() == ".pbp":
            return game.archive_origin.with_suffix(".chd").name
        return game.cue_path.with_suffix(".chd").name

    def _status_anchor_path(self, game: CueGame) -> Path:
        if game.archive_origin:
            return game.archive_origin.resolve()
        return game.cue_path.resolve()

    def _pbp_failure_suggestion(self, message: str) -> str:
        lowered = message.lower()
        if "psxtract.exe was not found" in lowered:
            return "Place psxtract.exe at tools\\psxtract\\psxtract.exe."
        if (
            "invalid 0x80 mac hash" in lowered
            or "iso header decryption failed" in lowered
            or "decryption failed" in lowered
        ):
            return (
                "This PBP appears unsupported/encrypted for psxtract. "
                "Try another PBP source (PSN-compatible) or pre-convert to BIN/CUE first."
            )
        if "no .cue was produced" in lowered:
            return "Verify PBP format; psxtract may only support specific PSOne Classic EBOOT formats."
        return "Verify PBP integrity and psxtract compatibility."

    def _apply_saved_geometry(self, geometry: str) -> None:
        try:
            size_part = geometry.split("+", 1)[0]
            width_str, height_str = size_part.split("x", 1)
            saved_w = int(width_str)
            saved_h = int(height_str)
        except (ValueError, TypeError):
            return

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(saved_w, max(860, screen_w - 40))
        height = min(saved_h, max(560, screen_h - 80))
        self.geometry("{0}x{1}".format(width, height))

    def _open_log_window(self) -> None:
        if self.log_popup and self.log_popup.winfo_exists():
            self.log_popup.deiconify()
            self.log_popup.lift()
            self.log_popup.focus_force()
            return

        popup = tk.Toplevel(self)
        popup.title("Conversion log")
        popup.geometry("920x420")
        popup.minsize(620, 260)

        frame = ttk.Frame(popup, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        popup_text = tk.Text(frame, state=tk.DISABLED, wrap="word")
        popup_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=popup_text.yview)
        popup_text.configure(yscrollcommand=popup_scroll.set)
        popup_text.grid(row=0, column=0, sticky="nsew")
        popup_scroll.grid(row=0, column=1, sticky="ns")

        actions = ttk.Frame(frame)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Clear log", command=self._clear_log).pack(side=tk.RIGHT)

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        existing_log = "".join(self.log_lines)
        popup_text.configure(state=tk.NORMAL)
        popup_text.insert(tk.END, existing_log)
        popup_text.see(tk.END)
        popup_text.configure(state=tk.DISABLED)

        self.log_popup = popup
        self.log_popup_text = popup_text
        popup.protocol("WM_DELETE_WINDOW", self._close_log_window)

    def _close_log_window(self) -> None:
        if self.log_popup and self.log_popup.winfo_exists():
            self.log_popup.destroy()
        self.log_popup = None
        self.log_popup_text = None

    def _clear_log(self) -> None:
        self.log_lines.clear()

        if self.log_popup_text:
            try:
                self.log_popup_text.configure(state=tk.NORMAL)
                self.log_popup_text.delete("1.0", tk.END)
                self.log_popup_text.configure(state=tk.DISABLED)
            except tk.TclError:
                self.log_popup = None
                self.log_popup_text = None

    def _show_credits(self) -> None:
        text = (
            "Project developer:\n"
            "Felipe Stroff\n\n"
            "Contact (questions, suggestions, and feedback):\n"
            "stroff.felipe@gmail.com\n\n"
            "GitHub:\n"
            "https://github.com/felipestroff"
        )
        self._play_system_sound(kind="info")
        messagebox.showinfo("Credits", text, parent=self)

        if messagebox.askyesno("Open GitHub", "Do you want to open the developer profile on GitHub?", parent=self):
            webbrowser.open("https://github.com/felipestroff")

    def _restore_source_from_settings(self) -> None:
        source_text = self.settings.last_source_path.strip()
        if not source_text:
            return

        source = Path(source_text)
        if source.exists():
            self._load_source(source)
        else:
            self.source_path_var.set("")

    def _save_settings(self) -> None:
        geometry = self.geometry()
        source_path = str(self.source_path) if self.source_path else self.source_path_var.get().strip()

        settings = AppSettings(
            last_source_path=source_path,
            destination_path=self.destination_path_var.get().strip(),
            same_folder=self.same_folder_var.get(),
            recursive_scan=self.recursive_var.get(),
            extract_archives=self.extract_archives_var.get(),
            overwrite_output=self.overwrite_var.get(),
            window_geometry=geometry,
        )

        try:
            self.settings_manager.save(settings)
        except OSError:
            pass

    def _on_close(self) -> None:
        if self.is_closing:
            return

        if self.is_converting:
            if not messagebox.askyesno(
                "Conversion in progress",
                "There is a conversion in progress. Do you want to cancel and exit?",
                parent=self,
            ):
                return
            self.cancel_event.set()

        self.is_closing = True
        if self.queue_drain_job is not None:
            try:
                self.after_cancel(self.queue_drain_job)
            except tk.TclError:
                pass
            self.queue_drain_job = None

        self._close_log_window()
        self._save_settings()
        self.destroy()

    def _log(self, message: str) -> None:
        if not message or self.is_closing or not self._is_window_alive():
            return
        timestamp = time.strftime("%H:%M:%S")
        prepared_lines = ["[{0}] {1}\n".format(timestamp, line) for line in message.splitlines()]
        self.log_lines.extend(prepared_lines)

        if self.log_popup_text:
            try:
                self.log_popup_text.configure(state=tk.NORMAL)
                for line in prepared_lines:
                    self.log_popup_text.insert(tk.END, line)
                self.log_popup_text.see(tk.END)
                self.log_popup_text.configure(state=tk.DISABLED)
            except tk.TclError:
                self.log_popup = None
                self.log_popup_text = None


def run_app() -> None:
    app = MainWindow()
    app.mainloop()






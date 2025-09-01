import os
import hashlib
import shutil
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
from datetime import datetime

# --- Settings ---
HASH_ALGORITHMS = {
    "Fast (MD5)": hashlib.md5,
    "Secure (SHA256)": hashlib.sha256
}

# Colors - Modern Professional Theme
PRIMARY_COLOR = "#1a73e8"     # Google Blue
SECONDARY_COLOR = "#424242"   # Dark Grey
ACCENT_COLOR = "#2196f3"      # Material Blue
SUCCESS_COLOR = "#00c853"     # Material Green
WARNING_COLOR = "#ffd600"     # Material Yellow
ERROR_COLOR = "#f44336"       # Material Red
INFO_COLOR = "#569cd6"        # Info Blue
BG_COLOR = "#f8f9fa"          # Light Grey Background
TEXT_COLOR = "#202124"        # Near Black
BORDER_COLOR = "#e0e0e0"      # Light Border
CARD_BG = "#ffffff"           # White for Cards
HOVER_COLOR = "#f1f3f4"       # Hover state

cancel_flag = False

# --- Hashing function ---
def get_file_hash(file_path, hash_func):
    h = hash_func()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
    except Exception as e:
        logging.warning(f"Cannot read file {file_path}: {e}")
        return None
    return h.hexdigest()

# --- Logging handler for GUI ---
class TextHandler(logging.Handler):
    def __init__(self, text_widget, verbose_var):
        super().__init__()
        self.text_widget = text_widget
        self.verbose_var = verbose_var

    def emit(self, record):
        msg = self.format(record)
        if not self.verbose_var.get() and record.levelno == logging.INFO:
            return  # skip detailed logs if summary mode

        self.text_widget.config(state=tk.NORMAL)
        if record.levelno == logging.WARNING:
            self.text_widget.insert(tk.END, "⚠️ " + msg + "\n", "warning")
        elif record.levelno == logging.ERROR:
            self.text_widget.insert(tk.END, "❌ " + msg + "\n", "error")
        else:
            self.text_widget.insert(tk.END, "ℹ️ " + msg + "\n")
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)


def setup_logging(log_dir, text_widget=None, verbose_var=None):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"duplicate_deletion_{timestamp}.log")

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s]: %(message)s"
    )

    if text_widget:
        handler = TextHandler(text_widget, verbose_var)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s"))
        logging.getLogger().addHandler(handler)

    return log_file

# --- Remove duplicates function ---
def remove_duplicate_files(directory, backup_dir, log_dir, hash_func, preserve_structure, 
                           progress_callback=None, status_callback=None, log_text=None, verbose_mode=None):
    global cancel_flag
    log_file = setup_logging(log_dir, log_text, verbose_mode)

    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    file_hashes = {}
    duplicate_count, skipped_count = 0, 0
    total_files = sum(len(files) for _, _, files in os.walk(directory))
    processed = 0
    if total_files == 0:
        logging.warning("No files found in the selected directory.")
        return 0, 0

    for root, dirs, files in os.walk(directory):
        for fname in files:
            if cancel_flag:
                logging.warning("Process cancelled by user.")
                return duplicate_count, skipped_count

            path = os.path.join(root, fname)
            file_hash = get_file_hash(path, hash_func)

            if not file_hash:
                skipped_count += 1
                continue

            if file_hash in file_hashes:
                # duplicate found
                if preserve_structure:
                    rel_path = os.path.relpath(root, directory)
                    dest_dir = os.path.join(backup_dir, rel_path)
                    os.makedirs(dest_dir, exist_ok=True)
                    backup_path = os.path.join(dest_dir, fname)
                else:
                    base, ext = os.path.splitext(fname)
                    backup_path = os.path.join(backup_dir, fname)
                    i = 1
                    while os.path.exists(backup_path):
                        backup_path = os.path.join(backup_dir, f"{base}_{i}{ext}")
                        i += 1

                try:
                    shutil.copy2(path, backup_path)
                    os.remove(path)
                    logging.info(f"Duplicate removed: {path} → Backup: {backup_path}")
                    duplicate_count += 1
                except PermissionError:
                    logging.warning(f"File locked: {path}. Skipped.")
                    skipped_count += 1
                except Exception as e:
                    logging.error(f"Error processing {path}: {e}")
                    skipped_count += 1
            else:
                file_hashes[file_hash] = path

            processed += 1
            if progress_callback:
                try:
                    progress_callback(processed, total_files)
                except Exception:
                    pass
            if status_callback:
                try:
                    status_callback(fname)
                except Exception:
                    pass

    logging.info(f"Total {duplicate_count} duplicates deleted, {skipped_count} skipped.")
    return duplicate_count, skipped_count

# --- GUI Functions ---
def select_folder():
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        txt_folder_path.delete(0, tk.END)
        txt_folder_path.insert(0, folder_selected)

def start_process():
    global cancel_flag
    cancel_flag = False

    source_dir = txt_folder_path.get()
    if not source_dir or not os.path.isdir(source_dir):
        messagebox.showerror("Error", "Please select a valid folder")
        return

    backup_dir = os.path.join(source_dir, "backup_duplicates")
    log_dir = os.path.join(source_dir, "logs")
    selected_hash = HASH_ALGORITHMS[hash_choice.get()]
    preserve = preserve_structure.get()

    btn_start.config(state=tk.DISABLED)
    btn_browse.config(state=tk.DISABLED)
    btn_cancel.config(state=tk.NORMAL)
    progress_var.set(0)
    lbl_status.config(text="Scanning for duplicates...")

    def progress_update(processed, total):
        percent = int(processed / total * 100)
        root.after(0, lambda: progress_var.set(percent))
        root.after(0, lambda: lbl_progress.config(text=f"{percent}% ({processed}/{total})"))

    def status_update(current_file):
        root.after(0, lambda: lbl_status.config(text=f"Processing: {current_file}..."))

    def worker():
        duplicates_deleted, skipped = remove_duplicate_files(
            source_dir, backup_dir, log_dir, selected_hash, preserve,
            progress_callback=progress_update,
            status_callback=status_update,
            log_text=log_text,
            verbose_mode=verbose_mode
        )
        root.after(0, lambda: lbl_status.config(
            text=f"Completed! {duplicates_deleted} duplicates removed, {skipped} skipped."))
        root.after(0, lambda: btn_start.config(state=tk.NORMAL))
        root.after(0, lambda: btn_browse.config(state=tk.NORMAL))
        root.after(0, lambda: btn_cancel.config(state=tk.DISABLED))

    threading.Thread(target=worker, daemon=True).start()

def cancel_process():
    global cancel_flag
    cancel_flag = True
    lbl_status.config(text="Cancelling... Please wait.")

def clear_log():
    log_text.config(state=tk.NORMAL)
    log_text.delete("1.0", tk.END)
    log_text.config(state=tk.DISABLED)

# --- GUI Layout ---
root = tk.Tk()
root.title("Duplicate File Remover")
root.geometry("800x650")  # More compact window
root.resizable(True, True)

# Create tooltip class
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind('<Enter>', self.enter)
        self.widget.bind('<Leave>', self.leave)

    def enter(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        
        label = ttk.Label(self.tooltip, text=self.text, style='ToolTip.TLabel')
        label.pack()

    def leave(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

# Style

def create_custom_style():
    style = ttk.Style()
    style.theme_use('clam')
    
    # Common styles
    style.configure('TFrame', background=CARD_BG)
    style.configure('App.TFrame', background=BG_COLOR)
    
    # Labels
    style.configure('TLabel', 
                   background=CARD_BG,
                   foreground=TEXT_COLOR, 
                   font=('Segoe UI', 10))
    style.configure('Header.TLabel',
                   background=BG_COLOR,
                   foreground=PRIMARY_COLOR,
                   font=('Segoe UI', 18, 'bold'))
    style.configure('Subheader.TLabel',
                   background=BG_COLOR,
                   foreground=SECONDARY_COLOR,
                   font=('Segoe UI', 12))
    
    # Buttons
    button_common = {
        'font': ('Segoe UI', 10, 'bold'),
        'borderwidth': 0,
        'relief': 'flat',
        'padding': (10, 6)  # More compact padding
    }
    
    style.configure('Primary.TButton',
                   **button_common,
                   background=PRIMARY_COLOR,
                   foreground='white')
    style.map('Primary.TButton',
              background=[('active', ACCENT_COLOR), ('pressed', ACCENT_COLOR)],
              relief=[('pressed', 'flat')],
              borderwidth=[('active', 0), ('pressed', 0)])
    
    style.configure('Secondary.TButton',
                   **button_common,
                   background=SECONDARY_COLOR,
                   foreground='white')
    style.map('Secondary.TButton',
              background=[('active', '#616161'), ('pressed', '#616161')],
              relief=[('pressed', 'flat')],
              borderwidth=[('active', 0), ('pressed', 0)])
    
    # Entry fields
    style.configure('TEntry',
                   fieldbackground='white',
                   background='white',
                   borderwidth=1,
                   relief='solid',
                   font=('Segoe UI', 10),
                   padding=3)  # More compact padding
    
    # Frames and cards
    style.configure('Card.TLabelframe',
                   background=CARD_BG,
                   foreground=TEXT_COLOR,
                   font=('Segoe UI', 11, 'bold'),
                   borderwidth=1,
                   relief='solid')
    style.configure('Card.TLabelframe.Label',
                   background=CARD_BG,
                   foreground=TEXT_COLOR,
                   font=('Segoe UI', 11, 'bold'))
    
    # Progress bar - more compact
    style.configure('Yellow.Horizontal.TProgressbar',
                   troughcolor='#f5f5f5',
                   background=WARNING_COLOR,
                   bordercolor=BORDER_COLOR,
                   lightcolor=WARNING_COLOR,
                   darkcolor=WARNING_COLOR,
                   thickness=6)  # Thinner progress bar
    
    style.configure('Green.Horizontal.TProgressbar',
                   troughcolor='#f5f5f5',
                   background=SUCCESS_COLOR,
                   bordercolor=BORDER_COLOR,
                   lightcolor=SUCCESS_COLOR,
                   darkcolor=SUCCESS_COLOR,
                   thickness=6)  # Thinner progress bar
                   
    # Tooltips style - new
    style.configure('ToolTip.TLabel',
                   background='#333333',
                   foreground='white',
                   font=('Segoe UI', 9),
                   padding=4)
    
    return style

style = create_custom_style()

root.option_add("*TButton*Cursor", "hand2")
root.option_add("*TButton*BorderWidth", 0)
root.option_add("*TEntry*BorderWidth", 2)
root.option_add("*TEntry*Relief", "flat")

root.configure(background=BG_COLOR)

main_frame = ttk.Frame(root, padding=15, style='App.TFrame')
main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

# Header - more compact
header_frame = ttk.Frame(main_frame)
header_frame.pack(fill=tk.X, pady=(0, 15))
ttk.Label(header_frame, text="🔍 Duplicate File Remover", style='Header.TLabel',
          background=BG_COLOR).pack(anchor=tk.CENTER, pady=(0, 2))
ttk.Label(header_frame, text="Scan and remove duplicate files efficiently", 
          style='Subheader.TLabel', background=BG_COLOR).pack(anchor=tk.CENTER)

# Folder selection - more compact
folder_frame = ttk.LabelFrame(main_frame, text="Folder Selection", padding=10, style='Card.TLabelframe')
folder_frame.pack(fill=tk.X, pady=(0, 15))
folder_grid = ttk.Frame(folder_frame)
folder_grid.pack(fill=tk.X)
ttk.Label(folder_grid, text="Source Folder:", style='TLabel').grid(row=0, column=0, padx=(0, 10), pady=5, sticky=tk.W)
txt_folder_path = ttk.Entry(folder_grid, width=50, font=('Segoe UI', 10))
txt_folder_path.grid(row=0, column=1, padx=(0, 10), pady=5, sticky=tk.EW)
btn_browse = ttk.Button(folder_grid, text="📂 Browse", command=select_folder, style='Secondary.TButton')
btn_browse.grid(row=0, column=2, padx=5, pady=5)
folder_grid.columnconfigure(1, weight=1)

# Options - more compact with tooltips
options_frame = ttk.LabelFrame(main_frame, text="Options", padding=10, style='Card.TLabelframe')
options_frame.pack(fill=tk.X, pady=(0, 15))
hash_choice = tk.StringVar(value="Secure (SHA256)")
preserve_structure = tk.BooleanVar(value=False)
verbose_mode = tk.BooleanVar(value=True)

# Hash Algorithm section - horizontal layout
options_grid = ttk.Frame(options_frame)
options_grid.pack(fill=tk.X, padx=5, pady=5)

hash_label = ttk.Label(options_grid, text="Hash Algorithm:", style='TLabel')
hash_label.pack(side=tk.LEFT, padx=(0, 10))

hash_frame = ttk.Frame(options_grid)
hash_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

rb_md5 = tk.Radiobutton(hash_frame, 
                        text="🚀 MD5 (Fast)", 
                        variable=hash_choice, 
                        value="Fast (MD5)", 
                        bg=CARD_BG, 
                        font=('Segoe UI', 10),
                        cursor="hand2")
rb_md5.pack(side=tk.LEFT, padx=(0, 15))
ToolTip(rb_md5, "Faster but less secure hash algorithm")

rb_sha = tk.Radiobutton(hash_frame, 
                        text="🔒 SHA256 (Secure)", 
                        variable=hash_choice, 
                        value="Secure (SHA256)", 
                        bg=CARD_BG, 
                        font=('Segoe UI', 10),
                        cursor="hand2")
rb_sha.pack(side=tk.LEFT)
ToolTip(rb_sha, "More secure but slower hash algorithm")

# Checkbuttons in a separate frame
check_frame = ttk.Frame(options_frame)
check_frame.pack(fill=tk.X, padx=5, pady=5)

preserve_check = ttk.Checkbutton(check_frame, 
                                text="📁 Preserve structure",
                                variable=preserve_structure,
                                style='TCheckbutton',
                                cursor="hand2")
preserve_check.pack(side=tk.LEFT, padx=(0, 20))
ToolTip(preserve_check, "Maintain folder hierarchy in backup location")

verbose_check = ttk.Checkbutton(check_frame, 
                               text="📝 Verbose logging",
                               variable=verbose_mode,
                               style='TCheckbutton',
                               cursor="hand2")
verbose_check.pack(side=tk.LEFT)
ToolTip(verbose_check, "Show detailed operation logs")

# Action buttons - compact row
action_frame = ttk.Frame(main_frame, style='App.TFrame')
action_frame.pack(fill=tk.X, pady=(0, 15))

btn_start = ttk.Button(action_frame, 
                      text="▶ Start",
                      command=start_process, 
                      style='Primary.TButton')
btn_start.pack(side=tk.LEFT, padx=(0, 10))
ToolTip(btn_start, "Start scanning and removing duplicates")

btn_cancel = ttk.Button(action_frame, 
                       text="⏹",
                       command=cancel_process, 
                       style='Secondary.TButton',
                       state=tk.DISABLED)
btn_cancel.pack(side=tk.LEFT, padx=(0, 10))
ToolTip(btn_cancel, "Cancel the current operation")

btn_clear = ttk.Button(action_frame, 
                      text="🗑",
                      command=clear_log, 
                      style='Secondary.TButton')
btn_clear.pack(side=tk.LEFT)
ToolTip(btn_clear, "Clear the activity log")

# Progress section - more compact
progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding=10, style='Card.TLabelframe')
progress_frame.pack(fill=tk.X, pady=(0, 15))

# Combined progress header and bar
progress_container = ttk.Frame(progress_frame)
progress_container.pack(fill=tk.X, padx=5, pady=5)

progress_left = ttk.Frame(progress_container)
progress_left.pack(side=tk.LEFT, fill=tk.X, expand=True)

# Progress header inline with bar
progress_header = ttk.Frame(progress_left)
progress_header.pack(fill=tk.X, pady=(0, 3))
ttk.Label(progress_header, text="📊 Scan Progress:", style='TLabel').pack(side=tk.LEFT)
lbl_progress = ttk.Label(progress_header, text="0%", style='TLabel', font=('Segoe UI', 10, 'bold'))
lbl_progress.pack(side=tk.RIGHT)

# Compact progress bar
progress_var = tk.IntVar()
progress_bar = ttk.Progressbar(progress_left, 
                             orient="horizontal", 
                             mode="determinate",
                             variable=progress_var, 
                             style="Yellow.Horizontal.TProgressbar")
progress_bar.pack(fill=tk.X)

# Status - inline
status_frame = ttk.Frame(progress_container)
status_frame.pack(side=tk.RIGHT, padx=(10, 0))
ttk.Label(status_frame, text="📝", style='TLabel').pack(side=tk.LEFT)
lbl_status = ttk.Label(status_frame, 
                      text="Ready to scan",
                      font=('Segoe UI', 10, 'italic'),
                      foreground=SECONDARY_COLOR)
lbl_status.pack(side=tk.LEFT, padx=(5, 0))

# Log frame with modern, compact styling
log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding=10, style='Card.TLabelframe')
log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

# Create a container frame for the log
log_container = ttk.Frame(log_frame)
log_container.pack(fill=tk.BOTH, expand=True)

# Text widget with modern styling - reduced height
log_text = tk.Text(log_container, 
                  height=10,  # Reduced height for compactness
                  wrap=tk.WORD, 
                  state=tk.DISABLED,
                  bg="#e1e1e1",  # VS Code-like dark background
                  fg="#000000",  # Light gray text
                  insertbackground="white",
                  font=('Cascadia Code', 10),  # Modern monospace font
                  padx=10,
                  pady=10,
                  relief='flat',
                  borderwidth=0)

# Modern scrollbar styling
log_scroll = ttk.Scrollbar(log_container, 
                          orient=tk.VERTICAL, 
                          command=log_text.yview)
log_text.configure(yscrollcommand=log_scroll.set)

# Pack scrollbar and text
log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# Configure log message styles with updated colors
log_text.tag_config("warning", foreground=WARNING_COLOR)
log_text.tag_config("error", foreground=ERROR_COLOR)
log_text.tag_config("info", foreground=INFO_COLOR)

# Compact footer with helpful note
footer_frame = ttk.Frame(main_frame, style='App.TFrame')
footer_frame.pack(fill=tk.X, pady=(5, 0))

footer_text = "💡 Duplicate files are safely moved to a backup folder"
ttk.Label(footer_frame, 
         text=footer_text,
         font=('Segoe UI', 9),
         foreground=SECONDARY_COLOR,
         background=BG_COLOR).pack(anchor=tk.CENTER, pady=(0, 2))

root.mainloop()

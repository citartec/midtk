import tkinter as tk
from tkinter import ttk, filedialog
import tkinter.font as tkfont
import tkinter.simpledialog as simpledialog
import mido
from mido import Message
import json
import threading
from queue import SimpleQueue  

# ---------------- Theme / constants ----------------
COL_BG = "#1e1e1e"
COL_FRAME = "#2e2e2e"
COL_ACCENT = "#bd6500"
COL_TEXT = "#686868"
COL_BTN_HOVER = "#444444"
COL_BTN = "#333333"
ICON_RESIZE = ""

# Placeholders — reassigned to named fonts after root is created:
ICON_FONT = ("Helvetica", 16)
COL_SLIDER_NAME = "#df4600"     # Colour for slider name entry
COL_SLIDER_VALUE = "#fc7100"    # Colour for value label
COL_BTN_DEFAULT = "#444444"     # grey when not latched
COL_BTN_LATCHED = "#ff8800"     # orange when latched
GRID_SIZE = 10
MIN_WIDTH = 50
MIN_HEIGHT = 20
# Placeholder — reassigned to named fonts after root is created:
BUTTON_FONT = ("Helvetica", 14, "bold")
BUTTON_FG = "#ffffff"
RADIO_PAD = 1

DRF_INSTANCES = []

# ---------------- Helpers (safe parsing / unassigned) ----------------
def _is_unassigned_cc(val) -> bool:
    """True if CC/note is not set (None, '', non-digit)."""
    if val is None:
        return True
    s = str(val).strip()
    return (s == "") or (not s.isdigit())

def _to_str_or_empty(val) -> str:
    """For tk.StringVar: keep '' for unassigned, else str(int)."""
    if _is_unassigned_cc(val):
        return ""
    try:
        return str(int(val))
    except Exception:
        return ""

def _to_int_or_none(val):
    """Return int(val) or None if unassigned/bad."""
    if _is_unassigned_cc(val):
        return None
    try:
        return int(val)
    except Exception:
        return None

# ---------------- Root / fonts ----------------
root = tk.Tk()

# Optional global scaling (1.0 default; bump for touch screens)
try:
    root.tk.call("tk", "scaling", 1.2)
except Exception:
    pass

# ---------- Global font setup ----------
FONT_FAMILY = "DejaVu Sans"
SIZE_UI      = 13
SIZE_LABEL   = 13
SIZE_HEADER  = 12
SIZE_VALUE   = 12
SIZE_BUTTON  = 14
SIZE_RADIO   = 16
SIZE_ICON    = 18

FONT_UI     = tkfont.Font(family=FONT_FAMILY, size=SIZE_UI)
FONT_LABEL  = tkfont.Font(family=FONT_FAMILY, size=SIZE_LABEL)
FONT_HEADER = tkfont.Font(family=FONT_FAMILY, size=SIZE_HEADER, weight="bold")
FONT_VALUE  = tkfont.Font(family=FONT_FAMILY, size=SIZE_VALUE)
FONT_BUTTON = tkfont.Font(family=FONT_FAMILY, size=SIZE_BUTTON, weight="bold")
FONT_RADIO  = tkfont.Font(family=FONT_FAMILY, size=SIZE_RADIO, weight="bold")
FONT_ICON   = tkfont.Font(family=FONT_FAMILY, size=SIZE_ICON)

root.option_add("*Font",              FONT_UI)
root.option_add("*Label.Font",        FONT_LABEL)
root.option_add("*Entry.Font",        FONT_UI)
root.option_add("*Button.Font",       FONT_BUTTON)
root.option_add("*Radiobutton.Font",  FONT_RADIO)
root.option_add("*Scale.Font",        FONT_UI)
root.option_add("*Menu.Font",         FONT_UI)

try:
    ttk.Style().configure(".", font=FONT_UI)
except Exception:
    pass

ICON_FONT   = FONT_ICON
BUTTON_FONT = FONT_RADIO

# Title / state
current_filename = tk.StringVar(value="blank")
root.title(f"Mid Tk - {current_filename.get()}")

root.geometry("700x777")
root.configure(bg=COL_BG)

locked = tk.BooleanVar(value=False)

output_names = mido.get_output_names()
input_names = mido.get_input_names()
print("Available MIDI inputs:", input_names)

midi_out = None
midi_queue = SimpleQueue()          # NEW: thread→UI queue
midi_in_thread = None               # NEW: single listener thread handle
midi_in_stop = threading.Event()    # NEW: stop signal for the listener

selected_port = tk.StringVar(value=output_names[0] if output_names else "")
selected_input_port = tk.StringVar(value=input_names[0] if input_names else "")

sliders = []
buttons = []
radio_groups = []

# ttk style (colors + font)
style = ttk.Style()
style.theme_use("default")
style.configure(
    "TCombobox",
    fieldbackground=COL_FRAME,
    background=COL_FRAME,
    foreground=COL_TEXT,
    arrowcolor=COL_ACCENT,
    selectbackground=COL_ACCENT,
    selectforeground=COL_BG,
    borderwidth=0,
    relief="flat",
    font=FONT_UI,
)
style.map(
    "TCombobox",
    fieldbackground=[("readonly", COL_FRAME)],
    background=[("active", COL_FRAME)],
    foreground=[("readonly", COL_TEXT)],
    arrowcolor=[("active", COL_ACCENT)],
)

def toggle_lock():
    locked.set(not locked.get())
    for fr in DRF_INSTANCES:
        fr.update_grips()
    print("Locked:", locked.get())

DEFAULT_WIDTH = MIN_WIDTH
DEFAULT_HEIGHT_SLIDER = 500
DEFAULT_HEIGHT_BUTTON = MIN_WIDTH
WIDGET_WIDTH = 60
SPAWN_GAP = 2

import time  # for lightweight motion throttling

# --- Guard to prevent MIDI echo/feedback when reflecting incoming MIDI to UI ---
UPDATING_FROM_MIDI = False

# --- Grouping support ---
group_boxes = []  # holds GroupBoxFrame instances

# ---- Scrollregion coalescing & suppression (ANTI-JITTER) ----
SR_SCHEDULED = False
SUPPRESS_SCROLL_UPDATES = False
# We temporarily unbind <Configure> on these to stop layout thrash during group moves
_CFG_BOUND = {"scrollable": True, "canvas": True}

# Larger touch-friendly scrollbars
SCROLLBAR_WIDTH = 20

# ---------------- Canvas + Scrollbars ----------------
canvas_container = tk.Frame(root, bg=COL_BG)
canvas_container.pack(fill="both", expand=True)

canvas_container.grid_rowconfigure(0, weight=1)
canvas_container.grid_columnconfigure(0, weight=1)

canvas = tk.Canvas(canvas_container, bg=COL_BG, highlightthickness=0)
canvas.grid(row=0, column=0, sticky="nsew")

def _on_canvas_configure(e):
    vw, vh = max(e.width, 1), max(e.height, 1)
    w = max(SR_W, vw + 1)
    h = max(SR_H, vh)
    canvas.itemconfig(window_id, width=w, height=h)
    canvas.configure(scrollregion=(0, 0, w, h))

canvas.bind("<Configure>", _on_canvas_configure)

v_scroll = tk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview, width=SCROLLBAR_WIDTH)
v_scroll.grid(row=0, column=1, sticky="ns")

h_scroll = tk.Scrollbar(canvas_container, orient="horizontal", command=canvas.xview, width=SCROLLBAR_WIDTH)
h_scroll.grid(row=1, column=0, sticky="ew")

canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

scrollable_frame = tk.Frame(canvas, bg=COL_BG)
window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

SR_W = 0
SR_H = 0
PADDING = 200
GROW_CHUNK = 2000

# Reserve Channel Mode CCs (120–127)
RESERVED_CCS = set(range(120, 128))

def _is_reserved_cc(val) -> bool:
    try:
        v = int(str(val).strip())
        return v in RESERVED_CCS
    except Exception:
        return False

def open_radio_group_setup(radio_group):
    DIALOG_PAD  = 6
    LIST_HEIGHT = 220

    win = tk.Toplevel(root)
    win.title("Edit MIDI Radio Group")
    win.configure(bg=COL_FRAME)
    win.resizable(False, True)

    mode_var        = radio_group.mode
    channel_var     = radio_group.channel
    orientation_var = radio_group.orientation
    num_var         = tk.IntVar(value=len(radio_group.button_data))

    existing_controls = [(_to_int_or_none(b.get("control"))) for b in radio_group.button_data]
    # if mixed/unassigned, show '' (empty) so user can pick one
    shared_ctrl = existing_controls[0] if existing_controls and all(c == existing_controls[0] for c in existing_controls) else None
    cc_all_var = tk.StringVar(value=_to_str_or_empty(shared_ctrl))

    entries = []

    top = tk.Frame(win, bg=COL_FRAME)
    top.pack(side="top", fill="x", padx=DIALOG_PAD, pady=DIALOG_PAD)

    tk.Label(top, text="MIDI Mode", bg=COL_FRAME, fg=COL_TEXT, font=FONT_LABEL)\
        .grid(row=0, column=0, sticky="w", padx=4, pady=2)
    ttk.Combobox(top, textvariable=mode_var, values=["CC", "Note", "Aftertouch"],
                 state="readonly", width=12)\
        .grid(row=0, column=1, sticky="w", padx=4, pady=2)

    tk.Label(top, text="Channel", bg=COL_FRAME, fg=COL_TEXT, font=FONT_LABEL)\
        .grid(row=1, column=0, sticky="w", padx=4, pady=2)
    ttk.Combobox(top, textvariable=channel_var, values=[str(i) for i in range(1, 17)],
                 state="readonly", width=4)\
        .grid(row=1, column=1, sticky="w", padx=4, pady=2)

    tk.Label(top, text="CC/Note", bg=COL_FRAME, fg=COL_TEXT, font=FONT_LABEL)\
        .grid(row=2, column=0, sticky="w", padx=4, pady=2)
    ttk.Combobox(top, textvariable=cc_all_var, values=[""] + [str(x) for x in range(0, 128)],
                 state="readonly", width=5)\
        .grid(row=2, column=1, sticky="w", padx=4, pady=2)

    tk.Label(top, text="Orientation", bg=COL_FRAME, fg=COL_TEXT, font=FONT_LABEL)\
        .grid(row=3, column=0, sticky="w", padx=4, pady=2)
    ttk.Combobox(top, textvariable=orientation_var, values=["vertical", "horizontal"],
                 state="readonly", width=12)\
        .grid(row=3, column=1, sticky="w", padx=4, pady=2)

    tk.Label(top, text="Number of Options", bg=COL_FRAME, fg=COL_TEXT, font=FONT_LABEL)\
        .grid(row=4, column=0, sticky="w", padx=4, pady=4)
    num_spin = tk.Spinbox(top, from_=1, to=64, textvariable=num_var, width=4, relief="flat",
                          bg=COL_BG, fg=COL_ACCENT, insertbackground=COL_ACCENT, font=FONT_UI)
    num_spin.grid(row=4, column=1, sticky="w", padx=4, pady=4)

    top.grid_columnconfigure(0, weight=0)
    top.grid_columnconfigure(1, weight=1)

    center = tk.Frame(win, bg=COL_FRAME)
    center.pack(side="top", fill="x", expand=False, padx=DIALOG_PAD, pady=(0, DIALOG_PAD))

    lst_canvas = tk.Canvas(center, bg=COL_FRAME, highlightthickness=0, height=LIST_HEIGHT)
    vsb = tk.Scrollbar(center, orient="vertical", command=lst_canvas.yview)

    list_frame = tk.Frame(lst_canvas, bg=COL_FRAME)
    list_frame.bind("<Configure>", lambda e: lst_canvas.configure(scrollregion=lst_canvas.bbox("all")))
    lst_canvas.create_window((0, 0), window=list_frame, anchor="nw")
    lst_canvas.configure(yscrollcommand=vsb.set)

    lst_canvas.pack(side="left", fill="x", expand=True)
    vsb.pack(side="right", fill="y")

    bottom = tk.Frame(win, bg=COL_FRAME)
    bottom.pack(side="bottom", fill="x", padx=DIALOG_PAD, pady=DIALOG_PAD)

    def bucket_mid(i: int, n: int) -> int:
        n = max(1, int(n))
        low  = (i * 128) // n
        high = ((i + 1) * 128) // n - 1
        if high < low: high = low
        return max(0, min(127, (low + high) // 2))

    def build_entries(recompute_values: bool):
        for w in list_frame.winfo_children(): w.destroy()
        entries.clear()

        try:
            n = max(1, int(num_var.get()))
        except Exception:
            n = 1

        hdr = {"bg": COL_FRAME, "fg": COL_TEXT, "font": FONT_HEADER}
        tk.Label(list_frame, text="Label", **hdr).grid(row=0, column=0, padx=4, pady=4, sticky="w")
        tk.Label(list_frame, text="Value (0–127)", **hdr).grid(row=0, column=1, padx=4, pady=4)

        keep_existing = (not recompute_values) and (n == len(radio_group.button_data))

        for i in range(n):
            label_var = tk.StringVar()
            val_var   = tk.StringVar()

            if i < len(radio_group.button_data) and keep_existing:
                bd = radio_group.button_data[i]
                label_var.set(bd.get("label", f"{i+1}"))
                val_var.set(str(int(bd.get("value", bucket_mid(i, n)))))
            else:
                label_var.set(radio_group.button_data[i]["label"] if i < len(radio_group.button_data) else f"{i+1}")
                val_var.set(str(bucket_mid(i, n)))

            tk.Entry(list_frame, textvariable=label_var, width=18,
                     bg=COL_BG, fg=COL_ACCENT, insertbackground=COL_ACCENT,
                     relief="flat", font=FONT_UI)\
                .grid(row=i+1, column=0, padx=4, pady=2, sticky="we")

            tk.Spinbox(list_frame, from_=0, to=127, textvariable=val_var, width=4, relief="flat",
                       bg=COL_BG, fg=COL_ACCENT, insertbackground=COL_ACCENT, font=FONT_UI)\
                .grid(row=i+1, column=1, padx=4, pady=2, sticky="w")

            entries.append((label_var, val_var))

        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_columnconfigure(1, weight=0)
        win.after_idle(lambda: lst_canvas.yview_moveto(0.0))

        win.update_idletasks()
        win.minsize(win.winfo_reqwidth(), win.winfo_reqheight())

    def apply_changes():
        shared_control = _to_int_or_none(cc_all_var.get())
        new_data = []
        for label, val in entries:
            try: v = int(val.get())
            except ValueError: v = 0
            v = max(0, min(127, v))
            new_data.append({"label": label.get(), "control": shared_control, "value": v})

        radio_group.button_data = new_data
        radio_group.orientation.set(orientation_var.get())
        radio_group.rebuild_controls()

        if radio_group.buttons:
            sel = radio_group.selected.get()
            if not (0 <= sel < len(radio_group.buttons)):
                radio_group.selected.set(0)
            radio_group.update_visuals()
        win.destroy()

    num_spin.config(command=lambda: build_entries(recompute_values=True))
    num_var.trace_add("write", lambda *_: build_entries(recompute_values=True))

    build_entries(recompute_values=True)

    tk.Button(bottom, text="Apply", command=apply_changes,
              bg=COL_ACCENT, fg=COL_TEXT, font=FONT_BUTTON,
              relief="flat", width=10).pack(side="right")

    # Center the dialog
    win.update_idletasks()
    root_x, root_y = root.winfo_x(), root.winfo_y()
    root_w, root_h = root.winfo_width(), root.winfo_height()
    win_w, win_h = win.winfo_width(), win.winfo_height()
    pos_x = root_x + (root_w // 2) - (win_w // 2)
    pos_y = root_y + (root_h // 2) - (win_h // 2)
    win.geometry(f"+{pos_x}+{pos_y}")

def update_scroll_region():
    global SR_W, SR_H
    max_right = 0
    max_bottom = 0
    for child in scrollable_frame.winfo_children():
        if isinstance(child, tk.Frame):
            child.update_idletasks()
            r = child.winfo_x() + child.winfo_width()
            b = child.winfo_y() + child.winfo_height()
            if r > max_right:  max_right = r
            if b > max_bottom: max_bottom = b

    needed_w = max_right + PADDING
    needed_h = max_bottom + PADDING

    vw = max(canvas.winfo_width(), 1)
    vh = max(canvas.winfo_height(), 1)

    if SR_W == 0: SR_W = vw + GROW_CHUNK
    if SR_H == 0: SR_H = vh + GROW_CHUNK

    if needed_w > SR_W - 100:
        SR_W = needed_w + GROW_CHUNK
    if needed_h > SR_H - 100:
        SR_H = needed_h + GROW_CHUNK

    w = max(SR_W, vw + 1)
    h = max(SR_H, vh)
    canvas.configure(scrollregion=(0, 0, w, h))
    canvas.itemconfig(window_id, width=w, height=h)

def _on_frame_configure(event):
    update_scroll_region()

scrollable_frame.bind("<Configure>", _on_frame_configure)

# ---- Mouse wheel bindings ----
def _on_mousewheel_windows_mac(event):
    units = -1 if event.delta > 0 else 1
    canvas.yview_scroll(units, "units")

def _on_mousewheel_linux_up(event):
    canvas.yview_scroll(-1, "units")

def _on_mousewheel_linux_down(event):
    canvas.yview_scroll(1, "units")

def _on_shift_wheel(event):
    step = -1 if getattr(event, "delta", 0) > 0 else 1
    canvas.xview_scroll(step, "units")

def _bind_wheels(_):
    canvas.bind_all("<MouseWheel>", _on_mousewheel_windows_mac)
    canvas.bind_all("<Button-4>", _on_mousewheel_linux_up)
    canvas.bind_all("<Button-5>", _on_mousewheel_linux_down)
    canvas.bind_all("<Shift-MouseWheel>", _on_shift_wheel)

def _unbind_wheels(_):
    canvas.unbind_all("<MouseWheel>")
    canvas.unbind_all("<Button-4>")
    canvas.unbind_all("<Button-5>")
    canvas.unbind_all("<Shift-MouseWheel>")

canvas.bind("<Enter>", _bind_wheels)
canvas.bind("<Leave>", _unbind_wheels)

def _safe_bg_menu(event):
    try:
        show_background_menu(event)  # defined in Part 2
    except NameError:
        pass

canvas.bind("<Button-3>", _safe_bg_menu)
scrollable_frame.bind("<Button-3>", _safe_bg_menu)

root.after_idle(update_scroll_region)

# ---------------- Spawn geometry helper ----------------
def get_spawn_geometry(widget_list, fallback_height):
    try:
        if widget_list:
            last_widget = widget_list[-1]["frame"] if isinstance(widget_list[-1], dict) else widget_list[-1].master
            last_widget.update_idletasks()
            last_x = int(last_widget.winfo_x())
            last_y = int(last_widget.winfo_y())
            last_width = int(last_widget.winfo_width())
            x = last_x + last_width + SPAWN_GAP
            y = last_y
        else:
            raise Exception
    except Exception:
        x, y = 10, 10

    x = max(0, round(x / GRID_SIZE) * GRID_SIZE)
    y = max(0, round(y / GRID_SIZE) * GRID_SIZE)
    return x, y, DEFAULT_WIDTH, fallback_height

class SliderProxy:
    def __init__(self, slider_entry):
        self.slider_entry = slider_entry
    def get_state(self):
        return slider_state(self.slider_entry)

# ---------------- Widgets ----------------
class MidiButtonFrame(tk.Frame):
    def __init__(self, master, state=None):
        super().__init__(master, bg=COL_FRAME)

        self.name = tk.StringVar(value=state["name"] if state else "?")
        self.mode = tk.StringVar(value=state["mode"] if state else "CC")
        self.channel = tk.StringVar(value=str(state["channel"]) if state else "1")
        # default UNASSIGNED control: empty string in UI (None in state)
        init_ctrl = state.get("control", None) if state else None
        self.control = tk.StringVar(value=_to_str_or_empty(init_ctrl))
        self.latch_mode = tk.BooleanVar(value=state["latch"] if state else False)

        self.latched = state.get("latched", False) if state else False
        self.value_on = 127
        self.value_off = 0

        self.button = tk.Button(
            self,
            text=self.name.get(),
            bg=COL_BTN_DEFAULT,
            fg=COL_TEXT,
            activebackground=COL_BTN_DEFAULT,
            activeforeground=COL_TEXT,
            font=FONT_BUTTON,
            relief="flat"
        )
        self.button.pack(fill="both", expand=True)

        if self.latch_mode.get() and self.latched:
            self.button.config(bg=COL_BTN_LATCHED, activebackground=COL_BTN_LATCHED)
        self.name.trace_add("write", lambda *_: self.button.config(text=self.name.get()))

        self.button.bind("<Button-1>", self.on_press)
        self.button.bind("<ButtonRelease-1>", self.on_release)
        self.button.bind("<Button-3>", self.show_context_menu)
        self.bind("<Button-3>", self.show_context_menu)

    def set_from_midi(self, value: int):
        """Update button UI/state from incoming MIDI *without* sending MIDI back."""
        v = int(value)
        if self.latch_mode.get():
            self.latched = (v >= 64)
            self.button.config(
                bg=COL_BTN_LATCHED if self.latched else COL_BTN_DEFAULT,
                activebackground=COL_BTN_LATCHED if self.latched else COL_BTN_DEFAULT
            )
        else:
            self.button.config(relief="sunken" if v > 0 else "flat")

    def on_press(self, event):
        if self.latch_mode.get():
            self.latched = not self.latched
            val = self.value_on if self.latched else self.value_off
            self.send_midi(val)
            self.button.config(
                bg=COL_BTN_LATCHED if self.latched else COL_BTN_DEFAULT,
                activebackground=COL_BTN_LATCHED if self.latched else COL_BTN_DEFAULT
            )
        else:
            self.send_midi(self.value_on)
            self.button.config(relief="sunken")

    def on_release(self, event):
        if not self.latch_mode.get():
            self.send_midi(self.value_off)
            self.button.config(relief="flat")

    def send_midi(self, val):
        # do nothing if CC/Note mode but control unassigned
        if self.mode.get() in ("CC", "Note") and _is_unassigned_cc(self.control.get()):
            return
        send_midi(val, self.channel, self.control, self.mode)

    def show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg=COL_FRAME, fg=COL_TEXT, activebackground=COL_ACCENT, font=FONT_UI)

        def open_setup():
            win = tk.Toplevel(self)
            win.title("Button Setup")
            win.configure(bg=COL_FRAME)
            win.geometry("300x230")

            tk.Label(win, text="Button Label", font=FONT_HEADER,
                     bg=COL_FRAME, fg=COL_TEXT).grid(row=0, column=0, padx=8, pady=6, sticky="e")
            tk.Entry(win, textvariable=self.name,
                     font=FONT_UI, bg=COL_BG, fg=COL_ACCENT,
                     insertbackground=COL_ACCENT, relief="flat").grid(row=0, column=1, padx=8, pady=6, sticky="w")

            tk.Label(win, text="Mode", font=FONT_HEADER,
                     bg=COL_FRAME, fg=COL_TEXT).grid(row=1, column=0, padx=8, pady=6, sticky="e")
            ttk.Combobox(win, textvariable=self.mode,
                         values=["CC", "Note", "Aftertouch"],
                         state="readonly", width=10).grid(row=1, column=1, padx=8, pady=6, sticky="w")

            tk.Label(win, text="Channel", font=FONT_HEADER,
                     bg=COL_FRAME, fg=COL_TEXT).grid(row=2, column=0, padx=8, pady=6, sticky="e")
            ttk.Combobox(win, textvariable=self.channel,
                         values=[str(i) for i in range(1, 17)],
                         state="readonly", width=4).grid(row=2, column=1, padx=8, pady=6, sticky="w")

            tk.Label(win, text="CC/Note", font=FONT_HEADER,
                     bg=COL_FRAME, fg=COL_TEXT).grid(row=3, column=0, padx=8, pady=6, sticky="e")
            ttk.Combobox(win, textvariable=self.control,
                         values=[""] + [str(i) for i in range(0, 128)],
                         state="readonly", width=5).grid(row=3, column=1, padx=8, pady=6, sticky="w")

            tk.Checkbutton(win, text="Latch Mode", variable=self.latch_mode,
                           bg=COL_FRAME, fg=COL_TEXT, selectcolor=COL_ACCENT,
                           activeforeground=COL_ACCENT, activebackground=COL_FRAME, font=FONT_UI).grid(
                row=4, column=0, columnspan=2, pady=(6, 4))

            tk.Button(win, text="Close", command=win.destroy,
                      bg=COL_ACCENT, fg=COL_TEXT, font=FONT_BUTTON,
                      relief="flat", width=12).grid(row=5, column=0, columnspan=2, pady=(10, 8))

        menu.add_command(label="MIDI Setup", command=open_setup)
        menu.add_command(label="Duplicate", command=lambda: duplicate(self))
        # IMPORTANT: list + UI cleanup
        menu.add_command(label="Delete", command=lambda: remove_button(self))
        menu.tk_popup(event.x_root, event.y_root)

    def get_state(self):
        if self.master:
            self.master.update_idletasks()
            info = self.master.place_info()
        else:
            info = {"x": 100, "y": 100, "width": 120, "height": 100}
        return {
            "name": self.name.get(),
            "mode": self.mode.get(),
            "channel": _to_channel_int_or_none(self.channel.get()),
            "control": _to_int_or_none(self.control.get()),  # None if unassigned
            "latch": self.latch_mode.get(),
            "latched": self.latched,
            "x": int(info.get("x", 100)),
            "y": int(info.get("y", 100)),
            "width": int(info.get("width", 120)),
            "height": int(info.get("height", 100)),
        }


class MidiRadioGroupFrame(tk.Frame):
    def __init__(self, master, state=None):
        super().__init__(master, bg=COL_FRAME)

        self.selected    = tk.IntVar(value=state["selected"] if state else 0)
        self.mode        = tk.StringVar(value=state["mode"] if state else "CC")
        self.channel     = tk.StringVar(value=str(state["channel"]) if state else "1")
        self.orientation = tk.StringVar(value=state.get("orientation", "vertical") if state else "vertical")

        def bucket_low(i: int, n: int) -> int:
            n = max(1, int(n))
            v = (i * 128) // n
            return 1 if v <= 0 else min(127, v)

        # Normalize button_data; allow unassigned control = None
        if state and "buttons" in state:
            raw = state["buttons"]
            n = max(len(raw), 1)
            self.button_data = []
            for i, b in enumerate(raw):
                ctrl = b.get("control", None)
                ctrl = None if _is_unassigned_cc(ctrl) else int(ctrl)
                self.button_data.append({
                    "label": b.get("label", f"{i+1}"),
                    "control": ctrl,
                    "value": int(b["value"]) if "value" in b else bucket_low(i, n),
                })
        else:
            n = 3
            self.button_data = [
                {"label": f"{i+1}", "control": None, "value": bucket_low(i, n)}
                for i in range(n)
            ]

        self.control_map = {}   # idx -> (label, control|None, value)
        self.buttons = []
        self.container = None

        self.rebuild_controls()
        self.selected.trace_add("write", lambda *_: self.update_visuals())
        self.update_visuals()

    def rebuild_controls(self):
        try:
            if getattr(self, "container", None) and self.container.winfo_exists():
                self.container.destroy()
        except Exception:
            pass

        self.control_map = {}
        self.buttons = []

        self.container = tk.Frame(self, bg=COL_FRAME)
        self.container.pack(fill="both", expand=True, padx=RADIO_PAD, pady=RADIO_PAD)
        self.container.pack_propagate(False)
        self.container.grid_propagate(False)

        for idx, data in enumerate(self.button_data):
            label   = data.get("label", f"{idx+1}")
            control = data.get("control", None)  # may be None
            value   = int(data.get("value", 0))
            self.control_map[idx] = (label, control, value)

            rb = tk.Radiobutton(
                self.container,
                text=label,
                variable=self.selected,
                value=idx,
                command=self.send_midi,
                indicatoron=0,
                font=BUTTON_FONT,
                bg=COL_BTN,
                fg=BUTTON_FG,
                selectcolor=COL_BTN_LATCHED,
                activebackground=COL_BTN_LATCHED,
                activeforeground=BUTTON_FG,
                relief="flat",
                bd=2,
            )
            self.buttons.append(rb)

        if self.orientation.get() == "horizontal":
            cols = len(self.buttons)
            for c in range(cols):
                self.container.grid_columnconfigure(c, weight=1, uniform="rb")
            self.container.grid_rowconfigure(0, weight=1, uniform="rb")
            for c, rb in enumerate(self.buttons):
                rb.grid(row=0, column=c, padx=RADIO_PAD, pady=RADIO_PAD, sticky="nsew")
        else:
            rows = len(self.buttons)
            for r in range(rows):
                self.container.grid_rowconfigure(r, weight=1, uniform="rb")
            self.container.grid_columnconfigure(0, weight=1, uniform="rb")
            for r, rb in enumerate(self.buttons):
                rb.grid(row=r, column=0, padx=RADIO_PAD, pady=RADIO_PAD, sticky="nsew")

        self.bind("<Button-3>", self.show_context_menu)
        for rb in self.buttons:
            rb.bind("<Button-3>", self.show_context_menu)

        self.update_idletasks()
        try:
            self.container.minsize(1, 1)
        except Exception:
            pass
        self.update_visuals()

    def update_visuals(self):
        sel = self.selected.get()
        for idx, rb in enumerate(self.buttons):
            is_sel = (idx == sel)
            rb.config(
                bg=COL_BTN_LATCHED if is_sel else COL_BTN,
                activebackground=COL_BTN_LATCHED if is_sel else COL_BTN
            )

    def _index_for_cc(self, control_num: int, value: int):
        cnum = int(control_num)
        candidates = []
        for idx, (_lbl, ctrl, val) in self.control_map.items():
            if ctrl is None:
                continue
            if int(ctrl) == cnum:
                candidates.append((idx, int(val)))
        if not candidates:
            return None
        value = max(0, min(127, int(value)))
        return min(candidates, key=lambda p: abs(p[1] - value))[0]

    def _index_for_note(self, note_num: int, velocity: int):
        nnum = int(note_num)
        candidates = []
        for idx, (_lbl, note, val) in self.control_map.items():
            if note is None:
                continue
            if int(note) == nnum:
                candidates.append((idx, int(val)))
        if not candidates:
            return None
        velocity = max(0, min(127, int(velocity)))
        return min(candidates, key=lambda p: abs(p[1] - velocity))[0]

    def set_from_midi_cc(self, control_num: int, value: int):
        idx = self._index_for_cc(control_num, value)
        if idx is not None and idx != self.selected.get():
            self.select_index_external(idx)

    def set_from_midi_note(self, note_num: int, velocity: int):
        idx = self._index_for_note(note_num, velocity)
        if idx is not None and idx != self.selected.get():
            self.select_index_external(idx)

    def select_index_external(self, idx: int):
        self.selected.set(idx)
        self.update_visuals()

    def send_midi(self):
        try:
            idx = self.selected.get()
            _, control, send_val = self.control_map[idx]
            value = max(0, min(127, int(send_val)))
            mode = self.mode.get()
            ch = int(self.channel.get()) - 1

            if mode == "CC":
                if control is None:
                    return
                msg = Message("control_change", channel=ch, control=int(control), value=value)
            elif mode == "Note":
                if control is None:
                    return
                msg = Message("note_on", channel=ch, note=int(control), velocity=value)
            elif mode == "Aftertouch":
                msg = Message("aftertouch", channel=ch, value=value)
            else:
                return

            if midi_out:
                midi_out.send(msg)
            print("Sent:", msg)
        except Exception as e:
            print("Radio MIDI send error:", e)

    def show_context_menu(self, event):
        try:
            menu = tk.Menu(self, tearoff=0, bg=COL_FRAME, fg=COL_TEXT, activebackground=COL_ACCENT, font=FONT_UI)
            menu.add_command(label="Edit Group Setup", command=lambda: open_radio_group_setup(self))
            menu.add_command(label="Duplicate", command=lambda: duplicate(self))  # clones only this radio group
            # IMPORTANT: proper cleanup so radio_groups list stays accurate
            menu.add_command(label="Delete", command=lambda: remove_radio_group_by_group(self))
            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def get_state(self):
        if self.master:
            self.master.update_idletasks()
            info = self.master.place_info()
        else:
            info = {"x": 100, "y": 100, "width": 200, "height": 200}
        return {
            "type": "radio",
            "mode": self.mode.get(),
            "channel": _to_channel_int_or_none(self.channel.get()),
            "selected": self.selected.get(),
            "buttons": self.button_data,
            "orientation": self.orientation.get(),
            "x": int(info.get("x", 100)),
            "y": int(info.get("y", 100)),
            "width": int(info.get("width", 200)),
            "height": int(info.get("height", 200)),
        }


#Part2

# ==== PART 2/2 — from show_background_menu() to end ====



def schedule_scroll_update():
    """Queue a single scrollregion update for the next idle moment."""
    global SR_SCHEDULED
    if SR_SCHEDULED or SUPPRESS_SCROLL_UPDATES:
        return
    SR_SCHEDULED = True
    root.after_idle(_perform_scroll_update)

def _perform_scroll_update():
    global SR_SCHEDULED
    SR_SCHEDULED = False
    if SUPPRESS_SCROLL_UPDATES:
        return
    update_scroll_region()  # defined in Part 1

def _begin_suppression():
    """Stop churn from <Configure> while we drag/resize groups."""
    global SUPPRESS_SCROLL_UPDATES, _CFG_BOUND
    SUPPRESS_SCROLL_UPDATES = True
    # Temporarily disable handlers that cause reflow
    if _CFG_BOUND["scrollable"]:
        try:
            scrollable_frame.unbind("<Configure>")
        except Exception:
            pass
        _CFG_BOUND["scrollable"] = False
    if _CFG_BOUND["canvas"]:
        try:
            canvas.unbind("<Configure>")
        except Exception:
            pass
        _CFG_BOUND["canvas"] = False

def _end_suppression():
    """Re-enable handlers and do exactly one scroll update."""
    global SUPPRESS_SCROLL_UPDATES, _CFG_BOUND
    SUPPRESS_SCROLL_UPDATES = False
    # Rebind the handlers we disabled
    try:
        canvas.bind("<Configure>", _on_canvas_configure)
    except Exception:
        pass
    try:
        scrollable_frame.bind("<Configure>", _on_frame_configure)
    except Exception:
        pass
    _CFG_BOUND["scrollable"] = True
    _CFG_BOUND["canvas"] = True
    schedule_scroll_update()


# ---------------- Background (canvas) context menu ----------------
def show_background_menu(event):
    menu = tk.Menu(root, tearoff=0, bg=COL_FRAME, fg=COL_TEXT, activebackground=COL_ACCENT, font=FONT_UI)
    menu.add_command(label="Add Slider", command=add_slider)
    menu.add_command(label="Add Button", command=add_midi_button)
    menu.add_command(label="Add Radio Group", command=add_radio_group)
    menu.add_command(label="Add Group Box", command=add_group_box)
    menu.add_separator()
    menu.add_command(label="Save Setup", command=save_state)
    menu.add_command(label="Load Setup", command=load_state)

    def _toggle_lock():
        toggle_lock()
    menu.add_separator()
    lock_label = "Unlock Controls" if locked.get() else "Lock Controls"
    menu.add_command(label=lock_label, command=_toggle_lock)

    if output_names:
        menu.add_separator()
        menu.add_command(label="Output Port")
        for port in output_names:
            menu.add_radiobutton(label=f"→ {port}", variable=selected_port, value=port, command=select_port)

    if input_names:
        menu.add_separator()
        menu.add_command(label="Input Port")
        for port in input_names:
            menu.add_radiobutton(label=f"← {port}", variable=selected_input_port, value=port, command=listen_midi_input)

    menu.tk_popup(event.x_root, event.y_root)

# ---------------- Utilities for CC assignment ----------------
def _collect_used_cc_for_channel(channel_int: int) -> set:
    """Return a set of CC numbers already used on a given 1-based MIDI channel."""
    used = set()

    # Sliders
    for entry in sliders:
        try:
            ch = _to_channel_int_or_none(entry["channel"].get())
            if ch == channel_int:
                c = entry["control"].get()
                if not _is_unassigned_cc(c):
                    used.add(int(c))
        except Exception:
            pass

    # Buttons
    for btn in buttons:
        try:
            ch = _to_channel_int_or_none(btn.channel.get())
            if ch == channel_int:
                c = btn.control.get()
                if not _is_unassigned_cc(c):
                    used.add(int(c))
        except Exception:
            pass

    # Radio groups
    for rg in radio_groups:
        try:
            g = rg["group"]
            ch = _to_channel_int_or_none(g.channel.get())
            if ch == channel_int:
                for bd in getattr(g, "button_data", []):
                    c = bd.get("control", None)
                    if c is not None and not _is_unassigned_cc(c):
                        used.add(int(c))
        except Exception:
            pass

    return used


def _next_free_cc_across_channels(start_channel: int = 1):
    """
    Find next available (channel, cc), scanning start_channel..16 then 1..start_channel-1,
    skipping Channel Mode CCs (120–127).
    """
    try:
        start_channel = int(start_channel)
    except Exception:
        start_channel = 1
    start_channel = max(1, min(16, start_channel))

    for off in range(16):
        ch = ((start_channel - 1 + off) % 16) + 1
        used = _collect_used_cc_for_channel(ch)
        for cc in range(128):
            if cc in RESERVED_CCS:
                continue
            if cc not in used:
                return ch, cc
    return None, None

def _next_free_cc(used: set):
    for cc in range(0, 128):
        if cc not in used:
            used.add(cc)
            return cc
    return None  # exhausted

# ---------------- Adders / Duplicator ----------------
def add_radio_group(state=None):
    """Spawn a radio group. Controls default to unassigned (None)."""
    frame = DraggableResizableFrame(scrollable_frame, bg=COL_FRAME, bd=2, relief="ridge")

    if state:
        x, y = state.get("x", 100), state.get("y", 100)
        w, h = state.get("width", 220), state.get("height", 200)
    else:
        x, y, w, h = get_spawn_geometry(radio_groups, 200)

    frame.place(x=x, y=y, width=w, height=h)

    radio_group = MidiRadioGroupFrame(frame, state)
    radio_group.pack(fill="both", expand=True, padx=4, pady=4)

    # Right-click anywhere on the frame or group shows its menu
    for wdg in (frame, radio_group):
        wdg.bind("<Button-3>", lambda e, rg=radio_group: rg.show_context_menu(e))

    radio_groups.append({"frame": frame, "group": radio_group})

    # If the group is inside a group box, try assigning missing CCs now
    _maybe_assign_for_containing_group_box(frame)

    schedule_scroll_update()


def add_slider(state=None):
    """Spawn a slider. CC defaults to unassigned (empty string)."""
    frame = DraggableResizableFrame(scrollable_frame, bg=COL_FRAME, bd=2, relief="ridge")

    if state:
        x, y = state.get("x", 10), state.get("y", 10)
        w, h = state.get("width", DEFAULT_WIDTH), state.get("height", DEFAULT_HEIGHT_SLIDER)
    else:
        x, y, w, h = get_spawn_geometry(sliders, DEFAULT_HEIGHT_SLIDER)

    frame.place(x=x, y=y, width=w, height=h)

    container = tk.Frame(frame, bg=COL_FRAME)
    container.pack(fill="both", expand=True, padx=4, pady=4)
    container.pack_propagate(False)

    container.grid_rowconfigure(0, weight=0)  # name
    container.grid_rowconfigure(1, weight=0)  # value
    container.grid_rowconfigure(2, weight=1)  # slider stretches
    container.grid_columnconfigure(0, weight=1)

    # --------- Vars (default CC unassigned = "") ----------
    mode_var    = tk.StringVar(value=(state["mode"] if state and "mode" in state else "CC"))
    channel_var = tk.StringVar(value=str(state["channel"]) if state and "channel" in state else "1")
    ctrl_seed   = state.get("control", None) if state else None
    control_var = tk.StringVar(value=_to_str_or_empty(ctrl_seed))
    name_var    = tk.StringVar(value=state.get("name", "Slider") if state else "Slider")

    name_entry = tk.Entry(container, textvariable=name_var, font=FONT_HEADER,
                          bg=COL_FRAME, fg=COL_SLIDER_NAME, insertbackground=COL_SLIDER_NAME,
                          relief="flat", highlightthickness=0, justify="center")
    name_entry.grid(row=0, column=0, sticky="we")

    value_var = tk.StringVar(value=str(state.get("value", 0) if state else 0))
    value_label = tk.Label(container, textvariable=value_var,
                           font=FONT_VALUE, bg=COL_FRAME, fg=COL_SLIDER_VALUE)
    value_label.grid(row=1, column=0, sticky="we")

    val_slider = tk.Scale(
        container, from_=127, to=0, orient=tk.VERTICAL,
        sliderlength=32,
        font=FONT_UI,
        troughcolor=COL_BG, fg=COL_ACCENT, bg=COL_FRAME,
        highlightthickness=0, bd=0, activebackground=COL_ACCENT,
        showvalue=0
    )
    val_slider.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)

    if state and "value" in state:
        try:
            val_slider.set(int(state["value"]))
        except Exception:
            pass

    def update_val(val, ch=channel_var, ctrl=control_var, mode=mode_var):
        value_var.set(val)
        if UPDATING_FROM_MIDI:
            return
        send_midi(val, ch, ctrl, mode)

    val_slider.config(command=update_val)

    slider_entry = {
        "frame": frame,
        "container": container,
        "slider": val_slider,
        "mode": mode_var,
        "channel": channel_var,
        "control": control_var,
        "name": name_var,
        "name_entry": name_entry,
    }
    # backref for resize logic
    val_slider._slider_entry_ref = slider_entry
    sliders.append(slider_entry)

    # Context menu on right click
    for wdg in (frame, container, name_entry, value_label, val_slider):
        wdg.bind("<Button-3>", lambda e, s=slider_entry: show_context_menu(e, s))

    resize_slider(slider_entry)
    root.after_idle(lambda: resize_slider(slider_entry))

    # If inside a group box, try assigning any missing CC now
    _maybe_assign_for_containing_group_box(frame)

    schedule_scroll_update()
    return slider_entry


def add_midi_button(state=None):
    """Spawn a button. CC defaults to unassigned ('')."""
    frame = DraggableResizableFrame(scrollable_frame, bg=COL_FRAME, bd=2, relief="ridge")
    if state:
        x = state.get("x", 100)
        y = state.get("y", 100)
        w = state.get("width", DEFAULT_WIDTH)
        h = state.get("height", DEFAULT_HEIGHT_BUTTON)
    else:
        x, y, w, h = get_spawn_geometry(buttons, DEFAULT_HEIGHT_BUTTON)

    frame.place(x=x, y=y, width=w, height=h)

    button = MidiButtonFrame(frame, state or {})
    button.pack(fill="both", expand=True, padx=4, pady=4)

    buttons.append(button)

    frame.bind("<Button-3>", lambda e, b=button: b.show_context_menu(e))

    # If inside a group box, try assigning any missing CC now
    _maybe_assign_for_containing_group_box(frame)

    schedule_scroll_update()


def duplicate(widget):
    """Duplicate a widget next to the original, but clear its CC/Note assignment."""
    if not hasattr(widget, "get_state"):
        print("Cannot duplicate: missing get_state()")
        return

    state = widget.get_state()

    # ---- Clear CC/Note so the duplicate starts unassigned ----
    if isinstance(widget, MidiButtonFrame):
        state["control"] = None  # Button: clear CC/Note
    elif isinstance(widget, MidiRadioGroupFrame):
        for bd in state.get("buttons", []):
            bd["control"] = None   # Radio: clear each option's control
    else:
        # Slider (via SliderProxy)
        state["control"] = None

    # ---- Place next to the original and spawn ----
    if isinstance(widget, MidiButtonFrame):
        x, y, _, _ = get_spawn_geometry(buttons, DEFAULT_HEIGHT_BUTTON)
        state["x"] = x
        state["y"] = y
        add_midi_button(state)

    elif isinstance(widget, MidiRadioGroupFrame):
        x, y, _, _ = get_spawn_geometry([], 200)
        state["x"] = x
        state["y"] = y
        add_radio_group(state)

    else:
        x, y, _, _ = get_spawn_geometry(sliders, DEFAULT_HEIGHT_SLIDER)
        state["x"], state["y"] = x, y
        add_slider(state)
        resize_slider(sliders[-1])


def _drf_bbox(drf):
    drf.update_idletasks()
    x, y = drf.winfo_x(), drf.winfo_y()
    return x, y, x + drf.winfo_width(), y + drf.winfo_height()

def _rect_contains_point(rect, px, py):
    x1, y1, x2, y2 = rect
    return (x1 <= px <= x2) and (y1 <= py <= y2)

def _identify_widget_for_drf(drf):
    # 1) Direct children that are custom widgets
    for ch in drf.winfo_children():
        if isinstance(ch, MidiButtonFrame):
            return ("button", ch)
        if isinstance(ch, MidiRadioGroupFrame):
            return ("radio", ch)

    # 2) Slider: look for a Scale anywhere inside this DRF
    for ch in drf.winfo_children():
        # direct scale?
        if isinstance(ch, tk.Scale) and hasattr(ch, "_slider_entry_ref"):
            return ("slider", ch._slider_entry_ref)
        # nested frames containing a scale?
        if isinstance(ch, tk.Frame):
            for sub in ch.winfo_children():
                if isinstance(sub, tk.Scale) and hasattr(sub, "_slider_entry_ref"):
                    return ("slider", sub._slider_entry_ref)

    return (None, None)

def _iter_member_frames():
    for child in scrollable_frame.winfo_children():
        if isinstance(child, DraggableResizableFrame) and not getattr(child, "is_group_box", False):
            yield child

def _maybe_assign_for_containing_group_box(drf):
    """If this widget frame lives inside any group box, trigger assignment there."""
    for gb in group_boxes:
        gx1, gy1, gx2, gy2 = _drf_bbox(gb)
        x1, y1, x2, y2 = _drf_bbox(drf)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        if _rect_contains_point((gx1, gy1, gx2, gy2), cx, cy):
            gb.compute_members()  # this will apply channel & assign missing CCs
            gb._redraw()
            break

# ---------------- Draggable/Resizable container ----------------
class DraggableResizableFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        DRF_INSTANCES.append(self)

        self._drag_data = {"x": 0, "y": 0}
        self._resize_data = {
            "active": False, "corner": None,
            "x": 0, "y": 0, "w": 0, "h": 0, "absx": 0, "absy": 0
        }

        self.grips = {
            "nw": tk.Label(self, bg=COL_ACCENT, width=1, height=1, cursor="top_left_corner"),
            "ne": tk.Label(self, bg=COL_ACCENT, width=1, height=1, cursor="top_right_corner"),
            "se": tk.Label(self, bg=COL_ACCENT, width=1, height=1, cursor="bottom_right_corner"),
            "sw": tk.Label(self, bg=COL_ACCENT, width=1, height=1, cursor="bottom_left_corner"),
        }
        for corner in ("nw", "ne", "se", "sw"):
            self.grips[corner].bind("<ButtonPress-1>", lambda e, c=corner: self.start_resize(e, c))
            self.grips[corner].bind("<B1-Motion>", self.do_resize)
            self.grips[corner].bind("<ButtonRelease-1>", self.stop_resize)

        self.update_grips()

        self.bind("<Button-1>", self.start_drag)
        self.bind("<B1-Motion>", self.do_drag)
        self.bind("<ButtonRelease-1>", self.snap_to_grid)

    def destroy(self):
        try:
            if self in DRF_INSTANCES:
                DRF_INSTANCES.remove(self)
        except Exception:
            pass
        super().destroy()

    def update_grips(self):
        for g in list(self.grips.values()):
            try:
                if g.winfo_exists():
                    g.place_forget()
            except Exception:
                pass

        if not locked.get():
            size = 10
            try:
                if self.grips["nw"].winfo_exists():
                    self.grips["nw"].place(relx=0.0, rely=0.0, anchor="nw", width=size, height=size)
                if self.grips["ne"].winfo_exists():
                    self.grips["ne"].place(relx=1.0, rely=0.0, anchor="ne", width=size, height=size)
                if self.grips["se"].winfo_exists():
                    self.grips["se"].place(relx=1.0, rely=1.0, anchor="se", width=size, height=size)
                if self.grips["sw"].winfo_exists():
                    self.grips["sw"].place(relx=0.0, rely=1.0, anchor="sw", width=size, height=size)
                for g in self.grips.values():
                    try:
                        if g.winfo_exists():
                            g.lift()
                    except Exception:
                        pass
            except Exception:
                pass

    def start_drag(self, event):
        if locked.get() or self._resize_data["active"]:
            return
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def do_drag(self, event):
        if locked.get() or self._resize_data["active"]:
            return
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.winfo_x() + dx
        y = self.winfo_y() + dy
        self.place(x=x, y=y)
        schedule_scroll_update()

    def snap_to_grid(self, event):
        if self._resize_data["active"]:
            return
        x = round(self.winfo_x() / GRID_SIZE) * GRID_SIZE
        y = round(self.winfo_y() / GRID_SIZE) * GRID_SIZE
        self.place(x=x, y=y)
        schedule_scroll_update()

        # NEW: refresh group memberships after any widget finishes moving
        try:
            for gb in group_boxes:
                gb.compute_members()
                gb._redraw()
        except Exception:
            pass

    def start_resize(self, event, corner):
        if locked.get():
            return
        _begin_suppression()  # smoother while any DRF is resizing
        self._resize_data.update({
            "active": True, "corner": corner, "x": event.x_root, "y": event.y_root,
            "w": self.winfo_width(), "h": self.winfo_height(),
            "absx": self.winfo_x(), "absy": self.winfo_y(),
        })

    def do_resize(self, event):
        rd = self._resize_data
        if not rd["active"]:
            return
        dx = event.x_root - rd["x"]
        dy = event.y_root - rd["y"]

        new_x, new_y = rd["absx"], rd["absy"]
        new_w, new_h = rd["w"], rd["h"]

        c = rd["corner"]
        if c == "se":
            new_w = rd["w"] + dx; new_h = rd["h"] + dy
        elif c == "ne":
            new_w = rd["w"] + dx; new_h = rd["h"] - dy; new_y = rd["absy"] + dy
        elif c == "sw":
            new_w = rd["w"] - dx; new_h = rd["h"] + dy; new_x = rd["absx"] + dx
        elif c == "nw":
            new_w = rd["w"] - dx; new_h = rd["h"] - dy; new_x = rd["absx"] + dx; new_y = rd["absy"] + dy

        new_w = max(MIN_WIDTH, round(new_w / GRID_SIZE) * GRID_SIZE)
        new_h = max(MIN_HEIGHT, round(new_h / GRID_SIZE) * GRID_SIZE)
        new_x = round(new_x / GRID_SIZE) * GRID_SIZE
        new_y = round(new_y / GRID_SIZE) * GRID_SIZE

        self.place(x=new_x, y=new_y, width=new_w, height=new_h)
        schedule_scroll_update()

        # Resize-aware children (sliders)
        for widget in self.winfo_children():
            if isinstance(widget, tk.Frame):
                for sub in widget.winfo_children():
                    if isinstance(sub, tk.Scale) and hasattr(sub, "_slider_entry_ref"):
                        resize_slider(sub._slider_entry_ref)

    def stop_resize(self, event):
        self._resize_data["active"] = False
        _end_suppression()
        schedule_scroll_update()


# ---------------- Group Box ----------------
def remove_button(button_frame):
    try:
        buttons.remove(button_frame)
    except ValueError:
        pass
    try:
        button_frame.master.destroy()
    except Exception:
        pass

def remove_radio_group_by_group(group_widget):
    target = None
    for rg in radio_groups:
        if rg["group"] is group_widget:
            target = rg
            break
    if target:
        try:
            radio_groups.remove(target)
        except ValueError:
            pass
        try:
            target["frame"].destroy()
        except Exception:
            pass

class GroupBoxFrame(DraggableResizableFrame):
    """A lasso-like box that groups widgets whose centers lie inside it.
       Always kept under other controls."""
    def __init__(self, parent, title="Group", state=None, **kwargs):
        kwargs.pop("title", None)
        super().__init__(parent, **kwargs)
        self.is_group_box = True

        group_title = state.get("title", title) if state else title
        self.title   = tk.StringVar(value=group_title)
        self.channel = state.get("channel", 1) if state else 1
        self.members = []
        self._last_motion_ts = 0.0

        initial_lock = bool(state.get("lock_ccs", False)) if state else False
        self.auto_assign_ccs = tk.BooleanVar(value=not initial_lock)
        self._lock_var = tk.BooleanVar(value=initial_lock)
        def _sync_lock_to_auto(*_): self.auto_assign_ccs.set(not self._lock_var.get())
        self._lock_var.trace_add("write", lambda *_: _sync_lock_to_auto())

        self._cnv = tk.Canvas(self, bg=COL_BG, highlightthickness=0, bd=0)
        self._cnv.pack(fill="both", expand=True)

        self._title_label_var = tk.StringVar()
        self._title = tk.Label(self, textvariable=self._title_label_var,
                               bg=COL_BG, fg=COL_ACCENT, font=FONT_LABEL, anchor="w")
        self._title.place(x=6, y=4)
        self.update_channel_label()

        for src in (self, self._cnv, self._title):
            src.bind("<Button-1>", self._on_press)
            src.bind("<B1-Motion>", self.do_drag)
            src.bind("<ButtonRelease-1>", self.snap_to_grid)
            src.bind("<Button-3>", self._show_menu)

        self.bind("<Configure>", lambda e: self._redraw())
        self.compute_members()
        self._redraw()
        try: self.lower()
        except Exception: pass

    def update_channel_label(self):
        lock_txt = " (locked)" if self._lock_var.get() else ""
        self._title_label_var.set(f"{self.title.get()} — Ch {self.channel}{lock_txt}")

    def _redraw(self):
        self._cnv.delete("all")
        w = max(1, self.winfo_width() - 1)
        h = max(1, self.winfo_height() - 1)
        self._cnv.create_rectangle(1, 1, w, h, outline=COL_ACCENT, width=2, dash=(5, 4))
        try: self._title.lift()
        except Exception: pass

    def update_grips(self):
        super().update_grips()
        try: self.lower()
        except Exception: pass

    def compute_members(self):
        gx1, gy1, gx2, gy2 = _drf_bbox(self)
        self.members = []
        for drf in _iter_member_frames():
            x1, y1, x2, y2 = _drf_bbox(drf)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            if _rect_contains_point((gx1, gy1, gx2, gy2), cx, cy):
                self.members.append(drf)
        self.apply_channel_to_members()
        if self.auto_assign_ccs.get():
            self._assign_missing_ccs_from_first_free()

    def apply_channel_to_members(self):
        for m in self.members:
            wtype, payload = _identify_widget_for_drf(m)
            try:
                if wtype == "slider" and "channel" in payload and "control" in payload:
                    if _is_unassigned_cc(payload["control"].get()) or _is_unassigned_ch(payload["channel"].get()):
                        payload["channel"].set(str(self.channel))
                elif wtype == "button":
                    if _is_unassigned_cc(payload.control.get()) or _is_unassigned_ch(payload.channel.get()):
                        payload.channel.set(str(self.channel))
                elif wtype == "radio":
                    needs_ctrl = any(_is_unassigned_cc(b.get("control", None)) for b in payload.button_data)
                    if needs_ctrl or _is_unassigned_ch(payload.channel.get()):
                        payload.channel.set(str(self.channel))
            except Exception as e:
                print(f"Failed to apply channel to {wtype}: {e}")

    def _assign_missing_ccs_from_first_free(self):
        """
        Assign controls to any members that are missing them.
        If the current group channel is full, roll over to the next channel,
        set the member's channel accordingly, and continue.
        """
        def _claim_slot():
            base_ch = _to_ch_or_default(self.channel)
            ch, cc = _next_free_cc_across_channels(base_ch)
            if ch is None:
                return (None, None)
            return ch, cc

        # sliders
        for m in self.members:
            wtype, payload = _identify_widget_for_drf(m)
            if wtype == "slider":
                try:
                    ctrl_var = payload.get("control")
                    if _is_unassigned_cc(ctrl_var.get()):
                        ch, cc = _claim_slot()
                        if ch is None:
                            print("No free CCs left on any channel."); return
                        payload["channel"].set(str(ch))
                        ctrl_var.set(str(cc))
                except Exception as e:
                    print("Assign-missing CC (slider) failed:", e)

        # buttons
        for m in self.members:
            wtype, payload = _identify_widget_for_drf(m)
            if wtype == "button":
                try:
                    if _is_unassigned_cc(payload.control.get()):
                        ch, cc = _claim_slot()
                        if ch is None:
                            print("No free CCs left on any channel."); return
                        payload.channel.set(str(ch))
                        payload.control.set(str(cc))
                except Exception as e:
                    print("Assign-missing CC (button) failed:", e)

        # radios: same CC for all options; also set group channel to the chosen one
        for m in self.members:
            wtype, payload = _identify_widget_for_drf(m)
            if wtype == "radio":
                try:
                    btns = payload.button_data
                    needs = any(_is_unassigned_cc(b.get("control", None)) for b in btns)
                    if needs:
                        ch, cc = _claim_slot()
                        if ch is None:
                            print("No free CCs left on any channel."); return
                        payload.channel.set(str(ch))
                        for bd in btns:
                            bd["control"] = int(cc)
                        payload.rebuild_controls()
                        payload.update_visuals()
                except Exception as e:
                    print("Assign-missing CC (radio) failed:", e)
                    
    def _on_press(self, event):
        if locked.get() or getattr(self, "_resize_data", {}).get("active"): return
        _begin_suppression()
        self._drag_data["x"] = event.x; self._drag_data["y"] = event.y
        self._start_pos = (self.winfo_x(), self.winfo_y())
        self._member_starts = {m: (m.winfo_x(), m.winfo_y()) for m in self.members}
        self._last_motion_ts = 0.0

    def do_drag(self, event):
        if locked.get() or getattr(self, "_resize_data", {}).get("active"): return
        import time
        now = time.time()
        if (now - self._last_motion_ts) < 0.01: return
        self._last_motion_ts = now
        dx = event.x - self._drag_data["x"]; dy = event.y - self._drag_data["y"]
        new_x = self.winfo_x() + dx; new_y = self.winfo_y() + dy
        self.place(x=new_x, y=new_y)
        off_x = new_x - self._start_pos[0]; off_y = new_y - self._start_pos[1]
        for m, (mx, my) in self._member_starts.items():
            m.place(x=mx + off_x, y=my + off_y)

    def snap_to_grid(self, event):
        if getattr(self, "_resize_data", {}).get("active"): return
        gx = round(self.winfo_x() / GRID_SIZE) * GRID_SIZE
        gy = round(self.winfo_y() / GRID_SIZE) * GRID_SIZE
        dx = gx - self.winfo_x(); dy = gy - self.winfo_y()
        self.place(x=gx, y=gy)
        for m in self.members:
            m.place(x=m.winfo_x() + dx, y=m.winfo_y() + dy)
        _end_suppression()
        self.compute_members(); self._redraw()

    def stop_resize(self, event):
        super().stop_resize(event)
        self.compute_members(); self._redraw(); _end_suppression()

    def _show_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg=COL_FRAME, fg=COL_TEXT, activebackground=COL_ACCENT, font=FONT_UI)
        menu.add_command(label="Rename Group", command=self._rename)
        menu.add_command(label="Edit Channel", command=self._edit_channel)
        menu.add_command(label="Recompute Members", command=self.compute_members)
        menu.add_checkbutton(
            label="Lock CCs (stop auto-assign)",
            onvalue=True, offvalue=False,
            variable=self._lock_var,
            command=self.update_channel_label
        )
        menu.add_command(label="Reassign Missing CCs Now",
                         command=lambda: (self._assign_missing_ccs_from_first_free(), self._redraw()))
        menu.add_separator()
        menu.add_command(label="Duplicate Box + Members", command=self.duplicate_group_box)
        menu.add_separator()
        menu.add_command(label="Delete Groupbox and Contents", command=self.delete_group_and_contents)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _rename(self):
        top = tk.Toplevel(self); top.title("Group Name"); top.configure(bg=COL_FRAME)
        tk.Label(top, text="Title", bg=COL_FRAME, fg=COL_TEXT, font=FONT_LABEL).grid(row=0, column=0, padx=8, pady=8)
        e = tk.Entry(top, textvariable=self.title, bg=COL_BG, fg=COL_ACCENT, insertbackground=COL_ACCENT, relief="flat")
        e.grid(row=0, column=1, padx=8, pady=8)
        def close_and_update(): self.update_channel_label(); top.destroy()
        tk.Button(top, text="Close", command=close_and_update,
                  bg=COL_ACCENT, fg=COL_TEXT, font=FONT_BUTTON, relief="flat").grid(
            row=1, column=0, columnspan=2, pady=8)

    def _edit_channel(self):
        win = tk.Toplevel(self); win.title("Group MIDI Channel"); win.configure(bg=COL_FRAME)
        win.geometry("240x120"); win.resizable(False, False)
        tk.Label(win, text="MIDI Channel", bg=COL_FRAME, fg=COL_TEXT, font=FONT_LABEL)\
            .grid(row=0, column=0, padx=12, pady=12, sticky="w")
        ch_var = tk.StringVar(value=str(self.channel))
        ttk.Combobox(win, textvariable=ch_var, values=[str(i) for i in range(1, 17)],
                     state="readonly", width=5)\
            .grid(row=0, column=1, padx=12, pady=12, sticky="w")
        def apply_and_close():
            try:
                self.channel = int(ch_var.get())
                self.apply_channel_to_members()
                if self.auto_assign_ccs.get():
                    self._assign_missing_ccs_from_first_free()
                self.update_channel_label()
            finally:
                win.destroy()
        tk.Button(win, text="Apply", command=apply_and_close,
                  bg=COL_ACCENT, fg=COL_TEXT, font=FONT_BUTTON, relief="flat", width=10)\
            .grid(row=1, column=0, columnspan=2, pady=(0, 12))

    def delete_group_and_contents(self):
        self.compute_members()
        for m in list(self.members):
            wtype, payload = _identify_widget_for_drf(m)
            if wtype == "slider":
                remove_slider(payload)
            elif wtype == "button":
                remove_button(payload)
            elif wtype == "radio":
                remove_radio_group_by_group(payload)
        try: group_boxes.remove(self)
        except ValueError: pass
        self.destroy()
        schedule_scroll_update()

    def duplicate_group_box(self, offset_px=20):
        """Duplicate this group box + all members.
           New copy uses NEXT channel, preserves ALL CC/Note numbers."""
        self.update_idletasks()
        x1, y1, x2, y2 = _drf_bbox(self)
        w, h = self.winfo_width(), self.winfo_height()
        cy = (y1 + y2) // 2
        new_x = x2 + offset_px
        new_y = cy - h // 2

        new_channel = self.channel + 1 if self.channel < 16 else 1

        st = {
            "type": "group_box",
            "title": self.title.get(),
            "x": new_x, "y": new_y,
            "width": w, "height": h,
            "channel": new_channel,
            "lock_ccs": self._lock_var.get(),
        }
        new_gb = add_group_box(st)
        new_gb.channel = new_channel
        new_gb.update_channel_label()

        original_lock = new_gb._lock_var.get()
        try:
            new_gb._lock_var.set(True)
            new_gb.auto_assign_ccs.set(False)

            dx = new_x - self.winfo_x()
            dy = new_y - self.winfo_y()

            self.compute_members()

            for m in list(self.members):
                wtype, payload = _identify_widget_for_drf(m)

                if wtype == "slider":
                    ms = slider_state(payload)
                    ms["x"], ms["y"] = m.winfo_x() + dx, m.winfo_y() + dy
                    ms["channel"] = new_channel
                    add_slider(ms)

                elif wtype == "button":
                    ms = payload.get_state()
                    ms["x"], ms["y"] = m.winfo_x() + dx, m.winfo_y() + dy
                    ms["channel"] = new_channel
                    add_midi_button(ms)

                elif wtype == "radio":
                    ms = payload.get_state()
                    ms["x"], ms["y"] = m.winfo_x() + dx, m.winfo_y() + dy
                    ms["channel"] = new_channel
                    add_radio_group(ms)

        finally:
            new_gb._lock_var.set(original_lock)
            new_gb.auto_assign_ccs.set(not original_lock)
            new_gb.update_channel_label()

        new_gb.compute_members()
        schedule_scroll_update()
    def get_state(self):
                """Serialize this group box for save/load."""
                try:
                    self.update_idletasks()
                    info = self.place_info()
                except Exception:
                    info = {}

                def _safe_int(v, fallback):
                    try:
                        return int(v)
                    except Exception:
                        return fallback

                x = _safe_int(info.get("x", self.winfo_x()), self.winfo_x())
                y = _safe_int(info.get("y", self.winfo_y()), self.winfo_y())
                w = _safe_int(info.get("width", self.winfo_width()), self.winfo_width())
                h = _safe_int(info.get("height", self.winfo_height()), self.winfo_height())

                return {
                    "type": "group_box",
                    "title": self.title.get(),
                    "channel": int(self.channel),
                    "lock_ccs": bool(self._lock_var.get()),
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                }      



def add_group_box(state=None):
    """Create a group box; always lowered behind other controls."""
    if state:
        x, y = state.get("x", 60), state.get("y", 60)
        w, h = state.get("width", 320), state.get("height", 240)
        title = state.get("title", "Group")
    else:
        x, y, w, h = get_spawn_geometry([], 240)
        w = max(240, w + 180)
        title = "Group"

    gb = GroupBoxFrame(scrollable_frame, title=title, state=state, bg=COL_BG, bd=0, highlightthickness=0)
    gb.place(x=x, y=y, width=w, height=h)
    group_boxes.append(gb)
    gb.compute_members()
    gb._redraw()

    try:
        gb.lower()
    except Exception:
        pass

    gb.update_grips()
    schedule_scroll_update()
    return gb

# ---------------- Slider helpers ----------------


def resize_slider(slider_entry):
    container   = slider_entry["container"]
    slider      = slider_entry["slider"]
    name_entry  = slider_entry["name_entry"]

    container.update_idletasks()

    name_h = name_entry.winfo_reqheight()
    value_label = None
    for w in container.grid_slaves(row=1, column=0):
        value_label = w
        break
    value_h = value_label.winfo_reqheight() if value_label else 0

    reserved = name_h + value_h
    height   = container.winfo_height()
    width    = container.winfo_width()

    slider_length = max(20, height - reserved)
    slider.config(length=slider_length, width=max(30, int(width)))

    fr = slider_entry["frame"]
    if hasattr(fr, "grips"):
        for g in fr.grips.values():
            try:
                if g.winfo_exists():
                    g.lift()
            except Exception:
                pass

def slider_state(slider_entry):
    frame = slider_entry["frame"]
    frame.update_idletasks()
    info = frame.place_info()
    return {
        "value": slider_entry["slider"].get(),
        "mode": slider_entry["mode"].get(),
        "channel": _to_channel_int_or_none(slider_entry["channel"].get()),
        "control": _to_int_or_none(slider_entry["control"].get()),  # None if unassigned
        "name": slider_entry["name"].get(),
        "x": int(info.get("x", 100)),
        "y": int(info.get("y", 100)),
        "width": int(info.get("width", MIN_WIDTH)),
        "height": int(info.get("height", MIN_HEIGHT)),
    }

def remove_slider(slider_entry):
    try:
        sliders.remove(slider_entry)
    except ValueError:
        pass
    try:
        slider_entry["frame"].destroy()
    except Exception:
        pass

# ---- Channel helpers ----
def _is_unassigned_ch(val) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    return s == ""

def _to_channel_int_or_none(val):
    """Return 1..16 or None if unassigned/bad."""
    if _is_unassigned_ch(val):
        return None
    try:
        v = int(val)
        return v if 1 <= v <= 16 else None
    except Exception:
        return None

def _to_ch_or_default(val, default=1) -> int:
    """Return 1..16; fallback to default if unassigned/bad."""
    v = _to_channel_int_or_none(val)
    return default if v is None else v

def _ch_str_or_empty(val) -> str:
    """'' when unassigned/None else '1'..'16'."""
    v = _to_channel_int_or_none(val)
    return "" if v is None else str(v)


# ---------------- MIDI ----------------
def open_midi_setup(slider_entry):
    win = tk.Toplevel(root)
    win.title("Slider Midi Settings ")
    win.configure(bg=COL_FRAME)
    win.geometry("220x160")

    tk.Label(win, text="Mode", font=FONT_HEADER, bg=COL_FRAME, fg=COL_TEXT).grid(row=0, column=0, sticky="e", padx=8, pady=6)
    ttk.Combobox(win, textvariable=slider_entry["mode"],
                 values=["CC", "Note", "Pitch Bend", "Aftertouch"],
                 state="readonly", width=12).grid(row=0, column=1, sticky="w", padx=8, pady=6)

    tk.Label(win, text="Channel", font=FONT_HEADER, bg=COL_FRAME, fg=COL_TEXT).grid(row=1, column=0, sticky="e", padx=8, pady=6)
    ttk.Combobox(win, textvariable=slider_entry["channel"],
                 values=[str(i) for i in range(1, 17)],
                 state="readonly", width=6).grid(row=1, column=1, sticky="w", padx=8, pady=6)

    tk.Label(win, text="CC/Note", font=FONT_HEADER, bg=COL_FRAME, fg=COL_TEXT).grid(row=2, column=0, sticky="e", padx=8, pady=6)
    ttk.Combobox(win, textvariable=slider_entry["control"],
                 values=[""] + [str(i) for i in range(0, 128)],
                 state="readonly", width=8).grid(row=2, column=1, sticky="w", padx=8, pady=6)

    tk.Button(win, text="Close", command=win.destroy,
              bg=COL_ACCENT, fg=COL_TEXT, font=FONT_BUTTON,
              relief="flat", width=12).grid(row=3, column=0, columnspan=2, pady=(10, 8))

def send_midi(value, channel_var, control_var, mode_var):
    """Global send — skips if control/note unassigned for modes that need it."""
    global midi_out
    if midi_out is None:
        print("No MIDI output selected.")
        return
    try:
        value = int(float(value))
        channel = _to_ch_or_default(channel_var.get()) - 1
        control_raw = control_var.get() if hasattr(control_var, "get") else control_var
        mode = mode_var.get() if hasattr(mode_var, "get") else str(mode_var)

        if mode in ("CC", "Note") and _is_unassigned_cc(control_raw):
            return  # nothing to send if control/note isn't set

        if mode == "CC":
            # Channel Mode caveats
            if _is_reserved_cc(control_raw):
                cr = int(control_raw)
                # CC 123 (All Notes Off) is defined to use value = 0; many hosts ignore other values.
                if cr == 123:
                    value = 0
                print(f"Warning: CC {cr} is a Channel Mode message; target may ignore/filter it.")

            msg = Message("control_change", channel=channel, control=int(control_raw), value=value)
        elif mode == "Note":
            msg = Message("note_on", channel=channel, note=int(control_raw), velocity=value)
        elif mode == "Pitch Bend":
            pitch_val = int((value / 127.0) * 16383) - 8192
            msg = Message("pitchwheel", channel=channel, pitch=pitch_val)
        elif mode == "Aftertouch":
            msg = Message("aftertouch", channel=channel, value=value)
        else:
            return

        midi_out.send(msg)
        print(f"Sent {mode} | Channel {channel+1} | Number {control_raw if control_raw is not None else '-'} | Value {value}")
    except Exception as e:
        print("MIDI Error:", e)

def _gather_cc_usage():
    """
    Return a dict:
        { channel_int: { cc_number: [human_label, ...] } }
    human_label is a small description of where that CC is used.
    """
    usage = {ch: {} for ch in range(1, 17)}

    # Sliders
    for entry in sliders:
        try:
            ch = int(entry["channel"].get())
            c  = entry["control"].get()
            if not _is_unassigned_cc(c):
                cc = int(c)
                lbl = f"Slider: {entry['name'].get()}"
                usage[ch].setdefault(cc, []).append(lbl)
        except Exception:
            pass

    # Buttons
    for btn in buttons:
        try:
            ch = int(btn.channel.get())
            c  = btn.control.get()
            if not _is_unassigned_cc(c):
                cc = int(c)
                lbl = f"Button: {btn.name.get()}"
                usage[ch].setdefault(cc, []).append(lbl)
        except Exception:
            pass

    # Radio groups (consider each option control)
    for rg in radio_groups:
        try:
            g  = rg["group"]
            ch = int(g.channel.get())
            for bd in getattr(g, "button_data", []):
                c = bd.get("control", None)
                if c is not None and not _is_unassigned_cc(c):
                    cc = int(c)
                    lbl = f"Radio: {bd.get('label','?')}"
                    usage[ch].setdefault(cc, []).append(lbl)
        except Exception:
            pass

    return usage


def show_ccs_by_channel_window():
    """Open a read-only window listing all assigned CCs grouped by channel."""
    win = tk.Toplevel(root)
    win.title("Assigned CCs by Channel")
    win.configure(bg=COL_FRAME)
    win.geometry("520x480")

    txt = tk.Text(win, bg=COL_BG, fg=COL_TEXT, insertbackground=COL_ACCENT,
                  relief="flat", wrap="word")
    txt.pack(fill="both", expand=True, padx=8, pady=8)

    usage = _gather_cc_usage()
    for ch in range(1, 17):
        items = usage[ch]
        txt.insert("end", f"Channel {ch}\n", ("hdr",))
        if not items:
            txt.insert("end", "  (none)\n\n")
            continue
        for cc in sorted(items.keys()):
            labels = ", ".join(items[cc])
            txt.insert("end", f"  CC {cc:>3}: {labels}\n")
        txt.insert("end", "\n")

    txt.tag_configure("hdr", foreground=COL_ACCENT, font=FONT_HEADER)
    txt.config(state="disabled")

    # Close button
    btn = tk.Button(win, text="Close", command=win.destroy,
                    bg=COL_ACCENT, fg=COL_TEXT, font=FONT_BUTTON, relief="flat", width=12)
    btn.pack(pady=(0, 8))
def _apply_incoming_midi_to_ui(msg):
    """Runs on the Tk main thread. Updates widgets in response to a MIDI message."""

    # ---------- SLIDERS ----------
    for entry in sliders:
        mode = entry["mode"].get()
        ch = _to_ch_or_default(entry["channel"].get()) - 1
        if getattr(msg, "channel", ch) != ch:
            continue

        ctrl_text = entry["control"].get()
        if mode == "CC" and msg.type == "control_change" and not _is_unassigned_cc(ctrl_text):
            if msg.control == int(ctrl_text):
                entry["slider"].set(msg.value)
        elif mode == "Note":
            if not _is_unassigned_cc(ctrl_text):
                if msg.type == "note_on" and msg.note == int(ctrl_text):
                    entry["slider"].set(msg.velocity)
                elif msg.type == "note_off" and msg.note == int(ctrl_text):
                    entry["slider"].set(0)
        elif mode == "Pitch Bend" and msg.type == "pitchwheel":
            val = int(((msg.pitch + 8192) / 16383.0) * 127)
            entry["slider"].set(val)
        elif mode == "Aftertouch" and msg.type == "aftertouch":
            entry["slider"].set(msg.value)

    # ---------- BUTTONS ----------
    for btn in buttons:
        mode = btn.mode.get()
        ch = _to_ch_or_default(btn.channel.get()) - 1
        if getattr(msg, "channel", ch) != ch:
            continue

        ctrl_text = btn.control.get()
        if mode == "CC" and msg.type == "control_change" and not _is_unassigned_cc(ctrl_text):
            if msg.control == int(ctrl_text):
                btn.set_from_midi(msg.value)
        elif mode == "Note" and not _is_unassigned_cc(ctrl_text):
            if msg.type == "note_on" and msg.note == int(ctrl_text):
                btn.set_from_midi(msg.velocity)
            elif msg.type == "note_off" and msg.note == int(ctrl_text):
                btn.set_from_midi(0)
        elif mode == "Aftertouch" and msg.type == "aftertouch":
            btn.set_from_midi(msg.value)

    # ---------- RADIO GROUPS ----------
    for rg in radio_groups:
        group = rg["group"]
        mode = group.mode.get()
        ch = _to_ch_or_default(group.channel.get()) - 1
        if getattr(msg, "channel", ch) != ch:
            continue

        if mode == "CC" and msg.type == "control_change":
            group.set_from_midi_cc(msg.control, msg.value)
        elif mode == "Note":
            if msg.type == "note_on":
                group.set_from_midi_note(msg.note, getattr(msg, "velocity", 0))
        elif mode == "Aftertouch" and msg.type == "aftertouch":
            group.set_from_midi_cc(0, msg.value)


def listen_midi_input():
    """(Re)start the single MIDI input listener for selected_input_port."""
    global midi_in_thread, midi_in_stop

    # Stop existing thread if running
    if midi_in_thread and midi_in_thread.is_alive():
        try:
            midi_in_stop.set()
            midi_in_thread.join(timeout=1.0)
        except Exception:
            pass

    # New stop event for fresh thread
    midi_in_stop = threading.Event()

    def midi_loop(stop_evt):
        try:
            port_name = selected_input_port.get()
            with mido.open_input(port_name) as midi_in:
                print(f"Listening for MIDI input on: {port_name}")
                # poll without blocking so we can stop quickly
                while not stop_evt.is_set():
                    for msg in midi_in.iter_pending():
                        if msg.type in ("control_change", "note_on", "note_off", "pitchwheel", "aftertouch"):
                            midi_queue.put(msg)
                    stop_evt.wait(0.01)  # small sleep; responsive to stop
        except Exception as e:
            print("MIDI input error:", e)

    midi_in_thread = threading.Thread(target=midi_loop, args=(midi_in_stop,), daemon=True)
    midi_in_thread.start()

def select_port():
    global midi_out
    if midi_out:
        try:
            midi_out.close()
        except Exception:
            pass
    try:
        midi_out = mido.open_output(selected_port.get())
        print(f"Connected to: {selected_port.get()}")
    except Exception as e:
        print("Failed to open port:", e)


# ---------------- Slider context menu ----------------
def show_context_menu(event, slider_entry):
    menu = tk.Menu(root, tearoff=0, bg=COL_FRAME, fg=COL_TEXT, activebackground=COL_ACCENT, font=FONT_UI)
    menu.add_command(label="MIDI Setup", command=lambda: open_midi_setup(slider_entry))
    menu.add_command(label="Rename", command=lambda: slider_entry["name_entry"].focus_set())
    menu.add_command(label="Duplicate", command=lambda: duplicate(SliderProxy(slider_entry)))
    menu.add_command(label="Delete", command=lambda: remove_slider(slider_entry))
    menu.tk_popup(event.x_root, event.y_root)

# ---------------- Save/Load ----------------
def save_state():
    file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")])
    if not file_path:
        return

    data = {"widgets": []}

    for entry in sliders:
        try:
            widget_data = slider_state(entry)
            widget_data["type"] = "slider"
            data["widgets"].append(widget_data)
        except Exception as e:
            print(f"Error saving slider: {e}")

    for button in buttons:
        try:
            widget_data = button.get_state()
            widget_data["type"] = "button"
            data["widgets"].append(widget_data)
        except Exception as e:
            print(f"Error saving button: {e}")

    for rg in radio_groups:
        try:
            widget_data = rg["group"].get_state()
            widget_data["type"] = "radio"
            data["widgets"].append(widget_data)
        except Exception as e:
            print(f"Error saving radio group: {e}")

    for gb in group_boxes:
        try:
            data["widgets"].append(gb.get_state())
        except Exception as e:
            print(f"Error saving group box: {e}")

    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        current_filename.set(file_path.split("/")[-1])
        root.title(f"MIDI Controller - {current_filename.get()}")
        print("Session saved:", file_path)
    except Exception as e:
        print(f"Final save error: {e}")

def load_state():
    file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
    if not file_path:
        return

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            print("Widgets in JSON:", data.get("widgets"))
            print("Widget count:", len(data.get("widgets", [])))
    except Exception as e:
        print("Failed to load:", e)
        return

    # Clear existing
    for entry in sliders[:]:
        remove_slider(entry)

    for button in buttons[:]:
        try:
            button.master.destroy()
        except Exception:
            pass
    buttons.clear()

    for rg in radio_groups[:]:
        try:
            rg["frame"].destroy()
        except Exception:
            pass
    radio_groups.clear()

    for gb in group_boxes[:]:
        try:
            gb.destroy()
        except Exception:
            pass
    group_boxes.clear()

    for widget in scrollable_frame.winfo_children():
        if isinstance(widget, DraggableResizableFrame):
            widget.destroy()

    # Recreate (widgets first, then group boxes)
    for item in data.get("widgets", []):
        t = item.get("type")
        if t == "slider":
            add_slider(item)
        elif t == "button":
            add_midi_button(item)
        elif t == "radio":
            add_radio_group(item)

    for item in data.get("widgets", []):
        if item.get("type") == "group_box":
            add_group_box(item)

    # Recompute memberships and assign CCs for all group boxes
    for gb in group_boxes:
        gb.compute_members()

    current_filename.set(file_path.split("/")[-1])
    root.title(f"MIDI Controller - {current_filename.get()}")
    print("Session loaded:", file_path)

    schedule_scroll_update()
    canvas.xview_moveto(0)
    canvas.yview_moveto(0)

def _process_midi_queue():
    """Main-thread pump: drain the MIDI queue and update the UI safely."""
    global UPDATING_FROM_MIDI
    try:
        while True:
            msg = midi_queue.get_nowait()
            UPDATING_FROM_MIDI = True
            try:
                _apply_incoming_midi_to_ui(msg)
            finally:
                UPDATING_FROM_MIDI = False
    except Exception:
        # queue empty or benign issue; ignore
        pass
    finally:
        # ~100 Hz poll; adjust if you want
        root.after(10, _process_midi_queue)

# --------------- App wiring ---------------
if selected_port.get():
    select_port()
if selected_input_port.get():
    listen_midi_input()

def clear_focus(event):
    if not isinstance(event.widget, tk.Entry):
        root.focus_set()

def _on_close():
    # stop input thread
    try:
        midi_in_stop.set()
        if midi_in_thread and midi_in_thread.is_alive():
            midi_in_thread.join(timeout=0.5)
    except Exception:
        pass
    # close midi out
    global midi_out
    try:
        if midi_out:
            midi_out.close()
    except Exception:
        pass
    root.destroy()

# ---------------- Fullscreen Toggle ----------------
def toggle_fullscreen(event=None):
    is_fullscreen = root.attributes("-fullscreen")
    root.attributes("-fullscreen", not is_fullscreen)
    return "break"

# Bind F11 to toggle fullscreen
root.bind("<F11>", toggle_fullscreen)

root.protocol("WM_DELETE_WINDOW", _on_close)

root.bind_all("<Button-1>", clear_focus, add="+")

# Start the safe MIDI→UI pump
root.after(10, _process_midi_queue)
root.mainloop()
# ==== END PART 2/2 ====
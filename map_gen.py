from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageTk

def load_ascii_map(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()

def pad_to_rect(lines: list[str]) -> tuple[list[str], int, int]:
    h = len(lines)
    w = max((len(line) for line in lines), default=0)
    padded = [line.ljust(w, " ") for line in lines]
    return padded, w, h

def pick_monospace_font(font_path: str | None, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_path:
        return ImageFont.truetype(font_path, font_size)
    candidates = [
        "DejaVuSansMono.ttf",
        "DejaVuSansMono-Regular.ttf",
        "LiberationMono-Regular.ttf",
        "Consolas.ttf",
        "Menlo.ttc",
        "Courier New.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, font_size)
        except Exception:
            pass
    return ImageFont.load_default()

def render_ascii_to_image(
    lines: list[str],
    *,
    font_path: str | None,
    font_size: int,
    cell_w: int | None,
    cell_h: int | None,
    margin: int,
    bg: str,
    fg: str,
    grid: bool,
    grid_color: str,
    grid_width: int,
) -> Image.Image:
    padded, w_chars, h_chars = pad_to_rect(lines)
    if w_chars == 0 or h_chars == 0:
        return Image.new("RGBA", (1, 1), bg)

    tmp = Image.new("RGBA", (10, 10), bg)
    tmp_draw = ImageDraw.Draw(tmp)
    font = pick_monospace_font(font_path, font_size)

    if cell_w is None or cell_h is None:
        bbox = tmp_draw.textbbox((0, 0), "M", font=font)
        gw = bbox[2] - bbox[0]
        gh = bbox[3] - bbox[1]
        cell_w = cell_w or (gw + 6)
        cell_h = cell_h or (gh + 6)

    img_w = margin * 2 + w_chars * cell_w
    img_h = margin * 2 + h_chars * cell_h

    img = Image.new("RGBA", (img_w, img_h), bg)
    draw = ImageDraw.Draw(img)

    for y, line in enumerate(padded):
        for x, ch in enumerate(line):
            cx0 = margin + x * cell_w
            cy0 = margin + y * cell_h

            bbox = draw.textbbox((0, 0), ch, font=font)
            gw = bbox[2] - bbox[0]
            gh = bbox[3] - bbox[1]

            tx = cx0 + (cell_w - gw) // 2 - bbox[0]
            ty = cy0 + (cell_h - gh) // 2 - bbox[1]

            draw.text((tx, ty), ch, fill=fg, font=font)

    if grid:
        left = margin
        top = margin
        right = margin + w_chars * cell_w
        bottom = margin + h_chars * cell_h

        for x in range(w_chars + 1):
            xx = left + x * cell_w
            draw.line([(xx, top), (xx, bottom)], fill=grid_color, width=grid_width)
        for y in range(h_chars + 1):
            yy = top + y * cell_h
            draw.line([(left, yy), (right, yy)], fill=grid_color, width=grid_width)

    return img


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ASCII Map -> PNG")
        self.geometry("1180x720")
        self.minsize(1000, 650)

        self.input_path: Path | None = None
        self.ascii_lines: list[str] = []

        # Settings
        self.var_font_size = tk.IntVar(value=18)
        self.var_cell_w = tk.IntVar(value=0)   # 0 means "auto"
        self.var_cell_h = tk.IntVar(value=0)   # 0 means "auto"
        self.var_margin = tk.IntVar(value=0)

        self.var_bg = tk.StringVar(value="#0b0f14")
        self.var_fg = tk.StringVar(value="#e6edf3")

        self.var_grid = tk.BooleanVar(value=True)
        self.var_grid_color = tk.StringVar(value="#2b3440")
        self.var_grid_width = tk.IntVar(value=1)

        # Font selection
        self.var_font_path = tk.StringVar(value="")  # empty => auto
        self._font_label_var = tk.StringVar(value="Font: Auto (monospace fallback)")

        # Render / preview state
        self._base_img: Image.Image | None = None
        self._preview_photo = None
        self._canvas_img_id = None

        # Zoom state
        self.zoom = 1.0
        self.zoom_min = 0.25
        self.zoom_max = 16.0

        # Editor state
        self._editor_change_job = None
        self._ignore_editor_events = False

        self._build_ui()
        self._wire_events()
        self._show_empty_preview()

    # ---------- UI helpers ----------

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        root.columnconfigure(0, weight=0)  # controls
        root.columnconfigure(1, weight=1)  # right pane
        root.rowconfigure(0, weight=1)

        # Left: controls
        controls = ttk.Frame(root)
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        controls.columnconfigure(0, weight=1)

        ttk.Label(controls, text="Input / Export", font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        self.lbl_file = ttk.Label(controls, text="No file selected", wraplength=280)
        self.lbl_file.grid(row=1, column=0, sticky="w", pady=(0, 8))

        btn_row = ttk.Frame(controls)
        btn_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        ttk.Button(btn_row, text="Select ASCII File…", command=self.on_select_file).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(btn_row, text="Export PNG…", command=self.on_export_png).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

        btn_row2 = ttk.Frame(controls)
        btn_row2.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        btn_row2.columnconfigure(0, weight=1)
        btn_row2.columnconfigure(1, weight=1)

        ttk.Button(btn_row2, text="Save ASCII…", command=self.on_save_ascii).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(btn_row2, text="Choose Font…", command=self.on_choose_font).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

        ttk.Label(controls, textvariable=self._font_label_var, wraplength=280, foreground="#666").grid(
            row=4, column=0, sticky="w", pady=(0, 6)
        )

        ttk.Separator(controls).grid(row=5, column=0, sticky="ew", pady=10)

        ttk.Label(controls, text="Render Settings", font=("TkDefaultFont", 11, "bold")).grid(
            row=6, column=0, sticky="w", pady=(0, 6)
        )

        self._add_spin(controls, "Font size", self.var_font_size, 8, 64, row=7)
        self._add_spin(controls, "Cell width (0=auto)", self.var_cell_w, 0, 256, row=8)
        self._add_spin(controls, "Cell height (0=auto)", self.var_cell_h, 0, 256, row=9)
        self._add_spin(controls, "Margin", self.var_margin, 0, 128, row=10)

        ttk.Separator(controls).grid(row=11, column=0, sticky="ew", pady=10)

        ttk.Label(controls, text="Colors", font=("TkDefaultFont", 11, "bold")).grid(
            row=12, column=0, sticky="w", pady=(0, 6)
        )
        self._add_entry(controls, "Background", self.var_bg, row=13, with_picker=True)
        self._add_entry(controls, "Text", self.var_fg, row=14, with_picker=True)

        ttk.Separator(controls).grid(row=15, column=0, sticky="ew", pady=10)

        ttk.Label(controls, text="Grid", font=("TkDefaultFont", 11, "bold")).grid(
            row=16, column=0, sticky="w", pady=(0, 6)
        )

        ttk.Checkbutton(controls, text="Enable grid lines", variable=self.var_grid).grid(
            row=17, column=0, sticky="w", pady=(0, 6)
        )
        self._add_entry(controls, "Grid color", self.var_grid_color, row=18, with_picker=True)
        self._add_spin(controls, "Grid width", self.var_grid_width, 1, 8, row=19)

        ttk.Separator(controls).grid(row=20, column=0, sticky="ew", pady=10)

        ttk.Label(controls, text="Replace Characters", font=("TkDefaultFont", 11, "bold")).grid(
            row=21, column=0, sticky="w", pady=(0, 6)
        )

        rep = ttk.Frame(controls)
        rep.grid(row=22, column=0, sticky="ew", pady=(0, 6))
        rep.columnconfigure(1, weight=1)
        rep.columnconfigure(3, weight=1)

        ttk.Label(rep, text="Find").grid(row=0, column=0, sticky="w")
        self.ent_find = ttk.Entry(rep, width=4)
        self.ent_find.grid(row=0, column=1, sticky="w", padx=(6, 10))

        ttk.Label(rep, text="Replace").grid(row=0, column=2, sticky="w")
        self.ent_replace = ttk.Entry(rep, width=4)
        self.ent_replace.grid(row=0, column=3, sticky="w", padx=(6, 0))

        rep2 = ttk.Frame(controls)
        rep2.grid(row=23, column=0, sticky="ew", pady=(0, 6))
        rep2.columnconfigure(0, weight=1)
        rep2.columnconfigure(1, weight=1)

        self.var_replace_mode = tk.StringVar(value="all")
        ttk.Radiobutton(rep2, text="Replace All", value="all", variable=self.var_replace_mode).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Radiobutton(rep2, text="Selection Only", value="selection", variable=self.var_replace_mode).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Button(controls, text="Apply Replace", command=self.on_apply_replace).grid(
            row=24, column=0, sticky="ew", pady=(0, 10)
        )

        ttk.Label(
            controls,
            text="Pan: drag with left mouse\nZoom: mouse wheel",
            foreground="#666"
        ).grid(row=25, column=0, sticky="w", pady=(6, 0))

        # Right: split editor + preview
        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        paned = ttk.Panedwindow(right, orient="horizontal")
        paned.grid(row=0, column=0, sticky="nsew")

        # Editor pane
        editor_frame = ttk.Frame(paned, padding=(0, 0, 8, 0))
        editor_frame.rowconfigure(1, weight=1)
        editor_frame.columnconfigure(0, weight=1)

        ttk.Label(editor_frame, text="ASCII Editor", font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.editor = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            font=("DejaVu Sans Mono", 11),
            height=10
        )
        self.editor.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        ed_vsb = ttk.Scrollbar(editor_frame, orient="vertical", command=self.editor.yview)
        ed_hsb = ttk.Scrollbar(editor_frame, orient="horizontal", command=self.editor.xview)
        self.editor.configure(yscrollcommand=ed_vsb.set, xscrollcommand=ed_hsb.set)

        ed_vsb.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        ed_hsb.grid(row=2, column=0, sticky="ew")

        # Preview pane
        preview_frame = ttk.Frame(paned)
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        ttk.Label(preview_frame, text="Preview", font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        canvas_container = ttk.Frame(preview_frame)
        canvas_container.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        canvas_container.rowconfigure(0, weight=1)
        canvas_container.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_container, bg="#111", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(canvas_container, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(canvas_container, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        paned.add(editor_frame, weight=1)
        paned.add(preview_frame, weight=2)

    def _add_spin(self, parent, label, var, frm, to, row):
        f = ttk.Frame(parent)
        f.grid(row=row, column=0, sticky="ew", pady=3)
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text=label).grid(row=0, column=0, sticky="w")
        sp = ttk.Spinbox(f, from_=frm, to=to, textvariable=var, width=8)
        sp.grid(row=0, column=1, sticky="e")

    def _add_entry(self, parent, label, var, row, *, with_picker: bool = False):
        f = ttk.Frame(parent)
        f.grid(row=row, column=0, sticky="ew", pady=3)
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text=label).grid(row=0, column=0, sticky="w")

        ent = ttk.Entry(f, textvariable=var)
        ent.grid(row=0, column=1, sticky="ew", padx=(6, 6) if with_picker else (0, 0))

        if with_picker:
            ttk.Button(f, text="Pick…", command=lambda: self._pick_color(var)).grid(
                row=0, column=2, sticky="e"
            )

    # ---------- Events / bindings ----------

    def _wire_events(self):
        for v in (
            self.var_font_size, self.var_cell_w, self.var_cell_h, self.var_margin,
            self.var_bg, self.var_fg,
            self.var_grid, self.var_grid_color, self.var_grid_width,
            self.var_font_path
        ):
            v.trace_add("write", lambda *_: self._schedule_rerender())

        self.canvas.bind("<Configure>", lambda e: self.update_display())

        # Pan
        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", self._pan_move)

        # Zoom
        self.canvas.bind("<MouseWheel>", self._zoom_wheel)   # some builds
        self.canvas.bind("<Button-4>", self._zoom_in_linux)  # X11 up
        self.canvas.bind("<Button-5>", self._zoom_out_linux) # X11 down

        # Editor live update
        self.editor.bind("<<Modified>>", self._on_editor_modified)

    # ---------- Color picker ----------

    def _pick_color(self, var: tk.StringVar):
        from tkinter import colorchooser
        _rgb, hex_color = colorchooser.askcolor(color=var.get(), parent=self)
        if hex_color:
            var.set(hex_color)

    # ---------- Settings ----------

    def _get_settings(self):
        def z_to_none(v: int) -> int | None:
            return None if v <= 0 else v

        font_path = self.var_font_path.get().strip() or None

        return dict(
            font_path=font_path,
            font_size=int(self.var_font_size.get()),
            cell_w=z_to_none(int(self.var_cell_w.get())),
            cell_h=z_to_none(int(self.var_cell_h.get())),
            margin=int(self.var_margin.get()),
            bg=self.var_bg.get().strip(),
            fg=self.var_fg.get().strip(),
            grid=bool(self.var_grid.get()),
            grid_color=self.var_grid_color.get().strip(),
            grid_width=int(self.var_grid_width.get()),
        )

    # ---------- Editor integration ----------

    def _set_editor_text(self, text: str):
        self._ignore_editor_events = True
        try:
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", text)
            self.editor.edit_reset()
            self.editor.edit_modified(False)
        finally:
            self._ignore_editor_events = False

    def _get_editor_text(self) -> str:
        return self.editor.get("1.0", "end-1c")

    def _get_editor_lines(self) -> list[str]:
        return self._get_editor_text().splitlines()

    def _on_editor_modified(self, _event=None):
        if self._ignore_editor_events:
            self.editor.edit_modified(False)
            return

        self.editor.edit_modified(False)
        self._schedule_rerender()

    def _schedule_rerender(self):
        if self._editor_change_job is not None:
            try:
                self.after_cancel(self._editor_change_job)
            except Exception:
                pass
            self._editor_change_job = None

        self._editor_change_job = self.after(120, self.rerender_base)

    # ---------- Rendering / preview ----------

    def _show_empty_preview(self):
        self.canvas.delete("all")
        self._base_img = None
        self._preview_photo = None
        self._canvas_img_id = None
        self.canvas.configure(scrollregion=(0, 0, 1, 1))
        self.canvas.create_text(10, 10, anchor="nw", fill="#ccc", text="Select an ASCII file to preview…")

    def rerender_base(self):
        lines = self._get_editor_lines()
        if not lines:
            self._show_empty_preview()
            return

        self.ascii_lines = lines

        try:
            self._base_img = render_ascii_to_image(self.ascii_lines, **self._get_settings())
        except Exception as e:
            self.canvas.delete("all")
            self._base_img = None
            self._canvas_img_id = None
            self.canvas.create_text(10, 10, anchor="nw", fill="#f88", text=f"Render error:\n{e}")
            return

        self.update_display()

    def update_display(self):
        if self._base_img is None:
            return

        z = float(self.zoom)
        iw, ih = self._base_img.size
        pw = max(1, int(iw * z))
        ph = max(1, int(ih * z))

        preview = self._base_img.resize((pw, ph), resample=Image.NEAREST)
        self._preview_photo = ImageTk.PhotoImage(preview)

        if self._canvas_img_id is None:
            self.canvas.delete("all")
            self._canvas_img_id = self.canvas.create_image(0, 0, anchor="nw", image=self._preview_photo)
        else:
            self.canvas.itemconfigure(self._canvas_img_id, image=self._preview_photo)

        self.canvas.configure(scrollregion=(0, 0, pw, ph))

    # ---------- Pan / zoom ----------

    def _pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _pan_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _apply_zoom(self, new_zoom: float, event=None):
        if self._base_img is None:
            return

        old_zoom = self.zoom
        new_zoom = max(self.zoom_min, min(self.zoom_max, new_zoom))
        new_zoom = round(new_zoom, 2)
        if new_zoom == old_zoom:
            return

        if event is not None:
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            old_pw = max(1, int(self._base_img.size[0] * old_zoom))
            old_ph = max(1, int(self._base_img.size[1] * old_zoom))
            relx = cx / old_pw
            rely = cy / old_ph
        else:
            relx = rely = 0.0

        self.zoom = new_zoom
        self.update_display()

        if event is not None:
            self.canvas.xview_moveto(max(0.0, min(1.0, relx)))
            self.canvas.yview_moveto(max(0.0, min(1.0, rely)))

    def _zoom_wheel(self, event):
        d = getattr(event, "delta", 0)
        if d == 0:
            return
        direction = 1 if d > 0 else -1
        step = 0.08  # 8% per notch
        factor = (1.0 + step) if direction > 0 else (1.0 / (1.0 + step))
        self._apply_zoom(self.zoom * factor, event)

    def _zoom_in_linux(self, event):
        step = 0.08
        self._apply_zoom(self.zoom * (1.0 + step), event)

    def _zoom_out_linux(self, event):
        step = 0.08
        self._apply_zoom(self.zoom / (1.0 + step), event)

    # ---------- File actions ----------

    def on_select_file(self):
        path = filedialog.askopenfilename(
            title="Select ASCII map file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return

        self.input_path = Path(path)
        try:
            lines = load_ascii_map(self.input_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file:\n{e}")
            return

        self.lbl_file.config(text=str(self.input_path))
        self._set_editor_text("\n".join(lines))

        self.zoom = 1.0
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)
        self.rerender_base()

    def on_save_ascii(self):
        text = self._get_editor_text()
        if not text:
            messagebox.showinfo("Save ASCII", "Nothing to save. Load or type an ASCII map first.")
            return

        out = filedialog.asksaveasfilename(
            title="Save ASCII",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not out:
            return

        try:
            Path(out).write_text(text, encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save ASCII:\n{e}")
            return

        messagebox.showinfo("Save ASCII", f"Saved:\n{out}")

    def on_export_png(self):
        lines = self._get_editor_lines()
        if not lines:
            messagebox.showinfo("Export", "Nothing to export. Load or type an ASCII map first.")
            return

        out = filedialog.asksaveasfilename(
            title="Export PNG",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")]
        )
        if not out:
            return

        try:
            img = render_ascii_to_image(lines, **self._get_settings())
            img.save(out)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export PNG:\n{e}")
            return

        messagebox.showinfo("Export", f"Saved:\n{out}")

    def on_choose_font(self):
        path = filedialog.askopenfilename(
            title="Choose a font file",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")]
        )
        if not path:
            return

        p = Path(path)
        self.var_font_path.set(str(p))

        self._font_label_var.set(f"Font: {p.name}")

        try:
            # can't load TTF directly as a named font so keep the editor monospace.
            pass
        except Exception:
            pass

    # ---------- Replace character ----------

    def on_apply_replace(self):
        find = self.ent_find.get()
        repl = self.ent_replace.get()

        if not find:
            messagebox.showinfo("Replace", "Enter a character to find.")
            return
        if len(find) != 1:
            messagebox.showinfo("Replace", "Find must be exactly 1 character.")
            return
        if repl == "":
            messagebox.showinfo("Replace", "Enter a replacement character.")
            return
        if len(repl) != 1:
            messagebox.showinfo("Replace", "Replace must be exactly 1 character.")
            return

        mode = self.var_replace_mode.get()

        self._ignore_editor_events = True
        try:
            if mode == "selection":
                try:
                    start = self.editor.index("sel.first")
                    end = self.editor.index("sel.last")
                except tk.TclError:
                    messagebox.showinfo("Replace", "No selection. Select text or switch to Replace All.")
                    return

                chunk = self.editor.get(start, end)
                chunk2 = chunk.replace(find, repl)
                if chunk2 != chunk:
                    self.editor.delete(start, end)
                    self.editor.insert(start, chunk2)
            else:
                text = self._get_editor_text()
                text2 = text.replace(find, repl)
                if text2 != text:
                    self.editor.delete("1.0", "end")
                    self.editor.insert("1.0", text2)

            self.editor.edit_modified(False)
        finally:
            self._ignore_editor_events = False

        self._schedule_rerender()




if __name__ == "__main__":
    App().mainloop()
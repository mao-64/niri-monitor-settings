#!/usr/bin/env python3
"""Arrange Niri outputs visually and export their output blocks as a KDL fragment."""

from __future__ import annotations

import json
import re
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

CONFIG = Path.home() / ".config/niri/config.kdl"
SNAP_DISTANCE = 36  # logical pixels

# Black-and-neon-green palette.
BG = "#070b08"
PANEL = "#0c130e"
SURFACE = "#101a13"
GRID = "#14251a"
BORDER = "#203b29"
GREEN = "#4dff88"
TEXT = "#d7f7df"
MUTED = "#80a68a"


def read_output_blocks(text: str) -> dict[str, str]:
    """Return complete output blocks, respecting braces inside quoted strings."""
    blocks: dict[str, str] = {}
    pattern = re.compile(r'(?m)^\s*output\s+"([^"]+)"\s*\{')
    for match in pattern.finditer(text):
        depth = 1
        quoted = False
        escaped = False
        end = match.end()
        while end < len(text) and depth:
            char = text[end]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            end += 1
        blocks[match.group(1)] = text[match.start():end]
    return blocks


def block_values(block: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in ("mode", "scale", "transform", "position"):
        match = re.search(rf'(?m)^\s*{key}\s+(.*?)(?:\s*//.*)?$', block)
        if match:
            values[key] = match.group(1).strip()
    return values


def walk_for_outputs(value):
    if isinstance(value, dict):
        if isinstance(value.get("name"), str) and isinstance(value.get("modes"), list):
            yield value
        for child in value.values():
            yield from walk_for_outputs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_for_outputs(child)


def query_niri() -> list[dict]:
    result = subprocess.run(
        ["niri", "msg", "--json", "outputs"],
        check=True,
        capture_output=True,
        text=True,
        timeout=4,
    )
    return list(walk_for_outputs(json.loads(result.stdout)))


def mode_string(mode: dict) -> str:
    width, height = mode.get("width"), mode.get("height")
    refresh = mode.get("refresh_rate")
    if width is None or height is None:
        return ""
    if refresh is None:
        return f"{width}x{height}"
    # Niri IPC reports refresh rate in millihertz.
    refresh_hz = refresh / 1000 if refresh > 1000 else refresh
    return f"{width}x{height}@{refresh_hz:.3f}"


def logical_state(output: dict) -> dict:
    logical = output.get("logical") or {}
    if isinstance(logical, dict):
        return logical
    return {}


class LayoutEditor:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Niri Monitor Layout")
        root.geometry("1080x700")
        root.minsize(780, 520)
        root.configure(background=BG)
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure(".", background=BG, foreground=TEXT, font=("TkDefaultFont", 10))
        self.style.configure("TFrame", background=BG)
        self.style.configure("Panel.TFrame", background=PANEL)
        self.style.configure("TLabel", background=PANEL, foreground=TEXT)
        self.style.configure("Heading.TLabel", background=PANEL, foreground=GREEN, font=("TkFixedFont", 17, "bold"))
        self.style.configure("Eyebrow.TLabel", background=PANEL, foreground=GREEN, font=("TkFixedFont", 9, "bold"))
        self.style.configure("Section.TLabel", background=PANEL, foreground=MUTED, font=("TkFixedFont", 9, "bold"))
        self.style.configure("Hint.TLabel", background=PANEL, foreground=MUTED)
        self.style.configure("TSeparator", background=BORDER)
        self.style.configure("TButton", background=SURFACE, foreground=TEXT, bordercolor=BORDER, padding=(10, 8))
        self.style.map("TButton", background=[("active", "#183322")], foreground=[("active", GREEN)])
        self.style.configure("Neon.TButton", background=GREEN, foreground=BG, bordercolor=GREEN, padding=(10, 10), font=("TkDefaultFont", 10, "bold"))
        self.style.map("Neon.TButton", background=[("active", "#8affae")], foreground=[("active", BG)])
        self.style.configure("TEntry", fieldbackground=SURFACE, foreground=GREEN, insertcolor=GREEN, bordercolor=BORDER, padding=7)
        self.style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE, foreground=GREEN, arrowcolor=GREEN, bordercolor=BORDER, padding=7)
        self.style.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("readonly", GREEN)], selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", GREEN)])

        try:
            blocks = read_output_blocks(CONFIG.read_text())
        except OSError:
            blocks = {}
        configured = {name: block_values(block) for name, block in blocks.items()}

        try:
            outputs = query_niri()
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror(
                "Cannot query Niri",
                f"Could not read connected outputs from Niri.\n\n{error}\n\n"
                "Run this utility inside a Niri session.",
            )
            root.destroy()
            return

        self.monitors: list[dict] = []
        for output in outputs:
            name = output["name"]
            settings = configured.get(name, {})
            modes = [mode_string(mode) for mode in output["modes"]]
            modes = [mode for mode in modes if mode]
            current_index = output.get("current_mode")
            current = modes[current_index] if isinstance(current_index, int) and current_index < len(modes) else ""
            current = settings.get("mode", "").strip('"') or current or (modes[0] if modes else "1920x1080")

            logical = logical_state(output)
            position = settings.get("position", "")
            position_match = re.search(r'x=(-?\d+)\s+y=(-?\d+)', position)
            x = int(position_match.group(1)) if position_match else int(logical.get("x", 0))
            y = int(position_match.group(2)) if position_match else int(logical.get("y", 0))
            scale_value = settings.get("scale", str(logical.get("scale", 1)))
            scale_match = re.search(r'[-+]?\d+(?:\.\d+)?', scale_value)
            scale = float(scale_match.group()) if scale_match else 1.0

            self.monitors.append({
                "name": name,
                "modes": modes,
                "mode": current,
                "scale": scale,
                "transform": settings.get("transform", '"normal"').strip('"'),
                "x": x,
                "y": y,
                "logical": logical,
            })

        if not self.monitors:
            messagebox.showerror("No monitors", "Niri did not report any connected outputs.")
            root.destroy()
            return

        self.selected: dict | None = None
        self.drag_offset: tuple[float, float] | None = None
        self.canvas = tk.Canvas(root, background=BG, highlightthickness=1, highlightbackground=BORDER)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=12)
        self.canvas.bind("<Configure>", lambda _event: self.draw())
        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)

        panel = ttk.Frame(root, padding=(20, 20), width=290, style="Panel.TFrame")
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)
        ttk.Label(panel, text="NIRI / DISPLAY MATRIX", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(panel, text="MONITOR LAYOUT", style="Heading.TLabel").pack(anchor="w", pady=(5, 2))
        ttk.Label(panel, text="●  SESSION LINK ACTIVE", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 18))
        ttk.Label(
            panel,
            text="Drag displays to arrange. Edges snap together within 36 logical pixels.",
            style="Hint.TLabel",
            wraplength=240,
        ).pack(anchor="w", pady=(0, 20))

        ttk.Label(panel, text="01  /  SELECTED OUTPUT", style="Section.TLabel").pack(anchor="w")
        self.name_var = tk.StringVar(value="Select a display")
        ttk.Label(panel, textvariable=self.name_var, foreground=GREEN, font=("TkFixedFont", 13, "bold")).pack(anchor="w", pady=(5, 14))
        ttk.Label(panel, text="RESOLUTION / REFRESH", style="Section.TLabel").pack(anchor="w")
        self.mode_var = tk.StringVar()
        self.mode_box = ttk.Combobox(panel, textvariable=self.mode_var, state="readonly")
        self.mode_box.pack(fill="x", pady=(3, 10))
        self.mode_box.bind("<<ComboboxSelected>>", self.update_mode)

        ttk.Label(panel, text="02  /  SCALE", style="Section.TLabel").pack(anchor="w", pady=(6, 0))
        self.scale_var = tk.StringVar()
        scale_row = ttk.Frame(panel)
        scale_row.pack(fill="x", pady=(3, 10))
        self.scale_entry = ttk.Entry(scale_row, textvariable=self.scale_var)
        self.scale_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(scale_row, text="Set", command=self.update_scale).pack(side="left", padx=(5, 0))
        self.scale_entry.bind("<Return>", lambda _event: self.update_scale())

        ttk.Label(panel, text="03  /  ROTATION", style="Section.TLabel").pack(anchor="w", pady=(6, 0))
        self.transform_var = tk.StringVar()
        self.transform_box = ttk.Combobox(
            panel,
            textvariable=self.transform_var,
            values=("normal", "90", "180", "270", "flipped", "flipped-90", "flipped-180", "flipped-270"),
            state="readonly",
        )
        self.transform_box.pack(fill="x", pady=(3, 10))
        self.transform_box.bind("<<ComboboxSelected>>", self.update_transform)

        ttk.Separator(panel).pack(fill="x", pady=12)
        ttk.Button(panel, text="↳  EXPORT LAYOUT FRAGMENT", command=self.save, style="Neon.TButton").pack(fill="x")
        ttk.Label(
            panel,
            text="Exports output blocks to a separate KDL file. Active config stays untouched.",
            style="Hint.TLabel",
            wraplength=240,
            justify="left",
        ).pack(anchor="w", pady=(12, 0))
        self.position_var = tk.StringVar(value="")
        ttk.Label(panel, textvariable=self.position_var, foreground=GREEN, font=("TkFixedFont", 9)).pack(anchor="w", pady=(14, 0))
        ttk.Label(panel, text="NIRI CONFIG TOOL  //  KDL", style="Section.TLabel").pack(side="bottom", anchor="w")

        self.scale_factor = 1.0
        self.select(self.monitors[0])
        self.draw()

    def dimensions(self, monitor: dict) -> tuple[float, float]:
        match = re.match(r'(\d+)x(\d+)', monitor["mode"])
        width, height = (int(match.group(1)), int(match.group(2))) if match else (1920, 1080)
        scale = monitor["scale"] or 1.0
        if monitor["transform"] in ("90", "270", "flipped-90", "flipped-270"):
            width, height = height, width
        return width / scale, height / scale

    def draw(self):
        if not hasattr(self, "monitors") or not self.monitors:
            return
        canvas = self.canvas
        canvas.delete("all")
        cw, ch = max(canvas.winfo_width(), 1), max(canvas.winfo_height(), 1)
        bounds = []
        for monitor in self.monitors:
            w, h = self.dimensions(monitor)
            bounds.append((monitor["x"], monitor["y"], monitor["x"] + w, monitor["y"] + h))
        left, top = min(b[0] for b in bounds), min(b[1] for b in bounds)
        right, bottom = max(b[2] for b in bounds), max(b[3] for b in bounds)
        span_w, span_h = max(right - left, 1), max(bottom - top, 1)
        if self.drag_offset is None or not hasattr(self, "origin"):
            self.scale_factor = min((cw - 70) / span_w, (ch - 70) / span_h, 0.35)
            self.scale_factor = max(self.scale_factor, 0.04)
            offset_x = (cw - span_w * self.scale_factor) / 2 - left * self.scale_factor
            offset_y = (ch - span_h * self.scale_factor) / 2 - top * self.scale_factor
            self.origin = (offset_x, offset_y)
        else:
            offset_x, offset_y = self.origin

        # Faint terminal-like coordinate grid behind the layout.
        grid_step = 28
        for gx in range(0, cw, grid_step):
            canvas.create_line(gx, 0, gx, ch, fill=GRID, tags=("grid",))
        for gy in range(0, ch, grid_step):
            canvas.create_line(0, gy, cw, gy, fill=GRID, tags=("grid",))
        canvas.create_text(
            18, 16, anchor="nw", text="SPATIAL MAPPING  //  DRAG OUTPUTS",
            fill=MUTED, font=("TkFixedFont", 9), tags=("hud",),
        )
        canvas.create_text(
            cw - 18, ch - 16, anchor="se", text="PREVIEW ONLY  ·  NOT APPLIED",
            fill=MUTED, font=("TkFixedFont", 9), tags=("hud",),
        )

        for monitor in self.monitors:
            w, h = self.dimensions(monitor)
            x1 = offset_x + monitor["x"] * self.scale_factor
            y1 = offset_y + monitor["y"] * self.scale_factor
            x2, y2 = x1 + w * self.scale_factor, y1 + h * self.scale_factor
            selected = monitor is self.selected
            color = "#12351f" if selected else "#102319"
            outline = GREEN if selected else "#35704a"
            tags = (monitor["name"], "monitor")
            if selected:
                canvas.create_rectangle(
                    x1 - 4, y1 - 4, x2 + 4, y2 + 4,
                    fill=BG, outline="#1c6335", width=5, tags=tags,
                )
            canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline=outline, width=2, tags=tags)
            canvas.create_oval(
                x2 - 17, y1 + 11, x2 - 9, y1 + 19,
                fill=GREEN if selected else "#55705b", outline="", tags=tags,
            )
            center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
            canvas.create_text(
                center_x, center_y - 17, text=monitor["name"], fill=GREEN if selected else TEXT,
                font=("TkFixedFont", 12, "bold"), tags=tags,
            )
            canvas.create_text(
                center_x, center_y + 5, text=f'{int(w)} × {int(h)}', fill=TEXT,
                font=("TkFixedFont", 10), tags=tags,
            )
            canvas.create_text(
                center_x, center_y + 25, text=f'x={monitor["x"]}  y={monitor["y"]}',
                fill=MUTED, font=("TkFixedFont", 8), tags=tags,
            )

    def select(self, monitor: dict):
        self.selected = monitor
        self.name_var.set(monitor["name"])
        self.mode_box["values"] = monitor["modes"]
        self.mode_var.set(monitor["mode"])
        self.scale_var.set(f'{monitor["scale"]:g}')
        self.transform_var.set(monitor["transform"])
        self.position_var.set(f'Position: x={monitor["x"]}, y={monitor["y"]}')
        self.draw()

    def start_drag(self, event):
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            monitor = next((m for m in self.monitors if m["name"] in tags), None)
            if monitor:
                self.select(monitor)
                ox, oy = self.origin
                self.drag_offset = (
                    event.x - (ox + monitor["x"] * self.scale_factor),
                    event.y - (oy + monitor["y"] * self.scale_factor),
                )
                return
        self.drag_offset = None

    def snap_position(self, moving: dict, x: int, y: int) -> tuple[int, int]:
        mw, mh = self.dimensions(moving)
        candidates = []
        for other in self.monitors:
            if other is moving:
                continue
            ox, oy = other["x"], other["y"]
            ow, oh = self.dimensions(other)

            # Snap left/right edges together, optionally aligning top or bottom edges.
            for snap_x in (ox - mw, ox + ow):
                for snap_y in (y, oy, oy + oh - mh):
                    overlap_y = min(snap_y + mh, oy + oh) - max(snap_y, oy)
                    if (overlap_y > 0 and abs(snap_x - x) <= SNAP_DISTANCE
                            and abs(snap_y - y) <= SNAP_DISTANCE):
                        candidates.append((round(snap_x), round(snap_y)))

            # Snap top/bottom edges together, optionally aligning left or right edges.
            for snap_y in (oy - mh, oy + oh):
                for snap_x in (x, ox, ox + ow - mw):
                    overlap_x = min(snap_x + mw, ox + ow) - max(snap_x, ox)
                    if (overlap_x > 0 and abs(snap_x - x) <= SNAP_DISTANCE
                            and abs(snap_y - y) <= SNAP_DISTANCE):
                        candidates.append((round(snap_x), round(snap_y)))

        if not candidates:
            return x, y

        # If two neighboring displays offer nearly the same snap point, add a
        # midpoint candidate so the dragged display can settle between both.
        anchors = list(candidates)
        for index, first in enumerate(anchors):
            for second in anchors[index + 1:]:
                if (abs(first[0] - second[0]) <= SNAP_DISTANCE * 2
                        and abs(first[1] - second[1]) <= SNAP_DISTANCE * 2):
                    candidates.append((round((first[0] + second[0]) / 2),
                                       round((first[1] + second[1]) / 2)))

        def touching_neighbors(point: tuple[int, int]) -> int:
            px, py = point
            count = 0
            for other in self.monitors:
                if other is moving:
                    continue
                ox, oy = other["x"], other["y"]
                ow, oh = self.dimensions(other)
                overlap_x = min(px + mw, ox + ow) - max(px, ox)
                overlap_y = min(py + mh, oy + oh) - max(py, oy)
                horizontal_touch = overlap_y > 0 and (
                    0 <= px - (ox + ow) <= SNAP_DISTANCE
                    or 0 <= ox - (px + mw) <= SNAP_DISTANCE
                )
                vertical_touch = overlap_x > 0 and (
                    0 <= py - (oy + oh) <= SNAP_DISTANCE
                    or 0 <= oy - (py + mh) <= SNAP_DISTANCE
                )
                if horizontal_touch or vertical_touch:
                    count += 1
            return count

        # Prefer a placement that snaps to multiple monitors, then the closest
        # one to the pointer-derived position.
        return min(
            candidates,
            key=lambda point: (
                -touching_neighbors(point),
                (point[0] - x) ** 2 + (point[1] - y) ** 2,
            ),
        )

    def drag(self, event):
        if self.drag_offset is None or self.selected is None:
            return
        ox, oy = self.origin
        x = round((event.x - self.drag_offset[0] - ox) / self.scale_factor / 10) * 10
        y = round((event.y - self.drag_offset[1] - oy) / self.scale_factor / 10) * 10
        x, y = self.snap_position(self.selected, int(x), int(y))
        self.selected["x"], self.selected["y"] = int(x), int(y)
        self.position_var.set(f"Position: x={int(x)}, y={int(y)}")
        self.draw()

    def end_drag(self, _event):
        self.drag_offset = None
        self.draw()

    def update_mode(self, _event=None):
        if self.selected:
            self.selected["mode"] = self.mode_var.get()
            self.draw()

    def update_scale(self):
        try:
            scale = float(self.scale_var.get())
            if not 0 < scale <= 8:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid scale", "Enter a number greater than 0 and no greater than 8.")
            return
        if self.selected:
            self.selected["scale"] = scale
            self.draw()

    def update_transform(self, _event=None):
        if self.selected:
            self.selected["transform"] = self.transform_var.get()
            self.draw()

    def save(self):
        path = filedialog.asksaveasfilename(
            title="Save Niri monitor layout",
            initialdir=str(CONFIG.parent),
            initialfile="monitor-layout.kdl",
            defaultextension=".kdl",
            filetypes=(("KDL config", "*.kdl"), ("All files", "*")),
        )
        if not path:
            return
        contents = [
            "// Niri monitor layout fragment. Review, then copy these output blocks into config.kdl.\n",
            "// Alternatively, use: include \"/absolute/path/to/this-file.kdl\"\n\n",
        ]
        for monitor in self.monitors:
            contents.extend([
                f'output "{monitor["name"]}" {{\n',
                f'    mode "{monitor["mode"]}"\n',
                f'    scale {monitor["scale"]:g}\n',
                f'    transform "{monitor["transform"]}"\n',
                f'    position x={monitor["x"]} y={monitor["y"]}\n',
                "}\n\n",
            ])
        try:
            Path(path).write_text("".join(contents))
        except OSError as error:
            messagebox.showerror("Save failed", str(error))
            return
        messagebox.showinfo("Layout saved", f"Saved output blocks to:\n{path}")


def main():
    root = tk.Tk()
    LayoutEditor(root)
    try:
        if root.winfo_exists():
            root.mainloop()
    except tk.TclError:
        pass


if __name__ == "__main__":
    main()

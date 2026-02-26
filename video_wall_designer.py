#!/usr/bin/env python3
"""
Video Wall Designer v1.1
Creates UV-mapped 3D meshes for video walls – flat or curved.
Compatible with Blender and Unreal Engine.

Requirements:
    pip install matplotlib numpy
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────

PANEL_DEPTH = 0.2   # metres – fixed Y dimension (depth of all panels)
APP_VERSION = "1.1"
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panels.json")

DEFAULT_PANELS = [
    {"name": "Absen A27S 2.7mm",        "width": 0.500, "height": 0.5625, "power": 160, "weight": 8.5},
    {"name": "Absen PL2.9 2.9mm",       "width": 0.576, "height": 0.576,  "power": 200, "weight": 9.5},
    {"name": "ROE Black Pearl 2.84mm",  "width": 0.500, "height": 0.5625, "power": 180, "weight": 9.0},
    {"name": "ROE CB5 5mm",             "width": 0.500, "height": 1.000,  "power": 350, "weight": 14.5},
    {"name": "Unilumin UPAD III 2.9mm", "width": 0.576, "height": 0.576,  "power": 210, "weight": 10.0},
    {"name": "Leyard TWS2.8",           "width": 0.500, "height": 0.500,  "power": 170, "weight": 8.8},
    {"name": "Generic 500x500mm",       "width": 0.500, "height": 0.500,  "power": 150, "weight": 8.0},
    {"name": "Generic 500x1000mm",      "width": 0.500, "height": 1.000,  "power": 300, "weight": 16.0},
]

# ──────────────────────────────────────────────────────────────────
# Panel Database
# ──────────────────────────────────────────────────────────────────

class PanelDB:
    """Manages the LED panel database stored in panels.json."""

    def __init__(self, path=DB_FILE):
        self.path = path
        self.panels = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.panels = json.load(f)
                return
            except Exception:
                pass
        self.panels = [dict(p) for p in DEFAULT_PANELS]
        self._save()

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.panels, f, indent=2)

    def names(self):
        return [p["name"] for p in self.panels]

    def get(self, name):
        for p in self.panels:
            if p["name"] == name:
                return p
        return None

    def add(self, panel):
        self.panels.append(panel)
        self._save()

    def remove(self, name):
        self.panels = [p for p in self.panels if p["name"] != name]
        self._save()


# ──────────────────────────────────────────────────────────────────
# Curved Wall Geometry
# ──────────────────────────────────────────────────────────────────

def compute_curved_transforms(cols, pw, pd, angle_per_col_deg):
    """
    Compute 2D panel corner positions for a horizontally curved video wall.

    The wall is concave (curves away from the viewer). The centre column faces
    straight forward (theta=0); outer columns angle away symmetrically.

    Coordinate system
    -----------------
    X : horizontal (wall width)
    Y : depth  — Y=0 is the viewer side, Y increases away from viewer

    Parameters
    ----------
    cols              : number of columns
    pw                : panel width  (m)
    pd                : panel depth  (m)
    angle_per_col_deg : rotation angle between adjacent columns (degrees)

    Returns
    -------
    List of dicts — one per column:
        lf, rf, lb, rb : 2D numpy arrays  (left/right × front/back corners)
        theta          : column face rotation in radians (for normal vectors)
    """
    if cols == 0:
        return []

    half = (cols - 1) / 2.0
    pen = np.array([0.0, 0.0])
    results = []

    for c in range(cols):
        theta = np.radians((c - half) * angle_per_col_deg)
        right = np.array([ np.cos(theta),  np.sin(theta)])   # along panel face
        depth = np.array([-np.sin(theta),  np.cos(theta)])   # into screen

        lf = pen.copy()
        rf = pen + pw * right
        lb = pen + pd * depth
        rb = pen + pw * right + pd * depth

        results.append({"lf": lf, "rf": rf, "lb": lb, "rb": rb, "theta": theta})
        pen = rf.copy()

    # Centre X so the wall is symmetric around x=0
    all_x = [r["lf"][0] for r in results] + [r["rf"][0] for r in results]
    cx = (min(all_x) + max(all_x)) / 2.0
    offset = np.array([cx, 0.0])
    for r in results:
        for k in ("lf", "rf", "lb", "rb"):
            r[k] = r[k] - offset

    return results


# ──────────────────────────────────────────────────────────────────
# Add Panel Dialog
# ──────────────────────────────────────────────────────────────────

class AddPanelDialog(tk.Toplevel):
    """Dialog window for entering a new panel specification."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add New Panel")
        self.resizable(False, False)
        self.configure(bg="#2b2b2b")
        self.result = None
        self.grab_set()

        FIELDS = [
            ("Panel Name",      "name",   str,   "My Panel 2.9mm"),
            ("Width / X (m)",   "width",  float, "0.500"),
            ("Height / Z (m)",  "height", float, "0.500"),
            ("Power (W)",       "power",  float, "150"),
            ("Weight (kg)",     "weight", float, "8.0"),
        ]

        self.vars = {}
        pad = {"padx": 12, "pady": 5}

        tk.Label(self, text="Add New Panel", bg="#2b2b2b", fg="#ffffff",
                 font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2,
                                                      pady=(12, 8), padx=12)

        for i, (label, key, typ, default) in enumerate(FIELDS, start=1):
            tk.Label(self, text=label, bg="#2b2b2b", fg="#cccccc",
                     font=("Segoe UI", 9), anchor="w", width=16).grid(
                         row=i, column=0, sticky="w", **pad)
            var = tk.StringVar(value=default)
            self.vars[key] = (var, typ)
            entry = tk.Entry(self, textvariable=var, width=22,
                             bg="#3a3a3a", fg="#ffffff", insertbackground="white",
                             relief="flat", bd=4, font=("Segoe UI", 9))
            entry.grid(row=i, column=1, sticky="ew", **pad)

        sep = tk.Frame(self, bg="#444444", height=1)
        sep.grid(row=len(FIELDS) + 1, column=0, columnspan=2, sticky="ew",
                 padx=12, pady=6)

        btn_frame = tk.Frame(self, bg="#2b2b2b")
        btn_frame.grid(row=len(FIELDS) + 2, column=0, columnspan=2, pady=(4, 12))

        tk.Button(btn_frame, text="Add Panel", command=self._add,
                  bg="#2a5298", fg="white", relief="flat", padx=14, pady=5,
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Cancel", command=self.destroy,
                  bg="#555555", fg="white", relief="flat", padx=14, pady=5,
                  font=("Segoe UI", 9)).pack(side="left", padx=6)

        self.transient(parent)
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph_ = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph_ - h) // 2}")
        self.wait_window()

    def _add(self):
        try:
            panel = {}
            for key, (var, typ) in self.vars.items():
                val = var.get().strip()
                if not val:
                    raise ValueError(f"'{key}' cannot be empty.")
                panel[key] = typ(val)
            if not panel["name"]:
                raise ValueError("Panel name cannot be empty.")
            if panel["width"] <= 0 or panel["height"] <= 0:
                raise ValueError("Width and Height must be greater than zero.")
            if panel["power"] < 0 or panel["weight"] < 0:
                raise ValueError("Power and Weight must be non-negative.")
            self.result = panel
            self.destroy()
        except ValueError as exc:
            messagebox.showerror("Invalid Input", str(exc), parent=self)


# ──────────────────────────────────────────────────────────────────
# Curve Editor Dialog
# ──────────────────────────────────────────────────────────────────

class CurveEditor(tk.Toplevel):
    """
    Popup for configuring the horizontal curve of the video wall.

    Step options
    ------------
    Per column      – the entered angle is applied at every column joint.
                      For a 500 mm panel this equals an angle every 0.5 m.
    Every 2 columns – the entered angle spans two panels (0° at midpoint).
                      For a 500 mm panel this equals an angle every 1.0 m.
                      Internally, angle_per_col = entered_angle / 2.
    """

    PRESETS = [("Gentle  3°", 3.0), ("Medium  8°", 8.0), ("Tight  15°", 15.0)]

    def __init__(self, parent, panel_width, current_angle, current_step, cols):
        super().__init__(parent)
        self.title("Edit Curve")
        self.resizable(False, False)
        self.configure(bg="#2b2b2b")
        self.result = None
        self.grab_set()

        self._pw   = panel_width
        self._cols = cols

        # Build human-readable step labels that include the physical distance
        self._step_labels = [
            f"Per column  ({panel_width:.3f} m)",
            f"Every 2 columns  ({2 * panel_width:.3f} m)",
        ]
        self._label_to_key = {
            self._step_labels[0]: "per_column",
            self._step_labels[1]: "every_2",
        }
        self._key_to_label = {v: k for k, v in self._label_to_key.items()}

        self.step_var  = tk.StringVar(value=self._key_to_label.get(current_step,
                                                                     self._step_labels[0]))
        self.angle_var = tk.StringVar(value=f"{current_angle:.1f}")

        self._build()
        self.transient(parent)
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw_, ph_ = parent.winfo_width(), parent.winfo_height()
        dw, dh = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw_ - dw) // 2}+{py + (ph_ - dh) // 2}")
        self._refresh_preview()
        self.wait_window()

    # ── Build UI ──────────────────────────────────────────────────

    def _build(self):
        pad = dict(padx=12, pady=5)

        tk.Label(self, text="Edit Curve", bg="#2b2b2b", fg="#ffffff",
                 font=("Segoe UI", 11, "bold")).pack(pady=(12, 6), padx=12)

        # ── Step size ────────────────────────────────────────────
        sf = tk.Frame(self, bg="#2b2b2b")
        sf.pack(fill="x", **pad)
        tk.Label(sf, text="Angle step:", bg="#2b2b2b", fg="#cccccc",
                 font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
        step_cb = ttk.Combobox(sf, textvariable=self.step_var,
                               values=self._step_labels, state="readonly", width=28)
        step_cb.pack(side="left")
        step_cb.bind("<<ComboboxSelected>>", lambda _: self._refresh_preview())

        # ── Angle per step ───────────────────────────────────────
        af = tk.Frame(self, bg="#2b2b2b")
        af.pack(fill="x", **pad)
        tk.Label(af, text="Angle per step:", bg="#2b2b2b", fg="#cccccc",
                 font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
        ae = tk.Entry(af, textvariable=self.angle_var, width=8,
                      bg="#3a3a3a", fg="#ffffff", insertbackground="white",
                      relief="flat", bd=4, font=("Segoe UI", 9))
        ae.pack(side="left")
        ae.bind("<Return>",   lambda _: self._refresh_preview())
        ae.bind("<FocusOut>", lambda _: self._refresh_preview())
        tk.Label(af, text="degrees", bg="#2b2b2b", fg="#888888",
                 font=("Segoe UI", 8)).pack(side="left", padx=6)

        # ── Presets ──────────────────────────────────────────────
        pf = tk.Frame(self, bg="#2b2b2b")
        pf.pack(fill="x", padx=12, pady=(0, 2))
        tk.Label(pf, text="Presets:", bg="#2b2b2b", fg="#666666",
                 font=("Segoe UI", 8)).pack(side="left")
        for label, val in self.PRESETS:
            v = val
            tk.Button(pf, text=label, command=lambda v=v: self._apply_preset(v),
                      bg="#3a3a3a", fg="#cccccc", relief="flat",
                      padx=8, pady=2, font=("Segoe UI", 8)).pack(side="left", padx=3)

        # ── Top-down preview canvas ──────────────────────────────
        tk.Label(self, text="Top-down preview  (▲ viewer at bottom)",
                 bg="#2b2b2b", fg="#666666", font=("Segoe UI", 8)).pack(
                     anchor="w", padx=12, pady=(6, 1))

        self.preview = tk.Canvas(self, width=380, height=180,
                                 bg="#0d0d0d", highlightthickness=1,
                                 highlightbackground="#333333")
        self.preview.pack(padx=12, pady=(0, 2))

        self.info_lbl = tk.Label(self, text="", bg="#2b2b2b", fg="#888888",
                                 font=("Segoe UI", 8))
        self.info_lbl.pack(padx=12, pady=(0, 4))

        # ── Buttons ──────────────────────────────────────────────
        tk.Frame(self, bg="#444444", height=1).pack(fill="x", padx=12, pady=6)
        bf = tk.Frame(self, bg="#2b2b2b")
        bf.pack(pady=(2, 12))
        tk.Button(bf, text="Apply", command=self._apply,
                  bg="#2a5298", fg="white", relief="flat", padx=16, pady=5,
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)
        tk.Button(bf, text="Cancel", command=self.destroy,
                  bg="#555555", fg="white", relief="flat", padx=16, pady=5,
                  font=("Segoe UI", 9)).pack(side="left", padx=6)

    # ── Logic ────────────────────────────────────────────────────

    def _apply_preset(self, val):
        self.angle_var.set(f"{val:.1f}")
        self._refresh_preview()

    def _angle_per_col(self):
        """Return the effective angle per column from current inputs."""
        try:
            a = float(self.angle_var.get())
        except ValueError:
            a = 5.0
        key = self._label_to_key.get(self.step_var.get(), "per_column")
        return a / 2.0 if key == "every_2" else a

    def _refresh_preview(self):
        cv = self.preview
        cv.delete("all")
        cw, ch = 380, 180

        apc = self._angle_per_col()
        transforms = compute_curved_transforms(self._cols, self._pw, PANEL_DEPTH, apc)
        if not transforms:
            return

        # Bounding box of all 2D corner points
        all_pts = [t[k] for t in transforms for k in ("lf", "rf", "lb", "rb")]
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        rx = max(max_x - min_x, 1e-3)
        ry = max(max_y - min_y, 1e-3)

        pad_px = 28
        scale = min((cw - 2 * pad_px) / rx, (ch - 2 * pad_px) / ry)

        def to_c(pt):
            """Convert world XY to canvas XY (Y flipped so viewer is at bottom)."""
            cx_ = (pt[0] - min_x) * scale + pad_px
            cy_ = ch - ((pt[1] - min_y) * scale + pad_px)
            return cx_, cy_

        # Draw each panel as a thin rectangle (top-down view = XY plane)
        for t in transforms:
            corners = [to_c(t["lf"]), to_c(t["rf"]),
                       to_c(t["rb"]), to_c(t["lb"])]
            flat = [v for pt in corners for v in pt]
            cv.create_polygon(flat, fill="#1a3a6b", outline="#3060bb", width=1)

        # Draw centre-line of front face as a subtle arc guide
        front_mids = [((t["lf"][0] + t["rf"][0]) / 2,
                       (t["lf"][1] + t["rf"][1]) / 2) for t in transforms]
        for i in range(len(front_mids) - 1):
            a, b = to_c(front_mids[i]), to_c(front_mids[i + 1])
            cv.create_line(a[0], a[1], b[0], b[1], fill="#4488cc", width=1, dash=(3, 3))

        # Viewer indicator
        viewer_y = ch - pad_px + 10
        cv.create_text(cw // 2, min(viewer_y + 8, ch - 4),
                       text="▲  Viewer", fill="#555555", font=("Segoe UI", 8))

        total_arc = (self._cols - 1) * apc
        step_label = "per col" if self._label_to_key.get(
            self.step_var.get(), "per_column") == "per_column" else "per 2 cols"
        entered_angle = float(self.angle_var.get()) if self.angle_var.get() else apc
        self.info_lbl.config(
            text=f"{entered_angle:.1f}° {step_label}  →  "
                 f"{apc:.2f}° per column  |  total arc: {total_arc:.1f}°"
        )

    def _apply(self):
        try:
            angle = float(self.angle_var.get())
            if not (0.0 < angle <= 45.0):
                raise ValueError("Angle must be between 0.1° and 45°.")
        except ValueError as exc:
            messagebox.showerror("Invalid Angle", str(exc), parent=self)
            return
        step_key = self._label_to_key.get(self.step_var.get(), "per_column")
        self.result = {"step": step_key, "angle": angle}
        self.destroy()


# ──────────────────────────────────────────────────────────────────
# Geometry & OBJ Export
# ──────────────────────────────────────────────────────────────────

def _box_for_panel(col, row, pw, ph, pd, cols, rows):
    """Return (verts 8×3, face-index dict, front_uvs) for one flat panel box."""
    x0, x1 = col * pw,  (col + 1) * pw
    z0, z1 = row * ph,  (row + 1) * ph
    y0, y1 = 0.0, pd

    verts = np.array([
        [x0, y0, z1],  # 0 front top-left
        [x1, y0, z1],  # 1 front top-right
        [x1, y0, z0],  # 2 front bottom-right
        [x0, y0, z0],  # 3 front bottom-left
        [x0, y1, z1],  # 4 back  top-left
        [x1, y1, z1],  # 5 back  top-right
        [x1, y1, z0],  # 6 back  bottom-right
        [x0, y1, z0],  # 7 back  bottom-left
    ], dtype=float)

    faces = {
        "front":  [0, 1, 2, 3],
        "back":   [5, 4, 7, 6],
        "left":   [4, 0, 3, 7],
        "right":  [1, 5, 6, 2],
        "top":    [4, 5, 1, 0],
        "bottom": [3, 2, 6, 7],
    }

    u0, u1 = col / cols, (col + 1) / cols
    v0, v1 = row / rows, (row + 1) / rows
    front_uvs = [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]

    return verts, faces, front_uvs


_BODY_UV = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def _curved_box_verts(t, z0, z1):
    """
    Return the 8 vertices of a curved panel box as a list of (x, y, z) tuples.

    Vertex order (mirrors _box_for_panel for consistency):
        0 lf z1,  1 rf z1,  2 rf z0,  3 lf z0
        4 lb z1,  5 rb z1,  6 rb z0,  7 lb z0
    """
    lf, rf, lb, rb = t["lf"], t["rf"], t["lb"], t["rb"]
    return [
        (lf[0], lf[1], z1),  # 0
        (rf[0], rf[1], z1),  # 1
        (rf[0], rf[1], z0),  # 2
        (lf[0], lf[1], z0),  # 3
        (lb[0], lb[1], z1),  # 4
        (rb[0], rb[1], z1),  # 5
        (rb[0], rb[1], z0),  # 6
        (lb[0], lb[1], z0),  # 7
    ]


def _curved_normals(theta):
    """Return face normals for a curved panel rotated by theta (radians)."""
    st, ct = np.sin(theta), np.cos(theta)
    return {
        "front":  ( st, -ct,  0),
        "back":   (-st,  ct,  0),
        "left":   (-ct, -st,  0),
        "right":  ( ct,  st,  0),
        "top":    ( 0,   0,   1),
        "bottom": ( 0,   0,  -1),
    }


_FLAT_NORMALS = {
    "front":  ( 0, -1,  0),
    "back":   ( 0,  1,  0),
    "left":   (-1,  0,  0),
    "right":  ( 1,  0,  0),
    "top":    ( 0,  0,  1),
    "bottom": ( 0,  0, -1),
}

_FACE_INDICES = {
    "front":  [0, 1, 2, 3],
    "back":   [5, 4, 7, 6],
    "left":   [4, 0, 3, 7],
    "right":  [1, 5, 6, 2],
    "top":    [4, 5, 1, 0],
    "bottom": [3, 2, 6, 7],
}


def export_obj(filepath, panel, cols, rows, angle_per_col=0.0):
    """
    Write a Wavefront OBJ + MTL pair for the video wall.

    Parameters
    ----------
    angle_per_col : degrees of rotation between adjacent columns.
                    0.0 (default) produces a flat wall.
    """
    pw, ph, pd = panel["width"], panel["height"], PANEL_DEPTH
    total_w = cols * pw
    total_h = rows * ph
    half_h  = total_h / 2.0
    curved  = angle_per_col != 0.0

    obj_name = os.path.splitext(os.path.basename(filepath))[0]
    mtl_name = obj_name + ".mtl"
    mtl_path = os.path.join(os.path.dirname(os.path.abspath(filepath)), mtl_name)

    all_verts   = []
    all_uvs     = []
    all_normals = []
    front_faces = []
    body_faces  = []

    if curved:
        transforms = compute_curved_transforms(cols, pw, pd, angle_per_col)
    else:
        cx = total_w / 2.0  # flat centring

    for r in range(rows):
        z0 = r * ph - half_h
        z1 = z0 + ph

        for c in range(cols):
            # ── Vertices ───────────────────────────────────────────
            if curved:
                t = transforms[c]
                verts_list = _curved_box_verts(t, z0, z1)
                norms = _curved_normals(t["theta"])
            else:
                raw, _, _ = _box_for_panel(c, r, pw, ph, pd, cols, rows)
                raw -= np.array([cx, 0.0, half_h])
                verts_list = [tuple(v) for v in raw]
                norms = _FLAT_NORMALS

            base_v = len(all_verts)
            all_verts.extend(verts_list)

            # ── UV (front face maps to its slice of the full texture) ──
            u0, u1 = c / cols, (c + 1) / cols
            v0_, v1_ = r / rows, (r + 1) / rows
            front_uvs = [(u0, v1_), (u1, v1_), (u1, v0_), (u0, v0_)]

            # ── Front face ─────────────────────────────────────────
            fi = _FACE_INDICES["front"]
            base_uv = len(all_uvs)
            all_uvs.extend(front_uvs)
            ni = len(all_normals)
            all_normals.append(norms["front"])
            front_faces.append({
                "vi": [base_v + i for i in fi],
                "ui": list(range(base_uv, base_uv + 4)),
                "ni": ni,
            })

            # ── Body faces ─────────────────────────────────────────
            for face_name in ("back", "left", "right", "top", "bottom"):
                fi2 = _FACE_INDICES[face_name]
                base_uv2 = len(all_uvs)
                all_uvs.extend(_BODY_UV)
                ni2 = len(all_normals)
                all_normals.append(norms[face_name])
                body_faces.append({
                    "vi": [base_v + i for i in fi2],
                    "ui": list(range(base_uv2, base_uv2 + 4)),
                    "ni": ni2,
                })

    # ── Write MTL ──────────────────────────────────────────────────
    with open(mtl_path, "w", encoding="utf-8") as f:
        f.write("# Video Wall Material File\n")
        f.write(f"# Generated by Video Wall Designer v{APP_VERSION}\n\n")
        f.write("newmtl display_face\n")
        f.write("Ka 0.00 0.00 0.00\n")
        f.write("Kd 0.05 0.05 0.08\n")
        f.write("Ks 0.50 0.50 0.60\n")
        f.write("Ns 80.000\nd 1.0\nillum 2\n")
        f.write("# map_Kd videowall_texture.png\n\n")
        f.write("newmtl panel_body\n")
        f.write("Ka 0.00 0.00 0.00\n")
        f.write("Kd 0.12 0.12 0.12\n")
        f.write("Ks 0.20 0.20 0.20\n")
        f.write("Ns 30.000\nd 1.0\nillum 2\n")

    # ── Write OBJ ──────────────────────────────────────────────────
    shape_note = (f"Curved  {angle_per_col:.2f} deg/column" if curved else "Flat")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# Video Wall Mesh\n")
        f.write(f"# Generated by Video Wall Designer v{APP_VERSION}\n")
        f.write(f"# Panel    : {panel['name']}\n")
        f.write(f"# Layout   : {cols} columns x {rows} rows\n")
        f.write(f"# Shape    : {shape_note}\n")
        f.write(f"# Panels   : {cols * rows}\n")
        f.write(f"# Wall size: {total_w:.3f} m (W) x {total_h:.3f} m (H) x {pd:.3f} m (D)\n")
        f.write(f"# Power    : {cols * rows * panel['power']:.0f} W total\n")
        f.write(f"# Weight   : {cols * rows * panel['weight']:.1f} kg total\n")
        f.write(f"# UV note  : Apply one texture to 'display_face' for full video content\n\n")
        f.write(f"mtllib {mtl_name}\n")
        f.write(f"o VideoWall_{cols}x{rows}\n\n")

        for v in all_verts:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        f.write("\n")
        for uv in all_uvs:
            f.write(f"vt {uv[0]:.6f} {uv[1]:.6f}\n")
        f.write("\n")
        for n in all_normals:
            f.write(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
        f.write("\n")

        f.write("g display_surface\nusemtl display_face\n")
        for face in front_faces:
            vi, ui, ni = face["vi"], face["ui"], face["ni"]
            tokens = " ".join(f"{vi[k]+1}/{ui[k]+1}/{ni+1}" for k in range(4))
            f.write(f"f {tokens}\n")
        f.write("\n")

        f.write("g panel_housing\nusemtl panel_body\n")
        for face in body_faces:
            vi, ui, ni = face["vi"], face["ui"], face["ni"]
            tokens = " ".join(f"{vi[k]+1}/{ui[k]+1}/{ni+1}" for k in range(4))
            f.write(f"f {tokens}\n")

    return filepath, mtl_path


# ──────────────────────────────────────────────────────────────────
# Main Application
# ──────────────────────────────────────────────────────────────────

class VideoWallApp:

    # ── Initialisation ──────────────────────────────────────────────

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"Video Wall Designer v{APP_VERSION}")
        self.root.minsize(1100, 700)
        self.root.configure(bg="#2b2b2b")

        self.db = PanelDB()
        self.show_info    = tk.BooleanVar(value=True)
        self._azim        = -50
        self._elev        = 22

        # Curve state
        self.curve_mode   = tk.StringVar(value="Flat")  # "Flat" | "Curved"
        self.curve_angle  = 5.0        # degrees per step (as entered in dialog)
        self.curve_step   = "per_column"  # "per_column" | "every_2"

        self._build_ui()
        self._on_panel_change()

    # ── UI Construction ─────────────────────────────────────────────

    def _build_ui(self):
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        ctrl = tk.Frame(self.root, width=300, bg="#2b2b2b")
        ctrl.grid(row=0, column=0, sticky="nsew")
        ctrl.grid_propagate(False)

        vp = tk.Frame(self.root, bg="#111111")
        vp.grid(row=0, column=1, sticky="nsew")
        vp.rowconfigure(0, weight=1)
        vp.columnconfigure(0, weight=1)

        self._build_controls(ctrl)
        self._build_viewport(vp)

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _section_header(parent, text):
        f = tk.Frame(parent, bg="#1e1e1e")
        f.pack(fill="x", padx=0, pady=(10, 2))
        tk.Label(f, text=f"  {text.upper()}", bg="#1e1e1e", fg="#777777",
                 font=("Segoe UI", 8, "bold"), pady=4).pack(side="left")
        return f

    @staticmethod
    def _dark_label(parent, text, **kw):
        d = {"bg": "#2b2b2b", "fg": "#bbbbbb", "anchor": "w", "font": ("Segoe UI", 9)}
        d.update(kw)
        return tk.Label(parent, text=text, **d)

    @staticmethod
    def _info_row(parent, label, value="–"):
        row = tk.Frame(parent, bg="#222222")
        row.pack(fill="x", padx=6, pady=1)
        tk.Label(row, text=label, bg="#222222", fg="#888888",
                 font=("Segoe UI", 8), width=14, anchor="w").pack(side="left")
        lbl = tk.Label(row, text=value, bg="#222222", fg="#e0e0e0",
                       font=("Segoe UI", 8, "bold"), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        return lbl

    # ── Controls sidebar ────────────────────────────────────────────

    def _build_controls(self, parent):
        tk.Label(parent, text="Video Wall Designer", bg="#1a1a1a", fg="#ffffff",
                 font=("Segoe UI", 13, "bold"), pady=14).pack(fill="x")

        # ── Panel selection ──────────────────────────────────────────
        self._section_header(parent, "LED Panel")
        self._dark_label(parent, "Panel Model:").pack(fill="x", padx=8, pady=(4, 0))

        combo_frame = tk.Frame(parent, bg="#2b2b2b")
        combo_frame.pack(fill="x", padx=8, pady=2)

        self.panel_var = tk.StringVar()
        self.panel_combo = ttk.Combobox(combo_frame, textvariable=self.panel_var,
                                         state="readonly")
        self.panel_combo.pack(side="left", fill="x", expand=True)
        self.panel_combo.bind("<<ComboboxSelected>>", lambda _: self._on_panel_change())

        tk.Button(combo_frame, text="＋", command=self._add_panel,
                  bg="#2a5298", fg="white", relief="flat", width=3,
                  font=("Segoe UI", 10)).pack(side="left", padx=(4, 0))

        self._refresh_combo()

        info_bg = tk.Frame(parent, bg="#222222", bd=0)
        info_bg.pack(fill="x", padx=8, pady=(4, 0))
        self.lbl_pw  = self._info_row(info_bg, "Width (X):")
        self.lbl_ph  = self._info_row(info_bg, "Height (Z):")
        self.lbl_pd  = self._info_row(info_bg, "Depth (Y):", f"{PANEL_DEPTH:.3f} m")
        self.lbl_pwr = self._info_row(info_bg, "Power:")
        self.lbl_wgt = self._info_row(info_bg, "Weight:")

        # ── Wall Layout ──────────────────────────────────────────────
        self._section_header(parent, "Wall Layout")

        grid_frame = tk.Frame(parent, bg="#2b2b2b")
        grid_frame.pack(fill="x", padx=8, pady=4)
        grid_frame.columnconfigure(1, weight=1)

        self._dark_label(grid_frame, "Columns (X):").grid(row=0, column=0, sticky="w", pady=3)
        self.cols_var = tk.IntVar(value=4)
        self._make_spinbox(grid_frame, self.cols_var).grid(row=0, column=1, sticky="e", pady=3)

        self._dark_label(grid_frame, "Rows (Z):").grid(row=1, column=0, sticky="w", pady=3)
        self.rows_var = tk.IntVar(value=3)
        self._make_spinbox(grid_frame, self.rows_var).grid(row=1, column=1, sticky="e", pady=3)

        # ── Curve ────────────────────────────────────────────────────
        self._section_header(parent, "Wall Shape")

        shape_row = tk.Frame(parent, bg="#2b2b2b")
        shape_row.pack(fill="x", padx=8, pady=(4, 2))

        self._dark_label(shape_row, "Shape:").pack(side="left")
        shape_cb = ttk.Combobox(shape_row, textvariable=self.curve_mode,
                                values=["Flat", "Curved"], state="readonly", width=8)
        shape_cb.pack(side="left", padx=(4, 8))
        shape_cb.bind("<<ComboboxSelected>>", self._on_curve_mode_change)

        self.btn_edit_curve = tk.Button(shape_row, text="Edit Curve ▶",
                                         command=self._open_curve_editor,
                                         bg="#4a3010", fg="#cc9944", relief="flat",
                                         padx=8, pady=3, font=("Segoe UI", 8),
                                         state="disabled")
        self.btn_edit_curve.pack(side="left")

        self.lbl_curve_info = tk.Label(parent, text="", bg="#2b2b2b", fg="#888888",
                                        font=("Segoe UI", 8))
        self.lbl_curve_info.pack(anchor="w", padx=10)

        # ── Wall Summary ─────────────────────────────────────────────
        self._section_header(parent, "Wall Summary")

        chk = tk.Checkbutton(parent, text="Show Info Overlay",
                              variable=self.show_info, command=self._update_view,
                              bg="#2b2b2b", fg="#cccccc", selectcolor="#2b2b2b",
                              activebackground="#2b2b2b", font=("Segoe UI", 9))
        chk.pack(padx=8, anchor="w", pady=(2, 0))

        summary_bg = tk.Frame(parent, bg="#222222")
        summary_bg.pack(fill="x", padx=8, pady=4)
        self.lbl_total_panels = self._info_row(summary_bg, "Total Panels:")
        self.lbl_total_power  = self._info_row(summary_bg, "Total Power:")
        self.lbl_total_weight = self._info_row(summary_bg, "Total Weight:")
        self.lbl_wall_w       = self._info_row(summary_bg, "Wall Width:")
        self.lbl_wall_h       = self._info_row(summary_bg, "Wall Height:")

        # ── View presets ─────────────────────────────────────────────
        self._section_header(parent, "View")

        vbf = tk.Frame(parent, bg="#2b2b2b")
        vbf.pack(fill="x", padx=8, pady=4)
        for label, cmd in [("Front", self._view_front),
                            ("Isometric", self._view_iso),
                            ("Top", self._view_top)]:
            tk.Button(vbf, text=label, command=cmd, bg="#3a3a3a", fg="#cccccc",
                      relief="flat", pady=4, font=("Segoe UI", 8)
                      ).pack(side="left", fill="x", expand=True, padx=2)

        # ── Export ───────────────────────────────────────────────────
        self._section_header(parent, "Export")

        tk.Button(parent, text="Export OBJ / MTL Mesh", command=self._export,
                  bg="#1a6b35", fg="white", relief="flat", pady=8,
                  font=("Segoe UI", 10, "bold")).pack(padx=8, pady=4, fill="x")

        tk.Label(parent, text="Exports .obj + .mtl with UV mapping\n"
                              "Ready for Blender & Unreal Engine",
                 bg="#2b2b2b", fg="#555555",
                 font=("Segoe UI", 8), justify="center").pack()

        tk.Frame(parent, bg="#2b2b2b").pack(expand=True, fill="both")

    def _make_spinbox(self, parent, var):
        sb = tk.Spinbox(parent, from_=1, to=200, textvariable=var, width=6,
                        bg="#3a3a3a", fg="#ffffff", insertbackground="white",
                        buttonbackground="#3a3a3a", relief="flat",
                        command=self._update_view, font=("Segoe UI", 9))
        sb.bind("<Return>",   lambda _: self._update_view())
        sb.bind("<FocusOut>", lambda _: self._update_view())
        return sb

    # ── 3D Viewport ─────────────────────────────────────────────────

    def _build_viewport(self, parent):
        self.fig = Figure(facecolor="#111111")
        self.ax  = self.fig.add_subplot(111, projection="3d")
        self.ax.set_facecolor("#111111")
        self.fig.subplots_adjust(left=0, right=1, bottom=0.02, top=0.98)

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        widget = self.canvas.get_tk_widget()
        widget.grid(row=0, column=0, sticky="nsew")
        widget.configure(bg="#111111")

        toolbar_frame = tk.Frame(parent, bg="#1a1a1a")
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        toolbar.configure(bg="#1a1a1a")
        toolbar.update()

    # ── Panel management ────────────────────────────────────────────

    def _refresh_combo(self):
        names = self.db.names()
        self.panel_combo["values"] = names
        if names and self.panel_var.get() not in names:
            self.panel_var.set(names[0])

    def _on_panel_change(self):
        panel = self._current_panel()
        if panel:
            self.lbl_pw.config(text=f"{panel['width']:.3f} m")
            self.lbl_ph.config(text=f"{panel['height']:.3f} m")
            self.lbl_pwr.config(text=f"{panel['power']:.0f} W")
            self.lbl_wgt.config(text=f"{panel['weight']:.2f} kg")
        self._update_view()

    def _add_panel(self):
        dlg = AddPanelDialog(self.root)
        if dlg.result:
            if self.db.get(dlg.result["name"]):
                messagebox.showerror("Duplicate", "A panel with that name already exists.")
                return
            self.db.add(dlg.result)
            self._refresh_combo()
            self.panel_var.set(dlg.result["name"])
            self._on_panel_change()

    def _current_panel(self):
        return self.db.get(self.panel_var.get())

    # ── Curve controls ───────────────────────────────────────────────

    def _on_curve_mode_change(self, *_):
        curved = self.curve_mode.get() == "Curved"
        self.btn_edit_curve.config(
            state="normal" if curved else "disabled",
            bg="#4a3010" if curved else "#3a3a3a",
            fg="#cc9944" if curved else "#555555",
        )
        self._update_curve_label()
        self._update_view()

    def _update_curve_label(self):
        if self.curve_mode.get() == "Curved":
            apc = self._angle_per_col()
            step_str = "per col" if self.curve_step == "per_column" else "per 2 cols"
            self.lbl_curve_info.config(
                text=f"  {self.curve_angle:.1f}° {step_str}  ({apc:.2f}°/col)"
            )
        else:
            self.lbl_curve_info.config(text="")

    def _angle_per_col(self):
        """Effective angle per column in degrees."""
        return self.curve_angle / 2.0 if self.curve_step == "every_2" else self.curve_angle

    def _open_curve_editor(self):
        panel = self._current_panel()
        pw = panel["width"] if panel else 0.5
        try:
            cols = max(1, int(self.cols_var.get()))
        except (tk.TclError, ValueError):
            cols = 4
        dlg = CurveEditor(self.root, pw, self.curve_angle, self.curve_step, cols)
        if dlg.result:
            self.curve_angle = dlg.result["angle"]
            self.curve_step  = dlg.result["step"]
            self._update_curve_label()
            self._update_view()

    # ── View presets ─────────────────────────────────────────────────

    def _view_front(self):
        self._elev = 0
        self._azim = -90
        self._update_view()

    def _view_iso(self):
        self._elev = 22
        self._azim = -50
        self._update_view()

    def _view_top(self):
        self._elev = 88
        self._azim = -90
        self._update_view()

    # ── 3D Rendering ─────────────────────────────────────────────────

    def _update_view(self, *_):
        panel = self._current_panel()
        if not panel:
            return

        try:
            cols = max(1, int(self.cols_var.get()))
            rows = max(1, int(self.rows_var.get()))
        except (tk.TclError, ValueError):
            return

        pw = panel["width"]
        ph = panel["height"]
        pd = PANEL_DEPTH

        total    = cols * rows
        t_power  = total * panel["power"]
        t_weight = total * panel["weight"]
        total_w  = cols * pw
        total_h  = rows * ph
        half_h   = total_h / 2.0

        # Update sidebar
        self.lbl_total_panels.config(text=f"{total}")
        self.lbl_total_power.config(text=f"{t_power:,.0f} W  ({t_power/1000:.2f} kW)")
        self.lbl_total_weight.config(text=f"{t_weight:,.1f} kg")
        self.lbl_wall_w.config(text=f"{total_w:.3f} m")
        self.lbl_wall_h.config(text=f"{total_h:.3f} m")

        curved = self.curve_mode.get() == "Curved"
        apc    = self._angle_per_col() if curved else 0.0

        ax = self.ax
        ax.cla()
        ax.set_facecolor("#111111")

        front_polys = []
        body_polys  = []

        if curved:
            transforms = compute_curved_transforms(cols, pw, pd, apc)

            for r in range(rows):
                z0 = r * ph - half_h
                z1 = z0 + ph
                for t in transforms:
                    lf, rf, lb, rb = t["lf"], t["rf"], t["lb"], t["rb"]
                    # 3D corners
                    lf0, lf1 = [lf[0], lf[1], z0], [lf[0], lf[1], z1]
                    rf0, rf1 = [rf[0], rf[1], z0], [rf[0], rf[1], z1]
                    lb0, lb1 = [lb[0], lb[1], z0], [lb[0], lb[1], z1]
                    rb0, rb1 = [rb[0], rb[1], z0], [rb[0], rb[1], z1]

                    front_polys.append([lf0, rf0, rf1, lf1])
                    body_polys.extend([
                        [lb0, rb0, rb1, lb1],   # back
                        [lb0, lf0, lf1, lb1],   # left
                        [rf0, rb0, rb1, rf1],   # right
                        [lf1, rf1, rb1, lb1],   # top
                        [lf0, rf0, rb0, lb0],   # bottom
                    ])

            # Vertical seam lines (between columns, on front face)
            for t in transforms:
                lf = t["lf"]
                ax.plot([lf[0], lf[0]], [lf[1], lf[1]],
                        [-half_h, half_h], color="#2a4a8a", lw=0.8, alpha=0.7)
            last_rf = transforms[-1]["rf"]
            ax.plot([last_rf[0], last_rf[0]], [last_rf[1], last_rf[1]],
                    [-half_h, half_h], color="#2a4a8a", lw=0.8, alpha=0.7)

            # Horizontal lines at each row boundary
            for r_idx in range(rows + 1):
                z = r_idx * ph - half_h
                for t in transforms:
                    lf, rf = t["lf"], t["rf"]
                    ax.plot([lf[0], rf[0]], [lf[1], rf[1]], [z, z],
                            color="#2a4a8a", lw=0.8, alpha=0.5)

            # Axis limits
            all_pts = [t[k] for t in transforms for k in ("lf", "rf", "lb", "rb")]
            xs = [p[0] for p in all_pts]
            ys = [p[1] for p in all_pts]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            mx = max(max_x - min_x, total_h) * 0.25
            ax.set_xlim(min_x - mx, max_x + mx)
            ax.set_ylim(min_y - pd * 0.5, max_y + mx)
            ax.set_zlim(-half_h - mx, half_h + mx)

        else:
            # Flat wall
            half_w = total_w / 2.0
            for r in range(rows):
                for c in range(cols):
                    x0 = c * pw - half_w
                    x1 = x0 + pw
                    z0 = r * ph - half_h
                    z1 = z0 + ph
                    y0, y1 = 0.0, pd

                    front_polys.append([[x0,y0,z0],[x1,y0,z0],[x1,y0,z1],[x0,y0,z1]])
                    body_polys.extend([
                        [[x0,y1,z0],[x1,y1,z0],[x1,y1,z1],[x0,y1,z1]],  # back
                        [[x0,y0,z0],[x0,y1,z0],[x0,y1,z1],[x0,y0,z1]],  # left
                        [[x1,y0,z0],[x1,y1,z0],[x1,y1,z1],[x1,y0,z1]],  # right
                        [[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]],  # top
                        [[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0]],  # bottom
                    ])

            # Grid seam lines on front face
            for c in range(cols + 1):
                x = c * pw - half_w
                ax.plot([x,x],[0,0],[-half_h,half_h], color="#2a4a8a", lw=0.8, alpha=0.7)
            for r in range(rows + 1):
                z = r * ph - half_h
                ax.plot([-half_w,half_w],[0,0],[z,z], color="#2a4a8a", lw=0.8, alpha=0.5)

            mx = max(total_w, total_h) * 0.25
            ax.set_xlim(-half_w - mx, half_w + mx)
            ax.set_ylim(-pd * 0.5, pd + max(total_w, total_h) * 0.35)
            ax.set_zlim(-half_h - mx, half_h + mx)

        # Draw collections
        fc = Poly3DCollection(front_polys, alpha=0.97, zsort="average")
        fc.set_facecolor("#0d2b5e")
        fc.set_edgecolor("#1a4a99")
        fc.set_linewidth(0.6)
        ax.add_collection3d(fc)

        bc = Poly3DCollection(body_polys, alpha=0.92, zsort="average")
        bc.set_facecolor("#1e1e1e")
        bc.set_edgecolor("#2e2e2e")
        bc.set_linewidth(0.3)
        ax.add_collection3d(bc)

        # Axis labels / styling
        ax.set_xlabel("X  (Width)",  color="#555555", labelpad=2, fontsize=8)
        ax.set_ylabel("Y  (Depth)",  color="#555555", labelpad=2, fontsize=8)
        ax.set_zlabel("Z  (Height)", color="#555555", labelpad=2, fontsize=8)
        ax.tick_params(colors="#444444", labelsize=7)
        for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
            pane.set_facecolor("#0d0d0d")
            pane.set_edgecolor("#222222")
        ax.grid(True, color="#2a2a2a", linewidth=0.4)

        # Info overlay
        self.fig.texts.clear()
        if self.show_info.get():
            shape_str = ""
            if curved:
                total_arc = (cols - 1) * apc
                shape_str = f"   Curve: {apc:.1f}°/col  ({total_arc:.1f}° total arc)"
            lines = [
                f"Panels: {total}  ({cols} cols × {rows} rows){shape_str}",
                f"Wall: {total_w:.2f} m wide × {total_h:.2f} m tall × {pd:.2f} m deep   "
                f"Power: {t_power:,.0f} W ({t_power/1000:.2f} kW)   "
                f"Weight: {t_weight:,.1f} kg",
            ]
            self.fig.text(
                0.5, 0.012, "\n".join(lines),
                ha="center", va="bottom", color="#aaaaaa", fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#0d0d0d",
                          edgecolor="#333333", alpha=0.85),
            )

        ax.view_init(elev=self._elev, azim=self._azim)
        self.canvas.draw_idle()

    # ── Export ──────────────────────────────────────────────────────

    def _export(self):
        panel = self._current_panel()
        if not panel:
            messagebox.showwarning("No Panel Selected", "Please select a panel model first.")
            return

        try:
            cols = max(1, int(self.cols_var.get()))
            rows = max(1, int(self.rows_var.get()))
        except (tk.TclError, ValueError):
            messagebox.showerror("Invalid Layout", "Columns and Rows must be positive integers.")
            return

        curved = self.curve_mode.get() == "Curved"
        apc    = self._angle_per_col() if curved else 0.0

        filepath = filedialog.asksaveasfilename(
            defaultextension=".obj",
            filetypes=[("Wavefront OBJ", "*.obj"), ("All Files", "*.*")],
            title="Export Video Wall Mesh",
            initialfile=f"videowall_{cols}x{rows}{'_curved' if curved else ''}.obj",
        )
        if not filepath:
            return

        try:
            obj_path, mtl_path = export_obj(filepath, panel, cols, rows,
                                             angle_per_col=apc)
            total    = cols * rows
            t_power  = total * panel["power"]
            t_weight = total * panel["weight"]
            curve_line = (f"\n  Curve  : {apc:.2f}°/col  "
                          f"({(cols-1)*apc:.1f}° total arc)" if curved else "")

            messagebox.showinfo(
                "Export Complete",
                f"Mesh exported successfully!\n\n"
                f"  OBJ    : {os.path.basename(obj_path)}\n"
                f"  MTL    : {os.path.basename(mtl_path)}\n"
                f"  Shape  : {'Curved' if curved else 'Flat'}{curve_line}\n\n"
                f"  Panels : {total}  ({cols} × {rows})\n"
                f"  Power  : {t_power:,.0f} W\n"
                f"  Weight : {t_weight:,.1f} kg\n\n"
                f"Tip: Apply a texture to the 'display_face' material\n"
                f"to show video content on the wall.",
            )
        except Exception as exc:
            messagebox.showerror("Export Failed", str(exc))


# ──────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TCombobox",
                    fieldbackground="#3a3a3a", background="#3a3a3a",
                    foreground="#cccccc", selectbackground="#2a5298",
                    selectforeground="#ffffff", arrowcolor="#cccccc")
    style.map("TCombobox",
              fieldbackground=[("readonly", "#3a3a3a")],
              foreground=[("readonly", "#cccccc")])

    app = VideoWallApp(root)

    root.update_idletasks()
    w, h = 1220, 760
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    root.mainloop()


if __name__ == "__main__":
    main()

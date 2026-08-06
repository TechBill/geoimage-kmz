"""geoimage_kmz_custom.py

Standalone control-panel + viewer app for building a map-image-to-KMZ overlay.

Features:
- Main window is a small control panel (points list + save/load + KMZ)
- Separate Viewer window for the image (fast pan/zoom)
- Left mouse drag = pan (works while zoomed in)
- Mouse wheel zoom + Zoom +/- buttons
- Add Point button arms the next click to place a point (then prompts for lat/lon)
- Points are draggable after placement
- Save/Load points JSON
- Generate KMZ using best-fit affine transform -> gx:LatLonQuad

Dependencies:
- Pillow (PIL):  python3 -m pip install pillow
- NumPy (for KMZ): python3 -m pip install numpy

Run:
  python3 geoimage_kmz_custom.py
"""

from __future__ import annotations

import json
import os
import sys
import tkinter as tk
import urllib.request
import urllib.parse
import urllib.error
import webbrowser
from dataclasses import dataclass, asdict
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageTk

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


# Application metadata
__version__ = "2.1"
__author__ = "Bill Fleming"

APP_NAME = "GeoImage KMZ"
APP_VERSION = __version__
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"

# Windows only: Set AppUserModelID for taskbar icon grouping
if sys.platform.startswith("win"):
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GeoImageKMZ.App")
    except Exception:
        pass


@dataclass
class ControlPoint:
    px: float
    py: float
    lat: float
    lon: float


def query_missouri_plss_section(township: int, township_dir: str, range_num: int, range_dir: str, section: int) -> Optional[dict]:
    """Query Missouri MSDIS PLSS web service for section geometry.

    Args:
        township: Township number
        township_dir: Township direction (N/S)
        range_num: Range number
        range_dir: Range direction (E/W)
        section: Section number (1-36)

    Returns: dict with 'geometry' (polygon rings) or None on failure
    """
    try:
        # Missouri Department of Agriculture PLSS FeatureServer (Layer 0)
        base_url = "https://gis.mo.gov/arcgis/rest/services/MDA/PLSS/FeatureServer/0/query"

        # Build WHERE clause using Missouri's field names
        # TWP_NUM, TWP_DIR, RNG_NUM, RNG_DIR, SEC_NUM
        where = (f"TWP_NUM = {township} AND TWP_DIR = '{township_dir}' AND "
                f"RNG_NUM = {range_num} AND RNG_DIR = '{range_dir}' AND "
                f"SEC_NUM = {section}")

        params = {
            'where': where,
            'outFields': 'TWP_NUM,TWP_DIR,RNG_NUM,RNG_DIR,SEC_NUM,LABEL_,GRANT_NAME',
            'returnGeometry': 'true',
            'f': 'json',
            'outSR': '4326'  # WGS84 lat/lon
        }

        query_string = urllib.parse.urlencode(params)
        url = f"{base_url}?{query_string}"

        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        if 'features' in data and len(data['features']) > 0:
            return data['features'][0]

        return None

    except Exception as e:
        print(f"PLSS query error: {e}")
        return None


def query_kansas_plss_section(township: int, township_dir: str, range_num: int, range_dir: str, section: int) -> Optional[dict]:
    """Query Kansas PLSS web service for section geometry.

    Args:
        township: Township number
        township_dir: Township direction (N/S)
        range_num: Range number
        range_dir: Range direction (E/W)
        section: Section number (1-36)

    Returns: dict with 'geometry' (polygon rings) or None on failure
    """
    try:
        # Kansas Department of Transportation PLSS MapServer (Layer 0)
        base_url = "https://wfs.ksdot.org/arcgis_web_adaptor/rest/services/Boundaries/PLSS/MapServer/0/query"

        # Build WHERE clause using Kansas's field names
        # Township format: "01S" (number + direction)
        # Range format: "41W" (number + direction)
        # Section format: "05" (number only)
        township_str = f"{township:02d}{township_dir}"
        range_str = f"{range_num:02d}{range_dir}"
        section_str = f"{section:02d}"

        where = (f"Township = '{township_str}' AND Range = '{range_str}' AND "
                f"Section = '{section_str}'")

        params = {
            'where': where,
            'outFields': 'Township,Range,Section,TownshipRangeSection',
            'returnGeometry': 'true',
            'f': 'json',
            'outSR': '4326'  # WGS84 lat/lon
        }

        query_string = urllib.parse.urlencode(params)
        url = f"{base_url}?{query_string}"

        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        if 'features' in data and len(data['features']) > 0:
            return data['features'][0]

        return None

    except Exception as e:
        print(f"PLSS query error: {e}")
        return None


def extract_corner_coordinate(geometry: dict, corner: str) -> Optional[tuple[float, float]]:
    """Extract corner coordinate from polygon geometry.

    Args:
        geometry: ArcGIS polygon geometry dict with 'rings'
        corner: One of 'NW', 'NE', 'SE', 'SW'

    Returns: (lat, lon) tuple or None
    """
    try:
        if 'rings' not in geometry or not geometry['rings']:
            return None

        # Flatten all rings into one list of points (handle multi-part polygons)
        all_points = []
        for ring in geometry['rings']:
            all_points.extend(ring)

        if not all_points:
            return None

        # Find corner based on min/max lat/lon
        # Note: points are [lon, lat] in ArcGIS JSON
        lons = [pt[0] for pt in all_points]
        lats = [pt[1] for pt in all_points]

        min_lon = min(lons)
        max_lon = max(lons)
        min_lat = min(lats)
        max_lat = max(lats)

        # Define target coordinates for each corner
        targets = {
            'NW': (max_lat, min_lon),  # Top Left
            'NE': (max_lat, max_lon),  # Top Right
            'SE': (min_lat, max_lon),  # Bottom Right
            'SW': (min_lat, min_lon),  # Bottom Left
        }

        if corner not in targets:
            return None

        target_lat, target_lon = targets[corner]

        # Find the point closest to the target corner
        best_point = None
        best_distance = float('inf')

        for pt in all_points:
            lon, lat = pt[0], pt[1]
            distance = ((lat - target_lat) ** 2 + (lon - target_lon) ** 2) ** 0.5
            if distance < best_distance:
                best_distance = distance
                best_point = (lat, lon)

        return best_point

    except Exception as e:
        print(f"Corner extraction error: {e}")
        return None


class PLSSLookupDialog(simpledialog.Dialog):
    """Dialog for PLSS (Public Land Survey System) coordinate lookup."""

    def __init__(self, parent, app=None):
        self.result: Optional[tuple[float, float]] = None
        self.app = app  # Store reference to main app for accessing last settings
        super().__init__(parent, title="PLSS Lookup")

    def body(self, master: tk.Frame):
        # Get last used values from app if available
        if self.app:
            init_state = self.app.last_plss_state
            init_township = self.app.last_plss_township
            init_township_dir = self.app.last_plss_township_dir
            init_range = self.app.last_plss_range
            init_range_dir = self.app.last_plss_range_dir
            init_section = self.app.last_plss_section
            init_corner = self.app.last_plss_corner
        else:
            init_state = "Missouri"
            init_township = ""
            init_township_dir = "N"
            init_range = ""
            init_range_dir = "W"
            init_section = ""
            init_corner = "NW"

        # State selector
        tk.Label(master, text="State:", font=("Helvetica", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 4)
        )

        self.state_var = tk.StringVar(value=init_state)
        state_combo = ttk.Combobox(master, textvariable=self.state_var,
                                   values=["Missouri", "Kansas"], width=18, state="readonly")
        state_combo.grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=4)

        # Township
        tk.Label(master, text="Township:", font=("Helvetica", 10, "bold")).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 4)
        )

        tk.Label(master, text="Number:").grid(row=3, column=0, sticky="w", padx=(20, 6), pady=4)
        self.township_entry = tk.Entry(master, width=10)
        self.township_entry.insert(0, init_township)
        self.township_entry.grid(row=3, column=1, sticky="w", padx=6, pady=4)

        tk.Label(master, text="Direction:").grid(row=4, column=0, sticky="w", padx=(20, 6), pady=4)
        self.township_dir_var = tk.StringVar(value=init_township_dir)
        township_dir_combo = ttk.Combobox(master, textvariable=self.township_dir_var,
                                          values=["N", "S"], width=8, state="readonly")
        township_dir_combo.grid(row=4, column=1, sticky="w", padx=6, pady=4)

        # Range
        tk.Label(master, text="Range:", font=("Helvetica", 10, "bold")).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 4)
        )

        tk.Label(master, text="Number:").grid(row=6, column=0, sticky="w", padx=(20, 6), pady=4)
        self.range_entry = tk.Entry(master, width=10)
        self.range_entry.insert(0, init_range)
        self.range_entry.grid(row=6, column=1, sticky="w", padx=6, pady=4)

        tk.Label(master, text="Direction:").grid(row=7, column=0, sticky="w", padx=(20, 6), pady=4)
        self.range_dir_var = tk.StringVar(value=init_range_dir)
        range_dir_combo = ttk.Combobox(master, textvariable=self.range_dir_var,
                                       values=["E", "W"], width=8, state="readonly")
        range_dir_combo.grid(row=7, column=1, sticky="w", padx=6, pady=4)

        # Section
        tk.Label(master, text="Section:", font=("Helvetica", 10, "bold")).grid(
            row=8, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 4)
        )

        tk.Label(master, text="Number (1-36):").grid(row=9, column=0, sticky="w", padx=(20, 6), pady=4)
        self.section_entry = tk.Entry(master, width=10)
        self.section_entry.insert(0, init_section)
        self.section_entry.grid(row=9, column=1, sticky="w", padx=6, pady=4)

        # Corner
        tk.Label(master, text="Corner:", font=("Helvetica", 10, "bold")).grid(
            row=10, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 4)
        )

        tk.Label(master, text="Select:").grid(row=11, column=0, sticky="w", padx=(20, 6), pady=4)
        # Map corner abbreviation to full display text
        corner_map = {
            "NW": "NW (Top Left)",
            "NE": "NE (Top Right)",
            "SE": "SE (Bottom Right)",
            "SW": "SW (Bottom Left)"
        }
        init_corner_display = corner_map.get(init_corner, "NW (Top Left)")
        self.corner_var = tk.StringVar(value=init_corner_display)
        corner_combo = ttk.Combobox(master, textvariable=self.corner_var,
                                    values=["NW (Top Left)", "NE (Top Right)",
                                           "SE (Bottom Right)", "SW (Bottom Left)"],
                                    width=20, state="readonly")
        corner_combo.grid(row=11, column=1, sticky="w", padx=6, pady=4)

        # Disclaimer and data source attribution
        disclaimer = tk.Label(
            master,
            text="Data Sources:\n"
                 "• Missouri: MSDIS / Missouri Dept. of Agriculture\n"
                 "• Kansas: Kansas Dept. of Transportation PLSS\n\n"
                 "THE STATE AGENCIES MAKE NO REPRESENTATIONS OR WARRANTY\n"
                 "AS TO THE COMPLETENESS, ACCURACY, TIMELINESS, OR CONTENT\n"
                 "OF ANY DATA MADE AVAILABLE.",
            font=("Helvetica", 10, "italic"),
            fg="gray",
            justify="left"
        )
        disclaimer.grid(row=12, column=0, columnspan=2, sticky="w", padx=6, pady=(10, 4))

        return self.township_entry

    def buttonbox(self):
        """Override to customize buttons."""
        box = tk.Frame(self)

        fetch_btn = tk.Button(box, text="Fetch", width=10, command=self.fetch_coordinates, default=tk.ACTIVE)
        fetch_btn.pack(side=tk.LEFT, padx=5, pady=5)

        cancel_btn = tk.Button(box, text="Cancel", width=10, command=self.cancel)
        cancel_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.bind("<Return>", lambda e: self.fetch_coordinates())
        self.bind("<Escape>", lambda e: self.cancel())

        box.pack()

    def fetch_coordinates(self):
        """Fetch coordinates from selected state's PLSS service."""
        try:
            # Validate inputs
            township = int(self.township_entry.get().strip())
            range_num = int(self.range_entry.get().strip())
            section = int(self.section_entry.get().strip())

            if not (1 <= section <= 36):
                messagebox.showerror("Invalid Section", "Section must be between 1 and 36.")
                return

            township_dir = self.township_dir_var.get()
            range_dir = self.range_dir_var.get()
            corner_text = self.corner_var.get()
            corner = corner_text.split()[0]  # Extract "NW" from "NW (Top Left)"
            selected_state = self.state_var.get()

            # Show progress
            self.config(cursor="watch")
            self.update()

            # Query the appropriate state's PLSS service
            if selected_state == "Kansas":
                feature = query_kansas_plss_section(township, township_dir, range_num, range_dir, section)
            else:  # Missouri
                feature = query_missouri_plss_section(township, township_dir, range_num, range_dir, section)

            if not feature:
                self.config(cursor="")
                messagebox.showerror("Lookup Failed",
                                   f"No section found: T{township}{township_dir} R{range_num}{range_dir} S{section}\n\n"
                                   "Please verify:\n"
                                   "• Township, Range, Section numbers are correct\n"
                                   "• Directions (N/S, E/W) are correct\n"
                                   f"• The section exists in {selected_state} PLSS")
                return

            # Extract corner coordinate
            geometry = feature.get('geometry')
            if not geometry:
                self.config(cursor="")
                messagebox.showerror("No Geometry", "Section found but no geometry data available.")
                return

            coord = extract_corner_coordinate(geometry, corner)

            if not coord:
                self.config(cursor="")
                messagebox.showerror("Extraction Failed", "Could not extract corner coordinate from section geometry.")
                return

            # Save settings for next time
            if self.app:
                self.app.last_plss_state = selected_state
                self.app.last_plss_township = str(township)
                self.app.last_plss_township_dir = township_dir
                self.app.last_plss_range = str(range_num)
                self.app.last_plss_range_dir = range_dir
                self.app.last_plss_section = str(section)
                self.app.last_plss_corner = corner

            self.result = coord
            self.config(cursor="")
            self.ok()

        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric values for Township, Range, and Section.")
        except Exception as e:
            self.config(cursor="")
            messagebox.showerror("Error", f"An error occurred during PLSS lookup:\n\n{str(e)}")

    def validate(self) -> bool:
        # Validation handled in fetch_coordinates
        return True


class LatLonDialog(simpledialog.Dialog):
    """Modal dialog to enter lat/lon."""

    def __init__(self, parent: tk.Tk, title: str, initial_lat: str = "", initial_lon: str = "", app=None):
        self.initial_lat = initial_lat
        self.initial_lon = initial_lon
        self.lat_var = tk.StringVar(value=initial_lat)
        self.lon_var = tk.StringVar(value=initial_lon)
        self.result: Optional[tuple[float, float]] = None
        self.app = app  # Store reference to main app for PLSS lookup
        super().__init__(parent, title=title)

    def body(self, master: tk.Frame):
        tk.Label(master, text="Latitude (decimal):").grid(row=0, column=0, sticky="w", padx=6, pady=(10, 4))
        lat_entry = tk.Entry(master, textvariable=self.lat_var, width=22)
        lat_entry.grid(row=0, column=1, sticky="we", padx=6, pady=(10, 4))

        tk.Label(master, text="Longitude (decimal):").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        lon_entry = tk.Entry(master, textvariable=self.lon_var, width=22)
        lon_entry.grid(row=1, column=1, sticky="we", padx=6, pady=4)

        # Paste Coordinates button
        paste_btn = tk.Button(master, text="Paste Coordinates", command=self.paste_coordinates)
        paste_btn.grid(row=2, column=0, columnspan=2, pady=(10, 4))

        # PLSS Lookup button
        plss_btn = tk.Button(master, text="PLSS Lookup…", command=self.open_plss_lookup)
        plss_btn.grid(row=3, column=0, columnspan=2, pady=(4, 4))

        master.grid_columnconfigure(1, weight=1)
        return lat_entry

    def open_plss_lookup(self):
        """Open PLSS Lookup dialog and auto-fill coordinates if successful."""
        dlg = PLSSLookupDialog(self, app=self.app)
        if dlg.result:
            lat, lon = dlg.result
            self.lat_var.set(f"{lat:.6f}")
            self.lon_var.set(f"{lon:.6f}")

    def paste_coordinates(self):
        """Parse coordinates from clipboard and populate lat/lon fields."""
        try:
            # Get text from clipboard
            clipboard_text = self.clipboard_get().strip()

            if not clipboard_text:
                messagebox.showinfo("Empty clipboard", "Clipboard is empty.")
                return

            # Check if it's KML/XML data (Google Earth placemark)
            if '<coordinates>' in clipboard_text and '</coordinates>' in clipboard_text:
                # Extract coordinates from KML
                import re
                coord_match = re.search(r'<coordinates>([-\d.,\s]+)</coordinates>', clipboard_text)
                if coord_match:
                    coords = coord_match.group(1).strip()
                    # KML format is: longitude,latitude,altitude
                    parts = coords.split(',')
                    if len(parts) >= 2:
                        try:
                            lon = float(parts[0].strip())
                            lat = float(parts[1].strip())
                            # Set the values (note: KML has lon first, then lat)
                            self.lat_var.set(str(lat))
                            self.lon_var.set(str(lon))
                            return
                        except ValueError:
                            pass

            # Try to parse coordinates - handle both comma and space separators
            # Remove multiple spaces and normalize
            text = clipboard_text.replace(',', ' ')
            parts = text.split()

            if len(parts) >= 2:
                # First part is latitude, second is longitude
                lat_str = parts[0].strip()
                lon_str = parts[1].strip()

                # Validate they are numbers
                try:
                    float(lat_str)
                    float(lon_str)

                    # Set the values
                    self.lat_var.set(lat_str)
                    self.lon_var.set(lon_str)

                except ValueError:
                    messagebox.showerror("Invalid format",
                        "Could not parse coordinates.\n\n"
                        "Expected format:\n"
                        "37.20176528102794, -93.36315532838486\n"
                        "or\n"
                        "37.20176528102794 -93.36315532838486\n"
                        "or Google Earth KML placemark")
            else:
                messagebox.showerror("Invalid format",
                    "Could not find two coordinate values.\n\n"
                    "Expected format:\n"
                    "37.20176528102794, -93.36315532838486\n"
                    "or\n"
                    "37.20176528102794 -93.36315532838486\n"
                    "or Google Earth KML placemark")

        except tk.TclError:
            messagebox.showerror("Clipboard error", "Could not access clipboard.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred:\n\n{e}")

    def validate(self) -> bool:
        try:
            lat = float(self.lat_var.get().strip())
            lon = float(self.lon_var.get().strip())
        except Exception:
            messagebox.showerror("Invalid input", "Please enter numeric decimal latitude and longitude.")
            return False

        if not (-90.0 <= lat <= 90.0):
            messagebox.showerror("Invalid latitude", "Latitude must be between -90 and 90.")
            return False
        if not (-180.0 <= lon <= 180.0):
            messagebox.showerror("Invalid longitude", "Longitude must be between -180 and 180.")
            return False

        self.result = (lat, lon)
        return True


class GeoImageKMZApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # Set window icon (Windows uses .ico, macOS handled by app bundle)
        if sys.platform.startswith("win"):
            try:
                # When frozen (PyInstaller), icon is bundled in _MEIPASS
                if getattr(sys, "frozen", False):
                    icon_path = os.path.join(sys._MEIPASS, "assets", "icon.ico")
                else:
                    icon_path = "assets/icon.ico"
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.title(APP_TITLE)
        self.geometry("320x750")

        # State
        self.image_path: Optional[str] = None
        self._pil_image: Optional[Image.Image] = None
        self._tk_image: Optional[ImageTk.PhotoImage] = None

        # Viewer (integrated)
        self.viewer_frame: Optional[tk.Frame] = None
        self.viewer_left_panel: Optional[tk.Frame] = None
        self.viewer_canvas: Optional[tk.Canvas] = None
        self._viewer_status_var: Optional[tk.StringVar] = None
        self._viewer_visible = False

        # Canvas transform state (viewer)
        self.scale = 1.0
        self.min_scale = 0.1
        self.max_scale = 12.0
        self.offset_x = 0.0
        self.offset_y = 0.0

        # Zoom throttling
        self._pending_zoom_id: Optional[str] = None
        self._accumulated_zoom_factor = 1.0
        self._zoom_center = (0, 0)

        # Items
        self._image_item_id: Optional[int] = None
        self._point_item_ids: list[tuple[int, int]] = []  # (oval_id, label_id)
        self._popup_rect_id: Optional[int] = None
        self._popup_text_id: Optional[int] = None

        # Interaction state
        self._pending_add_point = False
        self._pending_draw_border = False
        self._left_drag_start: Optional[tuple[int, int]] = None
        self._dragging_point_index: Optional[int] = None
        self._panning = False

        # Control points
        self.points: list[ControlPoint] = []

        # Border polygon points (in pixel coordinates)
        self.border_points: list[tuple[float, float]] = []
        self._border_line_ids: list[int] = []  # Canvas line IDs for visual feedback
        self._border_point_ids: list[int] = []  # Canvas oval IDs for border points

        # Last PLSS lookup settings (to remember between point additions)
        self.last_plss_state = "Missouri"
        self.last_plss_township = ""
        self.last_plss_township_dir = "N"
        self.last_plss_range = ""
        self.last_plss_range_dir = "W"
        self.last_plss_section = ""
        self.last_plss_corner = "NW"

        # Remember last directory for loading images (defaults to Desktop)
        self.last_image_dir = os.path.expanduser("~/Desktop")

        # Remember last directories for saving during session (defaults to Desktop)
        self.last_kmz_dir = os.path.expanduser("~/Desktop")
        self.last_points_dir = os.path.expanduser("~/Desktop")

        self._build_ui()

        # Set up exit confirmation dialog
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ------------------ UI (Control panel) ------------------
    def _build_ui(self) -> None:
        # Main container
        main_container = tk.Frame(self)
        main_container.pack(fill="both", expand=True)

        # Create a PanedWindow to allow resizing between panels
        self.paned_window = tk.PanedWindow(main_container, orient=tk.HORIZONTAL, sashwidth=5, bg="#cccccc")
        self.paned_window.pack(fill="both", expand=True)

        # Left panel for viewer controls (initially hidden)
        self.viewer_left_panel = tk.Frame(self.paned_window, bd=1, relief="groove", width=150)

        tk.Label(self.viewer_left_panel, text="Viewer", font=("Helvetica", 12, "bold")).pack(pady=(10, 5))

        # Mark Coordinate section
        tk.Label(self.viewer_left_panel, text="Mark Coordinate", font=("Helvetica", 10, "bold")).pack(pady=(5, 5))
        tk.Button(self.viewer_left_panel, text="Add Point", command=self._arm_add_point, width=12).pack(pady=3, padx=5)

        tk.Label(self.viewer_left_panel, text="", height=1).pack()  # Spacer

        # Border Mask section
        tk.Label(self.viewer_left_panel, text="Border Mask", font=("Helvetica", 10, "bold")).pack(pady=(5, 5))
        tk.Button(self.viewer_left_panel, text="Draw Border", command=self._arm_draw_border, width=12).pack(pady=3, padx=5)
        tk.Button(self.viewer_left_panel, text="Undo Line", command=self._undo_border_line, width=12).pack(pady=3, padx=5)
        tk.Button(self.viewer_left_panel, text="Reset Border", command=self._reset_border, width=12).pack(pady=3, padx=5)

        tk.Label(self.viewer_left_panel, text="", height=1).pack()  # Spacer

        # Zoom section
        tk.Label(self.viewer_left_panel, text="Zoom", font=("Helvetica", 10, "bold")).pack(pady=(5, 5))
        tk.Button(self.viewer_left_panel, text="Zoom +", command=lambda: self._zoom_button(1.1), width=12).pack(pady=3, padx=5)
        tk.Button(self.viewer_left_panel, text="Zoom -", command=lambda: self._zoom_button(1 / 1.1), width=12).pack(pady=3, padx=5)

        tk.Label(self.viewer_left_panel, text="", height=1).pack()  # Spacer

        # Rotate section
        tk.Label(self.viewer_left_panel, text="Rotate", font=("Helvetica", 10, "bold")).pack(pady=(5, 5))
        tk.Button(self.viewer_left_panel, text="↺ Left 90°", command=lambda: self.rotate_image(-90), width=12).pack(pady=3, padx=5)
        tk.Button(self.viewer_left_panel, text="↻ Right 90°", command=lambda: self.rotate_image(90), width=12).pack(pady=3, padx=5)
        tk.Button(self.viewer_left_panel, text="⟲ 180°", command=lambda: self.rotate_image(180), width=12).pack(pady=3, padx=5)

        # Controls help text
        tk.Label(self.viewer_left_panel, text="", height=2).pack()  # Spacer
        controls_help = tk.Label(
            self.viewer_left_panel,
            justify="left",
            anchor="nw",
            wraplength=134,
            text=(
                "Controls:\n"
                "• Left drag: pan\n"
                "• Mouse wheel: zoom\n"
                "• Add Point to place\n"
                "• Drag red dots to move"
            ),
            font=("Helvetica", 12)
        )
        controls_help.pack(fill="x", padx=8, pady=(5, 10))

        # Center viewer frame (initially hidden)
        self.viewer_frame = tk.Frame(self.paned_window, bg="#222222")

        self._viewer_status_var = tk.StringVar(value="Drag to pan. Wheel to zoom. Click Add Point to place a point.")
        tk.Label(self.viewer_frame, textvariable=self._viewer_status_var, anchor="w", bg="#333333", fg="white").pack(
            side="top", fill="x", padx=5, pady=5
        )

        self.viewer_canvas = tk.Canvas(self.viewer_frame, bg="#222222", highlightthickness=0)
        self.viewer_canvas.pack(fill="both", expand=True)

        # Bindings for viewer canvas
        self.viewer_canvas.bind("<ButtonPress-1>", self._on_left_press)
        self.viewer_canvas.bind("<B1-Motion>", self._on_left_drag)
        self.viewer_canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.viewer_canvas.bind("<ButtonPress-3>", self._on_right_press)
        self.viewer_canvas.bind("<B3-Motion>", self._on_right_drag)
        self.viewer_canvas.bind("<ButtonRelease-3>", self._on_right_release)
        self.viewer_canvas.bind("<ButtonPress-2>", self._on_right_press)
        self.viewer_canvas.bind("<B2-Motion>", self._on_right_drag)
        self.viewer_canvas.bind("<ButtonRelease-2>", self._on_right_release)
        self.viewer_canvas.bind("<MouseWheel>", self._on_mousewheel_viewer)
        self.viewer_canvas.bind("<Button-4>", lambda e: self.zoom_at(e.x, e.y, 1.1))
        self.viewer_canvas.bind("<Button-5>", lambda e: self.zoom_at(e.x, e.y, 1 / 1.1))
        self.viewer_canvas.bind("<Configure>", self._on_canvas_configure)

        # Right panel for main controls (always visible)
        right_panel = tk.Frame(self.paned_window, bd=1, relief="groove", width=320)
        # Add right panel to PanedWindow immediately (it's always visible)
        self.paned_window.add(right_panel, minsize=320, width=320)

        # Status at the top
        self.status_var = tk.StringVar(value="Load an image to begin.")
        tk.Label(right_panel, textvariable=self.status_var, anchor="w", justify="left", wraplength=290).pack(
            fill="x", padx=10, pady=(10, 10)
        )

        # Button row 1: Load Image, Open Viewer
        btn_row1 = tk.Frame(right_panel)
        btn_row1.pack(fill="x", padx=10, pady=5)
        tk.Button(btn_row1, text="Load Image…", command=self.load_image, width=14).pack(side="left", padx=(0, 5))
        tk.Button(btn_row1, text="Open Viewer", command=self._ensure_viewer, width=14).pack(side="left")

        # Button row 2: Save Points, Load Points
        btn_row2 = tk.Frame(right_panel)
        btn_row2.pack(fill="x", padx=10, pady=5)
        tk.Button(btn_row2, text="Save Points…", command=self.save_points, width=14).pack(side="left", padx=(0, 5))
        tk.Button(btn_row2, text="Load Points…", command=self.load_points, width=14).pack(side="left")

        # Button row 3: Create Border Mask (single button)
        tk.Button(right_panel, text="Create Border Mask", command=self.create_border_mask, width=29).pack(pady=5, padx=10)

        # Button row 4: Generate KMZ (single button)
        tk.Button(right_panel, text="Generate KMZ…", command=self.generate_kmz, width=29).pack(pady=5, padx=10)

        # Control Points section
        tk.Label(right_panel, text="Control Points", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        self.listbox = tk.Listbox(right_panel, height=15, width=35)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=5)

        # Edit/Delete buttons
        btn_edit_row = tk.Frame(right_panel)
        btn_edit_row.pack(fill="x", padx=10, pady=5)
        tk.Button(btn_edit_row, text="Edit…", command=self.edit_selected, width=14).pack(side="left", padx=(0, 5))
        tk.Button(btn_edit_row, text="Delete", command=self.delete_selected, width=14).pack(side="left")

        # Clear Points button
        tk.Button(right_panel, text="Clear Points", command=self.clear_points, width=29).pack(pady=5, padx=10)

        # Tip text at the bottom
        tip_box = tk.Label(
            right_panel,
            justify="left",
            anchor="nw",
            text=(
                "Tip: Add 4-8 control points\n"
                "for better alignment."
            ),
            font=("Helvetica", 12)
        )
        tip_box.pack(fill="x", padx=10, pady=(10, 10))

        # PayPal button
        paypal_frame = tk.Frame(right_panel, bg="#0070BA", bd=1, relief="raised", cursor="hand2")
        paypal_frame.pack(padx=10, pady=(0, 5), fill="x")
        paypal_label = tk.Label(paypal_frame, text="Donate on PayPal", bg="#0070BA", fg="white",
                               font=("Helvetica", 10, "bold"), pady=5)
        paypal_label.pack(fill="x")
        paypal_frame.bind("<Button-1>", lambda e: self._open_url("https://www.paypal.com/paypalme/techbill"))
        paypal_label.bind("<Button-1>", lambda e: self._open_url("https://www.paypal.com/paypalme/techbill"))
        paypal_frame.bind("<Enter>", lambda e: paypal_frame.config(bg="#005EA6") or paypal_label.config(bg="#005EA6"))
        paypal_label.bind("<Enter>", lambda e: paypal_frame.config(bg="#005EA6") or paypal_label.config(bg="#005EA6"))
        paypal_frame.bind("<Leave>", lambda e: paypal_frame.config(bg="#0070BA") or paypal_label.config(bg="#0070BA"))
        paypal_label.bind("<Leave>", lambda e: paypal_frame.config(bg="#0070BA") or paypal_label.config(bg="#0070BA"))

        # Buy Me a Coffee button
        coffee_frame = tk.Frame(right_panel, bg="#FFDD00", bd=1, relief="raised", cursor="hand2")
        coffee_frame.pack(padx=10, pady=(0, 10), fill="x")
        coffee_label = tk.Label(coffee_frame, text="☕ Buy Me a Coffee", bg="#FFDD00", fg="black",
                               font=("Helvetica", 10, "bold"), pady=5)
        coffee_label.pack(fill="x")
        coffee_frame.bind("<Button-1>", lambda e: self._open_url("https://buymeacoffee.com/techbill"))
        coffee_label.bind("<Button-1>", lambda e: self._open_url("https://buymeacoffee.com/techbill"))
        coffee_frame.bind("<Enter>", lambda e: coffee_frame.config(bg="#FFCC00") or coffee_label.config(bg="#FFCC00"))
        coffee_label.bind("<Enter>", lambda e: coffee_frame.config(bg="#FFCC00") or coffee_label.config(bg="#FFCC00"))
        coffee_frame.bind("<Leave>", lambda e: coffee_frame.config(bg="#FFDD00") or coffee_label.config(bg="#FFDD00"))
        coffee_label.bind("<Leave>", lambda e: coffee_frame.config(bg="#FFDD00") or coffee_label.config(bg="#FFDD00"))

    # ------------------ Viewer management ------------------
    def _ensure_viewer(self) -> None:
        """Show or toggle the viewer panel."""
        if self._viewer_visible:
            # Already visible, do nothing (or could toggle to hide)
            return

        # Expand window to show viewer
        self.geometry("1320x750")

        # Show the viewer panels by adding them to PanedWindow
        self._viewer_visible = True
        # Get the right panel (first pane in the panedwindow currently)
        right_panel = self.paned_window.panes()[0]
        # Add viewer panels before the right panel
        self.paned_window.add(self.viewer_left_panel, before=right_panel, minsize=150, width=150)
        self.paned_window.add(self.viewer_frame, before=right_panel, minsize=400)

        # Set sash positions after adding panes to control initial sizes
        # Position first sash at 150px (left panel width)
        # Position second sash at 1000px (leaving 320px for right panel)
        self.after(50, lambda: self.paned_window.sash_place(0, 150, 0))
        self.after(50, lambda: self.paned_window.sash_place(1, 1000, 0))

        # Redraw to show current state (will show "Load an image to proceed" if no image)
        # If image is loaded, reset view to fit first
        if self._pil_image:
            self.after(200, lambda: (self._reset_view_to_fit(), self.redraw()))
        else:
            self.after(200, self.redraw)

    def _on_canvas_configure(self, event: tk.Event) -> None:
        """Handle canvas resize - only redraw if size actually changed."""
        _ = event  # Event parameter required for binding signature
        if not self.viewer_canvas:
            return
        # Debounce resize events
        if hasattr(self, '_resize_after_id'):
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(100, self.redraw)

    def _hit_test_point(self, x: int, y: int, radius: int = 10) -> Optional[int]:
        """Return point index under (x,y) using an overlap search, or None."""
        if not self.viewer_canvas:
            return None
        items = self.viewer_canvas.find_overlapping(x - radius, y - radius, x + radius, y + radius)
        if not items:
            return None
        # Prefer the top-most item in the overlap set
        for item_id in reversed(items):
            tags = self.viewer_canvas.gettags(item_id)
            for t in tags:
                if t.startswith("pt:"):
                    try:
                        return int(t.split(":", 1)[1])
                    except Exception:
                        return None
        return None

    def _set_viewer_status(self, txt: str) -> None:
        if self._viewer_status_var is not None:
            self._viewer_status_var.set(txt)

    def _open_url(self, url: str) -> None:
        """Open URL in the default web browser."""
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open URL: {e}")

    def _on_closing(self) -> None:
        """Handle window close event with confirmation dialog."""
        result = messagebox.askyesno("Exit GeoImage KMZ?", "Exit GeoImage KMZ?", icon='question')
        if result:
            self.destroy()

    def _show_add_point_popup(self) -> None:
        """Show a popup notification in the upper left corner of the viewer."""
        if not self.viewer_canvas:
            return

        # Remove existing popup if any
        self._hide_add_point_popup()

        # Create popup box in upper left corner
        x, y = 20, 20
        text = "Click on map to add point"

        # Create background rectangle
        self._popup_rect_id = self.viewer_canvas.create_rectangle(
            x - 5, y - 5, x + 185, y + 25,
            fill="#FFA500", outline="#FF8C00", width=2, tags="popup"
        )

        # Create text
        self._popup_text_id = self.viewer_canvas.create_text(
            x + 90, y + 10,
            text=text,
            fill="black",
            font=("Helvetica", 12, "bold"),
            tags="popup"
        )

        # Raise popup to top
        self.viewer_canvas.tag_raise("popup")

    def _hide_add_point_popup(self) -> None:
        """Hide the add point popup notification."""
        if not self.viewer_canvas:
            return

        if self._popup_rect_id:
            try:
                self.viewer_canvas.delete(self._popup_rect_id)
            except Exception:
                pass
            self._popup_rect_id = None

        if self._popup_text_id:
            try:
                self.viewer_canvas.delete(self._popup_text_id)
            except Exception:
                pass
            self._popup_text_id = None

    def _arm_add_point(self) -> None:
        if not self._pil_image:
            messagebox.showinfo("No image", "Load an image first.")
            return
        self._pending_add_point = True
        self._set_viewer_status("Click on the map to place a new point (then enter lat/lon).")
        self._show_add_point_popup()

    def _arm_draw_border(self) -> None:
        if not self._pil_image:
            messagebox.showinfo("No image", "Load an image first.")
            return
        # Clear any existing border
        self.border_points.clear()
        self._clear_border_visuals()
        self._pending_draw_border = True
        self._set_viewer_status("Click to draw border polygon. Click near first point to close.")

    def _reset_border(self) -> None:
        """Reset/clear the border (manual or auto-generated) and exit draw-border mode."""
        if not self.border_points:
            messagebox.showinfo("No border", "No border has been drawn yet.")
            return
        result = messagebox.askyesno("Reset Border", "Remove the border mask?")
        if result:
            self.border_points.clear()
            self._clear_border_visuals()
            self._pending_draw_border = False  # Exit draw-border mode
            self._set_viewer_status("Border reset. Click Draw Border to start over.")
            self.redraw()

    def create_border_mask(self) -> None:
        """Create a border mask automatically from control points."""
        # Check if border already exists
        if self.border_points:
            messagebox.showwarning(
                "Border Mask Already Exists",
                "A border mask has already been created.\n\n"
                "To create a new one, you must reset/clear the current border mask first."
            )
            return

        # Check if we have control points
        if len(self.points) < 3:
            messagebox.showerror(
                "Not Enough Points",
                "You need at least 3 control points to create a border mask."
            )
            return

        # Show confirmation dialog
        result = messagebox.askyesno(
            "Create Border Mask from Points",
            "This will create a border mask using your control points in the order you placed them on the map.\n\n"
            "Continue?",
            icon='question'
        )

        if not result:
            return

        # Create border from control points
        self.border_points = [(p.px, p.py) for p in self.points]

        # Mark border as closed (not in draw mode)
        self._pending_draw_border = False

        # Ensure viewer is visible
        if not self._viewer_visible:
            self._ensure_viewer()

        # Redraw the border
        self._redraw_border()

        # Update status
        self._set_viewer_status(f"Border mask created from {len(self.border_points)} control points")
        self.status_var.set(f"Border mask created from {len(self.points)} control points")

    def _undo_border_line(self) -> None:
        """Undo the most recently added border line/point."""
        if not self.border_points:
            messagebox.showinfo("No border", "No border points to undo.")
            return

        # If border was closed, just reopen it without removing a point
        # This removes only the closing line on the first undo
        was_closed = not self._pending_draw_border
        if was_closed:
            self._pending_draw_border = True
            self._set_viewer_status(f"Border reopened: {len(self.border_points)} points. Click Undo Line again to remove points.")
            self._redraw_border()
            return

        # Border is already open, so remove the last point
        if len(self.border_points) == 1:
            # Only one point, just remove it
            self.border_points.clear()
            self._clear_border_visuals()
            self._set_viewer_status("Click to draw border polygon. Click near first point to close.")
        else:
            # Remove the last point
            self.border_points.pop()
            self._set_viewer_status(f"Undo: {len(self.border_points)} points remaining. Click to continue.")

        # Redraw the border
        self._redraw_border()

    def _clear_border_visuals(self) -> None:
        """Clear border visual elements from canvas."""
        if not self.viewer_canvas:
            return
        for line_id in self._border_line_ids:
            try:
                self.viewer_canvas.delete(line_id)
            except Exception:
                pass
        for point_id in self._border_point_ids:
            try:
                self.viewer_canvas.delete(point_id)
            except Exception:
                pass
        self._border_line_ids.clear()
        self._border_point_ids.clear()

    def _zoom_button(self, factor: float) -> None:
        if not self.viewer_canvas or not self._pil_image:
            return
        cw = self.viewer_canvas.winfo_width()
        ch = self.viewer_canvas.winfo_height()
        self.zoom_at(cw / 2, ch / 2, factor)

    def _on_mousewheel_viewer(self, event: tk.Event) -> None:
        """Handle mousewheel zoom with throttling for smooth performance."""
        if event.delta == 0:
            return

        factor = 1.1 if event.delta > 0 else 1 / 1.1

        # Accumulate zoom factor and update center position
        self._accumulated_zoom_factor *= factor
        self._zoom_center = (event.x, event.y)

        # Cancel pending zoom if exists
        if self._pending_zoom_id is not None:
            self.after_cancel(self._pending_zoom_id)

        # Schedule the actual zoom operation with a small delay (25ms)
        # This batches rapid scroll events together
        self._pending_zoom_id = self.after(25, self._execute_accumulated_zoom)

    def _on_left_press(self, event: tk.Event) -> None:
        if not self.viewer_canvas:
            return

        self._left_drag_start = (event.x, event.y)
        self._dragging_point_index = None
        self._panning = False

        # If add-point is armed, we will place on release (no panning/dragging).
        if self._pending_add_point:
            return

        # If drawing border, allow panning but track distance
        if self._pending_draw_border:
            return

        # Robust hit-test for points (more reliable than 'current')
        idx = self._hit_test_point(event.x, event.y)
        if idx is not None:
            self._dragging_point_index = idx
            return

        # Otherwise, begin panning
        self._panning = True

    def _on_left_drag(self, event: tk.Event) -> None:
        if not self.viewer_canvas or self._left_drag_start is None:
            return

        sx, sy = self._left_drag_start
        dx = event.x - sx
        dy = event.y - sy

        if self._dragging_point_index is not None:
            self._left_drag_start = (event.x, event.y)
            idx = self._dragging_point_index
            if idx < 0 or idx >= len(self.points) or not self._pil_image:
                return
            px, py = self.canvas_to_image(event.x, event.y)
            iw, ih = self._pil_image.size
            px = max(0.0, min(float(iw - 1), float(px)))
            py = max(0.0, min(float(ih - 1), float(py)))

            p = self.points[idx]
            self.points[idx] = ControlPoint(px=px, py=py, lat=p.lat, lon=p.lon)

            self._refresh_list()
            self._redraw_points_only()
            return

        if self._pending_add_point:
            return

        # Check if we've moved more than 6 pixels - if so, start panning
        if self._pending_draw_border or self._panning:
            total_distance = ((event.x - self._left_drag_start[0]) ** 2 +
                            (event.y - self._left_drag_start[1]) ** 2) ** 0.5

            if total_distance > 6:
                # Start panning mode
                if not self._panning:
                    self._panning = True
                    self.viewer_canvas.config(cursor="fleur")  # Hand cursor

                # Pan the canvas
                self.offset_x += dx
                self.offset_y += dy
                self.viewer_canvas.move("all", dx, dy)
                self._left_drag_start = (event.x, event.y)
            return

        if self._panning:
            self.offset_x += dx
            self.offset_y += dy
            self.viewer_canvas.move("all", dx, dy)
            self._left_drag_start = (event.x, event.y)

    def _on_left_release(self, event: tk.Event) -> None:
        if not self.viewer_canvas:
            return

        # Reset cursor
        self.viewer_canvas.config(cursor="")

        if self._dragging_point_index is not None:
            self._dragging_point_index = None
            self._left_drag_start = None
            self._panning = False
            return

        # If we were panning, don't place a point
        if self._panning:
            self._left_drag_start = None
            self._panning = False
            return

        if self._pending_add_point:
            self._pending_add_point = False
            self._set_viewer_status("Drag to pan. Wheel to zoom. Click Add Point to place a point.")
            self._hide_add_point_popup()

            if not self._pil_image:
                return

            px, py = self.canvas_to_image(event.x, event.y)
            iw, ih = self._pil_image.size
            if px < 0 or py < 0 or px >= iw or py >= ih:
                return

            dlg = LatLonDialog(self, "Enter coordinates", initial_lat="", initial_lon="", app=self)
            if dlg.result is None:
                return
            lat, lon = dlg.result

            self.points.append(ControlPoint(px=float(px), py=float(py), lat=float(lat), lon=float(lon)))
            self._refresh_list()
            self._redraw_points_only()

        if self._pending_draw_border:
            if not self._pil_image:
                return

            px, py = self.canvas_to_image(event.x, event.y)
            iw, ih = self._pil_image.size
            if px < 0 or py < 0 or px >= iw or py >= ih:
                return

            # Check if click is near the first point to close polygon
            close_distance = 10  # pixels on canvas
            if len(self.border_points) >= 3:
                first_px, first_py = self.border_points[0]
                first_cx, first_cy = self.image_to_canvas(first_px, first_py)
                distance = ((event.x - first_cx) ** 2 + (event.y - first_cy) ** 2) ** 0.5
                if distance < close_distance:
                    # Close the polygon
                    self._pending_draw_border = False
                    self._set_viewer_status(f"Border complete: {len(self.border_points)} points")
                    self._redraw_border()
                    return

            # Add new border point
            self.border_points.append((float(px), float(py)))
            self._redraw_border()

            # Update status
            if len(self.border_points) == 1:
                self._set_viewer_status("Click to add more points. Click near first point to close.")
            else:
                self._set_viewer_status(f"Border: {len(self.border_points)} points. Click near first to close.")

        self._left_drag_start = None
        self._panning = False

    def _on_right_press(self, event: tk.Event) -> None:
        """Right-click always pans (works in any mode)."""
        if not self.viewer_canvas:
            return
        self._left_drag_start = (event.x, event.y)
        self._panning = True
        # Change cursor to hand immediately
        self.viewer_canvas.config(cursor="fleur")

    def _on_right_drag(self, event: tk.Event) -> None:
        """Right-drag always pans the map."""
        if not self.viewer_canvas or self._left_drag_start is None:
            return

        sx, sy = self._left_drag_start
        dx = event.x - sx
        dy = event.y - sy

        # Pan the canvas
        self.offset_x += dx
        self.offset_y += dy
        self.viewer_canvas.move("all", dx, dy)
        self._left_drag_start = (event.x, event.y)

    def _on_right_release(self, event: tk.Event) -> None:
        """Reset after right-click panning."""
        if not self.viewer_canvas:
            return
        # Reset cursor
        self.viewer_canvas.config(cursor="")
        self._left_drag_start = None
        self._panning = False

    # ------------------ Coordinate transforms ------------------
    def canvas_to_image(self, cx: float, cy: float) -> tuple[float, float]:
        x = (cx - self.offset_x) / self.scale
        y = (cy - self.offset_y) / self.scale
        return (x, y)

    def image_to_canvas(self, px: float, py: float) -> tuple[float, float]:
        cx = self.offset_x + px * self.scale
        cy = self.offset_y + py * self.scale
        return (cx, cy)

    # ------------------ Image & drawing ------------------
    def load_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select map image",
            initialdir=self.last_image_dir,
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.tif *.tiff *.webp *.bmp"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            pil = Image.open(path)
            if pil.mode not in ("RGB", "RGBA"):
                pil = pil.convert("RGB")
        except Exception as e:
            messagebox.showerror("Load failed", f"Could not open image.\n\n{e}")
            return

        self.image_path = path
        self._pil_image = pil

        # Remember the directory for next time
        self.last_image_dir = os.path.dirname(path)

        self.points.clear()
        self.listbox.delete(0, tk.END)
        self._point_item_ids = []

        # Clear border when loading new image
        self.border_points.clear()
        self._clear_border_visuals()

        # Show viewer when image is loaded
        if not self._viewer_visible:
            # Expand window to show viewer
            self.geometry("1320x750")
            self._viewer_visible = True
            # Get the right panel (first pane in the panedwindow currently)
            right_panel = self.paned_window.panes()[0]
            # Add viewer panels before the right panel
            self.paned_window.add(self.viewer_left_panel, before=right_panel, minsize=150, width=150)
            self.paned_window.add(self.viewer_frame, before=right_panel, minsize=400)

            # Set sash positions after adding panes to control initial sizes
            # Position first sash at 150px (left panel width)
            # Position second sash at 1000px (leaving 320px for right panel)
            self.after(50, lambda: self.paned_window.sash_place(0, 150, 0))
            self.after(50, lambda: self.paned_window.sash_place(1, 1000, 0))

        # Reset view and redraw with the new image
        # Use longer delay to ensure canvas is fully laid out
        self.after(200, lambda: (self._reset_view_to_fit(), self.redraw()))
        self.status_var.set(f"Loaded: {os.path.basename(path)} | Add points to create overlay")

    def rotate_image(self, degrees: int) -> None:
        """Rotate the image by the specified degrees. Clears all control points."""
        if not self._pil_image:
            messagebox.showinfo("No image", "Load an image first.")
            return

        # Check if control points or border exist
        if self.points or self.border_points:
            # Show confirmation dialog
            result = messagebox.askyesno(
                "Clear Control Points & Border?",
                "Rotating the image will remove all existing control points and border.\n"
                "Rotate first, then add points/border. Continue?",
                icon='warning'
            )
            if not result:
                return

        # Perform rotation
        try:
            # PIL's rotate is counter-clockwise by default, but we want to use expand=True
            # to avoid cropping. For 90/-90/180, we can use transpose which is cleaner
            if degrees == 90:
                rotated = self._pil_image.transpose(Image.Transpose.ROTATE_270)  # PIL ROTATE_270 = clockwise 90
            elif degrees == -90:
                rotated = self._pil_image.transpose(Image.Transpose.ROTATE_90)  # PIL ROTATE_90 = counter-clockwise 90
            elif degrees == 180:
                rotated = self._pil_image.transpose(Image.Transpose.ROTATE_180)
            else:
                # Fallback for arbitrary angles
                rotated = self._pil_image.rotate(-degrees, expand=True)

            self._pil_image = rotated

            # Clear all control points and border
            self.points.clear()
            self.listbox.delete(0, tk.END)
            self._point_item_ids = []
            self.border_points.clear()
            self._clear_border_visuals()

            # Reset view and redraw
            self._reset_view_to_fit()
            self.redraw()

            # Update status
            self.status_var.set("Image rotated — control points and border cleared. Add points again.")

        except Exception as e:
            messagebox.showerror("Rotation failed", f"Could not rotate image.\n\n{e}")

    def _reset_view_to_fit(self) -> None:
        """Center and fit the image in the viewer canvas."""
        if not self._pil_image or not self.viewer_canvas:
            return

        # Force full geometry update to ensure canvas has correct dimensions
        self.update_idletasks()
        self.update()

        cw = self.viewer_canvas.winfo_width()
        ch = self.viewer_canvas.winfo_height()

        # If canvas not sized yet, use reasonable defaults based on expected viewer size
        if cw <= 1 or ch <= 1:
            # Expected canvas size: window width (1320) - left panel (150) - right panel (320) = ~850
            cw = 850
            ch = 750

        # Ensure minimum reasonable size
        cw = max(cw, 400)
        ch = max(ch, 300)

        iw, ih = self._pil_image.size

        # Calculate scale to fit image in canvas while maintaining aspect ratio
        sx = cw / iw
        sy = ch / ih
        # Use 0.95 to leave a small margin
        self.scale = max(self.min_scale, min(self.max_scale, min(sx, sy) * 0.95))

        # Center the image in the canvas
        self.offset_x = (cw - iw * self.scale) / 2
        self.offset_y = (ch - ih * self.scale) / 2

    def redraw(self) -> None:
        if not self.viewer_canvas:
            return

        c = self.viewer_canvas
        c.delete("all")
        self._image_item_id = None
        self._point_item_ids = []
        self._popup_rect_id = None
        self._popup_text_id = None

        if not self._pil_image:
            # Show centered message when no image is loaded
            cw = c.winfo_width() if c.winfo_width() > 1 else 800
            ch = c.winfo_height() if c.winfo_height() > 1 else 600
            c.create_text(
                cw / 2, ch / 2,
                text="Load an image to proceed",
                fill="white",
                anchor="center",
                font=("Helvetica", 24)
            )
            return

        iw, ih = self._pil_image.size
        scaled_w = max(1, int(iw * self.scale))
        scaled_h = max(1, int(ih * self.scale))

        resized = self._pil_image.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(resized)

        self._image_item_id = c.create_image(self.offset_x, self.offset_y, image=self._tk_image, anchor="nw")

        for idx, p in enumerate(self.points, start=1):
            cx, cy = self.image_to_canvas(p.px, p.py)
            r = 6
            oval_id = c.create_oval(
                cx - r, cy - r, cx + r, cy + r, outline="red", fill="", width=2, tags=("pt", f"pt:{idx-1}")
            )
            label_id = c.create_text(cx + 10, cy - 10, text=str(idx), fill="yellow", anchor="nw", tags=("pt", f"pt:{idx-1}"))
            self._point_item_ids.append((oval_id, label_id))

        # Draw border polygon if it exists
        self._redraw_border()

        # Restore popup if in add point mode
        if self._pending_add_point:
            self._show_add_point_popup()

    def _redraw_points_only(self) -> None:
        if not self.viewer_canvas or not self._pil_image:
            return

        c = self.viewer_canvas
        for oval_id, label_id in self._point_item_ids:
            try:
                c.delete(oval_id)
                c.delete(label_id)
            except Exception:
                pass
        self._point_item_ids = []

        for idx, p in enumerate(self.points, start=1):
            cx, cy = self.image_to_canvas(p.px, p.py)
            r = 6
            oval_id = c.create_oval(
                cx - r, cy - r, cx + r, cy + r, outline="red", fill="", width=2, tags=("pt", f"pt:{idx-1}")
            )
            label_id = c.create_text(cx + 10, cy - 10, text=str(idx), fill="yellow", anchor="nw", tags=("pt", f"pt:{idx-1}"))
            self._point_item_ids.append((oval_id, label_id))

        # Restore popup if in add point mode
        if self._pending_add_point:
            self._show_add_point_popup()

    def _redraw_border(self) -> None:
        """Redraw the border polygon on the canvas."""
        if not self.viewer_canvas or not self._pil_image:
            return

        # Clear existing border visuals
        self._clear_border_visuals()

        if len(self.border_points) == 0:
            return

        c = self.viewer_canvas

        # Draw lines between points
        for i in range(len(self.border_points)):
            px1, py1 = self.border_points[i]
            cx1, cy1 = self.image_to_canvas(px1, py1)

            # Draw point
            r = 4
            point_id = c.create_oval(
                cx1 - r, cy1 - r, cx1 + r, cy1 + r,
                outline="blue", fill="cyan", width=2, tags="border"
            )
            self._border_point_ids.append(point_id)

            # Draw line to next point (or back to first if closed)
            if i < len(self.border_points) - 1:
                px2, py2 = self.border_points[i + 1]
            elif not self._pending_draw_border and len(self.border_points) >= 3:
                # Closed polygon: connect last point to first
                px2, py2 = self.border_points[0]
            else:
                continue

            cx2, cy2 = self.image_to_canvas(px2, py2)
            line_id = c.create_line(
                cx1, cy1, cx2, cy2,
                fill="cyan", width=2, tags="border"
            )
            self._border_line_ids.append(line_id)

    def _execute_accumulated_zoom(self) -> None:
        """Execute the accumulated zoom operations in a single redraw."""
        if abs(self._accumulated_zoom_factor - 1.0) < 1e-9:
            self._accumulated_zoom_factor = 1.0
            self._pending_zoom_id = None
            return

        cx, cy = self._zoom_center
        self.zoom_at(cx, cy, self._accumulated_zoom_factor)

        # Reset accumulator
        self._accumulated_zoom_factor = 1.0
        self._pending_zoom_id = None

    def zoom_at(self, cx: float, cy: float, factor: float) -> None:
        if not self._pil_image or not self.viewer_canvas:
            return

        new_scale = self.scale * factor
        new_scale = max(self.min_scale, min(self.max_scale, new_scale))
        if abs(new_scale - self.scale) < 1e-9:
            return

        ix, iy = self.canvas_to_image(cx, cy)
        self.scale = new_scale
        self.offset_x = cx - ix * self.scale
        self.offset_y = cy - iy * self.scale
        self.redraw()

    # ------------------ Points list management ------------------
    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for i, p in enumerate(self.points, start=1):
            self.listbox.insert(tk.END, f"{i}. px={p.px:.1f}, py={p.py:.1f}  ->  lat={p.lat:.6f}, lon={p.lon:.6f}")
        self.status_var.set(f"Points: {len(self.points)}")

    def _get_selected_index(self) -> Optional[int]:
        sel = self.listbox.curselection()
        if not sel:
            return None
        return int(sel[0])

    def edit_selected(self) -> None:
        idx = self._get_selected_index()
        if idx is None:
            return
        p = self.points[idx]
        dlg = LatLonDialog(self, "Edit coordinates", initial_lat=str(p.lat), initial_lon=str(p.lon), app=self)
        if dlg.result is None:
            return
        lat, lon = dlg.result
        self.points[idx] = ControlPoint(px=p.px, py=p.py, lat=lat, lon=lon)
        self._refresh_list()
        self._redraw_points_only()

    def delete_selected(self) -> None:
        idx = self._get_selected_index()
        if idx is None:
            return
        del self.points[idx]
        self._refresh_list()
        self._redraw_points_only()

    def clear_points(self) -> None:
        if not self.points:
            return
        if not messagebox.askyesno("Clear points", "Remove all control points?"):
            return
        self.points.clear()
        self._refresh_list()
        self._redraw_points_only()

    # ------------------ Save/Load points ------------------
    def _default_points_path(self) -> str:
        if self.image_path:
            base, _ = os.path.splitext(self.image_path)
            return base + ".control_points.json"
        return "control_points.json"

    def save_points(self) -> None:
        if not self.points:
            messagebox.showinfo("Nothing to save", "No control points yet.")
            return

        path = filedialog.asksaveasfilename(
            title="Save control points",
            defaultextension=".json",
            initialdir=self.last_points_dir,
            initialfile=os.path.basename(self._default_points_path()),
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return

        payload = {"image_path": self.image_path, "points": [asdict(p) for p in self.points]}

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save points.\n\n{e}")
            return

        # Remember the directory for next save during this session
        self.last_points_dir = os.path.dirname(path)

        self.status_var.set(f"Saved points: {os.path.basename(path)}")

    def load_points(self) -> None:
        path = filedialog.askopenfilename(
            title="Load control points",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            messagebox.showerror("Load failed", f"Could not read JSON.\n\n{e}")
            return

        pts = payload.get("points", [])
        if not isinstance(pts, list) or not pts:
            messagebox.showerror("Invalid file", "No points found in this JSON file.")
            return

        new_points: list[ControlPoint] = []
        try:
            for item in pts:
                new_points.append(ControlPoint(px=float(item["px"]), py=float(item["py"]), lat=float(item["lat"]), lon=float(item["lon"])))
        except Exception as e:
            messagebox.showerror("Invalid file", f"Could not parse points.\n\n{e}")
            return

        # Don't overwrite image_path - keep the currently loaded image filename
        self.points = new_points
        self._refresh_list()
        if self._viewer_visible and self.viewer_canvas and self._pil_image:
            self._redraw_points_only()
        self.status_var.set(f"Loaded points: {os.path.basename(path)}")

    # ------------------ KMZ generation ------------------
    def _require_numpy(self) -> bool:
        if np is None:
            messagebox.showerror("Missing dependency", "KMZ generation requires NumPy.\n\nInstall it with:\n  python3 -m pip install numpy")
            return False
        return True

    def _fit_affine(self):
        if not self._require_numpy():
            return None
        if len(self.points) < 3:
            return None

        X = np.array([[p.px, p.py, 1.0] for p in self.points], dtype=float)
        y_lat = np.array([p.lat for p in self.points], dtype=float)
        y_lon = np.array([p.lon for p in self.points], dtype=float)

        A_lat, *_ = np.linalg.lstsq(X, y_lat, rcond=None)
        A_lon, *_ = np.linalg.lstsq(X, y_lon, rcond=None)
        return A_lat, A_lon

    def _latlon_for_pixel(self, A_lat, A_lon, x: float, y: float) -> tuple[float, float]:
        v = np.array([x, y, 1.0], dtype=float)
        lat = float(A_lat @ v)
        lon = float(A_lon @ v)
        return lat, lon

    def generate_kmz(self) -> None:
        if not self._pil_image or not self.image_path:
            messagebox.showinfo("No image", "Load an image first.")
            return

        if len(self.points) < 3:
            messagebox.showerror("Need more points", "To generate a KMZ, add at least 3 control points (4–8 is better).")
            return

        if not self._require_numpy():
            return

        fitted = self._fit_affine()
        if fitted is None:
            messagebox.showerror("Fit failed", "Could not fit an affine transform. Add more points and try again.")
            return
        A_lat, A_lon = fitted

        w, h = self._pil_image.size
        corners_px = [(0.0, float(h)), (float(w), float(h)), (float(w), 0.0), (0.0, 0.0)]
        corners_ll = [self._latlon_for_pixel(A_lat, A_lon, x, y) for (x, y) in corners_px]

        base = os.path.splitext(os.path.basename(self.image_path))[0]
        out_path = filedialog.asksaveasfilename(
            title="Save KMZ",
            defaultextension=".kmz",
            initialdir=self.last_kmz_dir,
            initialfile=base,
            filetypes=[("KMZ", "*.kmz")]
        )
        if not out_path:
            return

        coord_str = "\n".join([f"{lon:.8f},{lat:.8f},0" for (lat, lon) in corners_ll])

        # Preserve original filename (with .png extension for KMZ)
        original_filename = os.path.basename(self.image_path)
        image_filename = os.path.splitext(original_filename)[0] + ".png"

        kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <name>{base} overlay</name>
    <description></description>
    <GroundOverlay>
      <name>{base}</name>
      <Icon>
        <href>{image_filename}</href>
      </Icon>
      <gx:LatLonQuad>
        <coordinates>
{coord_str}
        </coordinates>
      </gx:LatLonQuad>
    </GroundOverlay>
  </Document>
</kml>
"""

        img = self._pil_image.copy()

        # Apply border mask if border exists
        if self.border_points and len(self.border_points) >= 3:
            # Convert to RGBA to support transparency
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            # Create a mask from the border polygon
            from PIL import ImageDraw
            mask = Image.new('L', (w, h), 0)  # Black (transparent)
            draw = ImageDraw.Draw(mask)

            # Convert border points to PIL polygon format (flat list of coordinates)
            polygon_coords = []
            for px, py in self.border_points:
                polygon_coords.extend([px, py])

            # Draw filled polygon on mask (white = opaque)
            draw.polygon(polygon_coords, fill=255, outline=255)

            # Apply mask to alpha channel
            img.putalpha(mask)
        else:
            # No border: ensure image is in a format suitable for PNG
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

        import io
        png_bytes = io.BytesIO()
        img.save(png_bytes, format="PNG")
        png_data = png_bytes.getvalue()

        try:
            with ZipFile(out_path, "w", compression=ZIP_DEFLATED) as z:
                z.writestr("doc.kml", kml)
                z.writestr(image_filename, png_data)
        except Exception as e:
            messagebox.showerror("Write failed", f"Could not write KMZ.\n\n{e}")
            return

        # Remember the directory for next save during this session
        self.last_kmz_dir = os.path.dirname(out_path)

        self.status_var.set(f"KMZ saved: {os.path.basename(out_path)}")
        messagebox.showinfo("KMZ created", f"Saved KMZ:\n{out_path}\n\nOpen it in Google Earth Pro.")


def main() -> None:
    app = GeoImageKMZApp()
    app.mainloop()


if __name__ == "__main__":
    main()

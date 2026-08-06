# GeoImage KMZ – User Guide (v2.1)

## Overview

GeoImage KMZ is a lightweight desktop app for historical and exploratory map
research. It helps you align scanned/photographed maps (plat maps, atlases,
aerials, etc.) to real coordinates and export a KMZ overlay for Google Earth
and other KMZ-compatible tools.

This is for research and visualization. It is not survey-grade GIS.

## What's New in v2.1

- **Bigger, easier-to-read help & tip text.** The "Controls" panel in the
  Viewer, the "Tip" box on the main control panel, and the PLSS Lookup
  disclaimer text were all increased in size (from 8–10pt up to 10–12pt) so
  they're easier to read at a glance. The Viewer's left control panel was
  also widened slightly so the larger text has room to display without
  getting clipped.
- Version bumped to 2.1 — shown in the window title bar, and (on macOS) in
  the app bundle's version info.

## Security Notice (macOS + Windows)

Because GeoImage KMZ is distributed as a downloadable app (not from the
official Apple App Store or Microsoft Store), your computer may display a
security warning the first time you run it. This is normal for many
independent / open-source apps.

### macOS (Apple Silicon + Intel)

When opening GeoImage KMZ for the first time, macOS may block it and show a
message like:

> "GeoImage KMZ can't be opened because Apple cannot check it for malicious
> software."

If that happens:

1. Try opening the app once (so macOS registers it)
2. Go to **System Settings**
3. Click **Privacy & Security**
4. Scroll down to the **Security** section
5. You should see a message about GeoImage KMZ being blocked → click **Open
   Anyway**
6. Confirm again if prompted

After you approve it once, the app should open normally in the future.

### Windows

When running GeoImage KMZ for the first time, Windows may show a warning
such as:

> "Windows protected your PC"

If that happens:

1. Click **More info**
2. Click **Run anyway**

This is common for smaller apps that are not digitally signed.

## Disclaimer

GeoImage KMZ was originally developed for personal historical and
exploratory map research, and it is being shared freely for anyone who
would like to try it.

GeoImage KMZ is provided as-is, without warranty of any kind. The author is
not responsible for any damage, data loss, or other issues resulting from
the use of this software.

## Quick Start Workflow

1. **Load Image…**
   Select a map image (PNG/JPG/TIF/etc.).
2. **Open Viewer**
   Pan/zoom the map and place control points.
3. **Add 3–8 Control Points**
   In the Viewer panel: *Mark Coordinate → Add Point*.
   Click on the map, then enter Latitude/Longitude (decimal degrees).
4. **Optional: Border Mask**
   Use *Create Border Mask* (automatic) or *Draw Border* (manual) to hide
   map margins.
5. **Generate KMZ…**
   Save a KMZ and open it in Google Earth / Google Earth Pro.

## Viewer Controls

### Panning and Zoom

- Left drag: pan (when not placing a point)
- Right drag: always pan (works in any mode)
- Mouse wheel: zoom at cursor position
- Zoom + / Zoom − buttons: zoom at center

### Add / Edit Points

- **Add Point**: arms the next click to place a point, then prompts for
  coordinates.
- **Drag red dots**: reposition a point (pixel position).
- **Edit… / Delete**: modify or remove a selected point in the list.
- **Clear Points**: removes all control points.

### Rotate

- Rotate clears **all** control points and any border mask.
- Always rotate first, then add points/border.

## Paste Coordinates

In the Enter Coordinates dialog:

- **Paste Coordinates** reads the clipboard and fills Latitude/Longitude
  automatically.

Works with:

- Google Earth Pro "Copy" on a placemark (KML)
- Google Maps coordinate copy
- Any plain text containing two decimal-degree values

Examples:

- `38.627003, -90.199402`
- `38.627003 -90.199402`
- `-90.199402,38.627003,0` (Google Earth KML order)

## PLSS Lookup (Missouri and Kansas Only)

GeoImage KMZ includes a PLSS (Public Land Survey System) helper that can
fetch section corner coordinates for **Missouri and Kansas**.

### Why only two states?

- PLSS data is not available from one single, universal "federal lookup"
  API that covers every state in a consistent way.
- In practice, PLSS services and datasets are **state-by-state**, with
  different formats, field names, and availability.
- This app currently includes only Missouri and Kansas because those are
  the states being researched right now. More may be added later if
  reliable, public sources exist.

### How to use PLSS Lookup

1. In the Viewer panel click **Add Point**
2. Click the map where you want that section corner
3. In the Enter Coordinates dialog click **PLSS Lookup…**
4. Choose:
   - State: Missouri or Kansas
   - Township number and direction (N/S)
   - Range number and direction (E/W)
   - Section (1–36)
   - Corner: NW, NE, SE, SW (the corner of that section you are marking)
5. Click **Fetch**
6. The Latitude/Longitude fields auto-fill; click **OK** to save the point.

**Tip:** The app remembers the last PLSS inputs **during the session** so
adding multiple corners is faster (you usually only change Section and
Corner).

## Border Mask Feature

A Border Mask makes everything outside a polygon transparent in the final
overlay image. This is useful to hide white margins, legend blocks,
publisher text, township/range notes, and other clutter so multiple maps
can sit edge-to-edge cleanly in Google Earth.

### Method A: Create Border Mask (Automatic)

- In the main window, click **Create Border Mask** (above Generate KMZ).
- If a border already exists, you will be told to reset it first.
- If no border exists, you will be warned it will connect your control
  points in the order you placed them, and you can Cancel or Proceed.

Notes for best results:

- Place your control points around the perimeter of the area you want
  visible.
- Add extra points along edges (not just corners).
- Place points in a sensible order around the map (clockwise or
  counterclockwise).

### Method B: Draw Border (Manual)

- In the Viewer panel: *Border Mask → Draw Border*.
- Click to place border points (cyan points/lines).
- Click near the first point to close the polygon.
- **Undo Line**:
  - First click re-opens a closed border (removes the closing line).
  - Additional clicks remove the most recently added point.
- **Reset Border** clears the entire border.

**Important:** Only one border mask is active at a time. Reset Border
removes either a manually drawn border OR an auto-generated border.

## Output Folder Behavior

During a single app session:

- The app remembers the last folder you loaded an image from.
- The app remembers the last folder you generated a KMZ to.

If you quit and relaunch the app, the default folder resets back to
Desktop.

## KMZ Contents

A KMZ is a zip-like container. Each generated KMZ contains:

- `doc.kml` (the KML definition)
- your overlay image stored inside the KMZ

The overlay image inside the KMZ uses the **same base filename** as your
input image (saved as PNG). This makes it easier if you unzip/organize
overlays manually.

**Tip:** You can rename `.kmz` to `.zip` and unzip it to inspect contents.

## Tips for Better Alignment

- Use 4–8 well-spread points for better results.
- Pick stable, easy-to-identify features: road intersections, bridges,
  building corners, section corners, etc.
- If a point is slightly off, Edit it or drag its dot on the map and
  regenerate the KMZ.

## Support & Contact

GeoImage KMZ is a free tool created for historical researchers,
genealogists, and metal detecting enthusiasts.

If you find it useful, please consider supporting development:

- PayPal: <https://www.paypal.com/paypalme/techbill>
- Buy Me a Coffee: <https://buymeacoffee.com/techbill>
- Author: Bill Fleming (TechBill)
- GitHub: <https://github.com/TechBill>

## License

GeoImage KMZ is provided as-is for personal and research use.

The application is distributed as a free binary. Redistribution is
permitted provided this README and author credit remain intact.

Thank you for using GeoImage KMZ.

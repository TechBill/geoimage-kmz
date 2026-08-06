# GeoImage KMZ

**GeoImage KMZ** is a lightweight desktop app that turns a scanned or
photographed map — plat maps, atlases, aerial photos, and similar — into a
geo-referenced KMZ overlay you can open in Google Earth (or any
KMZ-compatible viewer). You mark a handful of control points that tie pixel
locations on the image to known latitude/longitude coordinates, and the app
fits a best-fit affine transform to build the overlay.

It's built for historical researchers, genealogists, and metal detecting
enthusiasts who work with old maps and need to line them up against modern
coordinates.

This is a research/visualization tool — it is **not** survey-grade GIS.

## Features

- Pan/zoom image viewer with draggable control points
- Best-fit affine transform (least squares) from 3+ control points to
  lat/lon
- **Paste Coordinates** — auto-parses clipboard text or Google Earth KML
  placemarks
- **PLSS Lookup** (Public Land Survey System) for Missouri and Kansas —
  fetch section-corner coordinates directly instead of typing them
- **Border Mask** — hide map margins/legends so overlays sit edge-to-edge
  cleanly in Google Earth
- Save/Load control points as JSON, so an overlay can be revisited or
  refined later
- Rotate image (90° / 180° / 270°)
- Packaged as a standalone desktop app for Windows and macOS — no Python
  install required to run it

## What's new in v2.1

- **Bigger, easier-to-read help & tip text.** The "Controls" panel in the
  Viewer, the "Tip" box on the main control panel, and the PLSS Lookup
  disclaimer text were increased in size, and the Viewer's left control
  panel was widened slightly so the larger text isn't clipped.
- Version bumped to 2.1 (window title bar, and the macOS app bundle's
  version info).

Full usage instructions are in [USER_GUIDE.md](USER_GUIDE.md).

## Getting the app

GeoImage KMZ isn't distributed through the Apple App Store or Microsoft
Store, so macOS/Windows will show a security warning the first time you
open it — this is expected for independent apps that aren't code-signed or
notarized. See [Security Notice in the User Guide](USER_GUIDE.md#security-notice-macos--windows)
for how to get past it.

## Running from source

Requires Python 3.12+ and:

```bash
python3 -m pip install pillow numpy
```

Then:

```bash
python3 geoimage_kmz.py
```

## Building the standalone app

```bash
python -m PyInstaller --noconfirm --clean "GeoImage KMZ.spec"
```

- macOS → `dist/GeoImage KMZ.app`
- Windows → `dist/GeoImage KMZ.exe`

The spec must be built on the target platform (no cross-compiling). See
[AGENTS.md](AGENTS.md) for build/version/packaging notes.

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

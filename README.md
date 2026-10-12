# AI generated

# Niri Monitor Settings

A small graphical utility for arranging monitors in Niri. Drag displays into position, adjust their resolution, scale, and rotation, then export the layout as a separate KDL file. The program previews and exports your changes; it does not apply them to the running session.

## Start

Run the program from a Niri session with Python 3 and Tkinter installed:

```sh
python3 monitor-layout.py
```

## Use

- Drag monitors on the canvas to arrange them. Nearby edges snap together.
- Select a monitor to change its resolution, scale, or rotation.
- Choose **Export Layout Fragment** to save the layout to a `.kdl` file.

To use the exported layout, save the file beside your Niri config and add this top-level line to `~/.config/niri/config.kdl`:

```kdl
include "monitor-layout.kdl"
```

Remove or replace existing `output` blocks for those monitors in the main config so the layout has a single source of settings.

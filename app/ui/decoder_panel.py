"""Always-visible value decoder for resistors and capacitors.

This is one of the MVP differentiators: a bench-mode side panel consulted
dozens of times per soldering session. Bidirectional:
  - Type a value (e.g. "4K7", "100n") -> get the display and, for resistors,
    the 4-band color code.
  - Pick colors from dropdowns -> get the value.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.core import decoders
from app.ui.widgets import RESISTOR_BAND_HEX, band_fg


_DIGIT_COLORS = [
    "black", "brown", "red", "orange", "yellow",
    "green", "blue", "violet", "grey", "white",
]
_MULTIPLIER_COLORS = [
    "silver", "gold", "black", "brown", "red", "orange",
    "yellow", "green", "blue", "violet", "grey", "white",
]
_TOLERANCE_COLORS = ["brown", "red", "gold", "silver"]


class DecoderPanel(ttk.Frame):
    """Right-side dockable panel. Stays visible across view switches."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=12, width=260)
        self.pack_propagate(False)

        ttk.Label(
            self,
            text="Value Decoder",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor=tk.W, pady=(0, 8))

        self._build_resistor()
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        self._build_capacitor()

    # ---- resistor section -----------------------------------------------

    def _build_resistor(self) -> None:
        frame = ttk.LabelFrame(self, text="Resistor", padding=8)
        frame.pack(fill=tk.X)

        # Text -> display + bands
        ttk.Label(frame, text='e.g. "4K7", "1M", "100R"', foreground="#888",
                  font=("Segoe UI", 9)).pack(anchor=tk.W)
        self._r_text = tk.StringVar()
        r_entry = ttk.Entry(frame, textvariable=self._r_text)
        r_entry.pack(fill=tk.X, pady=(2, 4))
        r_entry.bind("<KeyRelease>", self._on_resistor_text_change)

        self._r_display = ttk.Label(frame, text="\u2014", font=("Segoe UI", 11, "bold"))
        self._r_display.pack(anchor=tk.W)

        bands_frame = ttk.Frame(frame)
        bands_frame.pack(fill=tk.X, pady=6)
        self._r_bands = self._build_band_strip(bands_frame)

        # Color -> value (reverse mode)
        ttk.Label(frame, text="Or pick bands:", foreground="#888",
                  font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(6, 2))
        combos_frame = ttk.Frame(frame)
        combos_frame.pack(fill=tk.X)
        self._r_combo_d1 = self._make_combo(combos_frame, _DIGIT_COLORS)
        self._r_combo_d2 = self._make_combo(combos_frame, _DIGIT_COLORS)
        self._r_combo_mult = self._make_combo(combos_frame, _MULTIPLIER_COLORS)
        for combo in (self._r_combo_d1, self._r_combo_d2, self._r_combo_mult):
            combo.pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
            combo.bind("<<ComboboxSelected>>", self._on_resistor_combo_change)

    def _build_band_strip(self, parent: ttk.Frame) -> list[tk.Label]:
        labels: list[tk.Label] = []
        for _ in range(4):
            lbl = tk.Label(parent, text="", width=4, height=2,
                           relief="flat", borderwidth=1,
                           background="#eeeeee", font=("Segoe UI", 8))
            lbl.pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
            labels.append(lbl)
        return labels

    def _make_combo(self, parent: tk.Misc, values: list[str]) -> ttk.Combobox:
        combo = ttk.Combobox(parent, values=values, state="readonly", width=8)
        return combo

    def _on_resistor_text_change(self, _event=None) -> None:
        text = self._r_text.get().strip()
        if not text:
            self._r_display.configure(text="\u2014")
            self._paint_bands([])
            return
        try:
            ohms = decoders.parse_resistor(text)
        except ValueError:
            self._r_display.configure(text="?", foreground="#c00")
            self._paint_bands([])
            return
        self._r_display.configure(text=decoders.resistor_display(ohms), foreground="#000")
        try:
            bands = decoders.resistor_to_bands(ohms)
        except ValueError:
            self._paint_bands([])
            return
        self._paint_bands(bands)

    def _on_resistor_combo_change(self, _event=None) -> None:
        bands = [
            self._r_combo_d1.get(),
            self._r_combo_d2.get(),
            self._r_combo_mult.get(),
        ]
        if not all(bands):
            return
        try:
            ohms = decoders.bands_to_resistor(bands)
        except ValueError:
            return
        self._r_text.set(decoders.resistor_to_text(ohms))
        self._on_resistor_text_change()

    def _paint_bands(self, bands: list[str]) -> None:
        for i, lbl in enumerate(self._r_bands):
            if i < len(bands):
                color = bands[i]
                lbl.configure(
                    background=RESISTOR_BAND_HEX.get(color, "#dddddd"),
                    foreground=band_fg(color),
                    text=color,
                )
            else:
                lbl.configure(background="#eeeeee", foreground="#888",
                              text="")

    # ---- capacitor section ----------------------------------------------

    def _build_capacitor(self) -> None:
        frame = ttk.LabelFrame(self, text="Capacitor", padding=8)
        frame.pack(fill=tk.X)

        ttk.Label(frame, text='e.g. "100n", "4n7", "10u", "100p"',
                  foreground="#888", font=("Segoe UI", 9)).pack(anchor=tk.W)
        self._c_text = tk.StringVar()
        c_entry = ttk.Entry(frame, textvariable=self._c_text)
        c_entry.pack(fill=tk.X, pady=(2, 4))
        c_entry.bind("<KeyRelease>", self._on_capacitor_text_change)

        self._c_display = ttk.Label(frame, text="\u2014", font=("Segoe UI", 11, "bold"))
        self._c_display.pack(anchor=tk.W)

        self._c_alt = ttk.Label(frame, text="", foreground="#666", font=("Segoe UI", 9))
        self._c_alt.pack(anchor=tk.W)

    def _on_capacitor_text_change(self, _event=None) -> None:
        text = self._c_text.get().strip()
        if not text:
            self._c_display.configure(text="\u2014")
            self._c_alt.configure(text="")
            return
        try:
            farads = decoders.parse_capacitor(text)
        except ValueError:
            self._c_display.configure(text="?", foreground="#c00")
            self._c_alt.configure(text="")
            return
        self._c_display.configure(text=decoders.capacitor_display(farads), foreground="#000")
        # Show the two alternative units too.
        alt_parts = []
        if farads >= 1e-6:
            alt_parts.append(f"{farads * 1e9:g} nF")
        elif farads >= 1e-9:
            alt_parts.append(f"{farads * 1e6:g} \u00B5F")
            alt_parts.append(f"{farads * 1e12:g} pF")
        else:
            alt_parts.append(f"{farads * 1e9:g} nF")
        self._c_alt.configure(text="  \u00B7  ".join(alt_parts))


__all__ = ["DecoderPanel"]


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from gi.repository import Gtk

def toggle_css(widget: "Gtk.Widget", class_name: str, active: bool) -> None:
    if active:
        widget.add_css_class(class_name)
    else:
        widget.remove_css_class(class_name)


def toggle_icon(widget: "Gtk.Button", active: bool, on_icon: str, off_icon: str) -> None:
    widget.set_icon_name(on_icon if active else off_icon)


def format_time(ns: int) -> str:
    if ns == 0:
        return "0:00"
    if ns < 0:
        return "N/A"
    seconds = ns // 1_000_000_000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"

def format_time_to_seconds(time_str: str) -> int:
    if time_str == "N/A":
        return 0
    hours = 0
    minutes = 0
    seconds = 0
    parts = time_str.split(":")
    if len(parts) >= 1:
        seconds = int(parts[-1])
    if len(parts) >= 2:
        minutes = int(parts[-2])
    if len(parts) >= 3:
        hours = int(parts[-3])
    return hours * 3600 + minutes * 60 + seconds



# Unit test
if __name__ == "__main__":
    print(format_time_to_seconds("0:00"))
    print(format_time_to_seconds("1:00"))
    print(format_time_to_seconds("1:01"))
    print(format_time_to_seconds("1:01:01"))

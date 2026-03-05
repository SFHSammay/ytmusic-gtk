from gi.repository import Gtk, Adw


def LoadingUI(
    primary_text: str = "Connecting...",
    spinner_size: int = 48,
    show_header: bool = True,
) -> Gtk.Widget:
    """Builds and returns a customizable loading screen widget."""
    loading_toolbar = Adw.ToolbarView()

    if show_header:
        loading_header = Adw.HeaderBar()
        loading_toolbar.add_top_bar(loading_header)

    loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    loading_box.set_valign(Gtk.Align.CENTER)

    spinner = Adw.Spinner()
    spinner.set_size_request(spinner_size, spinner_size)

    loading_label = Gtk.Label(label=primary_text)
    loading_label.add_css_class("title")

    loading_box.append(spinner)
    loading_box.append(loading_label)

    loading_toolbar.set_content(loading_box)

    return loading_toolbar

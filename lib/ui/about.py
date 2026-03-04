from typing import Optional
from gi.repository import Adw, Gio, Gtk


def show_about_window(
    application_name: str,
    application_icon: str,
    developer_name: str,
    app_version: str,
    repo_url: str,
    parent: Optional[Gtk.Window] = None,
) -> None:
    """Displays the Adwaita About Window."""
    about = Adw.AboutWindow(
        application_name=application_name,
        application_icon=application_icon,
        developer_name=developer_name,
        version=app_version,
        copyright="© 2026 Yamada Sexta",
        website=repo_url,
        issue_url=f"{repo_url}/issues",
        license_type=Gtk.License.LGPL_3_0,
    )
    if parent:
        about.set_transient_for(parent)
    about.show()

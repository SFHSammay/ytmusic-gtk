from typing import List
from typing import Optional
from lib.data import Thumbnail
import threading
import logging
from gi.repository import Gtk, GdkPixbuf, GLib, Gio, Gdk
import urllib.request


def load_image_async(image_widget: Gtk.Widget, url: str):
    """Fetches an image from a URL in the background and updates the widget.

    Works with both `Gtk.Picture` (using `set_paintable`) and `Gtk.Image`
    (using `set_from_pixbuf`).
    """

    def fetch():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            response = urllib.request.urlopen(req)
            data = response.read()

            # Convert network bytes to a GTK Texture or Pixbuf
            stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
            if pixbuf:
                # update widget appropriately on the main thread
                if hasattr(image_widget, "set_paintable"):
                    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                    GLib.idle_add(image_widget.set_paintable, texture)
                elif hasattr(image_widget, "set_from_pixbuf"):
                    GLib.idle_add(image_widget.set_from_pixbuf, pixbuf)
                else:
                    logging.debug(
                        f"Widget {image_widget} does not support image updates"
                    )
        except Exception as e:
            logging.debug(f"Failed to load image {url}: {e}")

    threading.Thread(target=fetch, daemon=True).start()


def load_thumbnail(image_widget: Gtk.Picture, thumbnails: Optional[List[Thumbnail]]):
    """Helper to load a thumbnail image with error handling."""
    if not thumbnails:
        logging.debug("No thumbnails provided for thumbnail loading.")
        return
    url = thumbnails[-1].url  # Use the last thumbnail (highest resolution)

    load_image_async(image_widget, url)

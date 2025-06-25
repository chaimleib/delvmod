import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, Gdk
from . import images
import delv

ABOUT_LICENSE = """This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. 

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program.  If not, see the GNU website at <http://www.gnu.org/licenses/>."""

ABOUT_COPYRIGHT = """"Cythera" and "Delver" are trademarks of either Glenn Andreas or Ambrosia Software, Inc. 

redelv is copyright 2015-16 Bryce Schroeder"""

ABOUT_COMMENTS = """Editor for Delver game engine files, which power Cythera."""

ABOUT_AUTHORS = [
    "Bryce Schroeder <bryce.schroeder@gmail.com>",
    "bryce.pw, Bryce Schroeder's website http://www.bryce.pw/",
    "delvmod GitHub https://github.com/BryceSchroeder/delvmod/",
    "Chaim Halbert <chaim.leib.halbert@gmail.com>"
]

ABOUT_WEBSITE = "https://github.com/BryceSchroeder/delvmod/wiki/Delver-Archive"

ABOUT_WEBSITE_LABEL = "Wiki"

ABOUT_VERSION = """delv version {delv_version}, redelv version {redelv_version}""" # .format(delv_version="", redelv_version="")

class AboutBox(Gtk.AboutDialog):
    def __init__(self, version: str, *args, **kwargs) -> None:
        super().__init__(
            *args,
            comments=ABOUT_COMMENTS,
            authors=ABOUT_AUTHORS,
            license=ABOUT_LICENSE,
            wrap_license=True,
            version=ABOUT_VERSION.format(
                delv_version=delv.version,
                redelv_version=version,
            ),
            copyright=ABOUT_COPYRIGHT,
            website=ABOUT_WEBSITE,
            website_label=ABOUT_WEBSITE_LABEL,
            **kwargs
        )

        icon = GdkPixbuf.Pixbuf.new_from_file(images.icon_path)
        self.set_icon(icon)

        logo = GdkPixbuf.Pixbuf.new_from_file(images.logo_path)
        self.set_logo(logo)

        self.connect("delete_event", self.on_hide)

    def on_hide(self, widget: Gtk.Widget, event: Gdk.Event) -> bool:
        widget.hide()
        return True # do not destroy

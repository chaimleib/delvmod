import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf
from typing import Any, Dict
from . import images
from .config import Config

class RedelvWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        application: Gtk.Application,
        cfg: Config,
        title: str,
        tree_data: Gtk.TreeStore,
        *args,
        **kwargs
    ) -> None:
        super().__init__(application=application, title=title, *args, **kwargs)
        self.cfg: Config = cfg
        if self.cfg.debug:
            print(f"RedelvWindow.__init__(title={repr(title)})")
        self.set_default_size(480, 512)
        self.tree_data = tree_data

        # Main content
        self.mvbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.mvbox)
        self.mvbox.show()

        self.set_icon(GdkPixbuf.Pixbuf.new_from_file(images.icon_path))

        # Set up the TreeView
        self.tree_view: Gtk.TreeView = self.init_treeview()
        sw = Gtk.ScrolledWindow(
            child=self.tree_view,
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        self.mvbox.pack_start(
            child=sw,
            expand=True,
            fill=True,
            padding=0
        )
        self.show_all()

    def init_treeview(self) -> Gtk.TreeView:
        view = Gtk.TreeView(model=self.tree_data)
        column_names = [
            "Subindex",
            "Size",
            "Description"
        ]
        for i, name in enumerate(column_names):
            column = Gtk.TreeViewColumn(name)
            r = Gtk.CellRendererText()
            column.pack_start(r, True)
            column.add_attribute(r, "text", i)
            view.append_column(column)
        return view

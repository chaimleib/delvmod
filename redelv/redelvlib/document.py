from sys import stderr
from os import path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gio, GdkPixbuf

import delv, delv.archive, delv.library
from . import images

def error(msg:str) -> None:
    print(msg, file=stderr)

class ReDelvWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        config: dict[str, str],
        title: str,
        tree_data: Gtk.TreeStore,
        *args,
        **kwargs
    ) -> None:
        super().__init__(title=title, *args, **kwargs)
        self.config: dict[str, str] = config
        if "debug" in self.config: print("ReDelvWindow.__init__")
        self.set_default_size(480, 512)
        self.tree_data = tree_data

        # Main content
        self.mvbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.mvbox)
        self.mvbox.show()

        ## Test label
        # lbl_variant = GLib.Variant.new_string("Hello world!")
        # self.label = Gtk.Label(label=lbl_variant.get_string(), margin=30)
        # self.mvbox.add(self.label)
        # self.label.show()

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

class Document(Gtk.WindowGroup):
    # new_document_count says how many new documents have been created so far.
    # This affects the window title, where fpath is not provided.
    new_document_count: int = 0

    def __init__(
        self,
        config: dict[str, str],
        application: Gtk.Application,
        fpath: str = "", # empty means no file exists yet
        *args,
        **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.config: dict[str, str] = config
        if "debug" in self.config: print("Document.__init__")

        documents.append(self)
        self.application: Gtk.Application = application
        # fpath: The file path of the document.
        # Empty means the document exists in memory only
        # and has not been saved yet.
        self.fpath: str = fpath
        # new_id: If a new document is created, remembers which number
        # document it is. This gives a temporary title for the document until
        # it gets saved.
        self.new_id: int = 0
        if not self.fpath:
            Document.new_document_count += 1
            self.new_id = Document.new_document_count
        # changed: Whether the document has changed since the last open or save.
        self.changed: bool = False
        # tree_data: model for the TreeView of the main window.
        self.tree_data = Gtk.TreeStore(str, str, str, int, int)
        # window: The main document window.
        self.window: ReDelvWindow = self.init_window()

        doc_actions = {
            "menu-open": self.menu_open,
        }
        for name, callback in doc_actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.window.add_action(action)

        self.library: None | delv.library.Library = None
        self.archive: None | delv.archive.Archive = None
        self.underlay: None | delv.archive.Archive = None
        if self.fpath: self.open_file(self.fpath)

    def init_window(self) -> ReDelvWindow:
        window = ReDelvWindow(
            application=self.application,
            config=self.config,
            title=self.title(),
            tree_data=self.tree_data
        )
        window.connect("delete_event", self.delete_event)
        window.tree_view.connect("cursor-changed", self.cursor_changed)
        window.tree_view.connect("row-activated", self.row_activated)

        # self.window.connect("destroy", self.on_quit)

        # Make the data tree
        return window

    def unsaved(self) -> bool:
        return not self.fpath or self.changed

    def fresh_document(self) -> bool:
        return not self.fpath and not self.changed

    # title returns the main window title for the document.
    def title(self) -> str:
        if self.fpath:
            name = path.basename(self.fpath)
        elif self.new_id == 1:
            # There's no need to number the new documents if there is only one.
            name = "New Document"
        else:
            name = f"New Document {Document.new_document_count}"
        return f"•  {name}" if self.changed else name

    def set_unsaved(self) -> None:
        self.window.set_title(self.title())
        self.changed = True

    def set_saved(self):
        self.window.set_title(self.title())
        self.changed = False

    def present(self) -> None:
        self.window.present()

    # delete_event returns whether Document closure should be blocked.
    # If not, remove self from the documents list.
    def delete_event(self) -> bool:
        if "debug" in self.config: print("Document.delete_event")
        veto: bool = False
        if self.unsaved():
            veto = self.warn_unsaved_changes()
        if not veto:
            documents.remove(self)
        return veto

    # warn_unsaved_changes should be called if the Document is about to be lost.
    # It asks the user whether to really discard the Document, and
    # returns whether Document closure should be blocked:
    # True if the user says No, and False if the user says Yes.
    def warn_unsaved_changes(self) -> bool:
        if "debug" in self.config: print("Document.warn_unsaved_changes")
        dialog = Gtk.MessageDialog(
            parent=self.window, 
            modal=True, 
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="This action will lose unsaved changes; are you sure?",
        )
        rv = Gtk.ResponseType.YES != dialog.run()
        dialog.destroy()
        return rv

    # load replaces open_file
    def load(self):
        if "debug" in self.config: print("Document.load")
        try:
            self.archive = delv.archive.Scenario(
                path,
                gui_treestore=self.tree_data
            )
            self.library = None
        except Exception as e:
            self.error_message(
                f"{repr(self.fpath)} doesn't seem to be a valid archive: {repr(e)}"
            )
            return
        # if directory: self.set_open_directory(path)
        # else: self.set_open_file(path)
        self.set_saved()

    def row_activated(self, tree_view, path, column):
        if "debug" in self.config: print("Document.row_activated")
        self.cursor_changed(tree_view)
        # if self.current_resource: self.menu_resource_editor(None)
        # elif tree_view.row_expanded(path): 
        if tree_view.row_expanded(path): 
            tree_view.collapse_row(path)
        else:
            tree_view.expand_row(path, False)

    def cursor_changed(self, tree_view):
        if "debug" in self.config: print("Document.cursor_changed")
        model, rows = tree_view.get_selection().get_selected_rows()
        row = rows[-1]
        subindex = model.get_value(model.get_iter(row), 3)
        resource_id = model.get_value(model.get_iter(row), 4)
        if resource_id < 0:
            self.current_resource = None
            self.current_resource_id = 0
            self.current_subindex_id = subindex
            return
        library = self.get_library()
        if not isinstance(library, delv.library.Library):
            error("cursor_changed: failed to get library")
            return
        self.current_subindex_id = subindex
        self.current_resource_id = delv.archive.resid(subindex, resource_id)
        self.current_resource = library.get_resource(self.current_resource_id)

        # for recp in self.subindexchange: recp.signal_subindexchange()
        # for recp in self.resourcechange: recp.signal_resourcechange()

    def get_library(self):
        if "debug" in self.config: print("ReDelv.get_library")
        try:
            if not self.library:
                self.library = delv.library.Library(
                    self.underlay,
                    self.archive
                ) 
        except Exception as e:
            self.error_message(
                f"Couldn't create library; if you are editing a saved game, you need to underlay a scenario.\nException was: {repr(e)}"
            )
        return self.library

    def menu_open(self, widget, data=None) -> None:
        if "debug" in self.config: print("Document.menu_open")
        chooser = Gtk.FileChooserDialog(
            title="Select a Delver Archive...",
            action=Gtk.FileChooserAction.OPEN
        )
        chooser.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        chooser.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        response = chooser.run()
        if response == Gtk.ResponseType.OK:
            self.open_file(chooser.get_filename())
        chooser.destroy()
        #t = self.temporary_data.append(None, ["131","42 Items", "Image Data"])
        #self.temporary_data.append(t, ["8E31","12 kB","Something"])

    def open_file(self, fpath, directory=False):
        if "debug" in self.config: print("Document.open_file")
        doc = self if self.fresh_document() else Document(
            application=self.application,
            config=self.config,
            fpath=fpath
        )
        try:
            doc.archive = delv.archive.Scenario(
                fpath,
                gui_treestore=doc.tree_data
            )
            doc.library = None
        except Exception as e:
            doc.error_message(
                f"{repr(fpath)} doesn't seem to be a valid archive: {repr(e)}"
            )
            # Close the Document if we created a new one.
            if doc != self: doc.delete_event()
            return
        if directory: doc.set_open_directory(fpath)
        doc.set_saved()

    def set_open_directory(self, fpath: str):
        if "debug" in self.config: print("ReDelv.set_open_directory")
        self.exported_directory = fpath

        # for recp in self.filechange: recp.signal_filechange()
        # for recp in self.subindexchange: recp.signal_subindexchange()
        # for recp in self.resourcechange: recp.signal_resourcechange()
    def error_message(self, message:str):
        if "debug" in self.config: print("Document.error_message")
        dialog = Gtk.MessageDialog(
            parent=self.window, 
            modal=True,
            buttons=Gtk.ButtonsType.OK,
            message_type=Gtk.MessageType.ERROR,
            text=message
        )
        dialog.run()
        dialog.destroy()

documents: list[Document] = []

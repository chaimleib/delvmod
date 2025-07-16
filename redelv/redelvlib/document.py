from sys import stderr
from os import path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio

from typing import Any, Optional

import delv, delv.archive, delv.library
from . import images
from .config import Config
from .redelvwindow import RedelvWindow

def error(msg: str) -> None:
    print(msg, file=stderr)

class Document(Gtk.WindowGroup):
    def __init__(
        self,
        cfg: Config,
        application: Gtk.Application,
        *args,
        **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.cfg: Config = cfg
        if self.cfg.debug: print("Document.__init__")

        documents.append(self)
        self.application: Gtk.Application = application
        # fpath: The file path of the document.
        # Empty means the document exists in memory only
        # and has not been saved yet.
        self.fpath: str = ""
        # new_id: If a new document is created, remembers which number
        # document it is. This gives a temporary title for the document until
        # it gets saved.
        self.new_id: int = 0
        if not self.fpath:
            self.new_id = max_new_id() + 1
        # changed: Whether the document has changed since the last open or save.
        self.changed: bool = False
        # tree_data: model for the TreeView of the main window.
        self.tree_data = Gtk.TreeStore(str, str, str, int, int)
        # window: The main document window.
        self.window: RedelvWindow = self.init_window(
            application=self.application,
            cfg=self.cfg,
            tree_data=self.tree_data
        )

        doc_actions = {
            "menu-close": self.menu_close,
            "menu-new": self.menu_new,
            "menu-open": self.menu_open,
            "menu-underlay": self.menu_underlay,
        }
        for name, callback in doc_actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.window.add_action(action)

        self.library: Optional[delv.library.Library] = None
        self.archive: Optional[delv.archive.Archive] = None
        self.underlay: Optional[delv.archive.Archive] = None

    def init_window(
        self,
        application: Gtk.Application,
        cfg: Config,
        tree_data: Gtk.TreeStore
    ) -> RedelvWindow:
        window = RedelvWindow(
            application=application,
            cfg=cfg,
            title=self.title(),
            tree_data=tree_data
        )
        def on_delete(event: Gdk.Event, event_type: Gdk.EventType) -> bool:
            return self.delete_event()
        window.connect("delete_event", on_delete)

        window.tree_view.connect("cursor-changed", self.cursor_changed)
        window.tree_view.connect("row-activated", self.row_activated)
        if not self.fpath:
            self.refresh_titles()

        # self.window.connect("destroy", self.on_quit)
        self.add_window(window)

        return window

    # fresh_document returns True if this is an unsaved document
    # with no changes. Otherwise, it returns False.
    def fresh_document(self) -> bool:
        return not self.fpath and not self.changed

    # title returns the main window title for the document.
    def title(self) -> str:
        if self.fpath:
            name = path.basename(self.fpath)
        elif max_new_id() == 1:
            # There's no need to number the new document if there is only one.
            name = "New Document"
        else:
            name = f"New Document {self.new_id}"
        return f"•  {name}" if self.changed else name

    # refresh_titles finds the document with the first placeholder name and
    # updates its window title, if needed.
    def refresh_titles(self) -> None:
        for doc in documents:
            # The only window that would change is New Document number 1.
            # That's only relevant before it gets saved to the FS.
            # That's also only relevant after the window gets initialized.
            if doc.new_id == 1 and not doc.fpath and hasattr(doc, 'window'):
                old_title = doc.window.get_title()
                new_title = doc.title()
                if old_title != new_title:
                    print(f'window {repr(old_title)} -> {repr(new_title)}')
                    doc.window.set_title(new_title)
                return

    def set_unsaved(self) -> None:
        self.window.set_title(self.title())
        self.changed = True

    def set_saved(self) -> None:
        self.window.set_title(self.title())
        self.changed = False

    def present(self) -> None:
        self.window.present()

    def menu_close(self, widget: Gtk.Widget, data: Any = None) -> None:
        if self.delete_event():
            return
        self.window.destroy()
        if len(documents) == 0:
            self.application.quit()

    # delete_event returns whether Document closure should be blocked.
    # If not, remove self from the documents list.
    def delete_event(self) -> bool:
        if self.cfg.debug: print("Document.delete_event")
        veto: bool = False
        if self.changed:
            veto = self.warn_unsaved_changes()
        if not veto:
            documents.remove(self)
            self.refresh_titles()
            self.remove_window(self.window)
        return veto

    # warn_unsaved_changes should be called if the Document is about to be lost.
    # It asks the user whether to really discard the Document, and
    # returns whether Document closure should be blocked:
    # True if the user says No, and False if the user says Yes.
    def warn_unsaved_changes(self) -> bool:
        if self.cfg.debug: print("Document.warn_unsaved_changes")
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
    def load(self) -> None:
        if self.cfg.debug: print("Document.load")
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

    def row_activated(
        self,
        tree_view: Gtk.TreeView,
        path: Gtk.TreePath,
        column: Gtk.TreeViewColumn
    ) -> None:
        if self.cfg.debug: print("Document.row_activated")
        self.cursor_changed(tree_view)
        # if self.current_resource: self.menu_resource_editor(None)
        # elif tree_view.row_expanded(path): 
        if tree_view.row_expanded(path): 
            tree_view.collapse_row(path)
        else:
            tree_view.expand_row(path, False)

    def cursor_changed(self, tree_view: Gtk.TreeView) -> None:
        if self.cfg.debug: print("Document.cursor_changed")
        model, rows = tree_view.get_selection().get_selected_rows()
        row = rows[-1]
        subindex = model.get_value(model.get_iter(row), 3)
        resource_number = model.get_value(model.get_iter(row), 4)
        if resource_number < 0:
            self.current_resource = None
            self.current_resource_id = 0
            self.current_subindex_id = subindex
            return
        library = self.get_library()
        if not isinstance(library, delv.library.Library):
            error("cursor_changed: failed to get library")
            return
        self.current_subindex_id = subindex
        self.current_resource_id = delv.archive.resid(subindex, resource_number)
        self.current_resource = library.get_resource(self.current_resource_id)

        # for recp in self.subindexchange: recp.signal_subindexchange()
        # for recp in self.resourcechange: recp.signal_resourcechange()

    def get_library(self) -> Optional[delv.library.Library]:
        if self.cfg.debug: print("Document.get_library")
        if not self.library:
            try:
                self.library = delv.library.Library(
                    self.underlay,
                    self.archive
                ) 
            except Exception as e:
                self.error_message(
                    f"Couldn't create library; if you are editing a saved game, you need to underlay a scenario.\nException was: {repr(e)}"
                )
        return self.library

    def menu_open(self, widget: Gtk.Widget, data: Any = None) -> None:
        if self.cfg.debug: print("Document.menu_open")
        fpath = self.ask_open_path(msg = "Select a Delver Archive...")
        if fpath: self.open_file(fpath)

    # open_file loads a file from the filesystem.
    # If the current document is a fresh_document,
    # the data is displayed in the current Document.
    # Otherwise, the data is loaded into a new Document.
    def open_file(self, fpath: str, directory: bool = False) -> None:
        if self.cfg.debug: print("Document.open_file")
        doc = self if self.fresh_document() else Document(
            application=self.application,
            cfg=self.cfg,
            fpath=fpath
        )
        if self.cfg.debug:
            print(f"open_file: reusing fresh document: {self == doc}")
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

    def set_open_directory(self, fpath: str) -> None:
        if self.cfg.debug: print("Document.set_open_directory")
        self.exported_directory = fpath

        # for recp in self.filechange: recp.signal_filechange()
        # for recp in self.subindexchange: recp.signal_subindexchange()
        # for recp in self.resourcechange: recp.signal_resourcechange()

    # An underlay scenario is required to edit a saved game.
    def menu_underlay(self, widget: Gtk.Widget, data: Any = None) -> None:
        if self.cfg.debug: print("Document.menu_underlay")
        fpath = self.ask_open_path("Select a scenario to underlay...")
        if fpath: self.underlay_archive(delv.archive.Scenario(fpath))

    def underlay_archive(self, archive: delv.archive.Archive) -> None:
        if self.cfg.debug: print("Document.underlay_archive")
        self.underlay = archive

    def menu_new(self, widget: Gtk.Widget, data: Any = None) -> None:
        #for recp in self.filechange: recp.signal_filechange()
        #for recp in self.subindexchange: recp.signal_subindexchange()
        #for recp in self.resourcechange: recp.signal_resourcechange()
        doc = Document(
            application=self.application,
            cfg=self.cfg
        )
        doc.present()
        return None

    def ask_open_path(self, msg: str = "Select a file...") -> Optional[str]:
        if self.cfg.debug: print("Document.ask_open_path")
        if self.changed and self.warn_unsaved_changes(): return
        chooser = Gtk.FileChooserDialog(
            title=msg,
            action=Gtk.FileChooserAction.OPEN
        )
        chooser.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        chooser.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        self.add_window(chooser)
        response = chooser.run()
        rv = chooser.get_filename() if response == Gtk.ResponseType.OK else None
        chooser.destroy()
        return rv

    def error_message(self, message: str) -> None:
        if self.cfg.debug: print("Document.error_message")
        dialog = Gtk.MessageDialog(
            parent=self.window, 
            modal=True,
            buttons=Gtk.ButtonsType.OK,
            message_type=Gtk.MessageType.ERROR,
            text=message
        )
        self.add_window(dialog)
        dialog.run()
        dialog.destroy()

documents: list[Document] = []
def max_new_id() -> int:
    return max(doc.new_id for doc in documents)

#!/usr/bin/env python
# Copyright 2015-6 Bryce Schroeder, www.bryce.pw, bryce.schroeder@gmail.com
# 
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# "Cythera" and "Delver" are trademarks of either Glenn Andreas or 
# Ambrosia Software, Inc. 
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gio, Gdk, GdkPixbuf, GObject
import os, sys, tempfile, subprocess, datetime
import json
from . import editgui, aboutbox, document
import delv
import delv.archive, delv.library

version = '0.2.2'
PATCHINFO = """Created with redelv {}, based on the delv library.""".format(version)
DEFAULT_PREFS = {# Command that will play sounds:
                   'play_sound_cmd': 'mplayer %s', 
                   # Enter the command for your hex editor here, e.g. ghex
                   'hex_editor_cmd': 'bless %s',
                   'graphics_editor_cmd': 'gimp -n %s',
                   'audio_editor_cmd': 'audacity %s',
                   'assembly_editor_cmd': 'gedit --standalone %s',

                   # If True, when an external editor edits a file open in
                   # an active editor, propagate those changes immediately
                   # (this generally looks pretty cool, but it may hose your
                   #  unsaved changes if any.)
                   'instant_editor_propagation':True,

                   # This is the info to add to patches produced.
                   'default_patch_info':PATCHINFO,

                   # URL form to retrieve human-checked source code from
                   'source_archive':  
                       'http://www.ferazelhosting.net/wiki/%04X?action=raw',
                   }
PREFS_PATH = os.path.expanduser('~/.redelv')

# class AskNewResourceBox(Gtk.Dialog):
#     def __init__(self,redelv,prompt="Create a new resource:"):
#         self.redelv=redelv
#         GObject.GObject.__init__(self)
#         v = Gtk.Label(label=prompt)
#         self.vbox.pack_start(v, True, True, 0)
#         v.show()
#         self.e = Gtk.Entry(max=6)
#         self.e.set_text("0x%04X"%self.redelv.get_new_resid(self.redelv.current_subindex_id))
#         self.vbox.pack_start(self.e, True, True, 0)
#         self.e.show()
#         #self.resid = 
#         #self.name = 
#         self.add_buttons(Gtk.STOCK_NEW, 1, Gtk.STOCK_CANCEL, 0)
#
#         self.vbox.show()
#     def get_value(self):
#         return int(self.e.get_text().replace('0x',''),16)

class ReDelv(Gtk.Application):
    # def get_new_resid(self, si):
    #     if si == 0: return 0
    #     for r in range(1,254):
    #         if not self.archive.get((si,r)): return ((si+1)<<8)|r
    #     return ((si+1)<<8)

    def load_prefs(self):
        if os.path.exists(PREFS_PATH):
            with open(PREFS_PATH, 'r') as f:
                self.preferences = json.load(f)
            for key in DEFAULT_PREFS.keys():
                if key not in self.preferences:
                    self.preferences[key] = DEFAULT_PREFS[key]
        else:
            self.preferences = DEFAULT_PREFS
            with open(PREFS_PATH, 'w') as f:
                json.dump(self.preferences, f, indent=True)

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            application_id="net.ferazelhosting.redelv",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,#|Gio.ApplicationFlags.HANDLES_OPEN,
            **kwargs
        )
        self.load_prefs()
        # self.base_archive=None
        # self.patch_base=None
        # self.library = None
        # self.underlay = None
        # self.patch_output_path=None
        # self.hex_editors_open = {}
        # self.queued_changes = []
        # self.tempfile_references = {}
        # self.timeout_sid = None
        # # Signals 
        # self.open_editors = {}
        # self.filechange = []
        # self.subindexchange = []
        # self.resourcechange = []
        # self.archive = None
        # self.library = None
        # #GObject.type_register(editgui.Receiver)
        # #GObject.signal_new("filechange", editgui.Receiver, 
        # #    GObject.SignalFlags.RUN_FIRST, None, ())
        # # Windows and globals
        # self._unsaved: bool = False
        # self.opened_file = None
        # self.exported_directory = None
        # self.current_resource = None
        # self.current_resource_id = 0
        # self.current_subindex_id = 0
        self.aboutbox: None | Gtk.AboutDialog = None
        # self.file_metadata_window = None
        # self.file_get_info_window = None
        self.config: dict[str, str] = {
            "debug": "y",
        }
        self.documents: list = []
        self.add_main_option(
            "debug",
                ord("d"),
                GLib.OptionFlags.NONE,
                GLib.OptionArg.NONE,
                "Debug",
                None,
        )

    def do_startup(self) -> None:
        if "debug" in self.config: print("ReDelv.do_startup")
        Gtk.Application.do_startup(self)
        # Prep the actions for the menu
        app_actions = {
            "menu-quit": self.menu_quit,
            "menu-about": self.menu_about,
        }
        for name, callback in app_actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        # self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        # Setup the menus
        if "debug" in self.config: print("make the menu")
        menu_xml_path = os.path.join(os.path.dirname(__file__), 'menubar.ui')
        builder = Gtk.Builder.new_from_file(menu_xml_path)
        # The app menu bears the name of the program.
        app_menu = builder.get_object("app-menu")
        if isinstance(app_menu, Gio.MenuModel):
            self.set_app_menu(app_menu)
        else:
            raise TypeError("expected #app-menu to be a MenuModel")
        # The menubar appears after the app menu.
        menubar = builder.get_object("menubar")
        if isinstance(menubar, Gio.MenuModel):
            self.set_menubar(menubar)
        else:
            raise TypeError("expected #menubar to be a MenuModel")

    def do_command_line(self, command_line) -> int:
        options = command_line.get_options_dict().end().unpack()
        if "debug" in options:
            del self.config["debug"]
        else:
            print("Debug mode")
        self.activate()
        return 0

    # def do_open(self, files, hint) -> None:
    #     if "debug" in self.config: print("ReDelv.do_open")
    #     if len(files) > 0: self.open_file(files[0])
    #     if len(files) > 1: self.underlay_archive(
    #         delv.archive.Scenario(files[1]))

    def do_activate(self) -> None:
        if "debug" in self.config: print("ReDelv.do_activate")
        if len(document.documents) == 0:
            document.Document(
                application=self,
                config=self.config
            )
        document.documents[-1].present()
            # self.window.connect("delete_event", self.delete_event)
            # self.window.connect("destroy", self.on_quit)
            # accel = Gtk.AccelGroup()
            # ifc = Gtk.ItemFactory(Gtk.MenuBar, "<main>", accel)
            # self.window.add_accel_group(accel)
            # ifc.create_items(menu_items)
            # self.menu_bar = ifc.get_widget("<main>")
            # self.mvbox.pack_start(self.menu_bar, False, True, 0)

            # # Make the data tree
            # if "debug" in self.config: print("make the data tree")
            # self.data_view = Gtk.TreeView()
            # dc1 = Gtk.TreeViewColumn()
            # dc1.set_title("Subindex") # Would it be so much to ask for this to be
            # # in the constructor...
            # dc2 = Gtk.TreeViewColumn()
            # dc2.set_title("Size")
            # dc3 = Gtk.TreeViewColumn()
            # dc3.set_title("Description")
            #
            # # Seriously it's like GUI programming is designed to be as clunky
            # # and non-functional as possible in the quest for generality
            # # Why is there no truly native python gui kit? It's the most popular
            # # language in the world now...
            # # Aren't we ready to move beyond the state machine model for building
            # # GUI stuff???
            # # and why are all the RAD tools broken?! They could at least plaster
            # # over this cruft...
            # c =Gtk.CellRendererText();dc1.pack_start(c,True);
            # dc1.add_attribute(c,"text",0)
            # c =Gtk.CellRendererText();dc2.pack_start(c,True);
            # dc2.add_attribute(c,"text",1)
            # c =Gtk.CellRendererText();dc3.pack_start(c,True);
            # dc3.add_attribute(c,"text",2)         
            # self.data_view.append_column(dc1)
            # self.data_view.append_column(dc2)
            # self.data_view.append_column(dc3)
            #
            # self.tree_data = Gtk.TreeStore(str,str,str,int,int)
            # self.data_view.set_model(self.tree_data)
            #
            # sw = Gtk.ScrolledWindow()
            # sw.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
            # sw.add(self.data_view)
            # self.mvbox.pack_start(sw, True, True, 0)
            #
            # self.data_view.connect("cursor-changed", self.cursor_changed)
            # self.data_view.connect("row-activated", self.row_activated)
            # self.window.show_all()

    def on_quit(self, action, param) -> None:
        if "debug" in self.config: print("ReDelv.on_quit")
        self.quit()

    def menu_quit(self, action, param) -> None:
        if "debug" in self.config: print("ReDelv.menu_quit")
        for doc in self.documents:
            if doc.delete_event():
                return
        self.on_quit(action, param)

    # Saving
    # def is_unsaved(self):
    #     return self._unsaved
    # def set_savedstate(self, v):
    #     if v: self.set_saved()
    #     else: self.set_unsaved()
    # def ask_open_path(self,msg="Select a file..."):
    #     if self.is_unsaved() and self.warn_unsaved_changes(): return
    #     chooser = Gtk.FileChooserDialog(title=msg,
    #               action=Gtk.FileChooserAction.OPEN,
    #               buttons=(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,
    #                        Gtk.STOCK_OPEN,Gtk.ResponseType.OK))
    #     response = chooser.run()
    #     if response == Gtk.ResponseType.OK:
    #         rv= chooser.get_filename()
    #     else: rv= None
    #     chooser.destroy()
    #     return rv
    #
    # # Underlay
    # def menu_underlay(self, *argv):
    #     path = self.ask_open_path("Select a scenario to underlay...")
    #     if not path: return
    #     self.underlay_archive(delv.archive.Scenario(path))
    # def underlay_archive(self, archive):
    #     if "debug" in self.config: print("ReDelv.underlay_archive")
    #     self.underlay = archive

    # def refresh_tree(self): 
    #     "Change the tree to reflect current data."
    #     print("WARNING: TreeView may be out of date.")
    #     return

    # Callbacks
    # def row_activated(self, w, path, *argv):
    #     self.cursor_changed(w)
    #     if self.current_resource: self.menu_resource_editor(None)
    #     elif self.data_view.row_expanded(path): 
    #         self.data_view.collapse_row(path)
    #     else:
    #         self.data_view.expand_row(path,False)
    # def cursor_changed(self, w, d=None):
    #     tm,crow = self.data_view.get_selection().get_selected_rows()
    #     crow = crow[-1]
    #     si = tm.get_value(tm.get_iter(crow), 3)
    #     rn = tm.get_value(tm.get_iter(crow), 4)
    #     if rn < 0:
    #         self.current_resource = None
    #         self.current_resource_id = 0
    #     else:
    #         self.current_resource_id = delv.archive.resid(si,rn)
    #         self.current_resource = self.get_library().get_resource(
    #             self.current_resource_id)
    #     self.current_subindex_id = si
    #
    #     for recp in self.subindexchange: recp.signal_subindexchange()
    #     for recp in self.resourcechange: recp.signal_resourcechange()
    #
    # def menu_new(self, widget, data=None):
    #     #for recp in self.filechange: recp.signal_filechange()
    #     #for recp in self.subindexchange: recp.signal_subindexchange()
    #     #for recp in self.resourcechange: recp.signal_resourcechange()
    #     return None
    # def menu_open(self, widget, data=None) -> None:
    #     chooser = Gtk.FileChooserDialog(
    #         title="Select a Delver Archive...",
    #         action=Gtk.FileChooserAction.OPEN,
    #     )
    #     chooser.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    #     chooser.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
    #     response = chooser.run()
    #     if response == Gtk.ResponseType.OK:
    #         self.open_file(chooser.get_filename())
    #     chooser.destroy()
        #t = self.temporary_data.append(None, ["131","42 Items", "Image Data"])
        #self.temporary_data.append(t, ["8E31","12 kB","Something"])
    # def menu_save_copy(self, widget, data=None):
    #     if not self.archive: 
    #         self.error_message("There is nothing to save.")
    #         return
    #     rv = self.ask_save_path()
    #     if not rv: return
    #     try:
    #         buf = self.archive.to_string()
    #         of = open(rv, 'wb')
    #         of.write(buf)
    #         of.close()
    #     except Exception as e:
    #         self.error_message("Unable to write '%s': %s"%(
    #             os.path.basename(self.opened_file), repr(e)))
    #         return
    # def menu_save_as(self, widget, data=None):
    #     if "debug" in self.config: print("ReDelv.menu_save_as")
    #     if not self.archive: 
    #         self.error_message("There is nothing to save.")
    #         return
    #     rv = self.ask_save_path()
    #     if not rv: return
    #     self.opened_file = rv
    #     try:
    #         # The string is a buffer so we can overwrite in place.
    #         buf = self.archive.to_string()
    #         of = open(self.opened_file, 'wb')
    #         of.write(buf)
    #         of.close()
    #         self.set_saved()
    #     except Exception as e:
    #         self.error_message("Unable to write '%s': %s"%(
    #             os.path.basename(self.opened_file), repr(e)))
    #         return
    #     self.set_open_file(rv)
    # def menu_save(self, widget, data=None):
    #     if "debug" in self.config: print("ReDelv.menu_save")
    #     if not self.archive: 
    #         self.error_message("There is nothing to save.")
    #         return
    #     if not self.opened_file: self.opened_file = self.ask_save_path()
    #     if not self.opened_file: return
    #     try:
    #         # The string is a buffer so we can overwrite in place.
    #         buf = self.archive.to_string()
    #         of = open(self.opened_file, 'wb')
    #         of.write(buf)
    #         of.close()
    #         self.set_saved()
    #         if "debug" in self.config: print("Saved.")
    #     except Exception as e:
    #         self.error_message("Unable to write '%s': %s"%(
    #             os.path.basename(self.opened_file), repr(e)))
    #         return
    # def menu_export(self, widget, data=None):
    #     if not self.archive: 
    #         self.error_message("There is nothing to export.")
    #         return
    #     if not self.exported_directory: 
    #          self.exported_directory = self.ask_dir_path()
    #     if not self.exported_directory: return
    #     try:
    #         # The string is a buffer so we can overwrite in place.
    #         self.archive.to_path(self.exported_directory)
    #         self.set_saved()
    #     except Exception as e:
    #         self.error_message("Unable to export to '%s': %s"%(
    #             self.exported_directory, repr(e)))
    #         return
    # def menu_export_as(self, widget, data=None):
    #     self.exported_directory = self.ask_dir_path()
    #     if not self.exported_directory: return
    #     try:
    #         # The string is a buffer so we can overwrite in place.
    #         self.archive.to_path(self.exported_directory)
    #         self.set_saved()
    #     except Exception as e:
    #         self.error_message("Unable to export to '%s': %s"%(
    #             self.exported_directory, repr(e)))
    #         return
    # def menu_import(self, widget, data=None):
    #     if self.is_unsaved() and self.warn_unsaved_changes(): return
    #     self.exported_directory = self.ask_dir_path(Gtk.STOCK_OPEN)
    #     if not self.exported_directory: return
    #     try:
    #         # The string is a buffer so we can overwrite in place.
    #         self.open_file(self.exported_directory)
    #         self.set_saved()
    #     except Exception as e:
    #         self.error_message("Unable to export to '%s': %s"%(
    #             self.exported_directory, repr(e)))
    #         return
    #     for recp in self.filechange: recp.signal_filechange()
    #     for recp in self.subindexchange: recp.signal_subindexchange()
    #     for recp in self.resourcechange: recp.signal_resourcechange()
    #
    def menu_about(self, widget, data=None):
        if not self.aboutbox:
            self.aboutbox = aboutbox.AboutBox(version=version)
        self.aboutbox.show_all()
    # def menu_get_info(self, widget, data=None):
    #     if not self.file_get_info_window:
    #          self.file_get_info_window = editgui.FileInfo(
    #              self, Gtk.WindowType.TOPLEVEL)
    #     self.file_get_info_window.show_all()
    # def menu_file_metadata(self, widget, data=None):
    #     if not self.file_metadata_window:
    #          self.file_metadata_window = editgui.FileMetadata(
    #              self, Gtk.WindowType.TOPLEVEL)
    #     self.file_metadata_window.show_all()
    # def menu_create_index(self, widget, data=None):
    #     return None
    # def menu_delete(self, widget, data=None):
    #     print("Delete")
    #     return None
    # def menu_duplicate(self, widget, data=None):
    #     if not self.current_resource_id: return
    #     askbox = AskNewResourceBox(self, 
    #         "Copy resource %04X to new ID:"%self.current_resource_id)
    #     #self.window.emit("filechange")
    #     choice = askbox.run() 
    #     new_resid = askbox.get_value()
    #     askbox.destroy()
    #     if not choice: return None
    #     data = self.archive.get(self.current_resource_id).get_data()
    #
    #     res = self.archive.get(new_resid, create_new=True)
    #     res.set_data(data)
    #     self.tree_data.clear()
    #     self.archive.add_gui_tree()
    #     self.set_unsaved()
    #
    #
    # def menu_create_resource(self, widget, data=None):
    #     askbox = AskNewResourceBox(self)
    #     #self.window.emit("filechange")
    #     choice = askbox.run() 
    #     new_resid = askbox.get_value()
    #     askbox.destroy()
    #
    #     if not choice: return None
    #
    #     res = self.archive.get(new_resid, create_new=True)
    #     res.set_data('\x00')
    #     self.tree_data.clear()
    #     self.archive.add_gui_tree()
    #     print("New resource", choice, new_resid, res)
    #     self.set_unsaved()
    #     return None
    # def menu_export_resource(self, widget, data=None):
    #     return None
    # def menu_import_resource(self, widget, data=None):
    #     return None
    # def menu_cut(self, widget, data=None):
    #     return None
    # def menu_copy(self, widget, data=None):
    #     if self.current_resource:
    #         self.clipboard.set_text("Resource:%04X"%(self.current_resource_id))
    #     else:
    #         self.clipboard.set_text("Subindex:%d"%(self.current_subindex_id))
    # def menu_paste(self, widget, data=None):
    #     return None
    # def menu_select_base(self, widget, data=None):
    #     patch_base = self.ask_open_path(
    #         "Select patch basis (Unmodified scenario)")
    #     if not patch_base: return
    #     try:
    #         self.base_archive = delv.archive.Scenario(patch_base)
    #     except Exception as e:
    #         self.error_message("'%s' doesn't seem to be a valid archive: %s"%(
    #             os.path.basename(path), repr(e)))
    #         return
    #     self.patch_base = patch_base
    #
    # def menu_save_patch(self, widget, data=None):
    #     if not self.base_archive:
    #         self.error_message(
    #             "No patch basis is set. Select one using Patch:Select Base.")
    #         return
    #     if not self.archive:
    #         self.error_message(
    #             "Nothing open. Do File:Open to open a modified scenario file.")
    #         return
    #     if not self.patch_output_path: 
    #         self.patch_output_path = self.ask_save_path("Untitled Patch")
    #     if not self.patch_output_path: return
    #     newpatch = delv.archive.Patch()
    #     newpatch.patch_info(self.preferences['default_patch_info'])
    #     newpatch.diff(self.base_archive, self.archive)
    #     newpatch.to_path(self.patch_output_path)
    #     resource_count = len(newpatch.resources())
    #     print("Saved patch with {} resources".format(resource_count))
    #
    # def menu_save_patch_as(self, widget, data=None):
    #     patch_output_path = self.ask_save_path("Untitled Patch")
    #     if not patch_output_path: return
    #     self.patch_output_path = patch_output_path
    #     self.menu_save_patch(self, widget, data)
    # def menu_apply(self, widget, data=None):
    #     patch_path = self.ask_open_path("Select a Magpie or mag.py patch")
    #     if not patch_path: return
    #     try: 
    #         patch = delv.archive.Patch(patch_path)
    #     except Exception as e:
    #         self.error_message("'%s' doesn't seem to be a valid archive: %s"%(
    #             os.path.basename(patch_path), repr(e)))
    #         return
    #     if not patch.get(0xFFFF): 
    #         self.error_message("That archive contains no patch resource.")
    #         return
    #     patch.patch(self.archive)
    #     self.set_unsaved()
    #     self.refresh_tree()
    #
    #     delv.archive.Patch(patch_path)
    # def specific_ed(self, which="Hex"):
    #     if "debug" in self.config: print("ReDelv.specific_ed(%s)"%which)
    #     if self.current_resource:
    #         editgui.editor_for_name(which)(
    #             self, self.current_resource,canonical=False).show_all()
    #     else:
    #         self.error_message("No resource is selected.")
    # def open_editor(self, resid):
    #     ed = editgui.editor_for_resource(resid)(
    #             self,self.get_library().get_resource(resid))
    #     ed.show_all()
    #     return ed
    # def menu_resource_editor(self, widget, data=None):
    #     if self.current_resource:
    #         #editgui.editor_for_subindex(self.current_subindex_id)(
    #         #    self, self.current_resource).show_all()
    #         editgui.editor_for_resource(self.current_resource.resid)(
    #             self,self.current_resource).show_all()
    #     else:
    #         self.error_message("No resource is selected.")
    # #def menu_image_editor(self, *argv):
    #
    # def menu_hex_editor(self, widget, data=None):
    #     if not self.current_resource:
    #         self.error_message("No resource is selected.")
    #         return
    #     if self.current_resource_id in self.hex_editors_open:
    #         self.error_message(
    #             "Close the existing external editor for resid %04X first."%(
    #                  self.current_resource_id))
    #         return
    #
    #     print("Using external hex editor", self.preferences['hex_editor_cmd'])
    #     temp = tempfile.NamedTemporaryFile('w+b',
    #         prefix="redelv",
    #         suffix="resid%04X"%self.current_resource_id)
    #     temp.write(self.get_library().get_resource(
    #         self.current_resource_id).get_data())
    #     temp.flush()
    #     command = self.preferences['hex_editor_cmd']%temp.name
    #     self.tempfile_references[self.current_resource_id] = temp
    #     p=subprocess.Popen(command, shell=True)
    #     mtime = os.path.getmtime(temp.name)
    #     self.hex_editors_open[self.current_resource_id] = (p,temp,mtime)
    #     # turns out bless is a replacer rather than an overwriter...
    #     if self.timeout_sid is None:
    #         self.timeout_sid = GObject.timeout_add(300, self.file_mon_timer)
    #     #gfile =  Gio.File.new_for_path(temp.name)
    #     #monitor =gfile.monitor_file(
    #     #    Gio.FileMonitorFlags.NONE, None)
    #     #monitor = gfile.monitor_file()
    #     #monitor.connect("changed", self.hex_editor_changed, 
    #     #    (self.current_resource, temp,gfile))
    #     #self.specific_ed("Hex")
    # def file_mon_timer(self):
    #     if "debug" in self.config: print("ReDelv.file_mon_timer")
    #     if not self.hex_editors_open:
    #         self.timeout_sid = None
    #         return False
    #     terminated = []
    #     for res,tfile in self.queued_changes:
    #         print("implemented queued change to", res.resid)
    #         tfile = open(tfile.name,'r+b')
    #         res.set_data(tfile.read())
    #         self.get_library().purge_cache(res.resid)
    #         if res.resid in self.hex_editors_open:
    #             process, oldfile, mtime = self.hex_editors_open[res.resid]
    #             self.hex_editors_open[res.resid] = (process, tfile, 
    #                 os.path.getmtime(tfile.name))
    #         if self.preferences['instant_editor_propagation']:
    #              # just be lazy, it's late
    #              if res.resid in self.open_editors:
    #                  for editor in self.open_editors[res.resid]:
    #                      editor.revert()
    #     self.queued_changes = []
    #     for rid, (process, tempf, mtime) in self.hex_editors_open.items():
    #         if process.poll() is not None:
    #             terminated.append(rid)
    #             print("finished watching external editor for ", rid)
    #             continue
    #         new_mtime = os.path.getmtime(tempf.name)
    #         if new_mtime != mtime:
    #             self.set_unsaved()
    #             print("external editor changed file", rid, mtime, new_mtime)
    #             self.queued_changes.append((
    #                  self.get_library().get_resource(rid), tempf))
    #             self.hex_editors_open[rid] = (process, tempf, new_mtime)
    #     for rid in terminated: 
    #         del self.hex_editors_open[rid]
    #         del self.tempfile_references[rid]
    #     return True
    #
    # def signal_resource_saved(self, resid):
    #     if "debug" in self.config: print("ReDelv.signal_resource_saved")
    #     if resid not in self.hex_editors_open:
    #         return
    #     print("Sending changes to an external editor for", resid)
    #     process, tempf, mtime = self.hex_editors_open[resid]
    #     tempf.seek(0)
    #     tempf.write(self.library.get_resource(resid).get_data())
    #     tempf.flush()
    #     self.hex_editors_open[resid] = (
    #         process, tempf, os.path.getmtime(tempf.name))
    # def menu_image_browser(self, widget, data=None):
    #     return None
    #
    # def menu_check_compatibility(self,widget,data=None):
    #     if not self.archive or not self.archive.get(0xFFFF):
    #         self.error_message("No patch is open; open one with File:Open.")
    #         return
    #     #other_patches = self.ask_multiple_files("Select one or more patches:")
    #     #if not other_patches: return
    #     #try:
    #     #    patches = [delv.archive.Patch(path) for path in other_patches]
    #     other_patch = self.ask_open_path("Select another patch:")
    #     if not other_patch: return
    #     try:
    #         patch = delv.archive.Patch(other_patch)
    #     except:
    #         self.error_message("Couldn't open that as a Delver Archive.")
    #         return
    #     if not patch.get(0xFFFF):
    #         self.error_message("That archive does not appear to be a patch.")
    #         return
    #     if patch.compatible(self.archive):
    #         self.info_message(
    #             "That patch appears to be compatible with the open patch.")
    #     else:
    #         self.info_message(
    #             "Incompatible: applying both patches may result in errors.")
    #
    #
    # # stub
    # def menu_(self, widget, data=None):
    #     return None

    #  # helpers
    # def error_message(self, message):
    #     if "debug" in self.config: print("ReDelv.error_message")
    #     dialog = Gtk.MessageDialog(self.window, 
    #         Gtk.DialogFlags.MODAL , 
    #         Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
    #         message)
    #     dialog.run()
    #     dialog.destroy()
    # def info_message(self, message):
    #     if "debug" in self.config: print("ReDelv.info_message")
    #     dialog = Gtk.MessageDialog(self.window, 
    #         Gtk.DialogFlags.MODAL , 
    #         Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
    #         message)
    #     dialog.run()
    #     dialog.destroy()
    # def ask_dir_path(self,button=Gtk.STOCK_SAVE):
    #     if "debug" in self.config: print("ReDelv.ask_dir_path")
    #     chooser = Gtk.FileChooserDialog(
    #               title="Select import/export directory...",
    #               action=Gtk.FileChooserAction.SELECT_FOLDER,
    #               buttons=(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,
    #                        button,Gtk.ResponseType.OK))
    #     response = chooser.run()
    #     if response == Gtk.ResponseType.OK:
    #         rv =chooser.get_filename()
    #     else:
    #         rv = None
    #     chooser.destroy()
    #     return rv
    # def ask_save_path(self, cname="Untitled Scenario"):
    #     if "debug" in self.config: print("ReDelv.ask_save_path")
    #     chooser = Gtk.FileChooserDialog(title="Select destination...",
    #               action=Gtk.FileChooserAction.SAVE,
    #               buttons=(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,
    #                        Gtk.STOCK_SAVE,Gtk.ResponseType.OK))
    #     chooser.set_current_name(cname)
    #     response = chooser.run()
    #     if response == Gtk.ResponseType.OK:
    #         rv =chooser.get_filename()
    #     else:
    #         rv = None
    #     chooser.destroy()
    #     return rv
    #
    # def send_resourcechange(self):
    #     if "debug" in self.config: print("ReDelv.send_resourcechange")
    #     for recp in self.resourcechange: recp.signal_resourcechange()
    # def get_library(self):
    #     if "debug" in self.config: print("ReDelv.get_library")
    #     try:
    #         if not self.library:
    #             self.library=delv.library.Library(self.underlay,self.archive) 
    #     except Exception as e:
    #         self.error_message(MSG_NO_UNDERLAY%repr(e))
    #     return self.library
    # def register_editor(self, editor):
    #     if "debug" in self.config: print("ReDelv.register_editor")
    #     if editor.res.resid not in self.open_editors:
    #         self.open_editors[editor.res.resid] = []
    #     self.open_editors[editor.res.resid].append(editor)
    # def unregister_editor(self, editor):
    #     if "debug" in self.config: print("ReDelv.unregister_editor")
    #     self.open_editors[editor.res.resid].remove(editor)
    # def get_registered_editors(self, resid):
    #     if "debug" in self.config: print("ReDelv.get_registered_editors")
    #     return self.open_editors.get(resid, [])

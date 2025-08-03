#!/usr/bin/env python
# Copyright 2014-2015 Bryce Schroeder, www.bryce.pw, bryce.schroeder@gmail.com
# Wiki: http://www.ferazelhosting.net/wiki/delv
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
# Please do not make trouble for me or the Technical Documentation Project by
# using this software to create versions of the "Cythera Data" file which
# have bypassed registration checks.
# Also, remember that the "Cythera Data" file is copyrighted by Ambrosia and
# /or Glenn Andreas, and publishing modified versions without their permission
# would violate that copyright.
#
# "Cythera" and "Delver" are trademarks of either Glenn Andreas or
# Ambrosia Software, Inc.

# from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import os
#import numpy as np
import operator
import json, string
from io import BytesIO, BufferedReader, BufferedWriter
from typing import Dict, Iterator, Optional
from . import util
from .hints import _RES_HINTS, _SCEN_HINTS

def decrypt(data: bytearray, prokey: int) -> bytearray:
    """Decrypt the data provided with the given pro-key. The prokey is
       used to generate the seed value and parameters for the
       pseudorandom number generator that is used to create the key."""
    cleartext = bytearray(len(data))
    key = prokey ^ (prokey>>8)
    m = ((prokey & 0x3f) <<2) + 1
    b = prokey >> 6

    for i in range(len(data)):
        key = (key*m + b) & 0xFFFF
        cleartext[i] = (data[i]^key)&0xFF

    return cleartext

encrypt = decrypt # Symmetric.

def entropy(data: bytearray) -> float:
    """Return a statistical measure of the entropy of the given data.
       Encrypted (or compressed) data has high entropy. Note that this is
       not infallable and if the cleartext has very high entropy, e.g. in
       the case of compressed data, it may not be able to distinguish
       a successful decryption, at least in principle."""
    counts = [0.0]*256
    #counts = np.zeros(256) # Uncomment for faster entropy calculations
    # in exchange for a numpy dependency
    for c in data: counts[c] += 1
    base = len(data)/256.0
    for i in range(256):
         counts[i] -= base
         counts[i] *= counts[i]
    #counts -= len(data)/256.0
    #counts *= counts
    #return 1 - ((counts.sum()**0.5)/len(data))
    return 1 - sum(counts)**0.5/len(data)

class ResourceFile(util.DelvReader):
    """Implements a simple file-like interface for resources,
       with the binary utility functions of DelvReader."""
    def __init__(
        self,
        resource: 'Resource',
        trans_offset: int = 0,
        length_limit: Optional[int] = None
    ) -> None:
        self.resource: Resource = resource
        self.trans_offset: int = trans_offset
        self.position: int = trans_offset
        self.length_limit: int = len(self.resource) if length_limit is None else (
            length_limit)
        self.name: str = repr(self)

    def __len__(self) -> int:
        return self.length_limit-self.trans_offset

    def __repr__(self) -> str:
        return '<ResourceFile from %s. P=%d T=%d L=%s>'%(repr(self.resource),
            self.position, self.trans_offset, self.length_limit)

    def tell(self) -> int:
        return self.position - self.trans_offset

    def res_tell(self) -> int:
        "Give position in the underlying resource."
        return self.position

    def get_res(self) -> 'Resource':
        return self.resource

    def seek(self, offset: int, whence: int = 0) -> None:
        offset += self.trans_offset
        if whence == 2: # Who uses this?
            self.position = self.length_limit - offset
        elif whence == 1:
            self.position += offset
        elif whence == 0:
            self.position = offset
        else:
            assert False, "seek: illegal whence: %d"%whence
        if self.position > self.length_limit:
            raise IndexError(
                "seek: position exceeds length_limit; offset 0x%08X, size 0x%08X"%(
                offset, len(self)))

    def eof(self) -> bool:
        return self.position >= self.length_limit

    def truncate(self, size: Optional[int] = None) -> int:
        assert not self.trans_offset
        if size is None: size = self.position
        self.resource.data = self.resource.data[:size]
        self.resource.dirty = True
        return size

    def readb(self, length: Optional[int] = None) -> bytearray:
        if not self.length_limit: return bytearray([])
        if self.position >= self.length_limit: assert False
        if length is None:
            rv = self.resource.data[self.position:self.length_limit]
            self.position = self.length_limit
        else:
            rv = self.resource.data[self.position:self.position+length]
            self.position += length
        return rv

    def read(self, length: Optional[int] = None) -> bytes:
        return bytes(self.readb(length))

    def write(self, string: bytes) -> None:
        self.resource.data[self.position:self.position+len(string)] = string
        self.resource.dirty = True
        self.position += len(string)

class Resource(object):
    """A Resource is an individual object in an Archive."""
    def __init__(
        self,
        offset: int,
        size: int,
        archive: 'Archive',
        subindex: int = 0,
        n: int = 0,
    ) -> None:
        self.offset: int = offset # 0 if never been on disk
        self.data: bytearray = bytearray(size) # Data in memory
        self.resid: int = resid(subindex,n)
        self.loaded: bool = not offset
        self.dirty: bool = True
        self.encrypted: Optional[bool] = False if self.loaded else None
        self.canon_encryption: Optional[bool] = self.encrypted
        # Multiple archives may be open.
        self.archive: Archive = archive
        # Only needed for debugging and decryption.
        self.subindex: int = subindex
        self.n: int = n

    def get_offset_file(
        self,
        offset: int,
        length: Optional[int] = None
    ) -> ResourceFile:
        if not self.loaded: self.load()
        if length is None:
            return ResourceFile(self, trans_offset=offset)
        else:
            return ResourceFile(self, trans_offset=offset,
                length_limit=offset+length)

    def get_dref(self, mdref: util.dref) -> ResourceFile:
        if not self.loaded: self.load()
        if mdref.length is None:
            return ResourceFile(self, trans_offset=mdref.offset)
        else:
            return ResourceFile(self, trans_offset=mdref.offset,
                length_limit=mdref.offset+mdref.length)

    def preview(self) -> str:
        """Generate a human-readable preview."""
        d = [
            s for s in map(chr, self.get_data())
            if s in string.printable and s not in string.whitespace
        ][:20]
        return repr(''.join(d))

    def human_readable_size(self) -> str:
        lend = len(self.data)
        if lend < 9999: return "%d B"%lend
        elif lend < 1e6: return "%.2f kB"%(lend/1000.0)
        else: return "%.2f MB"%(lend/1e6)

    def as_file(self) -> ResourceFile:
        """Return a file-like object representation of the resource.
           If you write to the object, it will indeed change the contents
           of the resource, but in all cases you need to explicitly write
           out the Archive to save changes to disk. It defines read,
           seek, tell, and the various binary helper methods found in
           util.DelvReader."""
        if not self.loaded:self.load()
        return ResourceFile(self)

    def __getitem__(self, n: int):
        """Return the nth byte of the resource."""
        if not self.loaded: self.load()
        return self.data[n]

    def __setitem__(self, n: int, v: int) -> None:
        """Set the nth byte of the resource to v."""
        if not self.loaded: self.load()
        self.dirty = True
        self.data[n] = v

    def set_data(self, data: bytes) -> None:
        """Replace the data of this resource."""
        self.dirty = True
        self.loaded = True
        self.data = bytearray(data)

    def get_data(self):
        """Return the data of this resource as a mutable bytearray.
           If you alter the bytearray, you must manually set .dirty to True."""
        if not self.loaded: self.load()
        return self.data

    def __repr__(self) -> str:
        return "<Resource %04X>"%resid(self.subindex,self.n)

    def __str__(self) -> str:
        """Return a string of the Resource's contents."""
        if not self.loaded: self.load()
        return str(self.data)

    def __len__(self) -> int:
        "Returns the size of the resource data."
        return len(self.data)

    def hint_encryption(self, encrypted, canon_encryption: Optional[bool] = None) -> None:
        self.encrypted = encrypted
        self.canon_encryption = canon_encryption if (
            canon_encryption is not None) else self.encrypted

    def is_encrypted(self):
        """Returns True if this resource is encrypted _in the medium
           it was loaded from_."""
        if self.encrypted is None: self.load()
        return self.encrypted

    def canonically_encrypted(self):
        """Returns True if this resource is encrypted in the single-file
           archive. If this Resource came from a Delver Archive loaded
           from a file (or created de novo), this function returns the
           same value as is_encrypted(). However, if we are dealing with
           an archive loaded from a directory that was dumped from an Archive,
           then this returns the original encryption state from that archive.
           (Recall that all resources are saved unencrypted when saving to
           a directory.)"""
        hint = self.archive.canon_encryption_of(self.subindex, self.resid)
        if hint is not None:
            self.canon_encryption = hint
            return hint
        if self.canon_encryption is None: self.load()
        return self.canon_encryption

    # Private methods
    def write(self, dest: util.DelvWriter) -> None:
        new_offset = dest.tell()
        if not self.loaded:
            self.load()
            #dest.seek(new_offset)
        self.offset = new_offset
        if self.canon_encryption is True:
            dest.write(encrypt(self.data, resid(self.subindex, self.n)))
        elif self.canon_encryption is False:
            dest.write(self.data)
        else:
            assert False,"write %s: undefined encryption status"%repr(self)

    def get_metadata(self) -> Optional[bool]:
        return self.canon_encryption

    def write_index(self, dest: util.DelvWriter) -> None:
        dest.write_offlen(self.offset, len(self.data))

    def save_to_file(self, dest: BufferedWriter) -> None:
        """Saves a resource to an individual file. Never encrypted."""
        if not self.loaded: self.load()
        dest.seek(0)
        dest.write(self.data)
        self.dirty = False

    def load_from_file(self, src: BufferedReader) -> None:
        self.data = bytearray(src.read())
        self.loaded = True
        self.encrypted = False
        self.canon_encryption = self.archive.canon_encryption_of(self.subindex,self.resid)

    def load(self) -> None:
        assert self.archive.arcfile, "load: archive has no arcfile"
        fpos = self.archive.arcfile.tell()
        self.archive.arcfile.seek(self.offset)
        self.data = bytearray(self.archive.arcfile.read(len(self.data)))
        self.loaded=True
        self.archive.arcfile.seek(fpos)
        if self.encrypted is None:
            self.encrypted = self.archive.canon_encryption_of(self.subindex, self.resid)
            if self.canon_encryption is None:
                self.canon_encryption = self.encrypted
        if self.encrypted is None:
            self.decrypt_if_required()
        elif self.encrypted is True:
            self.data = decrypt(self.data, resid(self.subindex,self.n))

    def decrypt_if_required(self) -> None:
        print("Decrypt if required", repr(self), self.archive)
        presumptive = decrypt(self.data, resid(self.subindex, self.n))
        if entropy(self.data) > entropy(presumptive):
            self.encrypted = True
            self.canon_encryption = True
            self.data = presumptive
        else:
            self.encrypted = False
            self.canon_encryption = False

class Archive(object):
    """Class for representing Delver Archives. The implementation is
       eager; the entire file is loaded into memory when it is opened."""
    known_encrypted: list[int] = []
    single_known: Dict[int, bool] = {}
    known_clear: list[int] = []
    source_string: str
    master_index: list[tuple[int, int]]
    def __init__(
        self,
        src: Optional[str|BufferedReader|BytesIO] = None,
        archive_type: str = 'scenario',
        gui_treestore = None
    ):
        """If src is None, then the constructor creates a new empty archive.
           If src is a file-like object, it will read in an archive from
           that file. If src is a string, it will attempt to open it as
           a file read-only."""
        self.gui_treestore=gui_treestore
        self.player_name: str = ''
        self.encryption_knowledge: Dict[int, bool] = {}
        for si in self.known_encrypted: self.encryption_knowledge[si] = True
        for si in self.known_clear: self.encryption_knowledge[si] = False

        if src is None:
            self.arcfile = None
            self.source_string = 'Created de novo by delv'
            self.create_header()
            self.create_index()
        elif isinstance(src, BufferedReader) or isinstance(src, BytesIO):
            self.from_file(src)
        else: # type(src) is str:
            if os.path.isfile(src):
                with open(src, 'rb') as f:
                    self.from_file(f)
            elif os.path.isdir(src):
                self.from_directory(src)
            else:
                assert False, "'%s' isn't a directory or file."%src

    def from_directory(self, path: str) -> None:
        """Load a delver archive from the provided path."""
        with open(os.path.join(path, "metadata.json"), 'r') as f:
            metadata = json.load(f)
        self.source_string = metadata['source']+' (From directory %s)'%path
        encrypt = metadata['should_encrypt']
        self.create_header()
        self.create_index()
        self.scenario_title = metadata['scenario_title']
        self.player_name = metadata['player_name']
        for rid, canon_e in encrypt.items():
            rid = int(rid, 16)
            subindex, ri = indices(rid)
            nres = Resource(0, 0, self, subindex, ri)
            with open(os.path.join(path, '%04X.data'%rid), 'rb') as dfile:
                nres.load_from_file(dfile)
            nres.hint_encryption(False, canon_e)
            self[rid] = nres

        self.source_string = 'Packed from %s'%path
        if self.gui_treestore: self.add_gui_tree()

    def from_file(self, src: BufferedReader|BytesIO) -> None:
        """Load a delver archive from a file-like object."""
        self.arcfile = util.DelvReader(src)
        self.load_header()
        self.load_index()
        self.source_string = "Loaded from file object %s"%src

    def from_string(self, src: bytes) -> None:
        """Load a delver archive from an indexable object."""
        self.from_file(BytesIO(src))
        self.source_string = "Loaded from string"

    def from_path(self, path: str) -> None:
        """Load a Delver archive from a file system path."""
        self.source_string = "Loaded from path %s"%path
        if os.path.isdir(path):
            self.from_directory(path)
        else:
            self.from_file(open(path, 'rb'))

    def source(self):
        '''Return a string explaining where this archive came from.'''
        return self.source_string

    def to_directory(self, path: str) -> None:
        """Dump the contents of the archive, unencrypted, to path."""
        assert os.path.isdir(path)
        metadata = {
            'source': self.source(),
            'creator': 'delv (www.ferazelhosting.net/wiki/delv)',
            'scenario_title': self.scenario_title,
            'player_name': self.player_name
        }
        encrypt = {}
        for resource in self.resources():
            if not resource: continue # don't preserve empties
            with open(os.path.join(path, "%04X.data"%resid(resource)), 'wb') as outf:
                resource.save_to_file(outf)
            encrypt["%04X"%resid(resource)] = resource.get_metadata()
        metadata['should_encrypt'] = encrypt
        with open(os.path.join(path, "metadata.json"), 'w') as metafile:
            json.dump(metadata, metafile)

    def to_file(self, dest_file: BytesIO|BufferedWriter):
        """Write a Delver archive to the destination file-like
           object (must be open for writing, obviously)"""
        print("Writing out to", repr(dest_file))
        dest = util.DelvWriter(dest_file)
        self.save_header(dest)
        # Skip to just past the spot where we'll put the master index later
        dest.write(bytearray(0x800))
        # Write all the resources.
        for n,subindex in enumerate(self.all_subindices):
            if not subindex:
                self.master_index[n] = 0,0
                continue
            at_least_one = False
            for res in subindex:
                if res:
                    res.write(dest)
                    at_least_one = True
            if not at_least_one: # Prune empty subindices, if any arise
                self.master_index[n] = 0,0
                self.all_subindices[n] = []
        # Write all our resource indices, now that they know where they are.
        for n,subindex in enumerate(self.all_subindices):
            if not subindex: continue

            # Can make it only as long as it needs to be...?
            self.master_index[n] = dest.tell(), 2048
            for res in subindex:
                if res:
                    res.write_index(dest)
                else:
                    dest.write_offlen(0,0)
        # Now write the master index:
        dest.seek(self.master_index_offset + 8)
        for offset,length in self.master_index:
            dest.write_offlen(offset,length)

    def canon_encryption_of(self, subindex: int, resid=None):
        if resid and resid in self.single_known: return self.single_known[resid]
        return self.encryption_knowledge.get(subindex, None)

    def to_string(self) -> bytes:
        """Produces one (possibly very large) bytes with the
           archive in it. Mainly here for front-end web stuff."""
        stio = BytesIO()
        self.to_file(stio)
        return stio.getvalue()

    def to_path(self, path: str) -> None:
        """Save the archive to a location on disk."""
        if os.path.isdir(path):
            self.to_directory(path)
        else:
            with open(path, 'wb') as f:
                self.to_file(f)

    def get(
        self,
        idx: int|tuple[int, int],
        create_new: bool = False
    ) -> Optional[Resource]:
        """Get a resource by its two-byte-integer composite resource ID,
           or by a tuple of integers (subindex, ID).
           A Resource object is returned if the resource exists, otherwise
           None is returned. (This can be efficiently used to check if a
           Resource exists.)"""
        subindex,n = indices(idx)
        if not self.all_subindices[subindex]:
            if create_new:
                self.all_subindices[subindex] = [None]*256
            else:
                return None
        r = self.all_subindices[subindex][n]
        if r is None and create_new:
            r = Resource(0, 0, self, subindex, n)
            self.all_subindices[subindex][n] = r
            print("creating new resource %04X"%idx,r)
        return r

    def __getitem__(self, idx: int|tuple[int, int]):
        """Retrieve the data of a resource using the index[] operator.
           Its sematics differ slightly from .get in that it will raise
           IndexError if the resource does not exist, whereas .get will not
           produce exceptions. idx can be the two-byte resource ID or it can be
           a tuple with the subindex and individual resource ID. Another
           difference is that the content of the resource, and not the
           corresponding Resource object, is returned."""
        res = self.get(idx)
        if res is None:
            raise IndexError("Resource %s is not in use"%idx)
        return res.get_data()

    def __setitem__(self, idx: int|tuple[int, int], value) -> None:
        """idx sematics are the same as __getitem__. If value is not
           already a Resource object, it will be automatically wrapped.
           New resources are created if needed."""
        subindex,n = indices(idx)
        if isinstance(value, Resource):
            if not self.all_subindices[subindex]:
                self.all_subindices[subindex] = [None]*256
            if not self.master_index[subindex]:
                self.master_index[subindex] = (-1,-1)
            self.all_subindices[subindex][n] = value
            if not value.loaded: value.load()
            value.archive = self
        else:
            res = self.get(idx, True)
            assert res, f"failed to create missing Resource at {indices(idx)}"
            res.set_data(value)

    def resource_ids(self, subindex: Optional[int] = None) -> list[int]:
        """If subindex is not None, returns a list of valid resource IDs
           (not resource objects) for that subindex, possibly empty if
           the subindex is empty or does not exist. If subindex is None,
           it returns a list of all resource IDs that are valid for this
           archive in toto."""
        if subindex is not None:
            sx = self.all_subindices[subindex]
            return [resid(subindex,n) for n,r in enumerate(sx) if r]
        else:
            return functools.reduce(operator.add,
                [self.resource_ids(si) for si in self.subindices()])

    def subindices(self) -> list[int]:
        """Return a list of valid subindices for this archive."""
        return [n for n in range(len(self.master_index)
            ) if self.master_index[n]]


    def resources(self, subindex=None) -> list[Resource]:
        """Returns a list of all the Resource objects in the subindex
           provided. (Possibly an empty list.) If no subindex is provided,
           returns a list of all the resources in the archive."""
        if subindex is not None:
            sx = self.all_subindices[subindex]
            return [r for r in sx if r]
        return functools.reduce(operator.add,
            [self.resources(si) for si in self.subindices()])

    def __iter__(self) -> Iterator[Resource]:
        """This iterator is over all extant resources in the archive. That
           is, if d is an Archive, the following are equivalent:
           for resource in d: ...
           for resource in d.resources(): ...
           Perhaps a future lazy version could be made, in which case the
           iterator would be more efficient.
        """
        return iter(self.resources())

    # --------------------------- Private methods ------------------------
    def create_header(self, scenario: str = "Cythera: Fate of Alaric") -> None:
        self.scenario_title = scenario
        # What these are for, we don't know.
        self.unknown_40 = 0x13
        self.unknown_42 = 2
        self.unknown_48 = 2
        self.master_index_offset = 0x80
        self.master_index_length = 2048

    def create_index(self, size: int = 256) -> None:
        self.master_index = [(0, 0)]*size
        self.all_subindices = []
        for _ in range(size): self.all_subindices.append([])
        self.master_index_length = 8*size

    def load_header(self) -> None:
        assert self.arcfile, "load_header: archive has no arcfile"
        self.scenario_title = self.arcfile.read_pstring(0)
        self.player_name = self.arcfile.read_pstring(0x20)
        self.unknown_40 = self.arcfile.read_uint8(0x40)
        self.unknown_42 = self.arcfile.read_uint8(0x42)
        self.unknown_48 = self.arcfile.read_uint8(0x48)
        self.master_index_offset = self.arcfile.read_uint32(0x80)
        self.master_index_length = self.arcfile.read_uint32(0x84)

    def save_header(self, dest: util.DelvWriter) -> None:
        dest.write_pstring(self.scenario_title, 0)
        dest.write_pstring(self.player_name, 0x20)
        dest.write_uint8(self.unknown_40, 0x40)
        dest.write_uint8(self.unknown_42, 0x42)
        dest.write_uint8(self.unknown_48, 0x48)
        dest.write_offlen(self.master_index_offset, self.master_index_length,
            self.master_index_offset)

    def load_index(self) -> None:
        assert self.arcfile, "load_index: archive has no arcfile"
        self.arcfile.seek(self.master_index_offset+8)
        self.master_index = [(0, 0)]*(self.master_index_length//8 - 1)
        for n in range(len(self.master_index)):
             self.master_index[n] = self.arcfile.read_offlen()
        self.all_subindices = []
        for subn, (offset, length) in enumerate(self.master_index):

            if not offset:
                self.all_subindices.append([])
                continue
            subindex = []
            self.arcfile.seek(offset)
            size = length // 8
            rescount = 0
            for n in range(size):
                res_offset, res_length = self.arcfile.read_offlen()
                if res_offset:
                    subindex.append(Resource(
                        res_offset, res_length,
                        self, subn, n
                    ))
                    rescount += 1
                else:
                    subindex.append(None)
            self.all_subindices.append(subindex)
        if self.gui_treestore: self.add_gui_tree()

    def add_gui_tree(self) -> None:
        assert self.gui_treestore is not None, \
            "add_gui_tree: gui_treestore was None"
        self.gui_tree_rows = {}
        for subn, subindex in enumerate(self.all_subindices):
            rescount = len([r for r in subindex if r])
            if not rescount: continue
            t=self.gui_treestore.append(None, [
                "%3d [%02Xxx]"%(subn, subn+1),
                "%3d item%s"%(rescount, '' if rescount == 1 else 's'),
                _SCEN_HINTS.get(subn, "Unknown"),
                subn,
                -1
            ])
            self.gui_tree_rows[subn] = t
            for r in subindex:
                if not r: continue
                self.gui_treestore.append(t, [
                    "%04X"%resid(r.subindex, r.n),
                    r.human_readable_size(),
                    _RES_HINTS.get(resid(r.subindex, r.n), ""),
                    r.subindex,
                    r.n
                ])

class Player(Archive):
    """Class for manipulating Delver Player Files, i.e. saved games."""

class Scenario(Archive):
    """Class for manipulating Delver Scenario files."""
    known_encrypted = [1,2,4,7,8,9,10,11,12,13,14,15,16,
                       19,20,23,24,25,26,27,29,47]
    single_known = {0x0210: False}
    known_clear = [0,3,127,128,131,135,137,141,142,143,
                   144,187,239,254]

class Patch(Scenario):
    """Class for manipulating Delver patchfiles."""
    # public:
    _patch_info: str = "This patch created by delv.archive.Patch"
    def patch_info(self, infostring: str):
        "Set the description of the patch."
        self[0xFFFF] = 'MAGPY'+infostring
        self._patch_info = infostring

    def get_patch_info(self) -> str:
        """Return the patch info string. mag.py and Magpie formats supported."""
        patchres = self.get(0xFFFF)
        if not patchres: return ''
        data = patchres.as_file()
        if data.read(5) == 'MAGPY': # mag.py format
            self._patch_info = data.read().decode("macroman")
        else: # Magpie format
            self._patch_info = data.read_pstring(0x138)
        return self._patch_info

    def compatible(
        self,
        other_patch: 'Patch',
        exclude: list[int] = [0xFFFF,0xBC00,0xBC35]
    ) -> bool:
        """Returns False if two patches are not compatible. Returns True
           if they might be compatible. ;) """
        set_exclude = set(exclude)
        set_res = set(self.resource_ids())
        patch_res = set(other_patch.resource_ids())
        return not (set_res-set_exclude).intersection(patch_res-set_exclude)

    def patch(self, target: Archive) -> None:
        "Apply this patch to the target."
        for resource in self:
            target[resid(resource)] = resource

    def diff(
        self,
        base: Archive,
        modified: Archive,
        exclude: list[int] = [0xFFFF]
    ) -> None:
        """Add the differences between Archives base and modified to this
           patch archive, such that if .apply(base) is subsequently used,
           base will come to contain the same data as modified."""
        set_exclude = set(exclude)
        for resid in modified.resource_ids():
            if resid in set_exclude: continue
            eq = base.get(resid)
            nd = modified.get(resid)
            if not nd: continue
            if (not eq) or (eq.get_data() != nd.get_data()):
                if not nd.loaded: nd.load()
                self[resid] = nd

def validate_resource_id(resid: int) -> bool:
    """Returns True if resid is valid, False otherwise. Note that validity
       does not imply the resource currently exists in an archive.
       (use .get for that.)"""
    return 0x0100 <= resid <= 0xFFFF

def resid(subindex: Resource|int, n: int=0) -> int:
    """Given a major (master) index page subindex and minor (page) index n,
       return the resource ID."""
    if isinstance(subindex, Resource): subindex,n=subindex.subindex,subindex.n
    assert n < 0x100 and subindex < 0x100
    return ((subindex+1)<<8) | n

def master_index(resid: int) -> int:
    """Return the major (master) index page associated with a resource ID."""
    return ((resid & 0xFF00) >> 8) - 1

def index(resid: int) -> int:
    """Return the minor (page) index associated with a resource ID."""
    return resid & 0xFF

def indices(resid: int|tuple[int, int]) -> tuple[int, int]:
    """Return the major and minor indicies associatied with a resource ID.
       If resid is infact already a tuple, return it. """
    return resid if isinstance(resid,tuple) else (master_index(
        resid), index(resid))

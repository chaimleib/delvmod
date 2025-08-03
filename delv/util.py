#!/usr/bin/env python
# Copyright 2014-2015 Bryce Schroeder, www.bryce.pw, bryce.schroeder@gmail.com
# Version: 0.20
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

def encode_int28(i):
    return i if i >= 0 else (0x0FFFFFFF+i+1)

from io import BufferedReader, BufferedWriter, BytesIO
import struct
from sys import stderr
from typing import Optional

class dref(object):
    def __init__(
        self,
        resid: int,
        offset: int,
        length: Optional[int] = None
    ) -> None:
        self.resid: int = resid
        #print("%04X %04X / %s"%(resid,offset,length))
        self.offset: int = offset
        self.length: Optional[int] = length

    # def load_from_library(
    #     self,
    #     library: Library,
    #     TF: Optional[Callable[['dref'], 'dref']] = None
    # ) -> 'dref':
    #     if TF:
    #         return TF(library.get_dref(self))
    #     else:
    #         return library.get_dref(self)

    def __str__(self) -> str:
        return "<dref 0x%04X:%04X %s>"%(self.resid,self.offset,self.length)


def int_to_bits(value: int, size: int) -> bytearray:
    result = bytearray(size)
    j = 0
    for i in range(size-1,-1,-1):
        result[j] = (value >> i)&1
        j += 1
    return result

def bytes_to_bits(src: int|bytearray) -> bytearray:
    src = bytearray(src) # Note that if src is an integer, a new empty bytearray is made.
    # this is not efficient, but it does at least make sense semantically.
    result = bytearray(len(src)*8)
    ri = 0
    for byte in src:
        for bi in range(7,-1,-1): 
            result[ri] = (byte>>bi)&1
            ri += 1
    return result

def bits_to_bytes(src: bytearray) -> bytearray:
    result = bytearray((len(src)+7)//8)
    byi = 0
    bi = 0
    for n,bit in enumerate(src):
        byte_index = n//8
        bit_index = n % 8
        result[byte_index] |= bit << (7-bit_index)
    return result

def bitstruct_pack(
    target: bytearray,
    pairs: list[tuple[int, list[tuple[int, int]]]]
) -> None:
    b = bytes_to_bits(target)
    for value, fieldspec in pairs:
        for size, index in fieldspec[::-1]:
            fieldbits = value & (0xFFFFFFFFFFFFFFFF >> (64-size))
            b[index:index+size] = int_to_bits(value,size)
            value >>= size
    t =  bits_to_bytes(b)
    for x in range(len(t)): target[x]=t[x]

def bits_pack(
    target: bytearray,
    value: int,
    size: int,
    index: int,
    debug: bool = False
) -> None:
    """Alter bytearray target so that size bits of target starting
       at index are replaced by value."""
    bit_index = index % 8
    startbyte = index // 8
    endbyte = (index+size+7) // 8
    section = bytes_to_bits(target[startbyte:endbyte])
    #if debug:print("BEFORE", ''.join(["%01d"%b for b in section]))
    section[bit_index:bit_index+size] = int_to_bits(value,size)
    #if debug:print("AFTER ", ''.join(["%01d"%b for b in section]))
    target[startbyte:endbyte] = bits_to_bytes(section)

def ncbits_pack(
    target: bytearray,
    value: int,
    *fields: tuple[int, int]
) -> None:
    """Alter target to contain the value given, broken up into
       nonconsecutive bitfields using the same sematics as ncbits_of.

       Look on this, ye coders, and repeat the sacred mantra:
          "Premature optimization is the root of all evil."
    """
    # This would be more efficient if we made it only convert to
    # bits and back once, or if we rewrote it to be like bits_of (I
    # actually wrote that first before I thought of this simpler way)
    # but why bother, it's only used compressing graphics, which is an
    # infrequent operation (whereas decompression happens a lot.)
    for size,index in fields[::-1]:
        fieldbits = value & (0xFFFFFFFFFFFFFFFF >> (64-size))
        bits_pack(target, fieldbits, size, index)
        value >>= size

def ncbits_of(data: bytearray, *fields: tuple[int, int]) -> int:
    """Returns an integer bit field from the bytearray data, 
       the integer being made up of all the fields combined.
       Each field is a tuple in the format (size,index). 
       e.g. if  you had a bytearray foo of three bytes as follows:

         -----AB-, ---CDEFG, HI--JKL-

       And you wanted to extract the bits ABCDEFGHIJKL as one
       12-bit integer, you'd say:
         ncbits_of(foo, (2,5), (7,11), (3,20))

       Note that if you ever use this function other than to be
       compatible with something already using nonconsecutive bits,
       I am pretty sure that D. E. Knuth will come to your home and
       perform an exorcism involving a shotgun and rock salt. Or at least,
       he ought to.
    """
    result = 0
    position = 0
    for size,index in fields:
        result <<= size
        result |= bits_of(data, size, index)
    return result

def bits_of(data: bytearray, size: int, index: int) -> int:
    "Read a slice of the bytearray data bitwise - indices in bits"
    byte_index = index // 8
    bit_index = index % 8
    byte_end = (size+index) // 8 
    bit_size = size % 8 
    result = data[byte_index] & (0xFF >> bit_index)
    while byte_index < byte_end:
        byte_index += 1
        if len(data) == byte_index: 
            result <<= 8; break
        result = (result << 8) | data[byte_index]
    result >>= 8 - (bit_index + bit_size) % 8
    return result

S_offlen = struct.Struct('>LL')
S_uint32 = struct.Struct('>L')
S_sint32 = struct.Struct('>l')
S_uint8 = struct.Struct('B')
S_sint8 = struct.Struct('b')
S_uint16 = struct.Struct('>H')
S_sint16 = struct.Struct('>h')

class DelvReader(object):
    file: BufferedReader|BytesIO
    def __init__(
        self,
        file: BufferedReader|BytesIO|bytes|bytearray,
        coverage_map: bool = False
    ) -> None:
        if type(file) is bytes or type(file) is bytearray:
            self.file = BytesIO(file)
        elif isinstance(file, BufferedReader) or isinstance(file, BytesIO):
            self.file = file
        else:
            assert False, f"DelvReader: unknown file type {type(file)}"
        self._read = self.read
        if coverage_map:
            self.coverage_map = [0]*len(self)
            self.read = self.cm_read
            self.readb = self.cm_readb

    # Wishing for a more elegant alternative
    def eof(self) -> bool:
        rv = self.file.read(1)
        self.file.seek(-1, 1)
        return rv == ''

    def seek(self, *vargs, **kwargs) -> None:
        self.file.seek(*vargs, **kwargs)

    def cm_read(self,  *vargs, **kwargs) -> bytes:
        p = self.tell()
        rv = self.file.read(*vargs,**kwargs)
        self.coverage_map[p:p+len(rv)] = [1]*len(rv)
        return rv

    def cm_readb(self, *vargs, **kwargs) -> bytearray:
        return bytearray(self.cm_read(*vargs, **kwargs))

    def cm_all(self) -> bool:
        return 0 not in self.coverage_map

    def cm_unseen(self) -> list[tuple[int, int]]:
        unseen = []
        start = 0
        i = 0
        cm = self.coverage_map
        while i < len(cm):
            if not cm[i]:
                start=i
                while i < len(cm) and not cm[i]:
                    i += 1
                unseen.append((start,i-start))
            i += 1
        return unseen

    def read(self, *vargs, **kwargs) -> bytes:
        return self.file.read(*vargs, **kwargs)

    def readb(self, *vargs, **kwargs) -> bytearray:
        return bytearray(self.file.read(*vargs, **kwargs))

    def tell(self, *vargs, **kwargs) -> int:
        return self.file.tell(*vargs, **kwargs)

    def __len__(self) -> int:
        p = self.tell()
        self.seek(0)
        # somewhere a Real Programmer is crying and doesn't know why
        length = len(self._read())
        self.seek(p)
        return length

    def read_struct(self, s: struct.Struct, offset: Optional[int] = None) -> tuple[int, int]:
        if offset is not None: self.seek(offset)
        return s.unpack(self.read(s.size))

    def read_offlen(self, offset: Optional[int] = None) -> tuple[int, int]:
        return self.read_struct(S_offlen, offset)

    def read_uint8(self, offset: Optional[int] = None) -> int:
        "Read 8-bit unsigned integer"
        return self.read_struct(S_uint8, offset)[0]

    def read_sint8(self, offset: Optional[int] = None) -> int:
        return self.read_struct(S_sint8, offset)[0]

    def read_uint16(self, offset: Optional[int] = None) -> int:
        "Read 16-bit big endian unsigned integer."
        return self.read_struct(S_uint16, offset)[0]

    def read_uint6_uint10(
        self,
        offset: Optional[int] = None
    ) -> tuple[int, int]:
        v = self.read_uint16(offset)
        return v>>10, v&0x3FF

    def read_sint16(self, offset: Optional[int] = None) -> int:
        "Read 16-bit big endian signed integer."
        return self.read_struct(S_sint16, offset)[0]

    def read_sint32(self, offset: Optional[int] = None) -> int:
        return self.read_struct(S_sint32, offset)[0]

    def read_uint24(self, offset: Optional[int] = None) -> int:
        first_part  = self.read_uint8(offset)
        return (first_part<<16) | self.read_uint16()

    def read_atom(self, offset: Optional[int] = None) -> int|str|dref:
        "Read a simple delver scripting system value"
        ty = self.read_uint8(offset)
        if ty == 0x50:
            empty = self.read_uint8()
            assert not empty
            atom = self.read_uint16()
            return {0xFFFF:None, 0: False, 1: True}[atom]
        elif ty&0x80 == 0x00:
            v = self.read_uint24()|((ty&0x0F)<<24)
            return v if not v&0x8000000 else (~v)+1
        elif ty & 0xF0 == 0x40:
            return "<0x%02X:%06X>"%(ty, self.read_uint24())
        elif ty >= 0x80:
            resid = ((ty&~0x80)<<8)|self.read_uint8()
            offset = self.read_uint16()
            return dref(resid, offset)
        else:
            print(repr(self), "==0x%02X"%ty, repr(self.file), file=stderr)
            assert False

    def read_sint24(self, offset: Optional[int] = None) -> int:
        "Return a signed 24-bit integer."
        first_part  = self.read_uint8(offset)
        uvar = (first_part<<16) | self.read_uint16()
        if uvar & 0x800000:
            uvar = -((0xFFFFFF^uvar)+1)
        return uvar

    def read_fo16(self, offset: Optional[int] = None) -> tuple[int, int]:
        v = self.read_uint16(offset)
        return (v&0xF000)>>12,v&0x0FFF

    def read_xy24(self, offset: Optional[int] = None) -> tuple[int, int]:
        "Read packed 12-bit xy coordinates, as used in prop lists."
        if offset is not None: self.seek(offset)
        d = self.readb(3)
        return (d[0]<<4)|(d[1]>>4), ((d[1]&0x0F)<<8)|d[2]

    def read_uint32(self, offset: Optional[int] = None) -> int:
        "Read 32-bit unsigned integer."
        return self.read_struct(S_uint32, offset)[0]

    def read_vm32(self, offset: Optional[int] = None) -> tuple[int, int]:
        "Read 24-bit signed integer and 8-bit flags. (Flags returned first.)"
        #FIXME, now known to use a 28 bit integer
        return self.read_uint8(offset), self.read_sint24()

    def read_pstring(self, offset: Optional[int] = None) -> str:
        "Read a Pascal String (Length byte followed by that many data bytes)"
        size = self.read_uint8(offset)
        return self.read(size).decode("macroman")

    def read_str31(self, offset: Optional[int] = None) -> str:
        "Read a Str31."
        size = self.read_uint8(offset)
        return self.read(31)[:size].decode("macroman")

    def read_fixed16(self, offset: Optional[int] = None) -> float:
        "Read an 8.8 Fixed number."
        units = self.read_uint8(offset)
        fraction = self.read_uint8()
        return units + fraction/256.0

    def read_cstring(self, offset: Optional[int] = None) -> str:
        if offset is not None: self.seek(offset)
        buf = bytearray()
        while True:
            b = self.read(1)
            if b == b'\0' or not b: break
            buf += b
        return buf.decode("macroman")

class DelvWriter(object):
    file: BufferedWriter|BytesIO
    def __init__(
        self,
        file: BufferedWriter|BytesIO
    ) -> None:
        if isinstance(file, BufferedWriter) or isinstance(file, BytesIO):
            self.file = file
        else:
            assert False, f"DelvWriter: unknown file type {type(file)}"

    def write(self, *vargs, **kwargs) -> None:
        self.file.write(*vargs, **kwargs)

    def truncate(self, *vargs, **kwargs):
        return self.file.truncate(*vargs,**kwargs)

    def seek(self, *vargs, **kwargs) -> None:
        self.file.seek(*vargs, **kwargs)

    def tell(self, *vargs, **kwargs) -> int:
        return self.file.tell(*vargs, **kwargs)

    def write_struct(
        self,
        s: struct.Struct,
        v: int|tuple[int, int],
        offset: Optional[int] = None
    ) -> None:
        if offset is not None: self.seek(offset)
        if type(v) is tuple:
            self.write(s.pack(*v))
        elif type(v) is int:
            self.write(s.pack(v))
        else:
            assert False, f"write_struct: unknown value type {type(v)}"

    def write_uint8(self, v: int, offset: Optional[int] = None) -> None:
        self.write_struct(S_uint8, v, offset)

    def write_sint8(self, v: int, offset: Optional[int] = None) -> None:
        self.write_struct(S_sint8, v, offset)

    def write_uint16(self, v: int, offset: Optional[int] = None) -> None:
        self.write_struct(S_uint16, v, offset)

    def write_uint6_uint10(
        self,
        v1: int,
        v2: int,
        offset: Optional[int] = None
    ) -> None:
        self.write_uint16((v1<<10)|(v2&0x3FF),offset)

    def write_fo16(
        self,
        flags: int,
        roffset: int,
        offset: Optional[int] = None
    ) -> None:
        self.write_uint16(((flags&0x0F)<<12)|roffset, offset)

    def write_sint16(self, v: int, offset: Optional[int] = None) -> None:
        self.write_struct(S_sint16, v, offset)

    def write_uint32(self, v: int, offset: Optional[int] = None) -> None:
        self.write_struct(S_uint32, v, offset)

    def write_sint32(self, v: int, offset: Optional[int] = None) -> None:
        self.write_struct(S_sint32, v, offset)

    def write_offlen(
        self,
        offs: int,
        length: int,
        offset: Optional[int] = None
    ) -> None:
        self.write_struct(S_offlen, (offs, length), offset)

    def write_sint24(self, v: int, offset: Optional[int] = None) -> None:
        if offset is not None: self.seek(offset)
        self.write_uint8((v&0xFF0000)>>16)
        self.write_uint16((v&0x00FFFF))

    def write_uint24(self, v: int, offset: Optional[int] = None) -> None:
        if offset is not None: self.seek(offset)
        self.write_uint8((v&0xFF0000)>>16)
        self.write_uint16((v&0x00FFFF))

    def write_xy24(self, x: int, y: int, offset: Optional[int] = None) -> None:
        if offset is not None: self.seek(offset)
        self.write_uint8((x&0xFF0)>>4)
        self.write_uint8(((x&0x00F)<<4)|((y&0xF00)>>8))
        self.write_uint8(y&0x0FF)

    def write_vm32(
        self,
        flags: int,
        v: int,
        offset: Optional[int] = None
    ) -> None:
        if offset is not None: self.seek(offset)
        self.write_uint8(flags)
        return self.write_sint24(v)

    def write_pstring(self, s: str, offset: Optional[int] = None) -> None:
        if offset is not None: self.seek(offset)
        "Write a pascal string - 8 bit length followed by data."
        assert len(s) < 256
        self.write_uint8(len(s))
        return self.write(s.encode("macroman"))

    def write_str31(self, s: str, offset: Optional[int] = None) -> None:
        if offset is not None: self.seek(offset)
        assert len(s) < 32
        self.write_uint8(len(s))
        self.write(s.encode("macroman"))
        self.write('\x00'*(31-len(s)))

    def write_cstring(self, s: str, offset: Optional[int] = None) -> None:
        "Write a null-terminated string."
        if offset is not None: self.seek(offset)
        self.write(s)
        self.write('\x00')

    def write_fixed16(self, s: float, offset: Optional[int] = None) -> None:
        "Write 8.8 fixed-point number."
        if offset is not None: self.seek(offset)
        self.write_uint8(int(s))
        self.write_uint8(int(round(255*(s-int(s)))))

    def write_atom(
        self,
        v: Optional[int|dref],
        offset: Optional[int] = None
    ) -> None:
        if offset is not None: self.seek(offset)
        if v is None:
            self.write_uint32(0x5000FFFF)
        elif isinstance(v, dref):
            self.write_uint16(v.resid+0x8000)
            self.write_uint16(v.offset)
        elif isinstance(v, int):
            self.write_uint8(0x00)
            self.write_sint24(v)
        else:
            assert False, f"write_atom: unknown value ({v}) for delver atom"

class UnimplementedFeature (Exception): pass

DLI_MSG = """This archive must be underlayed with a Scenario."""
class LibraryIncomplete(Exception): pass

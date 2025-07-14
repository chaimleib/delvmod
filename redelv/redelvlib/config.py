import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, TypeVar, Type

_Config = TypeVar('_Config', bound='Config')

@dataclass
class Config:
    @dataclass
    class Commands:
        # Command to edit assembly source code
        assembly_editor: str = 'gedit --standalone %s'
        # Command to edit sounds
        audio_editor: str = 'audacity %s'
        # Command to edit images
        graphics_editor: str = 'gimp -n %s'
        # Command to edit binary files, e.g. 'ghex %s'
        hex_editor: str = 'bless %s'
        # Command to play sounds
        play_sound: str = 'mplayer %s'

    # The info to add to patches produced.
    default_patch_info: str
    # External commands
    cmd: Commands = field(default_factory=Commands)
    # Show debug messages
    debug: bool = False
    # Watch for file changes and instantly update
    # (This generally looks pretty cool, but it may hose your
    #  unsaved changes if any.)
    instant_editor_propagation: bool = True
    # URL form to retrieve human-checked source code from
    source_archive: str = 'http://www.ferazelhosting.net/wiki/%04X?action=raw'

    @classmethod
    def from_dict(
        cls: Type[_Config],
        d: Dict[str, Any]
    ) -> _Config:
        if 'cmd' in d:
            cmd_dict = d['cmd']
            if not isinstance(cmd_dict, dict):
                raise TypeError("'cmd' was not a dict")
            cmd = Config.Commands(**cmd_dict)
        else:
            cmd = Config.Commands()
        del d['cmd']

        cfg = cls(**d)
        cfg.cmd = cmd
        return cfg

    @classmethod
    def open_or_create(
        cls: Type[_Config],
        fpath: str,
        default_patch_info: str,
    ) -> _Config:
        opened = cls.open(fpath)
        if opened is None:
            cfg = cls(default_patch_info=default_patch_info)
            cfg.save(fpath)
            return cfg
        opened.default_patch_info = default_patch_info
        return opened

    @classmethod
    def open(cls: Type[_Config], fpath: str) -> Optional[_Config]:
        if not os.path.exists(fpath):
            return None
        with open(fpath, 'r') as f:
            cfg_dict = json.load(f)
            if cfg_dict is None:
                return None
            elif not isinstance(cfg_dict, dict):
                return None
            return cls.from_dict(cfg_dict)

    def save(self, fpath: str) -> None:
        with open(fpath, 'w') as f:
            json.dump(asdict(self), f, indent=True)

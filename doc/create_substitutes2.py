import enum
import os
import re
import shutil
import subprocess
import sys
import warnings
from os import walk
from pathlib import Path
from typing import Dict, List, Optional, Union

import qgis
import qgis.PyQt.QtCore
import qgis.PyQt.QtGui
import qgis.PyQt.QtWidgets
import qgis.core
import qgis.gui

DIR_REPO = Path(__file__).parents[1]
DIR_SOURCE = DIR_REPO / 'doc/source'

DIR_ICONS = DIR_SOURCE / 'icons'

ICON_DIRS = [
    DIR_ICONS,
    DIR_REPO / 'eotimeseriesviewer/ui/icons',
    DIR_REPO / 'eotimeseriesviewer/qgispluginsupport/qps/ui/icons',
]

ENV_INKSCAPE_BIN = 'INKSCAPE_BIN'

if 'QGIS_REPO' in os.environ:
    ICON_DIRS.append(Path(os.environ['QGIS_REPO']))
else:
    QGIS_REPO = DIR_REPO.parent / 'QGIS'
    if QGIS_REPO.is_dir():
        ICON_DIRS.append(QGIS_REPO / 'images/themes/default')


def inkscapeBin() -> Path:
    """
    Searches for the Inkscape binary
    """
    if ENV_INKSCAPE_BIN in os.environ:
        path = os.environ[ENV_INKSCAPE_BIN]
    else:
        path = shutil.which('inkscape')
    if path:
        path = Path(path)

    assert path.is_file(), f'Could not find inkscape executable. Set {ENV_INKSCAPE_BIN}=<path to inkscape binary>'
    return path


class SourceType(enum.Flag):
    Icon = enum.auto()
    Link = enum.auto()
    Raw = enum.auto()


class Substitute(object):

    def __init__(self, name: str,
                 definition: Optional[str] = None,
                 stype: SourceType = SourceType.Link):
        self.name = name
        self.stype: SourceType = stype
        self.icon_path: Optional[Path] = None
        self.definition: Optional[str] = definition

    def __str__(self):
        return (f'{self.__class__.__name__}:{self.name}<{self.stype}>'
                f'\n\ticon_path="{self.icon_path}"'
                f'\n\tdefinition="{self.definition}"')


def isSubDir(parentDir, subDir) -> bool:
    parentDir = Path(parentDir)
    subDir = Path(subDir)
    return subDir.as_posix().startswith(parentDir.as_posix())


class SubstituteCollection(object):

    def __init__(self,
                 source_root: Union[Path, str],
                 dir_rst_icons: Union[Path, str, None] = None):
        assert source_root.is_dir()

        self.mIconSize: int = 28

        self.mSourceRoot = Path(source_root)

        self.mPathInkscapeBin: Optional[Path] = None

        if dir_rst_icons:
            assert isSubDir(self.mSourceRoot, dir_rst_icons)
        else:
            dir_rst_icons = source_root / 'icons'
        assert dir_rst_icons.is_dir()
        self.dir_rst_icons: Path = Path(dir_rst_icons)

        self.mSubstitutes: Dict[str, Substitute] = dict()

    def __getitem__(self, item):
        return self.mSubstitutes[item]

    def __contains__(self, item):
        return self.mSubstitutes.__contains__(item)

    def addLinkSubstitute(self, name: str, link: str):
        sub = Substitute(name, definition=link, stype=SourceType.Link)
        self.addSubstitute(sub)

    def addSubstitute(self, substitute: Substitute):
        assert isinstance(substitute, Substitute)
        if substitute.name in self.mSubstitutes:
            warnings.warn(f'Definition {substitute} already exists: {self[substitute.name]}')
        else:
            self.mSubstitutes[substitute.name] = substitute

    def readIcons(self, source: Path, extensions: List[str] = ['svg', 'png']):
        assert source.is_dir()

        for ext in extensions:
            for p in find_by_ext(source, ext):
                assert p.is_file()
                name = p.stem
                if name in self:
                    print(f'Name already exists "{name}" {p}:'
                          f'\n\t {self[name]}', file=sys.stderr)
                    continue

                sub = Substitute(name, stype=SourceType.Icon)
                sub.icon_path = p
                if isSubDir(self.mSourceRoot, p.parent):
                    sub.definition = p.relative_to(self.mSourceRoot)

                self.addSubstitute(sub)
                s = ""

    def addManualDefinitions(self, source: Path):
        source = Path(source)
        assert source.is_file()

        with open(source, 'r', encoding='utf8') as f:
            lines = f.readlines()
            lines = [l.split('#')[0] for l in lines]
            lines = ''.join(lines).strip()
            parts = lines.split('.. |')
            parts = [p.strip() for p in parts if len(p) > 0]
            for raw in parts:
                name = re.search(r'^[^|]+', raw).group()
                assert isinstance(name, str)
                raw = '.. |' + raw.strip()
                sub = Substitute(name, definition=raw, stype=SourceType.Raw)
                self.addSubstitute(sub)
            s = ""

    def updateRST(self, path: Union[str, Path]):
        path = Path(path)
        assert path.is_file()
        assert path.name.endswith('.rst')

        with open(path, 'r') as f:
            lines = f.readlines()

        new_lines = []
        s_pattern = re.compile(r"(?<!\.\. )\|([\w\d-]+)\|")

        requested = set()

        for line in lines:

            if line.startswith(MSG_DO_NOT_EDIT):
                break
            else:
                new_lines.append(line)

            for r in s_pattern.findall(line):
                requested.add(r)

        if len(requested) > 0:

            new_lines += [MSG_DO_NOT_EDIT, '']
            for r in sorted(requested):
                if r not in self:
                    raise Exception(f'Missing definition for "{r}"')
                sub = self[r]
                rst_code = self.toRST(sub, copy_icon=True)
                new_lines.append(rst_code)
                s = ""
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))

    def print(self):
        for s in self.mSubstitutes.values():
            print(self.toRST(s))

    def inkscapeBin(self) -> Path:

        if self.mPathInkscapeBin is None:
            self.mPathInkscapeBin = inkscapeBin()
        return self.mPathInkscapeBin

    def toRST(self, sub: Substitute, copy_icon: bool = False) -> str:
        """

        :param sub:
        :param copy_:
        :return:
        """
        if sub.stype == SourceType.Raw:
            return sub.definition

        elif sub.stype == SourceType.Link:
            # .. |Bitbucket| replace:: `Bitbucket <https://bitbucket.org>`_
            return f'.. |{sub.name}| replace:: `{sub.definition}`_'

        elif sub.stype == SourceType.Icon:
            # .. |classinfo_remove| image:: icons/classinfo_remove.png
            #    :width: 28px
            assert isinstance(sub.icon_path, Path)
            if sub.icon_path.is_absolute():
                assert sub.icon_path.is_file()
            else:
                assert (self.mSourceRoot / sub.icon_path).is_file()

            if not isSubDir(self.mSourceRoot, sub.icon_path):
                if copy_icon:
                    path_src = sub.icon_path
                    path_png = DIR_ICONS / f'{path_src.stem}.png'
                    if path_src.name.endswith('.svg'):
                        print(f'Convert {path_src}\n\tto {path_png}')
                        cmd = [
                            #  'inkscape',
                            f'{self.inkscapeBin()}',
                            '--export-type=png',
                            '--export-area-page',
                            f'--export-filename={path_png}',
                            f'{path_src}'
                        ]
                        subprocess.run(cmd, check=True)
                    elif path_src.name.endswith('.png'):
                        print(f'Copy {path_src}\n\tto {path_png}')
                        shutil.copy(path_src, path_png)
                    else:
                        raise NotImplementedError(f'Unsupported icon type: {path_src}')

                    sub.icon_path = path_png.relative_to(self.mSourceRoot)
                else:
                    warnings.warn(f'Icon does not exist in rst source folder: {sub.icon_path}')

            return '\n'.join([
                f'.. |{sub.name}| image:: {sub.icon_path}',
                f'   :width: {self.mIconSize}px'
            ])

            lines = []
            return '\n'.join(lines)
        else:
            raise NotImplementedError()


def add_api_definitions(collection: SubstituteCollection):
    # add manual links

    # autogenerated singular forms
    objects = []
    for module in [
        qgis,
        qgis.core,
        qgis.gui,
        qgis.PyQt.QtCore,
        qgis.PyQt.QtWidgets,
        qgis.PyQt.QtGui,
    ]:
        for key in module.__dict__.keys():
            if re.search('^(Qgs|Q)', key):
                objects.append(key)

    rx_qgis = re.compile('^Qgs|Qgis.*')
    objects = sorted(set(objects))
    for i, obj in enumerate(objects):
        if obj in ['QtCore', 'QtGui', 'QtWidget']:
            continue
        target = None
        if rx_qgis.match(obj):
            # https://qgis.org/api/classQgsProject.html
            target = "https://api.qgis.org/api/class{}.html".format(obj)
        elif obj.startswith('Q'):
            # https://doc.qt.io/qt-5/qwidget.html
            target = "https://doc.qt.io/qt-5/{}.html".format(obj.lower())

        if target is None:
            continue

        # singular + plural form
        names = [obj, obj + 's']
        for name in names:
            if name.endswith('ss'):
                continue
            if name not in collection.mSubstitutes.keys():
                collection.addLinkSubstitute(name, f'{name} <{target}>')


MSG_DO_NOT_EDIT = '.. Substitutions definitions - DO NOT EDIT PAST THIS LINE'


def read_rst_substitutes(file):
    """
    Returns sorted list of existing substitutions on a file
    :param file: string with path to file
    :return: list
    """

    # defines a pattern for a substitution
    # anything inside || except is preceded by ..
    s_pattern = re.compile(r"(?<!\.\. )\|([\w\d-]+)\|")
    s_title = re.compile(r"\.\. Substitutions definitions - AVOID EDITING "
                         r"PAST THIS LINE\n")
    subs = []
    with open(file, 'r+', encoding='utf-8') as f:
        pos = f.tell()
        line = f.readline()
        while line != "":
            if line.startswith(MSG_DO_NOT_EDIT):
                f.seek(pos - 4)
                f.truncate()
                break
            else:
                subs += s_pattern.findall(line)
                pos = f.tell()
                line = f.readline()
                # Making sure there is a newline at the end of the file
                if line == "" and len(subs) > 0:
                    f.seek(pos - 1)
                    if f.read() != "\n":
                        f.write("\n")
    list_subs = list(set(subs))
    list_subs.sort()
    return list_subs


def find_by_ext(folder, extension) -> List[Path]:
    """
    create list with absolute paths to all *.extension files inside
    folder and its sub-folders
    """
    found_files = [Path(dirpath) / f
                   for dirpath, dirnames, files in walk(folder)
                   for f in files if f.endswith('.' + extension)]
    return found_files


def create_substitutions(collection: SubstituteCollection):
    for file in find_by_ext(DIR_SOURCE, 'rst'):
        collection.updateRST(file)


if __name__ == '__main__':
    collection = SubstituteCollection(DIR_SOURCE)

    path_manual = DIR_SOURCE / 'substitutions/substitutions_manual.txt'
    collection.addManualDefinitions(path_manual)
    add_api_definitions(collection)

    for d in ICON_DIRS:
        print(f'Read icons from {d}')
        collection.readIcons(d)
    # collection.print()

    create_substitutions(collection)

    collection.print()

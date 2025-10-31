import enum
import os
import re
import shutil
import subprocess
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

DIR_REPO = Path(__file__).parents[2]
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

rx_subst_def = re.compile(r'^.. \|(?P<name>.*)\| .*')
rx_link_def = re.compile(r'^.. _(?P<name>.*): .*')


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

    def readIcons(self, source: Path, extensions: List[str] = ['svg', 'png']) -> List[str]:
        assert source.is_dir()
        errors = []
        for ext in extensions:
            for p in find_by_ext(source, ext):
                assert p.is_file()
                name = p.stem
                if name in self:
                    errors.append(
                        f'Name already exists "{name}" {p}:'
                        f'\n\t {self[name]}')
                    continue

                sub = Substitute(name, stype=SourceType.Icon)
                sub.icon_path = p
                if isSubDir(self.mSourceRoot, p.parent):
                    sub.definition = p.relative_to(self.mSourceRoot)

                self.addSubstitute(sub)
                s = ""
        return errors

    def addManualDefinitions(self, source: Path):
        source = Path(source)
        assert source.is_file()

        with open(source, 'r', encoding='utf8') as f:
            lines = f.readlines()
            lines = [l.split('#')[0] for l in lines]
            lines = ''.join(lines).strip()
            parts = re.split('(?m)^.. ', lines)
            parts = ['.. ' + p.strip() for p in parts if len(p) > 0]
            for raw in parts:

                if match := rx_subst_def.match(raw):
                    name = match.group('name')
                    sub = Substitute(name, definition=raw, stype=SourceType.Raw)
                    self.addSubstitute(sub)
                elif match := rx_link_def.match(raw):
                    name = match.group('name')
                    sub = Substitute(f'{name}_', definition=raw, stype=SourceType.Raw)
                    self.addSubstitute(sub)
                else:
                    s = ""

            s = ""

    def updateRST(self, path_rst: Union[str, Path], relative_paths: bool = False):
        path_rst = Path(path_rst)
        assert path_rst.is_file()
        assert path_rst.name.endswith('.rst')

        with open(path_rst, 'r', encoding='utf8') as f:
            lines = f.read().strip()
            if MSG_DO_NOT_EDIT in lines:
                lines = lines.split(MSG_DO_NOT_EDIT)[0].strip()
            lines = lines.splitlines()

        new_lines = []
        s_pattern = re.compile(r'(?<!\.\. )\|([\w\d-]+)\|')
        l_pattern = re.compile(r'[\w\d_-]+_(?=\s|[.:?!]|$)', re.I)
        requested = set()

        for line in lines:

            if line.startswith(MSG_DO_NOT_EDIT):
                break
            else:
                new_lines.append(line)

            for r in s_pattern.findall(line):
                requested.add(r)

            for r in l_pattern.findall(line):
                requested.add(r)

        if len(requested) > 0:
            print(f'Update {path_rst}')
            new_lines += [f'\n\n{MSG_DO_NOT_EDIT}\n']
            for r in sorted(requested):
                if r not in self:
                    raise Exception(f'{path_rst}\nMissing definition for "{r}" in {path_rst}.')
                sub = self[r]
                rst_code = self.toRST(sub,
                                      copy_icon=True,
                                      path_rst=path_rst if relative_paths else None)
                new_lines.append(rst_code)
                s = ""
            # add final newline
            new_lines.append('')
            with open(path_rst, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            s = ""

    def print(self):
        for s in self.mSubstitutes.values():
            print(self.toRST(s))

    def inkscapeBin(self) -> Path:

        if self.mPathInkscapeBin is None:
            self.mPathInkscapeBin = inkscapeBin()
        return self.mPathInkscapeBin

    def toRST(self,
              sub: Substitute,
              copy_icon: bool = False,
              path_rst: Optional[Path] = None) -> str:
        """
        Create the substitute definition
        :param sub: Substitute
        :param copy_icon: set True to copy icon files (*.svg, *.png) into the loca SOURCE/icons directory, if necessary
        :param path_rst: if set to the path of the rst file, the substitute code will use a relative icon path
        :return: str with substitue code, e.g.
            .. |icon| image:: /icons/icon.png
               :width: 28px
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

                    sub.icon_path = path_png
                else:
                    warnings.warn(f'Icon does not exist in rst source folder: {sub.icon_path}')

            if isinstance(path_rst, Path):
                path_rel = sub.icon_path.relative_to(path_rst, walk_up=True)
            else:
                path_rel = sub.icon_path.relative_to(self.mSourceRoot)

            return '\n'.join([
                f'.. |{sub.name}| image:: /{path_rel.as_posix()}',
                f'   :width: {self.mIconSize}px'
            ])

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


MSG_DO_NOT_EDIT = '.. AUTOGENERATED SUBSTITUTIONS - DO NOT EDIT PAST THIS LINE'


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


def update_all():
    collection = SubstituteCollection(DIR_SOURCE)

    path_manual = Path(__file__).parent / 'substitutions.txt'
    collection.addManualDefinitions(path_manual)
    add_api_definitions(collection)
    for d in ICON_DIRS:
        print(f'Read icons from {d}')
        collection.readIcons(d)

    for file in find_by_ext(DIR_SOURCE, 'rst'):
        collection.updateRST(file)

    # collection.print()


if __name__ == '__main__':
    update_all()

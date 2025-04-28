#!/usr/bin/env python3
"""
This script is a modification of
https://github.com/qgis/QGIS-Documentation/blob/master/scripts/find_set_subst.py

It read the source/substitution_*.txt files and each *.rst file.
If a rst file uses substitutions, the substitution definition will be appended to the rst file.
"""
import os
import shutil
import subprocess
from os import path, walk
import re
from os.path import getmtime
from pathlib import Path

import qgis
import qgis.core
import qgis.gui
import qgis.PyQt.QtCore
import qgis.PyQt.QtWidgets
import qgis.PyQt.QtGui
from eotimeseriesviewer import DIR_QGIS_RESOURCES
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search

DIR_REPO = Path(__file__).parents[1]

DIR_SOURCE = DIR_REPO / 'doc/source'
DIR_SUBSTITUTIONS = DIR_SOURCE / 'substitutions'
assert DIR_SOURCE.is_dir()
assert DIR_SUBSTITUTIONS.is_dir()

ENV_INKSCAPE_BIN = 'INKSCAPE_BIN'


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


def find_by_ext(folder, extension):
    """
    create list with absolute paths to all *.extension files inside
    folder and its sub-folders
    """
    found_files = [path.join(dirpath, f)
                   for dirpath, dirnames, files in walk(folder)
                   for f in files if f.endswith('.' + extension)]
    return found_files


def get_subst_from_file(file):
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
            if s_title.match(line) is not None:
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


def get_subst_definition(subst_list, s_dict):
    """
    returns substitution definition from list
    :param subst_list: list of necessary substitutions
    :param s_dict: dictionary with all substitutions
    :return: string with substitution definitions needed to add in rst file
    """
    global file

    s_def = "\n\n.. Substitutions definitions - AVOID EDITING PAST THIS " \
            "LINE\n" \
            "   This will be automatically updated by the find_set_subst.py " \
            "script.\n" \
            "   If you need to create a new substitution manually,\n" \
            "   please add it also to the substitutions.txt file in the\n" \
            "   source folder.\n\n"
    d = s_dict
    s_count = 0
    for subst in subst_list:
        if subst in d:
            s = d[subst]
            if 'image' in s:
                s_def += '.. |{}| image:: {}\n'.format(subst, s['image'])
                if 'width' in s:
                    s_def += '   :width: {}\n'.format(s['width'])
                if 'target' in s:
                    s_def += '   :target: {}\n'.format(s['target'])
            elif 'replace' in s:
                s_def += '.. |{}| replace:: {}\n'.format(subst, s['replace'])
            elif 'unicode' in s:
                s_def += '.. |{}| unicode:: {}\n   :ltrim:\n'.format(subst,
                                                                     s['unicode'])
            s_count += 1
        else:
            print("\033[91m\033[1m|{}|\033[0m is not available in a "
                  "substitution_*.txt file, please add it before use it in "
                  "\033[93m\033[1m{}\033[0m".format(subst, path.relpath(file)))
    if s_count == 0:
        # No substitution found in dict
        s_def = None
    return s_def


def read_subst(file):
    """
    Returns dictionary with all available substitutions
    :param file: file with substitutions in sphinx format
    :return: dictionary with substitutions in more scriptable format
    """
    file: Path = Path(file)

    subs_dict = dict()

    # Create patterns for image, width and replace substitutions
    image_pattern = re.compile(r"\.\. \|([\w\d\s-]+)\|\s+image::\s+([^\n]+)")
    width_pattern = re.compile(r"\s+:width:\s+([^\n]+)")
    target_pattern = re.compile(r"\s+:target:\s+([^\n]+)")
    replace_pattern = re.compile(r"\.\. \|([\w\d\s-]+)\|\s+replace::\s+([^\n]+)")
    unicode_pattern = re.compile(r"\.\. \|([\w\d\s-]+)\|\s+unicode::\s+([^\n]+)")

    # read substitutions file line by line searching for pattern matches
    with open(file) as f:
        for line in f:
            if image_pattern.match(line) is not None:
                # Adds new image object to dictionary
                m = image_pattern.match(line)
                subs_name = m.group(1)
                subs_dict[subs_name] = dict()
                path_rel = Path(m.group(2))
                path_full = DIR_SOURCE / path_rel
                assert path_full.is_file(), f'File: {file}\nImage link does not exist: {path_rel}'
                subs_dict[subs_name]['image'] = '/' + path_rel.as_posix()
            elif width_pattern.match(line) is not None:
                # complements last image object
                m = width_pattern.match(line)
                subs_dict[subs_name]['width'] = m.group(1)
            elif target_pattern.match(line) is not None:
                # complements last image object
                m = target_pattern.match(line)
                subs_dict[subs_name]['target'] = m.group(1)
            elif replace_pattern.match(line) is not None:
                # Adds new replace object to dictionary
                m = replace_pattern.match(line)
                subs_dict[m.group(1)] = dict()
                subs_dict[m.group(1)]['replace'] = m.group(2)
            elif unicode_pattern.match(line) is not None:
                # Adds new unicode replace object to dictionary
                m = unicode_pattern.match(line)
                subs_dict[m.group(1)] = dict()
                subs_dict[m.group(1)]['unicode'] = m.group(2)

    return subs_dict


def append_subst(file, subst_definition):
    """
    Adds substitution definition to the end of rst file
    :param file: path to rst file
    :param subst_definition: string with substitution definitions for file
    :return:
    """
    if subst_definition is not None:
        with open(file, 'a') as f:
            f.write(subst_definition)


def iconRstLink(path):
    path = Path(path)
    return re.sub(r'[ \\.]', '_', path.stem)


def create_icon_substitute_file():
    DIR_ICONS = DIR_SOURCE / 'icons'
    assert DIR_ICONS.is_dir()
    ICONS = dict()

    PATH_INKSCAPE = inkscapeBin()

    rx_extensions = re.compile(r'\.(svg|png)$')

    EOTSV_ICON_DIRS = \
        [DIR_REPO / 'eotimeseriesviewer/ui/icons',
         DIR_REPO / 'eotimeseriesviewer/qgispluginsupport/qps/ui/icons'
         DIR_QGIS_RESOURCES]

    PATH_LINKS_TXT = DIR_SUBSTITUTIONS / 'substitutions_generated.txt'

    for file in file_search(DIR_ICONS, rx_extensions):
        ICONS[iconRstLink(file)] = file

    for iconDir in EOTSV_ICON_DIRS:
        for file in file_search(iconDir, rx_extensions):
            linkName = iconRstLink(file)
            create_icon_png = False
            if linkName not in ICONS:
                create_icon_png = True
            else:
                # compare time stamp
                tSrc = getmtime(file)
                tDocs = getmtime(ICONS[linkName])
                if tSrc > tDocs:
                    create_icon_png = True

            if create_icon_png:
                # print(f'Copy {file}')
                # file2 = DIR_ICONS / basename(file)
                # shutil.copyfile(file, file2)
                # ICONS[linkName] = file2
                path_png = DIR_ICONS / f'{Path(file).stem}.png'
                print(f'Create {path_png}')
                # see https://inkscape.org/doc/inkscape-man.html
                cmd = [
                    #  'inkscape',
                    f'{PATH_INKSCAPE}',
                    '--export-type=png',
                    '--export-area-page',
                    f'--export-filename={path_png}',
                    f'{file}'
                ]
                subprocess.run(cmd, check=True)

    lines = []
    for linkName, path in ICONS.items():
        relPath = Path(path).relative_to(DIR_SOURCE).as_posix()
        lines.append(f'.. |{linkName}| image:: {relPath}\n   :width: 28px')

    # write rst file
    with open(PATH_LINKS_TXT, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(lines))


def create_external_links():
    PATH_LINK_RST = DIR_SUBSTITUTIONS / 'substitutions_links.txt'

    objects = []
    for module in [
        qgis,
        qgis.core,
        qgis.gui,
        qgis.PyQt.QtCore,
        qgis.PyQt.QtWidgets,
        qgis.PyQt.QtGui,
    ]:
        s = ""
        for key in module.__dict__.keys():
            if re.search('^(Qgs|Q)', key):
                objects.append(key)
    objects = sorted(objects)

    lines = """# autogenerated file.

    .. |PyCharm| replace:: `PyCharm <https://www.jetbrains.com/pycharm/>`_
    .. |PyQtGraph| replace:: `PyQtGraph <https://pyqtgraph.readthedocs.io/en/latest/>`_
    .. |PyDev| replace:: `PyDev <https://www.pydev.org>`_
    .. |OSGeo4W| replace:: `OSGeo4W <https://www.osgeo.org/projects/osgeo4w>`_
    .. |Bitbucket| replace:: `Bitbucket <https://bitbucket.org>`_
    .. |Git| replace:: `Git <https://git-scm.com/>`_
    .. |GitHub| replace:: `GitHub <https://github.com/>`_
    .. |GDAL| replace:: `GDAL <https://www.gdal.org>`_
    .. |QtWidgets| replace:: `QtWidgets <https://doc.qt.io/qt-5/qtwidgets-index.html>`_
    .. |QtCore| replace:: `QtCore <https://doc.qt.io/qt-5/qtcore-index.html>`_
    .. |QtGui| replace:: `QtGui <https://doc.qt.io/qt-5/qtgui-index.html>`_
    .. |QGIS| replace:: `QGIS <https://www.qgis.org>`_
    .. |qgis.gui| replace:: `qgis.gui <https://api.qgis.org/api/group__gui.html>`_
    .. |qgis.core| replace:: `qgis.core <https://api.qgis.org/api/group__core.html>`_
    .. |Miniconda| replace:: `Miniconda <https://docs.conda.io/en/latest/miniconda.html>`_
    .. |miniconda| replace:: `miniconda <https://docs.conda.io/en/latest/miniconda.html>`_
    .. |Numba| replace:: `Numba <https://numba.pydata.org/>`_
    .. |Conda| replace:: `Conda <https://docs.anaconda.com/miniconda/>`_
    .. |conda| replace:: `conda <https://docs.anaconda.com/miniconda/>`_
    .. |conda-forge| replace:: `conda-forge <https://conda-forge.org/>`_
    .. |pip| replace:: `pip <https://pip.pypa.io/en/stable>`_

    # autogenerated singular forms
    """

    WRITTEN = []

    rx_qgis = re.compile('^Qgs|Qgis.*')

    for obj in objects:
        obj: str
        if obj in ['QtCore', 'QtGui', 'QtWidget']:
            continue
        print(obj)

        target = None
        if rx_qgis.match(obj):
            # https://qgis.org/api/classQgsProject.html
            target = "https://api.qgis.org/api/class{}.html".format(obj)
        elif obj.startswith('Q'):
            # https://doc.qt.io/qt-5/qwidget.html
            target = "https://doc.qt.io/qt-5/{}.html".format(obj.lower())
        else:
            continue

        singular = obj
        plural = obj + 's'

        line = None
        if singular.upper() not in WRITTEN:
            line = f'.. |{singular}|  replace:: `{singular} <{target}>`_'
            WRITTEN.append(singular.upper())

            if plural.upper() not in WRITTEN:
                line += f'\n.. |{plural}| replace:: `{plural} <{target}>`_'
                WRITTEN.append(plural.upper())

        if line:
            lines += '\n' + line

    with open(PATH_LINK_RST, 'w', encoding='utf-8') as f:
        f.write(lines)


def append_substitute_definitions():
    src_path = DIR_REPO / 'doc/source/substitutions'
    substitution_files = [src_path / 'substitutions_manual.txt',
                          src_path / 'substitutions_generated.txt',
                          ]
    s_dict = dict()
    for p in substitution_files:
        d = read_subst(p)
        s_dict.update(d)
        s = ""
    for file in find_by_ext(DIR_SOURCE, 'rst'):
        s_list = get_subst_from_file(file)
        if len(s_list) > 0:
            s_definition = get_subst_definition(s_list, s_dict)
            append_subst(file, s_definition)


if __name__ == '__main__':
    create_external_links()
    create_icon_substitute_file()
    append_substitute_definitions()

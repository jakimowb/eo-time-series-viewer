import argparse
import copy
import re
import shutil
import site
import pathlib
import sys

from eotimeseriesviewer.qgispluginsupport.qps.resources import findQGISResourceFiles, initResourceFile, scanResources
from eotimeseriesviewer.qgispluginsupport.qps.utils import relativePath

site.addsitedir(pathlib.Path(__file__).parents[1])

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.core import QgsApplication
from eotimeseriesviewer import DIR_REPO, DIR_DOCS, ISSUE_TRACKER, initResources


def update_icons():
    from eotimeseriesviewer import DIR_REPO
    DIR_SOURCE = DIR_REPO / 'doc' / 'source'
    DIR_QGIS_ICONS = DIR_SOURCE / 'img' / 'qgis_icons'
    pathIconLinks = DIR_SOURCE / 'icon_links.rst'

    # load environment
    from eotimeseriesviewer.tests import start_app

    assert DIR_QGIS_ICONS.exists()
    app = None
    if not isinstance(QgsApplication.instance(), QgsApplication):
        app = start_app()

    initResources()
    for f in findQGISResourceFiles():
        initResourceFile(f)

    # get required icons
    rxIcon = re.compile(r'.*\|(?P<name>[^|]+)\|\s*image::.*')
    rxIconSource = re.compile(r'.*(png|svg)$', re.I)
    resourcePaths = list(scanResources())
    resourcePaths = [p for p in resourcePaths if rxIconSource.search(p)]

    assert len(resourcePaths) > 0, 'No resource icons found'
    # |mActionZoomOut| image::

    newLines = []
    iconSize = QSize(64, 64)

    missing = []
    with open(pathIconLinks, 'r', encoding='utf-8') as f:
        for line in f.readlines():
            match = rxIcon.search(line)
            newLine = line
            if match:
                pass
                name = match.group('name')
                if name == 'mActionZoomIn':
                    s = ""
                rxmatch = re.compile(r'.*/' + name + r'.(svg|png)$')
                found = False
                for p in resourcePaths:

                    if rxmatch.search(p):
                        icon: QIcon = QIcon(p)

                        pm: QPixmap = icon.pixmap(iconSize)
                        path = DIR_QGIS_ICONS / f'{name}.png'

                        pm.save(path.as_posix(), format='PNG')
                        assert path.is_file()
                        relPath = relativePath(path, pathIconLinks.parent)
                        newLine = f'.. |{name}| image:: {relPath.as_posix()} \n'
                        found = True
                        break
                if not found:
                    missing.append(line)
            newLines.append(newLine)

    if len(missing) > 0:
        print('Icon sources not found for:', file=sys.stderr)
        print(''.join(missing), file=sys.stderr)
        print(f'Please check manually if they can be removed from {pathIconLinks}')

    with open(pathIconLinks, 'w', encoding='utf8') as f:
        f.writelines(newLines)

    if isinstance(app, QgsApplication):
        app.exit()

    return True


def update_markdown():
    DIR_DOC_SOURCE = DIR_DOCS / 'source'

    def copy_to_dir(file: pathlib.Path, dirpath: pathlib.Path):
        assert file.is_file()
        shutil.copy(file, dirpath / file.name)

    for f in ['CHANGELOG.md', 'ABOUT.md', 'CONTRIBUTORS.md', 'LICENSE.md']:
        copy_to_dir(DIR_REPO / f, DIR_DOC_SOURCE)


def update_documentation():
    update_icons()
    update_markdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Update documentation')
    args = parser.parse_args()
    update_documentation()
    print('Update documentation finished')
    exit(0)

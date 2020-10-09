
import argparse
import re
import site
import pathlib
import sys
site.addsitedir(pathlib.Path(__file__).parents[1])

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.core import QgsApplication
from eotimeseriesviewer import DIR_REPO, DIR_DOCS, ISSUE_TRACKER



def convert_changelog():
    """
    Converts <repo>/CHANGELOG.rst to <repo>/doc/source/changelog.rst
    """
    pathSrc = DIR_REPO / 'CHANGELOG.rst'
    pathDst = DIR_DOCS / 'source' / 'changelog.rst'

    assert pathSrc.is_file()

    with open(pathSrc, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for i in range(len(lines)):
        line = lines[i]
        # convert #104 to
        #         `#104 <https://bitbucket.org/jakimowb/eo-time-series-viewer/issues/104>`_
        line = re.sub(r' #(\d+)', r' `#\1 <{}/\1>`_'.format(ISSUE_TRACKER), line)

        lines[i] = line

    with open(pathDst, 'w', encoding='utf-8') as f:
        f.writelines(lines)

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

    from eotimeseriesviewer.externals.qps.resources import findQGISResourceFiles, scanResources, initResourceFile
    from eotimeseriesviewer import initResources
    from eotimeseriesviewer.utils import relativePath


    initResources()
    for f in findQGISResourceFiles():
        initResourceFile(f)

    # get required icons
    rxIcon = re.compile(r'.*\|(?P<name>[^|]+)\|\s*image::.*')
    rxIconSource = re.compile(r'.*(png|svg)$', re.I)
    resourcePaths = list(scanResources())
    resourcePaths = [p for p in resourcePaths if rxIconSource.search(p)]

    assert len(resourcePaths) > 0, 'No resource icons found'
    #|mActionZoomOut| image::

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
                    s =""
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


def update_documentation():

    convert_changelog()

    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Update documentation')
    args = parser.parse_args()
    update_icons()
    update_documentation()
    print('Update documentation finished')
    exit(0)


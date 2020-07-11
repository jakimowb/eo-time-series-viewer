
import argparse
import re

from eotimeseriesviewer import DIR_REPO, DIR_DOCS, ISSUE_TRACKER
def convert_changelog():
    """
    Converts <repo>/CHANGELOG.rst to <repo>/doc/source/changelog.rst
    """
    pathSrc = DIR_REPO / 'CHANGELOG'
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


def update_documentation():

    convert_changelog()

    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Update documentation')
    args = parser.parse_args()

    update_documentation()
    print('Update documentation finished')
    exit(0)


# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import unittest
import pathlib
import re
import os

from qgis.PyQt.QtGui import QIcon

from eotimeseriesviewer import icon as eotsvIcon, DIR_UI
from eotimeseriesviewer.qgispluginsupport.qps.utils import file_search, scanResources
from eotimeseriesviewer.tests import EOTSVTestCase


class TestResources(EOTSVTestCase):

    def test_icon(self):
        existing = list(scanResources())
        self.assertFalse(eotsvIcon().isNull())
        iconSVGs = file_search(os.path.join(DIR_UI, 'icons'), '*.svg')
        iconSVGs = [pathlib.Path(s).as_posix() for s in iconSVGs]
        iconSVGs = sorted([re.sub(r'^.*/eotimeseriesviewer/ui/icons/', ':/eotimeseriesviewer/icons/', s)
                           for s in iconSVGs])

        unusedSVGs = []
        for resource in iconSVGs:
            if resource not in existing:
                unusedSVGs.append(resource)
            else:
                icon = QIcon(resource)
                self.assertFalse(icon.isNull(), msg=f'unable to load icon {resource}')

        self.assertTrue(len(unusedSVGs) == 0,  msg='Unused resources:\n{}'.format('\n'.join(sorted(unusedSVGs))))


if __name__ == "__main__":
    unittest.main(buffer=False)
    exit(0)



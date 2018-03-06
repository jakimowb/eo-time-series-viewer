# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 : 30.11.2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming



import os, unittest
from timeseriesviewer.utils import initQgisApplication
QGIS_APP = initQgisApplication()

from timeseriesviewer.plotstyling import *


class TestPlotStyling(unittest.TestCase):
    """Test translations work."""


    def test_plotstyles(self):
        s1 = PlotStyle()
        s2 = PlotStyle()

        self.assertEqual(s1,s2)
        s2.markerSize = 3
        self.assertNotEqual(s1,s2)


        #test if we can pickle a plot style
        import pickle

        s2 = pickle.loads(pickle.dumps(s1))
        self.assertEqual(s1,s2)


    def test_dialogs(self):

        s1 = PlotStyle()

        s1.markerPen.setColor(QColor('yellow'))

        s2 = PlotStyle(plotStyle=s1)

        self.assertEqual(s1,s2)



        d = PlotStyleDialog()
        self.assertIsInstance(d, PlotStyleDialog)

        try:
            d.show()
            d.setPlotStyle(s1)
        except Exception:
            self.fail('Unable to initialize PlotStyleDialog')

        self.assertEqual(s1, d.plotStyle())

        try:
            btn = PlotStyleButton()
            btn.show()
        except Exception:
            self.fail('Unable to initialize PlotStyleButton')


if __name__ == "__main__":
    unittest.main()

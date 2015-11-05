# -*- coding: utf-8 -*-
"""
/***************************************************************************
 EnMAPBoxDialog
                                 A QGIS plugin
 EnMAP-Box V3
                             -------------------
        begin                : 2015-08-20
        git sha              : $Format:%H$
        copyright            : (C) 2015 by HU-Berlin
        email                : bj@geo.hu-berlin.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os

from PyQt4 import QtGui, uic

#FORM_CLASS, _ = uic.loadUiType(os.path.join(
#    os.path.dirname(__file__), 'sensecarbon_tsv_gui_base.ui'))

#from enmapbox_gui_base import Ui_EnMAPBoxGUIBase
import six, sys
sys.path.append(os.path.dirname(__file__))
if six.PY3:
    rc_suffix = 'py3'
else:
    rc_suffix = 'py2'

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'sensecarbon_tsv_gui_base.ui'), resource_suffix=rc_suffix)



class SenseCarbon_TSVGui(QtGui.QMainWindow, FORM_CLASS):
#class EnMAPBoxGUI(QtGUI.QMainwindow, Ui_EnMAPBoxGUIBase):
    def __init__(self, parent=None):
        """Constructor."""
        super(SenseCarbon_TSVGui, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

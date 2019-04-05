# coding=utf-8

import os
import unittest
from qgis import *
from qgis.core import *
from qgis.gui import *

from eotimeseriesviewer.tests import *
QGIS_APP = initQgisApplication()


class QGISTest(unittest.TestCase):
    """Test the QGIS Environment"""

    def test_QgsLayerTreeViewDefaultActions(self):
        pass

    def test_mapcanvasbridge(self):

        from eotimeseriesviewer.tests import TestObjects
        layer = TestObjects.createVectorLayer()
        layer2 = TestObjects.createVectorLayer()
        layer2.setName('free layer')
        layer3fix = TestObjects.createVectorLayer()
        layer3fix.setName('Time Series Raster')
        assert isinstance(layer3fix, QgsMapLayer)
        layer3fix.setProperty('eotsv/fixed', True)
        QgsProject.instance().addMapLayers([layer, layer2, layer3fix])
        w = QWidget()
        w.setLayout(QHBoxLayout())

        c = QgsMapCanvas()
        c.setVisible(True)
        c.setLayers([layer])
        c.setDestinationCrs(layer.crs())
        c.setExtent(c.fullExtent())

        ltree = QgsLayerTree()
        bridge = QgsLayerTreeMapCanvasBridge(ltree, c)

        model = QgsLayerTreeModel(ltree)

        model.setFlags(QgsLayerTreeModel.AllowNodeChangeVisibility |
                       QgsLayerTreeModel.AllowNodeRename |
                       QgsLayerTreeModel.AllowNodeReorder)


        class MenuProvider(QgsLayerTreeViewMenuProvider):

            def __init__(self, view:QgsLayerTreeView, canvas:QgsMapCanvas):
                super(MenuProvider, self).__init__()
                assert isinstance(view, QgsLayerTreeView)
                assert isinstance(canvas, QgsMapCanvas)
                self._view = view
                self._canvas = canvas
                self.mDefActions = QgsLayerTreeViewDefaultActions(self._view)

                self.actionAddGroup = self.mDefActions.actionAddGroup()
                self.actionRename = self.mDefActions.actionRenameGroupOrLayer()
                self.actionRemove = self.mDefActions.actionRemoveGroupOrLayer()

            def layerTreeView(self)->QgsLayerTreeView:
                return self._view

            def layerTree(self)->QgsLayerTree:
                return self.layerTreeModel().rootGroup()

            def layerTreeModel(self)->QgsLayerTreeModel:
                return self.layerTreeView().model()

            def onAddGroup(self, *args):
                view = self.layerTreeView()
                l = view.currentLayer()
                i = view.currentIndex()
                view.currentGroupNode().insertGroup(i.row(), 'Group')

            def createContextMenu(self)->QMenu:

                model = self.layerTreeModel()
                ltree = self.layerTree()
                view = self.layerTreeView()
                l = view.currentLayer()
                i = view.currentIndex()
                fixedLayers = [l for l in view.selectedLayersRecursive() if l.property('eotsv/fixed')]
                self.actionRemove.setEnabled(len(fixedLayers) == 0)

                def copyAction(menu:QMenu, action:QAction):

                    a = menu.addAction(action.text())
                    a.setIcon(action.icon())
                    a.triggered.connect(action.trigger)

                menu = QMenu(view)
                #copyAction(menu, self.actionAddGroup)
                menu.addAction(self.actionAddGroup)
                menu.addAction(self.actionRename)
                #copyAction(menu, self.actionRename)

                menu.addAction(self.actionRemove)



                #a = menu.addAction('Settings')
                #from qps.layerproperties import showLayerPropertiesDialog
                #a.triggered.connect(lambda *args, lyr=l:showLayerPropertiesDialog(lyr, self._canvas))

                return menu

        v = QgsLayerTreeView()
        # v.setContextMenuPolicy(Qt.DefaultContextMenu)
        v.setModel(model)
        menuProvider = MenuProvider(v, c)
        v.setMenuProvider(menuProvider)



        ltree.addLayer(layer)
        ltree.addLayer(layer3fix)
        ltree.addLayer(layer2)
        grp = ltree.addGroup('Name')
        grp.addLayer(layer)
        grp.addLayer(layer2)

        w.layout().addWidget(v)
        w.layout().addWidget(c)


        if True:
            w.show()
            QGIS_APP.exec_()

    def test_qgis_environment(self):
        """QGIS environment has the expected providers"""

        r = QgsProviderRegistry.instance()
        self.assertIn('gdal', r.providerList())
        self.assertIn('ogr', r.providerList())
        self.assertIn('postgres', r.providerList())

    def test_projection(self):
        """Test that QGIS properly parses a wkt string.
        """
        crs = QgsCoordinateReferenceSystem()
        wkt = (
            'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
            'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
            'PRIMEM["Greenwich",0.0],UNIT["Degree",'
            '0.0174532925199433]]')
        crs.createFromWkt(wkt)
        auth_id = crs.authid()
        expected_auth_id = 'EPSG:4326'
        self.assertEqual(auth_id, expected_auth_id)


        from example.Images import Img_2014_08_11_LC82270652014223LGN00_BOA
        path = Img_2014_08_11_LC82270652014223LGN00_BOA
        title = 'TestRaster'
        layer = QgsRasterLayer(path, title)
        auth_id = layer.crs().authid()
        self.assertEqual(auth_id, 'EPSG:32621')

if __name__ == '__main__':
    unittest.main()

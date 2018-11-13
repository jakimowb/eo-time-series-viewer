# import qgis libs so that ve set the correct sip api version
import qgis

__package__ = "test"

import os, sys, re, importlib
import qgis
from qgis.gui import *
from qgis.core import *
import qgis.testing
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *



def initQgisApplication(*args, qgisResourceDir:str=None, **kwds)->QgsApplication:
    """
    Initializes a QGIS Environment
    :return: QgsApplication instance of local QGIS installation
    """
    if isinstance(QgsApplication.instance(), QgsApplication):
        return QgsApplication.instance()
    else:

        if not 'QGIS_PREFIX_PATH' in os.environ.keys():
            raise Exception('env variable QGIS_PREFIX_PATH not set')


        if sys.platform == 'darwin':
            # add location of Qt Libraries
            assert '.app' in qgis.__file__, 'Can not locate path of QGIS.app'
            PATH_QGIS_APP = re.search(r'.*\.app', qgis.__file__).group()
            QApplication.addLibraryPath(os.path.join(PATH_QGIS_APP, *['Contents', 'PlugIns']))
            QApplication.addLibraryPath(os.path.join(PATH_QGIS_APP, *['Contents', 'PlugIns', 'qgis']))

        qgsApp = qgis.testing.start_app()

        if not isinstance(qgisResourceDir, str):
            parentDir = os.path.dirname(os.path.dirname(__file__))
            resourceDir = os.path.join(parentDir, 'qgisresources')
            if os.path.exists(resourceDir):
                qgisResourceDir = resourceDir

        if isinstance(qgisResourceDir, str) and os.path.isdir(qgisResourceDir):
            modules = [m for m in os.listdir(qgisResourceDir) if re.search(r'[^_].*\.py', m)]
            modules = [m[0:-3] for m in modules]
            for m in modules:
                mod = importlib.import_module('qgisresources.{}'.format(m))
                if "qInitResources" in dir(mod):
                    mod.qInitResources()

        #initiate a PythonRunner instance if None exists
        if not QgsPythonRunner.isValid():
            r = PythonRunnerImpl()
            QgsPythonRunner.setInstance(r)
        return qgsApp



class PythonRunnerImpl(QgsPythonRunner):
    """
    A Qgs PythonRunner implementation
    """

    def __init__(self):
        super(PythonRunnerImpl, self).__init__()


    def evalCommand(self, cmd:str, result:str):
        try:
            o = compile(cmd)
        except Exception as ex:
            result = str(ex)
            return False
        return True

    def runCommand(self, command, messageOnError=''):
        try:
            o = compile(command, 'fakemodule', 'exec')
            exec(o)
        except Exception as ex:
            messageOnError = str(ex)
            command = ['{}:{}'.format(i+1, l) for i,l in enumerate(command.splitlines())]
            print('\n'.join(command), file=sys.stderr)
            raise ex
            return False
        return True

class QgisMockup(QgisInterface):
    """
    A "fake" QGIS Desktop instance that should provide all the inferfaces a plugin developer might need (and nothing more)
    """

    def pluginManagerInterface(self)->QgsPluginManagerInterface:
        return self.mPluginManager

    @staticmethod
    def create()->QgisInterface:
        """
        Create the QgisMockup and sets the global variables
        :return: QgisInterface
        """

        iface = QgisMockup()

        import qgis.utils
        # import processing
        # p = processing.classFactory(iface)
        if not isinstance(qgis.utils.iface, QgisInterface):

            import processing
            qgis.utils.iface = iface
            processing.Processing.initialize()

            import pkgutil
            prefix = str(processing.__name__ + '.')
            for importer, modname, ispkg in pkgutil.walk_packages(processing.__path__, prefix=prefix):
                try:
                    module = __import__(modname, fromlist="dummy")
                    if hasattr(module, 'iface'):
                        print(modname)
                        module.iface = iface
                except:
                    pass
        #set 'home_plugin_path', which is required from the QGIS Plugin manager
        assert qgis.utils.iface == iface
        qgis.utils.home_plugin_path = os.path.join(QgsApplication.instance().qgisSettingsDirPath(), *['python', 'plugins'])
        return iface

    def __init__(self, *args):
        # QgisInterface.__init__(self)
        super(QgisMockup, self).__init__()

        self.mCanvas = QgsMapCanvas()
        self.mCanvas.blockSignals(False)
        self.mCanvas.setCanvasColor(Qt.black)
        self.mCanvas.extentsChanged.connect(self.testSlot)
        self.mLayerTreeView = QgsLayerTreeView()
        self.mRootNode = QgsLayerTree()
        self.mLayerTreeModel = QgsLayerTreeModel(self.mRootNode)
        self.mLayerTreeView.setModel(self.mLayerTreeModel)
        self.mLayerTreeMapCanvasBridge = QgsLayerTreeMapCanvasBridge(self.mRootNode, self.mCanvas)
        self.mLayerTreeMapCanvasBridge.setAutoSetupOnFirstLayer(True)

        import pyplugin_installer.installer
        PI = pyplugin_installer.instance()
        self.mPluginManager = QgsPluginManagerMockup()

        self.ui = QMainWindow()



        self.mMessageBar = QgsMessageBar()
        mainFrame = QFrame()

        self.ui.setCentralWidget(mainFrame)
        self.ui.setWindowTitle('QGIS Mockup')


        l = QHBoxLayout()
        l.addWidget(self.mLayerTreeView)
        l.addWidget(self.mCanvas)
        v = QVBoxLayout()
        v.addWidget(self.mMessageBar)
        v.addLayout(l)
        mainFrame.setLayout(v)
        self.ui.setCentralWidget(mainFrame)
        self.lyrs = []
        self.createActions()

    def iconSize(self, dockedToolbar=False):
        return QSize(30,30)

    def testSlot(self, *args):
        # print('--canvas changes--')
        s = ""

    def mainWindow(self):
        return self.ui


    def addToolBarIcon(self, action):
        assert isinstance(action, QAction)

    def removeToolBarIcon(self, action):
        assert isinstance(action, QAction)


    def addVectorLayer(self, path, basename=None, providerkey=None):
        if basename is None:
            basename = os.path.basename(path)
        if providerkey is None:
            bn, ext = os.path.splitext(basename)

            providerkey = 'ogr'
        l = QgsVectorLayer(path, basename, providerkey)
        assert l.isValid()
        QgsProject.instance().addMapLayer(l, True)
        self.mRootNode.addLayer(l)
        self.mLayerTreeMapCanvasBridge.setCanvasLayers()
        s = ""

    def legendInterface(self):
        return None

    def addRasterLayer(self, path, baseName=''):
        l = QgsRasterLayer(path, os.path.basename(path))
        self.lyrs.append(l)
        QgsProject.instance().addMapLayer(l, True)
        self.mRootNode.addLayer(l)
        self.mLayerTreeMapCanvasBridge.setCanvasLayers()
        return

        cnt = len(self.canvas.layers())

        self.canvas.setLayerSet([QgsMapCanvasLayer(l)])
        l.dataProvider()
        if cnt == 0:
            self.canvas.mapSettings().setDestinationCrs(l.crs())
            self.canvas.setExtent(l.extent())

            spatialExtent = SpatialExtent.fromMapLayer(l)
            # self.canvas.blockSignals(True)
            self.canvas.setDestinationCrs(spatialExtent.crs())
            self.canvas.setExtent(spatialExtent)
            # self.blockSignals(False)
            self.canvas.refresh()

        self.canvas.refresh()

    def createActions(self):
        m = self.ui.menuBar().addAction('Add Vector')
        m = self.ui.menuBar().addAction('Add Raster')

    def mapCanvas(self):
        return self.mCanvas

    def mapNavToolToolBar(self):
        super().mapNavToolToolBar()

    def messageBar(self, *args, **kwargs):
        return self.mMessageBar

    def rasterMenu(self):
        super().rasterMenu()

    def vectorMenu(self):
        super().vectorMenu()

    def viewMenu(self):
        super().viewMenu()

    def windowMenu(self):
        super().windowMenu()

    def zoomFull(self, *args, **kwargs):
        super().zoomFull(*args, **kwargs)


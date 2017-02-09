import os
import sys

from qgis.gui import *
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtXml import *
from PyQt4.QtGui import *

from timeseriesviewer import jp, SETTINGS
from timeseriesviewer.timeseries import *
from timeseriesviewer.ui.docks import TsvDockWidgetBase, load
import pyqtgraph as pg
from osgeo import gdal, gdal_array
import numpy as np


class DateAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(DateAxis, self).__init__(*args, **kwds)

    def logTickStrings(self, values, scale, spacing):
        s = ""

    def tickStrings(self, values, scale, spacing):
        strns = []
        rng = max(values)-min(values)
        #if rng < 120:
        #    return pg.AxisItem.tickStrings(self, values, scale, spacing)
        if rng < 3600*24:
            string = '%H:%M:%S'
            label1 = '%b %d -'
            label2 = ' %b %d, %Y'
        elif rng >= 3600*24 and rng < 3600*24*30:
            string = '%d'
            label1 = '%b - '
            label2 = '%b, %Y'
        elif rng >= 3600*24*30 and rng < 3600*24*30*24:
            string = '%b'
            label1 = '%Y -'
            label2 = ' %Y'
        elif rng >=3600*24*30*24:
            string = '%Y'
            label1 = ''
            label2 = ''
        for x in values:
            try:
                strns.append(time.strftime(string, time.localtime(x)))
            except ValueError:  ## Windows can't handle dates before 1970
                strns.append('')
        try:
            label = time.strftime(label1, time.localtime(min(values)))+time.strftime(label2, time.localtime(max(values)))
        except ValueError:
            label = ''
        #self.setLabel(text=label)
        return strns



class PixelLoadWorker(QObject):
    #qRegisterMetaType
    sigPixelLoaded = pyqtSignal(dict)

    sigWorkStarted = pyqtSignal(int)

    sigWorkFinished = pyqtSignal()

    def __init__(self, files, parent=None):
        super(PixelLoadWorker, self).__init__(parent)
        assert isinstance(files, list)
        self.files = files

    def info(self):
        return 'recent file {}'.format(self.recentFile)

    @pyqtSlot(str, str)
    def doWork(self, theGeometryWkt, theCrsDefinition):

        g = QgsGeometry.fromWkt(theGeometryWkt)
        if g.wkbType() == QgsWKBTypes.Point:
            g = g.asPoint()
        elif g.wkbType() == QgsWKBTypes.Polygon:
            g = g.asPolygon()
        else:
            raise NotImplementedError()



        crs = QgsCoordinateReferenceSystem(theCrsDefinition)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        paths = self.files
        self.sigWorkStarted.emit(len(paths))

        for i, path in enumerate(paths):
            self.recentFile = path

            lyr = QgsRasterLayer(path)
            dp = lyr.dataProvider()

            trans = QgsCoordinateTransform(crs, dp.crs())
            #todo: add with QGIS 3.0
            #if not trans.isValid():
            #    self.sigPixelLoaded.emit({})
            #    continue

            try:
                geo = trans.transform(g)
            except(QgsCsException):
                self.sigPixelLoaded.emit({})
                continue

            ns = dp.xSize()  # ns = number of samples = number of image columns
            nl = dp.ySize()  # nl = number of lines
            ex = dp.extent()

            xres = ex.width() / ns  # pixel size
            yres = ex.height() / nl

            if not ex.contains(geo):
                self.sigPixelLoaded.emit({})
                continue

            def geo2px(x, y):
                x = int(np.floor((x - ex.xMinimum()) / xres).astype(int))
                y = int(np.floor((ex.yMaximum() - y) / yres).astype(int))
                return x, y

            if isinstance(geo, QgsPoint):
                px_x, px_y = geo2px(geo.x(), geo.y())

                size_x = 1
                size_y = 1
                UL = geo
            elif isinstance(geo, QgsRectangle):

                px_x, px_y = geo2px(geo.xMinimum(), geo.yMaximum())
                px_x2, px_y2 = geo2px(geo.xMaximum(), geo.yMinimum())
                size_x = px_x2 - px_x
                size_y = px_y2 - px_y
                UL = QgsPoint(geo.xMinimum(), geo.yMaximum())

            ds = gdal.Open(path)
            if ds is None:
                self.sigPixelLoaded.emit({})
                continue
            nb = ds.RasterCount
            values = gdal_array.DatasetReadAsArray(ds, px_x, px_y, win_xsize=size_x, win_ysize=size_y)

            nodata = [ds.GetRasterBand(b+1).GetNoDataValue() for b in range(nb)]


            md = dict()
            md['_worker_'] = self.objectName()
            md['_thread_'] = QThread.currentThread().objectName()
            md['_wkt_'] = theGeometryWkt
            md['path'] = path
            md['xres'] = xres
            md['yres'] = xres
            md['geo_ul_x'] = UL.x()
            md['geo_ul_y'] = UL.y()
            md['px_ul_x'] = px_x
            md['px_ul_y'] = px_y
            md['values'] = values
            md['nodata'] = nodata

            self.sigPixelLoaded.emit(md)
        self.recentFile = None
        self.sigWorkFinished.emit()




class PixelLoader(QObject):


    sigPixelLoaded = pyqtSignal(int, int, dict)
    sigLoadingStarted = pyqtSignal()
    sigLoadingDone = pyqtSignal()
    sigLoadingFinished = pyqtSignal()
    sigLoadingCanceled = pyqtSignal()
    _sigLoadCoordinate = pyqtSignal(str, str)

    def __init__(self, *args, **kwds):
        super(PixelLoader, self).__init__(*args, **kwds)

        self.nThreads = 1
        self.nMax = 0
        self.nDone = 0
        self.threadsAndWorkers = []

    @QtCore.pyqtSlot(dict)
    def onPixelLoaded(self, d):
        self.nDone += 1
        self.sigPixelLoaded.emit(self.nDone, self.nMax, d)

        if self.nDone == self.nMax:
            self.sigLoadingFinished.emit()


    def setNumberOfThreads(self, nThreads):
        assert nThreads >= 1
        self.nThreads = nThreads

    def threadInfo(self):
        info = []
        info.append('done: {}/{}'.format(self.nDone, self.nMax))
        for i, t in enumerate(self.threads):
            info.append('{}: {}'.format(i, t.info() ))

        return '\n'.join(info)

    def cancelLoading(self):
        for t in self.threadsAndWorkers:
            thread, worker = t
            thread.quit()
        del self.threadsAndWorkers[:]

        for t,w in self.workerThreads.items():
            w.stop()
            t.quit()
            t.deleteLater()
            self.workerThreads.pop(t)
        self.nMax = self.nDone = None
        self.sigLoadingCanceled.emit()

    def removeFinishedThreads(self):

        toRemove = []
        for i, t in enumerate(self.threadsAndWorkers):
            thread, worker = t
            if thread.isFinished():
                thread.quit()
                toRemove.append(t)
        for t in toRemove:
            self.threadsAndWorkers.remove(t)

    def startLoading(self, pathList, theGeometry, crs):
        self.removeFinishedThreads()
        self.sigLoadingStarted.emit()

        assert isinstance(pathList, list)

        if isinstance(theGeometry, QgsPoint):
            theGeometry = QgsPointV2(theGeometry)
        elif isinstance(theGeometry, QgsRectangle):
            theGeometry = QgsPolygonV2(theGeometry.asWktPolygon())
        assert type(theGeometry) in [QgsPointV2, QgsPolygonV2]


        wkt = theGeometry.asWkt(50)


        l = len(pathList)
        self.nMax = l
        self.nFailed = 0
        self.nDone = 0

        nThreads = self.nThreads
        filesPerThread = int(np.ceil(float(l) / nThreads))

        if True:
            worker = PixelLoadWorker(pathList[0:1])
            worker.doWork(wkt, str(crs.authid()))

        n = 0
        files = pathList[:]

        while len(files) > 0:
            n += 1

            i = min([filesPerThread, len(files)])
            thread = QThread()
            thread.setObjectName('Thread {}'.format(n))
            thread.finished.connect(self.removeFinishedThreads)
            thread.terminated.connect(self.removeFinishedThreads)

            worker = PixelLoadWorker(files[0:i])
            worker.setObjectName('W {}'.format(n))
            worker.moveToThread(thread)
            worker.sigPixelLoaded.connect(self.onPixelLoaded)
            worker.sigWorkFinished.connect(thread.quit)
            self._sigLoadCoordinate.connect(worker.doWork)
            thread.start()
            self.threadsAndWorkers.append((thread, worker))
            del files[0:i]

        #stark the workers

        self._sigLoadCoordinate.emit(theGeometry.asWkt(50), str(crs.authid()))


class ProfilePoint(pg.GraphicsObject):
    """
    This class draws a rectangular area. Right-clicking inside the area will
    raise a custom context menu which also includes the context menus of
    its parents.
    """

    def __init__(self, name):
        self.name = name
        self.pen = pg.mkPen('r')

        # menu creation is deferred because it is expensive and often
        # the user will never see the menu anyway.
        self.menu = None

        # note that the use of super() is often avoided because Qt does not
        # allow to inherit from multiple QObject subclasses.
        pg.GraphicsObject.__init__(self)


        # All graphics items must have paint() and boundingRect() defined.

    def boundingRect(self):
        return QtCore.QRectF(0, 0, 10, 10)

    def paint(self, p, *args):
        p.setPen(self.pen)
        p.drawRect(self.boundingRect())

    # On right-click, raise the context menu
    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            if self.raiseContextMenu(ev):
                ev.accept()

    def raiseContextMenu(self, ev):
        menu = self.getContextMenus()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))
        return True

    # This method will be called when this item's _children_ want to raise
    # a context menu that includes their parents' menus.
    def getContextMenus(self, event=None):
        if self.menu is None:
            self.menu = QtGui.QMenu()
            self.menu.setTitle(self.name + " options..")

            green = QtGui.QAction("Turn green", self.menu)
            green.triggered.connect(self.setGreen)
            self.menu.addAction(green)
            self.menu.green = green

            blue = QtGui.QAction("Turn blue", self.menu)
            blue.triggered.connect(self.setBlue)
            self.menu.addAction(blue)
            self.menu.green = blue

            alpha = QtGui.QWidgetAction(self.menu)
            alphaSlider = QtGui.QSlider()
            alphaSlider.setOrientation(QtCore.Qt.Horizontal)
            alphaSlider.setMaximum(255)
            alphaSlider.setValue(255)
            alphaSlider.valueChanged.connect(self.setAlpha)
            alpha.setDefaultWidget(alphaSlider)
            self.menu.addAction(alpha)
            self.menu.alpha = alpha
            self.menu.alphaSlider = alphaSlider
        return self.menu


class PlotSettingsWidgetDelegate(QStyledItemDelegate):

    def __init__(self, tableView, parent=None):

        super(PlotSettingsWidgetDelegate, self).__init__(parent=parent)
        self._preferedSize = QgsFieldExpressionWidget().sizeHint()
        self.tableView = tableView

    def getColumnName(self, index):
        assert index.isValid()
        assert isinstance(index.model(), PlotSettingsModel)
        return index.model().columnames[index.column()]
    """
    def sizeHint(self, options, index):
        s = super(ExpressionDelegate, self).sizeHint(options, index)
        exprString = self.tableView.model().data(index)
        l = QLabel()
        l.setText(exprString)
        x = l.sizeHint().width() + 100
        s = QSize(x, s.height())
        return self._preferedSize
    """

    def createEditor(self, parent, option, index):
        cname = self.getColumnName(index)
        if cname == 'y-value':
            w = QgsFieldExpressionWidget(parent)
            sv = self.tableView.model().data(index, Qt.UserRole)
            w.setLayer(sv.memLyr)
            w.setExpressionDialogTitle('Values sensor {}'.format(sv.sensor.sensorName))
            w.setToolTip('Set values shown for sensor {}'.format(sv.sensor.sensorName))
            w.fieldChanged.connect(lambda : self.commitExpression(w, w.expression()))
        elif cname == 'style':
            sv = self.tableView.model().data(index, Qt.UserRole)
            sn = sv.sensor.sensorName
            w = QgsColorButton(parent, 'Point color {}'.format(sn))
            w.setColor(QColor(index.data()))
            w.colorChanged.connect(lambda: self.commitData.emit(w))
        else:
            raise NotImplementedError()
        return w

    def commitExpression(self, w, expression):

        assert expression == w.expression()
        assert w.isExpressionValid(expression) == w.isValidExpression()

        if w.isValidExpression():
            self.commitData.emit(w)
        else:
            print(('Delegate commit failed',w.asExpression()))


    def setEditorData(self, editor, index):
        cname = self.getColumnName(index)
        if cname == 'y-value':
            lastExpr = index.model().data(index, Qt.DisplayRole)
            assert isinstance(editor, QgsFieldExpressionWidget)
            #print(('Set expr2editor', lastExpr))
            editor.setProperty('lastexpr', lastExpr)
            editor.setField(lastExpr)
        elif cname == 'style':
            lastColor = index.data()
            assert isinstance(editor, QgsColorButton)
            assert isinstance(lastColor, QColor)
            editor.setColor(QColor(lastColor))
        else:
            raise NotImplementedError()

    def setModelData(self, w, model, index):
        cname = self.getColumnName(index)
        if cname == 'y-value':
            assert isinstance(w, QgsFieldExpressionWidget)
            assert w.isValidExpression()
            expr = w.expression()
            exprLast = model.data(index, Qt.DisplayRole)

            if expr != exprLast:
                model.setData(index, w.expression(), Qt.DisplayRole)
        elif cname == 'style':
            assert isinstance(w, QgsColorButton)
            if index.data() != w.color():
                model.setData(index, w.color(), Qt.DisplayRole)
        else:
            raise NotImplementedError()

class PixelCollection(QObject):
    """
    Object to store pixel data returned by PixelLoader
    """

    sigSensorAdded = pyqtSignal(SensorInstrument)
    sigSensorRemoved = pyqtSignal(SensorInstrument)
    sigPixelAdded = pyqtSignal()
    sigPixelRemoved = pyqtSignal()



    def __init__(self, timeSeries):
        assert isinstance(timeSeries, TimeSeries)
        super(PixelCollection, self).__init__()

        self.TS = timeSeries
        self.sensors = []
        self.sensorPxLayers = dict()


    def getFieldDefn(self, name, values):
        if isinstance(values, np.ndarray):
            # add bands
            if values.dtype in [np.int8, np.int16, np.int32, np.int64,
                                np.uint8, np.uint16, np.uint32, np.uint64]:
                fType = QVariant.Int
                fTypeName = 'integer'
            elif values.dtype in [np.float16, np.float32, np.float64]:
                fType = QVariant.Double
                fTypeName = 'decimal'
        else:
            raise NotImplementedError()

        return QgsField(name, fType, fTypeName)

    def setFeatureAttribute(self, feature, name, value):
        assert isinstance(feature, QgsFeature)
        assert isinstance(name, str)
        i = feature.fieldNameIndex(name)
        assert i >= 0
        field = feature.fields()[i]
        if field.isNumeric():
            if field.type() == QVariant.Int:
                value = int(value)
            elif field.type() == QVariant.Double:
                value = float(value)
            else:
                raise NotImplementedError()
        feature.setAttribute(i, value)


    def addPixel(self, d):
        assert isinstance(d, dict)
        if len(d) > 0:
            tsd = self.TS.getTSD(d['path'])
            values = d['values']
            nodata = np.asarray(d['nodata'])

            nb, nl, ns = values.shape
            assert nb >= 1

            assert isinstance(tsd, TimeSeriesDatum)
            if tsd.sensor not in self.sensorPxLayers.keys():
                #create new temp layer
                mem = QgsVectorLayer('point', 'Pixels_sensor_'+tsd.sensor.sensorName, 'memory')

                self.sensorPxLayers[tsd.sensor] = mem
                assert mem.startEditing()

                #standard field names, types, etc.
                fieldDefs = [('date',QVariant.String, 'char'),
                             ('doy', QVariant.Int, 'integer'),
                             ('geo_x', QVariant.Double, 'decimal'),
                             ('geo_y', QVariant.Double, 'decimal'),
                             ('px_x', QVariant.Int, 'integer'),
                             ('px_y', QVariant.Int, 'integer'),
                             ]
                for fieldDef in fieldDefs:
                    field = QgsField(fieldDef[0], fieldDef[1], fieldDef[2])
                    mem.addAttribute(field)

                for i in range(nb):
                    fName = 'b{}'.format(i+1)
                    mem.addAttribute(self.getFieldDefn(fName, values))
                assert mem.commitChanges()



                self.sigSensorAdded.emit(tsd.sensor)
                s = ""

            mem = self.sensorPxLayers[tsd.sensor]


            #insert each single pixel, line by line
            xres = d['xres']
            yres = d['yres']
            geo_ul_x = d['geo_ul_x']
            geo_ul_y = d['geo_ul_y']
            px_ul_x = d['px_ul_x']
            px_ul_y = d['px_ul_y']

            doy = tsd.doy
            for i in range(ns):
                geo_x = geo_ul_x + xres * i
                px_x = px_ul_x + i
                for j in range(nl):
                    geo_y = geo_ul_y + yres * j
                    px_y = px_ul_y + j
                    profile = values[:,j,i]

                    if np.any(np.any(profile == nodata)):
                        continue


                    geometry = QgsPointV2(geo_x, geo_y)

                    feature = QgsFeature(mem.fields())

                    #fnames = [f.name() for f in mem.fields()]

                    feature.setGeometry(QgsGeometry(geometry))
                    feature.setAttribute('date', str(tsd.date))
                    feature.setAttribute('doy', doy)
                    feature.setAttribute('geo_x', geo_x)
                    feature.setAttribute('geo_y', geo_y)
                    feature.setAttribute('px_x', px_x)
                    feature.setAttribute('px_y', px_y)
                    for b in range(nb):
                        name ='b{}'.format(b+1)
                        self.setFeatureAttribute(feature, name, profile[b])
                    mem.startEditing()
                    assert mem.addFeature(feature)
                    assert mem.commitChanges()

            #each pixel is a new feature
            self.sigPixelAdded.emit()

        pass



    def clear(self):
        for sensor in self.sensorPxLayers.keys():
            self.sigSensorRemoved.emit(sensor)
        self.sigPixelRemoved.emit()

    def dateValues(self, sensor, expression):
        if sensor not in self.sensorPxLayers.keys():
            return []
        mem = self.sensorPxLayers[sensor]
        dp = mem.dataProvider()
        exp = QgsExpression(expression)
        exp.prepare(dp.fields())

        possibleTsds = self.TS.getTSDs(sensorOfInterest=sensor)


        tsds = []
        values =  []

        if exp.isValid():
            mem.selectAll()
            for feature in mem.selectedFeatures():
                date = np.datetime64(feature.attribute('date'))
                y = exp.evaluatePrepared(feature)
                if y is not None:
                    tsd = next(tsd for tsd in possibleTsds if tsd.date == date)
                    tsds.append(tsd)
                    values.append(y)
                else:
                    print(exp.evalErrorString())

        return tsds, values

class SensorPlotSettings(object):
    def __init__(self, sensor, memoryLyr):

        assert isinstance(sensor, SensorInstrument)
        assert isinstance(memoryLyr, QgsVectorLayer)
        self.sensor = sensor
        self.expression = u'"b1"'
        self.color = QColor('green')
        self.isVisible = True
        self.memLyr = memoryLyr


class PlotSettingsModel(QAbstractTableModel):

    sigSensorAdded = pyqtSignal(SensorPlotSettings)
    sigVisiblityChanged = pyqtSignal(SensorPlotSettings)

    columnames = ['sensor','nb','style','y-value']
    def __init__(self, pxCollection, parent=None, *args):

        #assert isinstance(tableView, QTableView)

        super(PlotSettingsModel, self).__init__()

        self.items = []

        self.sortColumnIndex = 0
        self.sortOrder = Qt.AscendingOrder
        self.pxCollection = pxCollection
        self.pxCollection.sigSensorAdded.connect(self.addSensor)
        #self.pxCollection.sigSensorRemoved.connect(self.removeSensor)

        self.sort(0, Qt.AscendingOrder)
        s = ""
        self.dataChanged.connect(self.signaler)

    def testSlot(self, *args):
        print('TESTSLOT')
        s = ""

    def signaler(self, idxUL, idxLR):
        if idxUL.isValid():
            cname = self.columnames[idxUL.column()]
            if cname in ['style', 'sensor','y-value']:
                sensorView = self.getSensorFromIndex(idxUL)
                self.sigVisiblityChanged.emit(sensorView)


    def addSensor(self, sensor):
        assert isinstance(sensor, SensorInstrument)
        assert sensor in self.pxCollection.sensorPxLayers.keys()
        sensorSettings = SensorPlotSettings(sensor, self.pxCollection.sensorPxLayers[sensor])

        i = len(self.items)
        idx = self.createIndex(i,i, sensorSettings)
        self.beginInsertRows(QModelIndex(),i,i)
        self.items.append(sensorSettings)
        self.endInsertRows()
        #self.sort(self.sortColumnIndex, self.sortOrder)

        self.sigSensorAdded.emit(sensorSettings)


    def sort(self, col, order):
        if self.rowCount() == 0:
            return


        colName = self.columnames[col]
        r = order != Qt.AscendingOrder

        #self.beginMoveRows(idxSrc,

        if colName == 'sensor':
            self.items.sort(key = lambda sv:sv.sensor.sensorName, reverse=r)
        elif colName == 'nb':
            self.items.sort(key=lambda sv: sv.sensor.nb, reverse=r)
        elif colName == 'y-value':
            self.items.sort(key=lambda sv: sv.expression, reverse=r)
        elif colName == 'style':
            self.items.sort(key=lambda sv: sv.color, reverse=r)





    def rowCount(self, parent = QModelIndex()):
        return len(self.items)


    def removeRows(self, row, count , parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row+count-1)
        toRemove = self.items[row:row+count]
        for tsd in toRemove:
            self.items.remove(tsd)
        self.endRemoveRows()

    def getIndexFromSensor(self, sensor):
        sensorViews = [i for i, s in enumerate(self.items) if s.sensor == sensor]
        assert len(sensorViews) == 1
        return self.createIndex(sensorViews[0],0)

    def getSensorFromIndex(self, index):
        if index.isValid():
            return self.items[index.row()]
        return None

    def columnCount(self, parent = QModelIndex()):
        return len(self.columnames)

    def data(self, index, role = Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        value = None
        columnName = self.columnames[index.column()]
        sw = self.getSensorFromIndex(index)
        #print(('data', columnName, role))
        if role == Qt.DisplayRole:
            if columnName == 'sensor':
                value = sw.sensor.sensorName
            elif columnName == 'nb':
                value = str(sw.sensor.nb)
            elif columnName == 'y-value':
                value = sw.expression
            elif columnName == 'style':
                value = QColor(sw.color)

        elif role == Qt.CheckStateRole:
            if columnName == 'sensor':
                value = Qt.Checked if sw.isVisible else Qt.Unchecked
        elif role == Qt.UserRole:
            value = sw
        #print(('get data',value))
        return value

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return False
        #print(('Set data', index.row(), index.column(), value, role))
        columnName = self.columnames[index.column()]

        result = False
        sw = self.getSensorFromIndex(index)
        if role in [Qt.DisplayRole, Qt.EditRole]:
            if columnName == 'y-value':
                sw.expression = value
                result = True
            elif columnName == 'style':
                if isinstance(value, QColor):
                    sw.color = value
                    result = True

        if role == Qt.CheckStateRole:
            if columnName == 'sensor':
                sw.isVisible = value == Qt.Checked
                result = True


        if result:
            self.dataChanged.emit(index, index)

        return result

    def flags(self, index):
        if index.isValid():
            columnName = self.columnames[index.column()]
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if columnName == 'sensor':
                flags = flags | Qt.ItemIsUserCheckable

            if columnName in ['y-value']: #allow check state
                flags = flags | Qt.ItemIsEditable
            return flags
            #return item.qt_flags(index.column())
        return Qt.NoItemFlags

    def headerData(self, col, orientation, role):
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None



class ProfileViewDockUI(TsvDockWidgetBase, load('profileviewdock.ui')):
    def __init__(self, parent=None):
        super(ProfileViewDockUI, self).__init__(parent)
        self.setupUi(self)
        from timeseriesviewer import OPENGL_AVAILABLE, SETTINGS
        if OPENGL_AVAILABLE:
            l = self.page3D.layout()
            l.removeWidget(self.labelDummy3D)
            from pyqtgraph.opengl import GLViewWidget
            self.plotWidget3D = GLViewWidget(self.page3D)
            l.addWidget(self.plotWidget3D)
        else:
            self.plotWidget3D = None

        pi = self.plotWidget2D.plotItem
        ax = DateAxis(orientation='bottom', showValues=True)
        pi.layout.addItem(ax, 3,2)

        self.baseTitle = self.windowTitle()
        self.TS = None
        self.pxCollection = None
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)
        self.progressInfo.setText('')
        self.pxViewModel2D = None
        self.pxViewModel3D = None
        self.pixelLoader = PixelLoader()
        self.pixelLoader.sigPixelLoaded.connect(self.onPixelLoaded)
        self.pixelCollection = None
        self.tableView2DBands.horizontalHeader().setResizeMode(QHeaderView.ResizeToContents)
        self.tableView2DBands.setSortingEnabled(True)
        self.btnRefresh2D.setDefaultAction(self.actionRefresh2D)

    def connectTimeSeries(self, TS):

        assert isinstance(TS, TimeSeries)
        self.TS = TS
        self.pixelCollection = PixelCollection(self.TS)
        self.spectralTempVis = SpectralTemporalVisualization(self.pixelCollection, self.tableView2DBands, self.plotWidget2D)
        self.actionRefresh2D.triggered.connect(lambda : self.spectralTempVis.refresh())
        self.pixelLoader.sigLoadingStarted.connect(self.pixelCollection.clear)
        self.pixelLoader.sigLoadingFinished.connect(lambda : QTimer.singleShot(200, lambda : self.spectralTempVis.refresh()))


    def onPixelLoaded(self, nDone, nMax, d):
        self.progressBar.setValue(nDone)
        self.progressBar.setMaximum(nMax)
        t = ''
        if len(d) > 0:
            t = 'Last loaded from {}.'.format(os.path.basename(d['path']))
            QgsApplication.processEvents()
            if self.pixelCollection is not None:
                self.pixelCollection.addPixel(d)
        self.progressInfo.setText(t)



    def loadCoordinate(self, coordinate, crs):

        assert isinstance(coordinate, QgsPoint)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        from timeseriesviewer.timeseries import TimeSeries
        assert isinstance(self.TS, TimeSeries)

        self.setWindowTitle('{} | {} {}'.format(self.baseTitle, str(coordinate), crs.authid()))
        self.pixelLoader.setNumberOfThreads(SETTINGS.value('n_threads', 1))
        #shoudl we allow to keep pixels in memory, e.g. limited by buffer?
        if self.pxCollection is not None:
            self.pxCollection.clear()
        files = [d.pathImg for d in self.TS.data]
        self.progressInfo.setText('Start loading from {} images...'.format(len(files)))
        self.pixelLoader.startLoading(files, coordinate, crs)


class SpectralTemporalVisualization(QObject):

    sigShowPixel = pyqtSignal(TimeSeriesDatum, QgsPoint, QgsCoordinateReferenceSystem)

    def __init__(self, pixelCollection, tableView, graphic2D):
        super(SpectralTemporalVisualization, self).__init__()
        #assert isinstance(timeSeries, TimeSeries)
        assert isinstance(tableView, QTableView)
        assert isinstance(graphic2D, pg.PlotWidget)
        assert isinstance(pixelCollection, PixelCollection)
        #self.TS = timeSeries
        self.TV = tableView
        self.TV.setSortingEnabled(False)
        self.plot2D = graphic2D
        self.pxCollection = pixelCollection
        self.plotSettingsModel = PlotSettingsModel(self.pxCollection)
        self.plotSettingsModel.sigSensorAdded.connect(self.refresh)
        #self.plotSettingsModel.sigVisiblityChanged.connect(self.setVisibility)

        self.plotSettingsModel.sigVisiblityChanged.connect(self.refresh)
        self.plotSettingsModel.rowsInserted.connect(self.onRowsInserted)
        self.TV.setModel(self.plotSettingsModel)
        self.delegate = PlotSettingsWidgetDelegate(self.TV)
        self.TV.setItemDelegateForColumn(2, self.delegate)
        self.TV.setItemDelegateForColumn(3, self.delegate)
        #self.TV.setItemDelegateForColumn(3, PointStyleDelegate(self.TV))
        for s in self.pxCollection.sensorPxLayers.keys():
            self.plotSettingsModel.addSensor(s)





        """
        def setPersistentWidgets(self, index, start, end):
            self.VIEW.openPersistentEditor(self.createIndex(index.row(), 2))
            self.VIEW.openPersistentEditor(self.createIndex(index.row(), 3))
        """
        # self.VIEW.setItemDelegateForColumn(3, PointStyleDelegate(self.VIEW))
        self.plotData2D = dict()
        self.plotData3D = dict()
        self.refresh()

    def onRowsInserted(self, parent, start, end):
        model = self.TV.model()
        if model:
            colExpression = model.columnames.index('y-value')
            colStyle = model.columnames.index('style')
            while start <= end:
                idxExpr = model.createIndex(start, colExpression)
                idxStyle = model.createIndex(start, colStyle)
                self.TV.openPersistentEditor(idxExpr)
                self.TV.openPersistentEditor(idxStyle)
                start += 1
                #self.TV.openPersistentEditor(model.createIndex(start, colStyle))
            s = ""


    def setVisibility(self, sensorView):
        assert isinstance(sensorView, SensorPlotSettings)
        self.setVisibility2D(sensorView)

    def setVisibility2D(self, sensorView):
        assert isinstance(sensorView, SensorPlotSettings)
        scatter = self.plotData2D[sensorView.sensor]
        scatter.setVisible(sensorView.isVisible)
        scatter.setData(brush=sensorView.color)

        self.plot2D.removeItem(scatter)
        self.plot2D.addItem(scatter)

    def refresh(self, sensorView = None):

        if sensorView is None:
            for sv in self.plotSettingsModel.items:
                self.refresh(sv)
        else:
            assert isinstance(sensorView, SensorPlotSettings)
            self.refresh2D(sensorView)
        pass

    def refresh2D(self, sensorView):
        assert isinstance(sensorView, SensorPlotSettings)
        pi = self.plot2D
        assert isinstance(pi, pg.PlotWidget)

        if sensorView.sensor not in self.plotData2D.keys():
            #init scatter plot item
            scatter = pg.ScatterPlotItem()
            scatter.setToolTip('Values {}'.format(sensorView.sensor.sensorName))
            pi.addItem(scatter)
            self.plotData2D[sensorView.sensor] = scatter

        scatter = self.plotData2D[sensorView.sensor]
        scatter.clear()
        scatter.setVisible(sensorView.isVisible)

        #https://github.com/pyqtgraph/pyqtgraph/blob/5195d9dd6308caee87e043e859e7e553b9887453/examples/customPlot.py

        if sensorView.isVisible:

            tsds, values = self.pxCollection.dateValues(sensorView.sensor, sensorView.expression)
            if len(tsds) > 0:

                dates = np.asarray([tsd.date for tsd in tsds])
                values = np.asarray(values)

                scatter.setData(x=dates, y=values, data=tsds, brush=sensorView.color)

                pi.addItem(scatter)

            s = ""
        s = ""

    def refresh3D(self, *arg):
        pass
    #
    def loadCoordinate(self, point, crs):
        assert isinstance(point, QgsPoint)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        pass





def testPixelLoader():

    # prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        os.environ['GDAL_DATA'] = r'/usr/local/Cellar/gdal/1.11.3_1/share'
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()


    gb = QGroupBox()
    gb.setTitle('Sandbox')

    PL = PixelLoader()
    PL.setNumberOfThreads(1)

    if False:
        files = ['observationcloud/testdata/2014-07-26_LC82270652014207LGN00_BOA.bsq',
                 'observationcloud/testdata/2014-08-03_LE72270652014215CUB00_BOA.bsq'
                 ]
    else:
        from utils import file_search
        searchDir = r'H:\LandsatData\Landsat_NovoProgresso'
        files = file_search(searchDir, '*227065*band4.img', recursive=True)
        #files = files[0:3]

    lyr = QgsRasterLayer(files[0])
    coord = lyr.extent().center()
    crs = lyr.crs()

    l = QVBoxLayout()

    btnStart = QPushButton()
    btnStop = QPushButton()
    prog = QProgressBar()
    tboxResults = QPlainTextEdit()
    tboxResults.setMaximumHeight(300)
    tboxThreads = QPlainTextEdit()
    tboxThreads.setMaximumHeight(200)
    label = QLabel()
    label.setText('Progress')

    def showProgress(n,m,md):
        prog.setMinimum(0)
        prog.setMaximum(m)
        prog.setValue(n)

        info = []
        for k, v in md.items():
            info.append('{} = {}'.format(k,str(v)))
        tboxResults.setPlainText('\n'.join(info))
        #tboxThreads.setPlainText(PL.threadInfo())
        qgsApp.processEvents()

    PL.sigPixelLoaded.connect(showProgress)
    btnStart.setText('Start loading')
    btnStart.clicked.connect(lambda : PL.startLoading(files, coord, crs))
    btnStop.setText('Cancel')
    btnStop.clicked.connect(lambda: PL.cancelLoading())
    lh = QHBoxLayout()
    lh.addWidget(btnStart)
    lh.addWidget(btnStop)
    l.addLayout(lh)
    l.addWidget(prog)
    l.addWidget(tboxThreads)
    l.addWidget(tboxResults)

    gb.setLayout(l)
    gb.show()
    #rs.setBackgroundStyle('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #222, stop:1 #333);')
    #rs.handle.setStyleSheet('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #282, stop:1 #393);')
    qgsApp.exec_()
    qgsApp.exitQgis()

if __name__ == '__main__':
    import site, sys
    #add site-packages to sys.path as done by enmapboxplugin.py

    from timeseriesviewer import DIR_SITE_PACKAGES
    site.addsitedir(DIR_SITE_PACKAGES)

    #prepare QGIS environment
    if sys.platform == 'darwin':
        PATH_QGS = r'/Applications/QGIS.app/Contents/MacOS'
        os.environ['GDAL_DATA'] = r'/usr/local/Cellar/gdal/1.11.3_1/share'
    else:
        # assume OSGeo4W startup
        PATH_QGS = os.environ['QGIS_PREFIX_PATH']
    assert os.path.exists(PATH_QGS)

    qgsApp = QgsApplication([], True)
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns')
    QApplication.addLibraryPath(r'/Applications/QGIS.app/Contents/PlugIns/qgis')
    qgsApp.setPrefixPath(PATH_QGS, True)
    qgsApp.initQgis()

    #run tests
    #d = AboutDialogUI()
    #d.show()

    from timeseriesviewer.tests import *

    TS = TestObjects.TimeSeries(100)
    ext = TS.getMaxSpatialExtent()

    d = ProfileViewDockUI()
    d.connectTimeSeries(TS)
    d.show()
    d.loadCoordinate(ext.center(), ext.crs())

    #close QGIS
    try:
        qgsApp.exec_()
    except:
        s = ""
    qgsApp.exitQgis()

import os, sys, fnmatch, six, subprocess, re
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from PyQt4.QtSvg import *
from PyQt4.QtXml import *
from PyQt4.QtXmlPatterns import *

from PyQt4.uic.Compiler.qtproxies import QtGui

import gdal

from timeseriesviewer import DIR_UI, file_search
jp = os.path.join


def getDOMAttributes(elem):
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[str(attr.nodeName())] = attr.nodeValue()
    return values


def createTestData(dirTestData, pathTS, subsetRectangle, crs, drv=None):
    lines = open(pathTS).readlines()
    import tempfile, random
    from timeseriesviewer.main import TimeSeries, TimeSeriesDatum
    from qgis.core import QgsRectangle, QgsPoint, QgsPointV2, QgsCoordinateReferenceSystem

    max_offset = 0 #in %


    assert isinstance(subsetRectangle, QgsRectangle)
    assert isinstance(crs, QgsCoordinateReferenceSystem)
    TS = TimeSeries()
    TS.loadFromFile(pathTS)

    sw = subsetRectangle.width()
    sh = subsetRectangle.height()

    max_offset_x = sw / 100 * max_offset
    max_offset_y = sw / 100 * max_offset
    center = subsetRectangle.center()

    if not os.path.exists(dirTestData):
        os.mkdir(dirTestData)
    dirImages = os.path.join(dirTestData, 'Images')
    if not os.path.exists(dirImages):
        os.mkdir(dirImages)

    def random_offset():
        offset_x = random.randrange(-max_offset_x, max_offset_x) if max_offset_x > 0 else 0
        offset_y = random.randrange(-max_offset_y, max_offset_y) if max_offset_y > 0 else 0
        return offset_x, offset_y

    drvMEM = gdal.GetDriverByName('MEM')

    from timeseriesviewer.main import transformGeometry
    for TSD in TS.data:
        assert isinstance(TSD, TimeSeriesDatum)

        ox, oy = random_offset()

        UL = QgsPoint(subsetRectangle.xMinimum() + ox,
                      subsetRectangle.yMaximum() + oy)
        LR = QgsPoint(subsetRectangle.xMaximum() + ox,
                      subsetRectangle.yMinimum() + oy)
        UL = transformGeometry(UL, crs, TSD.crs)
        LR = transformGeometry(LR, crs, TSD.crs)
        BBOX = QgsRectangle(UL, LR)
        if not BBOX.intersects(TSD.getBoundingBox()):
            print('Please note: no intersection with BBOX: '+TSD.pathImg)
        #crop src dataset to BBOX
        #for this we use GDAL
        LUT_EXT = {'ENVI':'.bsq'}


        filesToCopy = [f for f in [TSD.pathImg, TSD.pathMsk] if f is not None and os.path.exists(f)]
        for pathSrc in filesToCopy:
            dsSrc = gdal.Open(pathSrc)

            assert isinstance(dsSrc, gdal.Dataset)
            proj = dsSrc.GetProjection()
            trans = list(dsSrc.GetGeoTransform())
            trans[0] = UL.x()
            trans[3] = UL.y()

            nsDst = int(BBOX.width() / TSD.lyrImg.rasterUnitsPerPixelX())
            nlDst = int(BBOX.height() / TSD.lyrImg.rasterUnitsPerPixelY())

            dsDst = drvMEM.Create('', nsDst, nlDst, dsSrc.RasterCount, eType = dsSrc.GetRasterBand(1).DataType)
            assert isinstance(dsDst, gdal.Dataset)
            dsDst.SetProjection(proj)
            dsDst.SetGeoTransform(trans)
            wo = gdal.WarpOptions()
            r = gdal.Warp(dsDst, dsSrc)

            assert r > 0

            drvDst = gdal.GetDriverByName(drv) if drv is not None else dsSrc.GetDriver()
            #try to retireve an extension
            pathDst = os.path.join(dirImages, os.path.splitext(os.path.basename(pathSrc))[0])
            ext = drvDst.GetMetadata_Dict().get('DMD_EXTENSION','')
            if ext == '':
                ext = LUT_EXT.get(drvDst.ShortName, '')
            if not pathDst.endswith(ext):
                pathDst += ext
            print('Write {}'.format(pathDst))
            drvDst.CreateCopy(pathDst, dsDst)




def make(ROOT):
    #find ui files
    ui_files = file_search(ROOT, '*.ui', recursive=True)
    qrcs = set()

    doc = QDomDocument()
    reg = re.compile('(?<=resource=")[^"]+\.qrc(?=")')

    for ui_file in ui_files:
        pathDir = os.path.dirname(ui_file)
        doc.setContent(QFile(ui_file))
        includeNodes = doc.elementsByTagName('include')
        for i in range(includeNodes.count()):
            attr = getDOMAttributes(includeNodes.item(i).toElement())
            if 'location' in attr.keys():
                qrcs.add((pathDir, str(attr['location'])))

    #compile Qt resource files
    #resourcefiles = file_search(ROOT, '*.qrc', recursive=True)
    resourcefiles = list(qrcs)
    assert len(resourcefiles) > 0
    for root_dir, f in resourcefiles:
        #dn = os.path.dirname(f)
        pathQrc = os.path.normpath(jp(root_dir, f))
        assert os.path.exists(pathQrc)
        bn = os.path.basename(f)
        bn = os.path.splitext(bn)[0]
        pathPy2 = os.path.join(DIR_UI, bn+'_py2.py' )
        pathPy3 = os.path.join(DIR_UI, bn+'_py3.py' )
        print('Make {}'.format(pathPy2))
        subprocess.call(['pyrcc4','-py2','-o',pathPy2, pathQrc])
        print('Make {}'.format(pathPy3))
        subprocess.call(['pyrcc4','-py3','-o',pathPy3, pathQrc])


def svg2png(pathDir, overwrite=False, mode='INKSCAPE'):
    assert mode in ['INKSCAPE', 'WEBKIT', 'SVG']
    from PyQt4.QtWebKit import QWebPage

    svgs = file_search(pathDir, '*.svg')
    app = QApplication([], True)
    buggySvg = []

    for pathSvg in svgs:
        dn = os.path.dirname(pathSvg)
        bn, _ = os.path.splitext(os.path.basename(pathSvg))
        pathPng = jp(dn, bn+'.png')

        if mode == 'SVG':
            renderer = QSvgRenderer(pathSvg)
            doc_size = renderer.defaultSize() # size in px
            img = QImage(doc_size, QImage.Format_ARGB32)
            #img.fill(0xaaA08080)
            painter = QPainter(img)
            renderer.render(painter)
            painter.end()
            if overwrite or not os.path.exists(pathPng):
                img.save(pathPng, quality=100)
            del painter, renderer
        elif mode == 'WEBKIT':
            page = QWebPage()
            frame = page.mainFrame()
            f = QFile(pathSvg)
            if f.open(QFile.ReadOnly | QFile.Text):
                textStream = QTextStream(f)
                svgData = textStream.readAll()
                f.close()

            qba = QByteArray(str(svgData))
            frame.setContent(qba,"image/svg+xml")
            page.setViewportSize(frame.contentsSize())

            palette = page.palette()
            background_color = QColor(50,0,0,50)
            palette.setColor(QPalette.Window, background_color)
            brush = QBrush(background_color)
            palette.setBrush(QPalette.Window, brush)
            page.setPalette(palette)

            img = QImage(page.viewportSize(), QImage.Format_ARGB32)
            img.fill(background_color) #set transparent background
            painter = QPainter(img)
            painter.setBackgroundMode(Qt.OpaqueMode)
            #print(frame.renderTreeDump())
            frame.render(painter)
            painter.end()

            if overwrite or not os.path.exists(pathPng):
                print('Save {}...'.format(pathPng))
                img.save(pathPng, quality=100)
            del painter, frame, img, page
            s  =""
        elif mode == 'INKSCAPE':
            if not os.path.exists(pathPng) or overwrite:
                if sys.platform == 'darwin':
                    cmd = ['inkscape']
                else:
                    dirInkscape = r'C:\Program Files\Inkscape'
                    assert os.path.isdir(dirInkscape)
                    cmd = [jp(dirInkscape,'inkscape')]
                cmd.append('--file={}'.format(pathSvg))
                cmd.append('--export-png={}'.format(pathPng))
                from subprocess import PIPE
                p = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
                output, err = p.communicate()
                rc = p.returncode
                print('Saved {}'.format(pathPng))
                if err != '':
                    buggySvg.append((pathSvg, err))

    if len(buggySvg) > 0:
        six._print('SVG Errors')
        for t in buggySvg:
            pathSvg, error = t
            six._print(pathSvg, error, file=sys.stderr)
    s = ""


def png2qrc(icondir, pathQrc, pngprefix='timeseriesviewer'):
    pathQrc = os.path.abspath(pathQrc)
    dirQrc = os.path.dirname(pathQrc)
    app = QApplication([])
    assert os.path.exists(pathQrc)
    doc = QDomDocument()
    doc.setContent(QFile(pathQrc))

    pngFiles = set()
    fileAttributes = {}
    #add files already included in QRC

    fileNodes = doc.elementsByTagName('file')
    for i in range(fileNodes.count()):
        fileNode = fileNodes.item(i).toElement()

        file = str(fileNode.childNodes().item(0).nodeValue())
        if file.lower().endswith('.png'):
            pngFiles.add(file)
            if fileNode.hasAttributes():
                attributes = {}
                for i in range(fileNode.attributes().count()):
                    attr = fileNode.attributes().item(i).toAttr()
                    attributes[str(attr.name())] = str(attr.value())
                fileAttributes[file] = attributes

    #add new pngs in icondir
    for f in  file_search(icondir, '*.png'):
        file = os.path.relpath(f, dirQrc).replace('\\','/')
        pngFiles.add(file)

    pngFiles = sorted(list(pngFiles))

    def elementsByTagAndProperties(elementName, attributeProperties, rootNode=None):
        assert isinstance(elementName, str)
        assert isinstance(attributeProperties, dict)
        if rootNode is None:
            rootNode = doc
        resourceNodes = rootNode.elementsByTagName(elementName)
        nodeList = []
        for i in range(resourceNodes.count()):
            resourceNode = resourceNodes.item(i).toElement()
            for aName, aValue in attributeProperties.items():
                if resourceNode.hasAttribute(aName):
                    if aValue != None:
                        assert isinstance(aValue, str)
                        if str(resourceNode.attribute(aName)) == aValue:
                            nodeList.append(resourceNode)
                    else:
                        nodeList.append(resourceNode)
        return nodeList


    resourceNodes = elementsByTagAndProperties('qresource', {'prefix':pngprefix})
    if len(resourceNodes) == 1:
        resourceNode = resourceNodes[0]
    elif len(resourceNodes) == 0:
        resourceNode = doc.createElement('qresource')
        resourceNode.setAttribute('prefix', pngprefix)
    else:
        raise NotImplementedError()

    #remove childs, as we have all stored in list pngFiles
    childs = resourceNode.childNodes()
    while not childs.isEmpty():
        node = childs.item(0)
        node.parentNode().removeChild(node)

    #insert new childs
    for pngFile in pngFiles:

        node = doc.createElement('file')
        attributes = fileAttributes.get(pngFile)
        if attributes:
            for k, v in attributes.items():
                node.setAttribute(k,v)
            s = 2
        node.appendChild(doc.createTextNode(pngFile))
        resourceNode.appendChild(node)

    f = open(pathQrc, "w")
    f.write(doc.toString())
    f.close()
    s = ""



if __name__ == '__main__':
    icondir = jp(DIR_UI, *['icons'])
    pathQrc = jp(DIR_UI,'resources.qrc')
    if False:
        from qgis import *
        from qgis.core import *
        from qgis.gui import *

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

        pathDirTestData = r'C:\Users\geo_beja\Repositories\QGIS_Plugins\SenseCarbonTSViewer\example'
        #path Novo Progresso site L7/L8/RE time series
        #pathTS = r'C:\Users\geo_beja\Repositories\QGIS_Plugins\SenseCarbonTSViewer\make\testdata_sources2.txt'
        pathTS = r'C:\Users\geo_beja\Repositories\QGIS_Plugins\SenseCarbonTSViewer\make\testdata_sources.txt'
        from qgis.core import QgsCoordinateReferenceSystem, QgsPoint, QgsRectangle
        subset = QgsRectangle(QgsPoint(-55.36091,-6.79851), #UL
                              QgsPoint(-55.34132,-6.80514)) #LR

        crs = QgsCoordinateReferenceSystem('EPSG:4326') # lat lon coordinates


        createTestData(pathDirTestData, pathTS,subset, crs, drv='ENVI')
        exit(0)

    if True:
        #convert SVG to PNG and link them into the resource file
        #svg2png(icondir, overwrite=True)
        #add png icons to qrc file
        png2qrc(icondir, pathQrc)
    if True:
        make(DIR_UI)
    print('Done')


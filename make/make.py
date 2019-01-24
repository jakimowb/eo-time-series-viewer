# -*- coding: utf-8 -*-

import os, sys, fnmatch, six, subprocess, re
#from qgis import *
#from qgis.core import *
#from qgis.gui import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtSvg import *
from PyQt5.QtXml import *

from osgeo import gdal
from timeseriesviewer import DIR_UI, DIR_REPO
from timeseriesviewer.utils import file_search, jp


def createFilePackage(dirData, recursive=True):
    import numpy as np
    from timeseriesviewer import DIR_REPO
    pathInit = jp(dirData, '__init__.py')
    code = ['#!/usr/bin/env python',
            '"""',
            'This file is auto-generated.',
            'Do not edit manually, as changes might get overwritten.',
            '"""',
            '__author__ = "auto-generated by {}"'.format(os.path.relpath(__file__, DIR_REPO)),
            '__date__ = "{}"'.format(np.datetime64('now')),
            '',
            'import sys, os',
            '',
            'thisDir = os.path.dirname(__file__)',
            '# File path attributes:',
            ]
    files = file_search(dirData, '*', recursive=recursive)

    filePathAttributes = set()
    def addFiles(files, comment=None, numberPrefix='File'):
        if len(files) > 0:
            if comment:
                code.append('# '+comment)
            for f in files:
                an, ext = os.path.splitext(os.path.basename(f))
                if re.search(r'^\d', an):
                    an = numberPrefix+an
                an = re.sub(r'[-.]', '_',an)

                assert an not in filePathAttributes
                relpath = os.path.relpath(f, dirData)
                code.append("{} = os.path.join(thisDir,r'{}')".format(an, relpath))
                filePathAttributes.add(an)
            code.append('\n')

    raster = [f for f in files if re.search(r'.*\.(bsq|bip|bil|tif|tiff)$', f)]
    vector = [f for f in files if re.search(r'.*\.(shp|kml|kmz)$', f)]

    addFiles(raster, 'Raster files:', numberPrefix='Img_')
    addFiles(vector, 'Vector files:', numberPrefix='Shp_')

    #add self-test for file existence
    if len(filePathAttributes) > 0:
        code.extend(
        [
        "",
        "# self-test to check each file path attribute",
        "for a in dir(sys.modules[__name__]):",
        "    v = getattr(sys.modules[__name__], a)",
        "    if type(v) == str and os.path.isabs(v):" ,
        "        if not os.path.exists(v):",
        "            sys.stderr.write('Missing package attribute file: {}={}'.format(a, v))",
        "",
        "# cleanup",
        "del thisDir, a, v ",
        ]
        )

    open(pathInit, 'w').write('\n'.join(code))
    print('Created '+pathInit)


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
    from qgis.core import QgsRectangle, QgsPoint, QgsPointXY, QgsCoordinateReferenceSystem

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
    for TSD in TS.mTSDs:
        assert isinstance(TSD, TimeSeriesDatum)

        ox, oy = random_offset()

        UL = QgsPointXY(subsetRectangle.xMinimum() + ox,
                      subsetRectangle.yMaximum() + oy)
        LR = QgsPointXY(subsetRectangle.xMaximum() + ox,
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


def compile_rc_files(ROOT, targetDir=None):
    #find ui files
    ui_files = file_search(ROOT, '*.ui', recursive=True)
    qrcs = set()

    doc = QDomDocument()
    reg = re.compile(r'(?<=resource=")[^"]+\.qrc(?=")')

    for ui_file in ui_files:
        pathDir = os.path.dirname(ui_file)
        doc.setContent(QFile(ui_file))
        includeNodes = doc.elementsByTagName('include')
        for i in range(includeNodes.count()):
            attr = getDOMAttributes(includeNodes.item(i).toElement())
            if 'location' in attr.keys():
                print((ui_file, str(attr['location'])))
                qrcs.add((pathDir, str(attr['location'])))

    #compile Qt resource files
    #resourcefiles = file_search(ROOT, '*.qrc', recursive=True)
    resourcefiles = list(qrcs)
    assert len(resourcefiles) > 0

    shell_cmds = []
    subprocess_args = []
    for root_dir, f in resourcefiles:
        #dn = os.path.dirname(f)
        pathQrc = os.path.normpath(jp(root_dir, f))
        if not os.path.exists(pathQrc):
            print('Resource file does not exist: {}'.format(pathQrc))
            continue
        bn = os.path.basename(pathQrc)

        if isinstance(targetDir, str):
            dn = targetDir
        else:
            dn = os.path.dirname(pathQrc)

        bn = os.path.splitext(bn)[0]
        pathPy = os.path.join(dn, bn+'.py' )
        cmd = 'pyrcc5 -o {} {}'.format(pathPy, pathQrc)
        print(cmd)
        os.system(cmd)




def fileNeedsUpdate(file1, file2):
    if not os.path.exists(file2):
        return True
    else:
        if not os.path.exists(file1):
            return True
        else:
            return os.path.getmtime(file1) > os.path.getmtime(file2)


def svg2png(pathDir, overwrite=False, mode='INKSCAPE', filterFile=None):
    """
    Converts SVG files into PNG raster images
    :param pathDir:
    :param overwrite:
    :param mode:
    :return:
    """
    assert mode in ['INKSCAPE', 'WEBKIT', 'SVG']

    svgs = file_search(pathDir, '*.svg')
    if filterFile is not None:
        print('use file filter')
        lines = open(filterFile).readlines()
        lines = [l.strip() for l in lines]
        lines = [l for l in lines if not l.startswith('#') or len(l) == 0]
        svgs = [f for f in svgs if
                f in lines or os.path.basename(f) in lines]

    if len(svgs) == 0:
        print('No SVGs to convert')
        return

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
            """
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
            """
        elif mode == 'INKSCAPE':
            if fileNeedsUpdate(pathSvg, pathPng):
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


def file2qrc(icondir, pathQrc, qrcPrefix='timeseriesviewer', fileExtension='.png'):
    pathQrc = os.path.abspath(pathQrc)
    dirQrc = os.path.dirname(pathQrc)
    app = QApplication([])
    assert os.path.exists(pathQrc)

    #create the new RCC
    doc = QDomDocument('RCC')
    doc.setContent(QFile(pathQrc))
    if str(doc.toString()) == '':
        doc.appendChild(doc.createElement('RCC'))
    root = doc.documentElement()
    fileOfInterest = set()
    fileAttributes = {}

    #add files that are already included in the QRC file
    fileNodes = doc.elementsByTagName('file')
    for i in range(fileNodes.count()):
        fileNode = fileNodes.item(i).toElement()

        file = str(fileNode.childNodes().item(0).nodeValue())
        #if file.lower().endswith(fileExtension):
        fileOfInterest.add(file)
        if fileNode.hasAttributes():
            attributes = {}
            for i in range(fileNode.attributes().count()):
                attr = fileNode.attributes().item(i).toAttr()
                attributes[str(attr.name())] = str(attr.value())
            fileAttributes[file] = attributes

    #add new files from the icondir
    for f in  file_search(icondir, '*'+fileExtension):
        file = os.path.relpath(f, dirQrc).replace('\\','/')
        fileOfInterest.add(file)

    fileOfInterest = sorted(list(fileOfInterest))

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


    resourceNodes = elementsByTagAndProperties('qresource', {'prefix':qrcPrefix})

    if len(resourceNodes) == 0:
        resourceNode = doc.createElement('qresource')
        root.appendChild(resourceNode)
        resourceNode.setAttribute('prefix', qrcPrefix)
    elif len(resourceNodes) == 1:
        resourceNode = resourceNodes[0]
    else:
        raise NotImplementedError('Multiple resource nodes')

    #remove childs, as we have all stored in list pngFiles
    childs = resourceNode.childNodes()
    while not childs.isEmpty():
        node = childs.item(0)
        node.parentNode().removeChild(node)

    #insert new childs
    for file in fileOfInterest:

        node = doc.createElement('file')
        attributes = fileAttributes.get(file)
        if attributes:
            for k, v in attributes.items():
                node.setAttribute(k,v)
            s = 2
        node.appendChild(doc.createTextNode(file))
        resourceNode.appendChild(node)
        print(file)

    f = open(pathQrc, "w")
    f.write(doc.toString())
    f.close()



def updateMetadataTxt():
    #see http://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/plugins.html#plugin-metadata
    #for required metatags
    pathDst = jp(DIR_REPO, 'metadata.txt')
    pathAboutPlugin = jp(DIR_REPO, 'ABOUT_Plugin.html')
    assert os.path.exists(pathDst)
    import timeseriesviewer.utils
    #required to use QIcons
    qgis = timeseriesviewer.utils.initQgisApplication()

    import timeseriesviewer, collections
    md = collections.OrderedDict()

    with open(pathDst) as f:
        for line in f.readlines():
            parts = line.split('=')
            if len(parts) >= 2:
                md[parts[0]] = '='.join(parts[1:])

    #update/set new metadata
    md['name'] = timeseriesviewer.TITLE
    md['qgisMinimumVersion'] = "3.0"
    #md['qgisMaximumVersion'] =
    md['description'] = timeseriesviewer.DESCRIPTION.strip()
    md['about'] = timeseriesviewer.ABOUT.strip()
    md['version'] = timeseriesviewer.__version__.strip()
    md['author'] = r"Benjamin Jakimow, Geomatics Lab, Humboldt-Universität zu Berlin"
    md['email'] = "benjamin.jakimow@geo.hu-berlin.de"
    #md['changelog'] =

    with open(pathAboutPlugin, 'r', encoding='utf-8') as f:
        aboutText =f.read()
        aboutText=aboutText.replace('\n','')


    md['about'] = aboutText
    md['experimental'] = "False"
    md['deprecated'] = "False"
    md['tags'] = "remote sensing, raster, time series"
    md['homepage'] = timeseriesviewer.HOMEPAGE
    md['repository'] = timeseriesviewer.HOMEPAGE
    md['tracker'] = timeseriesviewer.HOMEPAGE + '/issues'
    md['icon'] = r'timeseriesviewer/icon.png'
    md['category'] = 'Raster'

    lines = ['[general]']
    for k, line in md.items():
        lines.append('{}={}'.format(k, line))

    with open(pathDst, 'w', encoding='utf-8') as f:
        f.writelines('\n'.join(lines))
        f.flush()



def make_pb_tool_cfg():
    pathPBToolCgf = r''

    lines = open(pathPBToolCgf).readlines()

    #main_dialog:


def copyQGISRessourceFile():
    if sys.platform == 'darwin':
        pathQGISRepo = r'/Users/benjamin.jakimow/Repositories/QGIS'
    else:
        pathQGISRepo = r'C:\Users\geo_beja\Repositories\QGIS'

    assert os.path.isdir(pathQGISRepo)
    dirTarget = os.path.join(DIR_REPO, *['qgisresources'])
    os.makedirs(dirTarget, exist_ok=True)
    compile_rc_files(pathQGISRepo, targetDir=dirTarget)


    #qrcFiles = file_search(pathQGISRepo, '*.qrc')

    #for qrcFile in qrcFiles:




def checkFileHeader():


    hdr = """
    # -*- coding: utf-8 -*-
    \"\"\"
    /***************************************************************************
                                  EO Time Series Viewer
                                  -------------------
            begin                : 2017-08-04
            git sha              : $Format:%H$
            copyright            : (C) 2017 by HU-Berlin
            email                : benjamin.jakimow@geo.hu-berlin.de
     ***************************************************************************/

    /***************************************************************************
     *                                                                         *
     *   This program is free software; you can redistribute it and/or modify  *
     *   it under the terms of the GNU General Public License as published by  *
     *   the Free Software Foundation; either version 2 of the License, or     *
     *   (at your option) any later version.                                   *
     *                                                                         *
     ***************************************************************************/
    \"\"\"
    """
    # noinspection PyPep8Naming

    root = jp(DIR_REPO, 'timeseriesviewer')
    pyFiles = file_search(root, '*.py')

    for path in pyFiles:
        file = open(path, 'r', encoding='utf8')
        lines = file.readlines()
        file.close()

        lineFirstImport = None
        for i in range(len(lines)):
            if re.search('^[ ]*import ', lines[i]):
                lineFirstImport = i
                break

        if isinstance(lineFirstImport, int) and lineFirstImport < 50:
            pass






if __name__ == '__main__':

    if True:
        compile_rc_files(DIR_UI)


    print('Done')


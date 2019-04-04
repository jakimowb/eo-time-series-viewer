
import xml.etree.ElementTree as ET
from qps.testing import initQgisApplication
app = initQgisApplication()
from qps.utils import *
from osgeo import gdal, ogr, osr

DIR_QGIS_REPO = r'C:\Users\geo_beja\Repositories\QGIS'
DIR_REPO = dn(findUpwardPath(__file__, '.git'))


def rasterize_vector_labels(pathRef, pathDst, pathShp, label_field, band_ref=1, label_layer=0):
    drvMemory = ogr.GetDriverByName('Memory')
    drvMEM = gdal.GetDriverByName('MEM')

    dsShp = drvMemory.CopyDataSource(ogr.Open(pathShp),'')
    dsRef = gdal.Open(pathRef)

    assert label_layer < dsShp.GetLayerCount()
    lyr_tmp1 = dsShp.GetLayerByIndex(label_layer)
    lyr_name1 = lyr_tmp1.GetName()
    lyr_def1 = lyr_tmp1.GetLayerDefn()
    field_names1 = [lyr_def1.GetFieldDefn(f).GetName() for f  in range(lyr_def1.GetFieldCount())]
    assert label_field in field_names1, 'field {} does not exist. possible names are: {}'.format(label_field, ','.join(field_names1))
    fieldDef = lyr_def1.GetFieldDefn(field_names1.index(label_field))

    IS_CATEGORICAL = fieldDef.GetType() == ogr.OFTString
    label_names = None
    if IS_CATEGORICAL:
        #label_names = dsRef.GetRasterBand(band_ref).GetCategoryNames()
        label_names = set()
        for feat in lyr_tmp1:
            value = str(feat.GetField(label_field)).strip()
            if len(value) > 0:
                label_names.add(value)
            #get label names from values
        lyr_tmp1.ResetReading()
        label_names = sorted(list(label_names))
        if not 'unclassified' in label_names:
            label_names.insert(0, 'unclassified')
        label_values = list(range(len(label_names)))


    # transform geometries into target reference system
    for name in [lyr.GetName() for lyr in dsShp if lyr.GetName() != lyr_name1]:
        dsShp.Delete(name)
    lyr_name2 = lyr_name1 + '2'
    srs = osr.SpatialReference()
    srs.ImportFromWkt(dsRef.GetProjection())

    trans = None
    if not srs.IsSame(lyr_tmp1.GetSpatialRef()):
        trans = osr.CoordinateTransformation(lyr_tmp1.GetSpatialRef(), srs)
    lyr_tmp2 = dsShp.CreateLayer(lyr_name2, srs=srs, geom_type=ogr.wkbPolygon)


    if IS_CATEGORICAL:
        lyr_tmp2.CreateField(ogr.FieldDefn(label_field, ogr.OFTInteger))
        no_data = 0
    else:
        lyr_tmp2.CreateField(ogr.FieldDefn(label_field, fieldDef.GetType()))
        no_data = dsRef.GetRasterBand(band_ref).GetNoDataValue()

    n = 0
    for feature_src in lyr_tmp1:
        value = feature_src.GetField(label_field)
        if value is None:
            continue

        if IS_CATEGORICAL:
            if value in label_names:
                value = label_values[label_names.index(value)]
            elif value not in label_values:
                print('Not found in prediction labels: {}'.format(value))

        if value is not None:
            geom = feature_src.GetGeometryRef().Clone()
            if trans:
                geom.Transform(trans)

            feature_tmp = ogr.Feature(lyr_tmp2.GetLayerDefn())
            feature_tmp.SetGeometry(geom)
            feature_tmp.SetField(label_field, value)
            lyr_tmp2.CreateFeature(feature_tmp)
            lyr_tmp2.SyncToDisk()
            n += 1

    lyr_tmp2.ResetReading()
    ns = dsRef.RasterXSize
    nl = dsRef.RasterYSize



    dsRasterTmp = drvMEM.Create('', ns, nl, eType=gdal.GDT_Int32)
    dsRasterTmp.SetProjection(dsRef.GetProjection())
    dsRasterTmp.SetGeoTransform(dsRef.GetGeoTransform())
    band_ref = dsRasterTmp.GetRasterBand(1)
    assert type(band_ref) is gdal.Band
    if IS_CATEGORICAL:
        band_ref.Fill(0)  # by default = unclassified = 0
    elif no_data is not None:
        band_ref.Fill(no_data)
        band_ref.SetNoDataValue(no_data)

    # print('Burn geometries...')
    # http://www.gdal.org/gdal__alg_8h.html for details on options
    options = ['ATTRIBUTE={}'.format(label_field)
        , 'ALL_TOUCHED=TRUE']
    err = gdal.RasterizeLayer(dsRasterTmp, [1], lyr_tmp2, options=options)
    assert err in [gdal.CE_None, gdal.CE_Warning], 'Something failed with gdal.RasterizeLayer'

    band_ref = dsRasterTmp.GetRasterBand(1)
    validated_labels = band_ref.ReadAsArray()
    if IS_CATEGORICAL:
        #set classification info
        import matplotlib.cm
        label_colors = list()
        cmap = matplotlib.cm.get_cmap('brg', n)
        for i in range(n):
            if i == 0:
                c = (0,0,0, 255)
            else:
                c = tuple([int(255*c) for c in cmap(i)])
            label_colors.append(c)

        CT = gdal.ColorTable()
        names = list()
        for value in sorted(label_values):
            i = label_values.index(value)
            names.append(label_names[i])
            CT.SetColorEntry(value, label_colors[i])

        band_ref.SetCategoryNames(names)
        band_ref.SetColorTable(CT)

        s = ""
    drvDst = dsRef.GetDriver()
    drvDst.CreateCopy(pathDst, dsRasterTmp)


def getDOMAttributes(elem):
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[str(attr.nodeName())] = attr.nodeValue()
    return values


def searchAndCompileResourceFiles(dirRoot:str, targetDir:str=None):
    """
    Searches for *.ui files and compiles the *.qrc files they use.
    :param dirRoot: str, root directory, in which to search for *.qrc files or a list of *.ui file paths.
    :param targetDir: str, output directory to write the compiled *.py files to.
           Defaults to the *.qrc's directory
    """
    # find ui files
    assert os.path.isdir(dirRoot)
    ui_files = list(file_search(dirRoot, '*.ui', recursive=True))

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

    for root_dir, f in resourcefiles:

        pathQrc = os.path.normpath(jp(root_dir, f))
        if not os.path.exists(pathQrc):
            print('Resource file does not exist: {}'.format(pathQrc))
            continue
        compileResourceFile(pathQrc, targetDir=targetDir)


def compileResourceFile(pathQrc:str, targetDir:str=None):
    """
    Compiles a *.qrc file
    :param pathQrc:
    :return:
    """
    assert isinstance(pathQrc, str)
    assert os.path.isfile(pathQrc)
    assert pathQrc.endswith('.qrc')

    bn = os.path.basename(pathQrc)
    if isinstance(targetDir, str):
        os.makedirs(targetDir, exist_ok=True)
        dn = targetDir
    else:
        dn = os.path.dirname(pathQrc)

    bn = os.path.splitext(bn)[0]
    pathPy = os.path.join(dn, bn + '.py')
    cmd = 'pyrcc5 -o {} {}'.format(pathPy, pathQrc)
    print(cmd)
    os.system(cmd)

def fileNeedsUpdate(file1, file2):
    """
    Returns True if file2 does not exist or is older than file1
    :param file1:
    :param file2:
    :return:
    """
    if not os.path.exists(file2):
        return True
    else:
        if not os.path.exists(file1):
            return True
        else:
            return os.path.getmtime(file1) > os.path.getmtime(file2)

def createResourceIconPackage(dirIcons, pathResourceFile):
    import numpy as np

    pathInit = jp(dirIcons, '__init__.py')
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
    files = list(file_search(dirIcons, '*.png', recursive=True))

    filePathAttributes = set()

    def addFiles(files, comment=None, numberPrefix='File'):
        if len(files) > 0:
            if comment:
                code.append('# ' + comment)
            for f in files:
                an, ext = os.path.splitext(os.path.basename(f))
                if re.search(r'^\d', an):
                    an = numberPrefix + an
                an = re.sub(r'[-.]', '_', an)

                assert an not in filePathAttributes
                relpath = os.path.relpath(f, dirIcons)
                code.append("{} = os.path.join(thisDir,r'{}')".format(an, relpath))
                filePathAttributes.add(an)
            code.append('\n')

    raster = [f for f in files if re.search(r'.*\.(bsq|bip|bil|tif|tiff)$', f)]
    vector = [f for f in files if re.search(r'.*\.(shp|kml|kmz)$', f)]

    addFiles(raster, 'Raster files:', numberPrefix='Img_')
    addFiles(vector, 'Vector files:', numberPrefix='Shp_')

    # add self-test for file existence
    if len(filePathAttributes) > 0:
        code.extend(
            [
                "",
                "# self-test to check each file path attribute",
                "for a in dir(sys.modules[__name__]):",
                "    v = getattr(sys.modules[__name__], a)",
                "    if type(v) == str and os.path.isabs(v):",
                "        if not os.path.exists(v):",
                "            sys.stderr.write('Missing package attribute file: {}={}'.format(a, v))",
                "",
                "# cleanup",
                "del thisDir ",
            ]
        )

    open(pathInit, 'w').write('\n'.join(code))
    print('Created ' + pathInit)


def createIconProvider(resourceFiles:list, pathIconProvider:str, className = 'IconProvider'):

    """

    class IconProvider:
        EnMAP_Logo = ':/enmapbox/icons/enmapbox.svg'
        Map_Link_Remove = ':/enmapbox/icons/link_open.svg'
        Map_Link = ':/enmapbox/icons/link_basic.svg'
        Map_Link_Center = ':/enmapbox/icons/link_center.svg'

    :param resourceFiles:
    :param pathIconProvider:
    :return:
    """
    info = ['#autogenerated file. do not modify']
    info.append('class {}:'.format(className))

    for file in resourceFiles:
        assert os.path.isfile(file)
        assert file.endswith('.qrc')

        xml = ''
        with open(file, encoding='utf8') as f:
            xml = f.read()
        #:/qps/ui/icons/classinfo.svg
        tree = ET.fromstring(xml)
        for xmlResource in tree.findall('qresource'):
            prefix = xmlResource.attrib['prefix']
            for xmlFile in xmlResource.findall('file'):
                uri = xmlFile.text

                uriSrc = ':/{}/{}'.format(prefix, uri)

                name, ext = os.path.splitext(uriSrc)
                varname = '_'.join([s for s in re.split(r'[ :/\.]+', name) if len(s) > 0])
                #name = ' '.join(re.split('[:/\.]', name))
                #name = ''.join(x for x in name.title() if not x.isspace())
                info.append("    {} = '{}'".format(varname, uriSrc))





def createFilePackage(dirData):
    import numpy as np
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
    files = list(file_search(dirData, '*', recursive=True))

    filePathAttributes = set()
    def addFiles(files, comment=None, numberPrefix='File'):
        if len(files) > 0:
            if comment:
                code.append('# '+comment)
            for f in files:
                attributeName, ext = os.path.splitext(os.path.basename(f))
                #take care of leading numbers
                if re.search(r'^\d', attributeName):
                    attributeName = numberPrefix+attributeName
                # append extension
                attributeName += ext
                #take care of not allowed characters
                attributeName = re.sub(r'[-.]', '_',attributeName)



                assert attributeName not in filePathAttributes, attributeName
                relpath = os.path.relpath(f, dirData)
                code.append("{} = os.path.join(thisDir,r'{}')".format(attributeName, relpath))
                filePathAttributes.add(attributeName)
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
        "del thisDir ",
        ]
        )

    open(pathInit, 'w').write('\n'.join(code))
    print('Created '+pathInit)


def compileQGISResourceFiles(pathQGISRepo:str, target:str=None):
    """
    Searches for *qrc file in QGIS repository, compile them into <DIR_REPO>/qgisresources
    :param pathQGISRepo: str, path to local QGIS repository
    :param target: str, path to directory that contains the compiled QGIS resources. By default it will be
            `<REPOSITORY_ROOT>/qgisresources`
    """
    if pathQGISRepo is None:
        pathQGISRepo = os.environ.get('QGIS_REPOSITORY')
        if isinstance(pathQGISRepo, str):
            pathQGISRepo = pathQGISRepo.strip("'").strip('"')


    assert os.path.isdir(pathQGISRepo)
    if not isinstance(target, str):
        target = jp(DIR_REPO, 'qgisresources')
    searchAndCompileResourceFiles(pathQGISRepo, targetDir=target)


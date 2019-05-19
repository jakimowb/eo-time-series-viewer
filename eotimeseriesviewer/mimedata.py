

from qgis.core import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtXml import *
import re
from qgis.gui import *

MDF_DOCKTREEMODELDATA = 'application/enmapbox.docktreemodeldata'
MDF_DOCKTREEMODELDATA_XML = 'dock_tree_model_data'

MDF_DATASOURCETREEMODELDATA = 'application/enmapbox.datasourcetreemodeldata'
MDF_DATASOURCETREEMODELDATA_XML = 'data_source_tree_model_data'

MDF_LAYERTREEMODELDATA = 'application/qgis.layertreemodeldata'
MDF_LAYERTREEMODELDATA_XML = 'layer_tree_model_data'

MDF_PYTHON_OBJECTS = 'application/enmapbox/objectreference'
MDF_SPECTRALPROFILE = 'application/enmapbox/spectralprofile'
MDF_SPECTRALLIBRARY = 'application/enmapbox/spectrallibrary'
MDF_URILIST = 'text/uri-list'
MDF_TEXT_HTML = 'text/html'
MDF_TEXT_PLAIN = 'text/plain'


def attributesd2dict(attributes):
    d = {}
    assert isinstance(attributes, QDomNamedNodeMap)
    for i in range(attributes.count()):
        attribute = attributes.item(i)
        d[attribute.nodeName()] = attribute.nodeValue()
    return d


def fromLayerList(mapLayers):
    """
    Converts a list of QgsMapLayers into a QMimeData object
    :param mapLayers: [list-of-QgsMapLayers]
    :return: QMimeData
    """
    for lyr in mapLayers:
        assert isinstance(lyr, QgsMapLayer)

    tree = QgsLayerTree()
    mimeData = QMimeData()

    urls = []
    for l in mapLayers:
        tree.addLayer(l)
        urls.append(QUrl.fromLocalFile(l.source()))
    doc = QDomDocument()
    context = QgsReadWriteContext()
    node = doc.createElement(MDF_LAYERTREEMODELDATA_XML)
    doc.appendChild(node)
    for c in tree.children():
        c.writeXml(node, context)

    mimeData.setData(MDF_LAYERTREEMODELDATA, doc.toByteArray())

    return mimeData




def toLayerList(mimeData):
    """
    Extracts a layer-tree-group from a QMimeData
    :param mimeData: QMimeData
    :return: QgsLayerTree
    """
    supported = [MDF_LAYERTREEMODELDATA, MDF_DATASOURCETREEMODELDATA]
    assert isinstance(mimeData, QMimeData)
    newMapLayers = []
    if MDF_LAYERTREEMODELDATA in mimeData.formats():
        doc = QDomDocument()
        doc.setContent(mimeData.data(MDF_LAYERTREEMODELDATA))
        xml = doc.toString()
        node = doc.firstChildElement(MDF_LAYERTREEMODELDATA_XML)
        context = QgsReadWriteContext()
        #context.setPathResolver(QgsProject.instance().pathResolver())
        layerTree = QgsLayerTree.readXml(node, context)
        lt = QgsLayerTreeGroup.readXml(node, context)
        #layerTree.resolveReferences(QgsProject.instance(), True)
        registeredLayers = QgsProject.instance().mapLayers()


        attributesLUT= {}
        childs = node.childNodes()

        for i in range(childs.count()):
            child = childs.at(i).toElement()
            if child.tagName() == 'layer-tree-layer':
                attributesLUT[child.attribute('id')] = attributesd2dict(child.attributes())

        for treeLayer in layerTree.findLayers():
            assert isinstance(treeLayer, QgsLayerTreeLayer)

            mapLayer = treeLayer.layer()
            if isinstance(mapLayer, QgsMapLayer):
                s = ""
            if not isinstance(mapLayer, QgsMapLayer):
                id = treeLayer.layerId()
                if id in registeredLayers.keys():
                    mapLayer = registeredLayers[id]
                elif id in attributesLUT.keys():
                    attributes = attributesLUT[id]

                    if attributes['providerKey'] == 'gdal':
                        mapLayer = QgsRasterLayer(attributes['source'])
                    elif attributes['providerKey'] == 'ogr':
                        mapLayer = QgsVectorLayer(attributes['source'])
                    else:
                        s = ""

                    if isinstance(mapLayer, QgsMapLayer):
                        mapLayer.setName(attributes['name'])

            if isinstance(mapLayer, QgsMapLayer):
                newMapLayers.append(mapLayer)
    elif MDF_URILIST in mimeData.formats():
       pass
    else:
        s = ""

    return newMapLayers


def textToByteArray(text):
    """
    Converts input into a QByteArray
    :param text: bytes or str
    :return: QByteArray
    """

    if isinstance(text, QDomDocument):
        return textToByteArray(text.toString())
    else:
        data = QByteArray()
        data.append(text)
        return data

def textFromByteArray(data):
    """
    Decodes a QByteArray into a str
    :param data: QByteArray
    :return: str
    """
    assert isinstance(data, QByteArray)
    s = data.data().decode()
    return s


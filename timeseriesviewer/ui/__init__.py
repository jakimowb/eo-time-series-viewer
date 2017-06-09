import os, sys, six, importlib, logging, StringIO
logger = logging.getLogger(__name__)

from qgis.core import *
from qgis.gui import *
from PyQt4.QtCore import *
from PyQt4.QtXml import *
from PyQt4.QtGui import *
from PyQt4 import uic
#dictionary to store form classes. *.ui file name is key



from timeseriesviewer import jp, DIR_UI
load = lambda p : loadUIFormClass(jp(DIR_UI,p))

FORM_CLASSES = dict()
def loadUIFormClass(pathUi, from_imports=False):
    """
    Load UI files and takes care on Qgs custom widgets
    :param pathUi:
    :param from_imports:
    :return:
    """
    RC_SUFFIX =  '_py3' if six.PY3 else '_py2'
    assert os.path.exists(pathUi), '*.ui file does not exist: {}'.format(pathUi)

    buffer = StringIO.StringIO() #buffer to store modified XML
    if pathUi not in FORM_CLASSES.keys():
        #parse *.ui xml and replace *.h by qgis.gui
        doc = QDomDocument()
        doc.setContent(QFile(pathUi))

        # Replace *.h file references in <customwidget> with <class>Qgs...</class>, e.g.
        #       <header>qgscolorbutton.h</header>
        # by    <header>qgis.gui</header>
        # this is require to compile QgsWidgets on-the-fly
        elem = doc.elementsByTagName('customwidget')
        for child in [elem.item(i) for i in range(elem.count())]:
            child = child.toElement()
            className = str(child.firstChildElement('class').firstChild().nodeValue())
            if className.startswith('Qgs'):
                cHeader = child.firstChildElement('header').firstChild()
                cHeader.setNodeValue('qgis.gui')

        #collect resource file locations
        elem = doc.elementsByTagName('include')
        qrcPathes = []
        for child in [elem.item(i) for i in range(elem.count())]:
            path = child.attributes().item(0).nodeValue()
            if path.endswith('.qrc'):
                qrcPathes.append(path)



        #logger.debug('Load UI file: {}'.format(pathUi))
        buffer.write(doc.toString())
        buffer.flush()
        buffer.seek(0)

        s = doc.toString()

        #make resource file directories temporary available
        baseDir = os.path.dirname(pathUi)
        tmpDirs = []
        for qrcPath in qrcPathes:
            d = os.path.dirname(os.path.join(baseDir, os.path.dirname(qrcPath)))
            if d not in sys.path:
                tmpDirs.append(d)
        sys.path.extend(tmpDirs)

        #load form class
        try:
            FORM_CLASS, _ = uic.loadUiType(buffer, resource_suffix=RC_SUFFIX)
        except:
            FORM_CLASS, _ = uic.loadUiType(pathUi, resource_suffix=RC_SUFFIX)

        FORM_CLASSES[pathUi] = FORM_CLASS

        for d in tmpDirs:
            sys.path.remove(d)

    return FORM_CLASSES[pathUi]


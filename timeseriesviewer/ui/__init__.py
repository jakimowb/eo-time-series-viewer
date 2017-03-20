import os, sys, six, importlib, logging
logger = logging.getLogger(__name__)
from PyQt4.QtCore import *
from PyQt4.QtXml import *
from PyQt4.QtGui import *
from qgis.gui import *
from qgis.core import *
from PyQt4 import uic
#dictionary to store form classes. *.ui file name is key
FORM_CLASSES = dict()

from timeseriesviewer import jp, DIR_UI


def loadUIFormClass(pathUi, from_imports=False):
    """
    Load UI files and takes care on Qgs custom widgets
    :param pathUi:
    :param from_imports:
    :return:
    """
    RC_SUFFIX =  '_py3' if six.PY3 else '_py2'
    dirUi = os.path.dirname(pathUi)
    assert os.path.exists(pathUi), 'Missing UI file:'+pathUi
    if pathUi not in FORM_CLASSES.keys():
        add_and_remove = dirUi not in sys.path
        if add_and_remove:
            sys.path.append(dirUi)


        #replace for <customwidget> with <class>Qgs...</class>
        #       <header>qgscolorbutton.h</header>
        # by    <header>qgis.gui</header>

        if True:
            pathTmp = jp(os.path.dirname(pathUi), 'tmp.ui')

            doc = QDomDocument()
            doc.setContent(QFile(pathUi))
            elem = doc.elementsByTagName('customwidget')
            overwrite = False
            for child in [elem.item(i) for i in range(elem.count())]:
                child = child.toElement()
                className = str(child.firstChildElement('class').firstChild().nodeValue())
                if className.startswith('Qgs'):
                    cHeader = child.firstChildElement('header').firstChild()
                    cHeader.setNodeValue('qgis.gui')
                    overwrite=True
            if overwrite:
                s = str(doc.toString())
                file = open(pathTmp, 'w')
                file.write(s)
                file.close()
                #os.remove(pathTmp)
                pathUi = pathTmp


        assert os.path.exists(pathUi), 'File does not exist: '+pathUi
        #dprint('Load UI file: {}'.format(pathUi))
        t = open(pathUi).read()
        #dprint(t)
        formClass, _ = uic.loadUiType(pathUi,from_imports=from_imports, resource_suffix=RC_SUFFIX)

        if add_and_remove:
            sys.path.remove(dirUi)
        FORM_CLASSES[pathUi] = formClass

    return FORM_CLASSES[pathUi]

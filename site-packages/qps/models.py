# -*- coding: utf-8 -*-

# noinspection PyPep8Naming


import os, pickle, copy

from collections import OrderedDict

from qgis.core import *
from qgis.gui import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from osgeo import gdal, osr


def currentComboBoxValue(comboBox):
    assert isinstance(comboBox, QComboBox)
    if isinstance(comboBox.model(), OptionListModel):
        o = comboBox.currentData(Qt.UserRole)
        assert isinstance(o, Option)
        return o.mValue
    else:
        return comboBox.currentData()

def setCurrentComboBoxValue(comboBox, value):
    """
    Sets a QComboBox to the value `value`, if it exists in the underlying item list
    :param comboBox: QComboBox
    :param value: any type
    :return: True | False
    """
    assert isinstance(comboBox, QComboBox)
    model = comboBox.model()
    if not isinstance(model, OptionListModel):
        i = comboBox.findData(value, role=Qt.DisplayRole)
        if i == -1:
            i = comboBox.findData(value, role=Qt.UserRole)

        if i != -1:
            comboBox.setCurrentIndex(i)
            return True
    else:
        if not isinstance(value, Option):
            value = Option(value)
        for i in range(comboBox.count()):
            option = comboBox.itemData(i, role=Qt.UserRole)
            if option == value:
                comboBox.setCurrentIndex(i)
                return True
    return False


class Option(object):
    """
    Represents an option
    """

    def __init__(self, value, name=None, toolTip='', icon=QIcon()):
        self.mValue = value
        if name is None:
            name = str(value)
        self.mName = name
        self.mTooltip = toolTip
        self.mIcon = icon

    def value(self)->object:
        """
        Returns the option value
        :return: object
        """
        return self.mValue

    def name(self)->str:
        """
        Returns the option name
        :return: str
        """
        return self.mName

    def toolTip(self)->str:
        """
        Returns the option tooltip.
        :return: str
        """
        return self.mTooltip

    def icon(self)->QIcon:
        """
        Returns an option icon
        :return: QIcon
        """
        return self.mIcon

    def __eq__(self, other):
        if not isinstance(other, Option):
            return False
        else:
            return other.mValue == self.mValue



class OptionListModel(QAbstractListModel):
    def __init__(self, options=None, parent=None):
        super(OptionListModel, self).__init__(parent)

        self.mOptions = []

        self.insertOptions(options)

    def __len__(self):
        return len(self.mOptions)

    def __iter__(self):
        return iter(self.mOptions)

    def addOption(self, option):
        self.insertOptions([option])

    def addOptions(self, options):
        assert isinstance(options, list)
        self.insertOptions(options)

    sigOptionsInserted = pyqtSignal(list)
    def insertOptions(self, options, i=None):
        if options is None:
            return
        if not isinstance(options, list):
            options = [options]
        assert isinstance(options, list)

        options = [self.o2o(o) for o in options]

        options = [o for o in options if o not in self.mOptions]

        l = len(options)
        if l > 0:
            if i is None:
                i = len(self.mOptions)
            self.beginInsertRows(QModelIndex(), i, i + len(options) - 1)
            for o in options:
                self.mOptions.insert(i, o)
                i += 1
            self.endInsertRows()

            self.sigOptionsInserted.emit(options)


    def o2o(self,  value):
        if not isinstance(value, Option):
            value = Option(value, '{}'.format(value))
        return value

    def options(self)->list:
        """
        :return: [list-of-Options]
        """
        return self.mOptions[:]

    def optionValues(self)->list:
        """
        :return: [list-str-of-Option-Values]
        """
        return [o.mValue for o in self.options()]

    sigOptionsRemoved = pyqtSignal(list)
    def removeOptions(self, options):
        """
        Removes a list of options from this Options list.
        :param options: [list-of-Options]
        """
        options = [self.o2o(o) for o in options]
        options = [o for o in options if o in self.mOptions]
        removed = []
        for o in options:
            row = self.mOptions.index(o)
            self.beginRemoveRows(QModelIndex(), row, row)
            o2 = self.mOptions[row]
            self.mOptions.remove(o2)
            removed.append(o2)
            self.endRemoveRows()

        if len(removed) > 0:
            self.sigOptionsRemoved.emit(removed)

    def clear(self):
        self.removeOptions(self.mOptions)

    def rowCount(self, parent=None, *args, **kwargs)->int:
        return len(self.mOptions)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return 1

    def idx2option(self, index):
        if index.isValid():
            return self.mOptions[index.row()]
        return None

    def option2idx(self, option):
        if isinstance(option, Option):
            option = option.mValue

        idx = self.createIndex(None, -1, 0)
        for i, o in enumerate(self.mOptions):
            assert isinstance(o, Option)
            if o.mValue == option:
                idx.setRow(i)
                break
        return idx


    def optionNames(self):
        return [o.mName for o in self.mOptions]

    def optionValues(self):
        return [o.mValue for o in self.mOptions]




    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if (index.row() >= len(self.mOptions)) or (index.row() < 0):
            return None
        option = self.idx2option(index)
        if not isinstance(option, Option):
            s = ""
        result = None
        if role == Qt.DisplayRole:
            result = '{}'.format(option.mName)
        elif role == Qt.ToolTipRole:
            result = '{}'.format(option.mName if option.mTooltip is None else option.mTooltip)
        elif role == Qt.DecorationRole:
            result = option.mIcon
        elif role == Qt.UserRole:
            result =  option
        return result



class TreeNode(QObject):

    sigWillAddChildren = pyqtSignal(QObject, int, int)
    sigAddedChildren = pyqtSignal(QObject, int, int)
    sigWillRemoveChildren = pyqtSignal(QObject, int, int)
    sigRemovedChildren = pyqtSignal(QObject, int, int)
    sigUpdated = pyqtSignal(QObject)
    sigExpandedChanged = pyqtSignal(QObject, bool)

    def __init__(self, parentNode, name=None, value=None, values=None, icon=None, toolTip:str=None, statusTip:str=None, **kwds):
        super(TreeNode, self).__init__()
        QObject.__init__(self)

        self.mParentNode = parentNode

        self.mChildren = []
        self.mName = name
        self.mValues = []
        self.mIcon = None
        self.mToolTip = None
        self.mCheckState = Qt.Unchecked
        self.mCheckable = False
        self.mStatusTip = ''
        self.mExpanded = False

        if name:
            self.setName(name)
        if value is not None:
            self.setValue(value)
        if icon:
            self.setIcon(icon)
        if toolTip:
            self.setToolTip(toolTip)

        if statusTip:
            self.setStatusTip(statusTip)

        if values is not None:
            self.setValues(values)

        if isinstance(parentNode, TreeNode):
            parentNode.appendChildNodes([self])

        s = ""


    def __iter__(self):
        return iter(self.mChildren)

    def __len__(self):
        return len(self.mChildren)


    def setExpanded(self, expanded:bool):
        """
        Expands the node
        :param expanded:
        :return:
        """
        assert isinstance(expanded, bool)
        b = self.mExpanded != expanded
        self.mExpanded = expanded

        if b and not self.signalsBlocked():
            self.sigExpandedChanged.emit(self, self.mExpanded)

    def expanded(self)->bool:
        return self.mExpanded == True

    def setStatusTip(self, statusTip:str):
        """
        Sets the nodes's status tip to the string specified by statusTip.
        :param statusTip: str
        """
        assert isinstance(statusTip, str)
        self.mStatusTip = statusTip

    def statusTip(self)->str:
        """
        Returns the nodes's status tip.
        :return: str
        """
        return self.mStatusTip

    def setCheckState(self, checkState):
        assert isinstance(checkState, Qt.CheckState)
        self.mCheckState = checkState

    def checkState(self)->Qt.CheckState:
        return self.mCheckState

    def checked(self)->bool:
        return self.isCheckable() and self.mCheckState == Qt.Checked

    def isCheckable(self)->bool:
        return self.mCheckable == True

    def setCheckable(self, b:bool):
        assert isinstance(b, bool)
        self.mCheckable = b


    def clone(self, parent=None):

        n = TreeNode(parent)
        n.mName = self.mName
        n.mValues = copy.copy(self.mValues[:])
        n.mIcon = QIcon(self.mIcon)
        n.mToolTip = self.mToolTip

        for childNode in self.mChildren:
            assert isinstance(childNode, TreeNode)
            childNode.clone(parent=n)
        return n



    def nodeIndex(self):
        return self.mParentNode.mChildren.index(self)

    def next(self):
        i = self.nodeIndex()
        if i < len(self.mChildren.mChildren):
            return self.mParentNode.mChildren[i + 1]
        else:
            return None

    def previous(self):
        i = self.nodeIndex()
        if i > 0:
            return self.mParentNode.mChildren[i - 1]
        else:
            return None

    def detach(self):
        """
        Detaches this TreeNode from its parent TreeNode
        :return:
        """
        if isinstance(self.mParentNode, TreeNode):
            self.mParentNode.mChildren.remove(self)
            self.setParentNode(None)

    def appendChildNodes(self, listOfChildNodes):
        self.insertChildNodes(len(self.mChildren), listOfChildNodes)

    def insertChildNodes(self, index, listOfChildNodes):
        assert index <= len(self.mChildren)
        if isinstance(listOfChildNodes, TreeNode):
            listOfChildNodes = [listOfChildNodes]
        assert isinstance(listOfChildNodes, list)
        listOfChildNodes = [l for l in listOfChildNodes if l not in self.mChildren]

        l = len(listOfChildNodes)
        idxLast = index + l - 1
        self.sigWillAddChildren.emit(self, index, idxLast)
        if not self.signalsBlocked():
            self.sigWillAddChildren.emit(self, index, idxLast)
        for i, node in enumerate(listOfChildNodes):
            assert isinstance(node, TreeNode)
            node.mParentNode = self
            # connect node signals
            node.sigWillAddChildren.connect(self.sigWillAddChildren)
            node.sigAddedChildren.connect(self.sigAddedChildren)
            node.sigWillRemoveChildren.connect(self.sigWillRemoveChildren)
            node.sigRemovedChildren.connect(self.sigRemovedChildren)
            node.sigUpdated.connect(self.sigUpdated)

            self.mChildren.insert(index + i, node)
        import time
        t0 = time.time()

        self.sigAddedChildren.emit(self, index, idxLast)
        s = ""
        if not self.signalsBlocked():
            self.sigAddedChildren.emit(self, index, idxLast)

    def removeChildNode(self, node):
        assert node in self.mChildren
        i = self.mChildren.index(node)
        self.removeChildNodes(i, 1)

    def removeChildNodes(self, row, count):

        if row < 0 or count <= 0:
            return False

        rowLast = row + count - 1

        if rowLast >= self.childCount():
            return False

        self.sigWillRemoveChildren.emit(self, row, rowLast)
        to_remove = self.childNodes()[row:rowLast + 1]
        for n in to_remove:
            self.mChildren.remove(n)
            # n.mParent = None

        self.sigRemovedChildren.emit(self, row, rowLast)

    def setToolTip(self, toolTip:str):
        """
        Sets the tooltip
        :param toolTip: str
        """
        self.mToolTip = toolTip

    def toolTip(self)->str:
        """
        Returns a tooltip
        :return: str
        """
        return self.mToolTip

    def parentNode(self):
        """
        Returns the parent TreeNode that owns this TreeNode
        :return: TreeNode
        """
        return self.mParentNode

    def setParentNode(self, treeNode):
        """
        :param treeNode:
        :return:
        """
        assert isinstance(treeNode, TreeNode)
        self.mParentNode = treeNode

    def setIcon(self, icon:QIcon):
        """
        Sets the TreeNode icon
        :param icon: QIcon
        """
        self.mIcon = icon

    def icon(self)->QIcon:
        """
        Returns the TreeNode icon
        :return: QIcon
        """
        return self.mIcon

    def setName(self, name:str):
        """
        Sets the TreeNodes name
        :param name: str
        """
        self.mName = name

    def name(self)->str:
        """
        Returns the TreeNodes name
        :return: str
        """
        return self.mName

    def contextMenu(self):
        return None

    def setValue(self, value):
        """
        Same as setValues([value])
        :param value: any
        """
        if value == None:
            self.setValues(None)
        else:
            self.setValues([value])

    def setValues(self, listOfValues:list):
        """
        Sets the values show by this TreeNode
        :param listOfValues: [list-of-values]
        """
        old = self.mValues
        if listOfValues is None:
            self.mValues = []
        else:
            if not isinstance(listOfValues, list):
                listOfValues = [listOfValues]
            self.mValues = listOfValues[:]
        if self.mValues != old:
            self.sigUpdated.emit(self)
            if not self.signalsBlocked():
                self.sigUpdated.emit(self)

    def values(self)->list:
        """
        Returns the list of values
        :return:
        """
        return self.mValues[:]

    def value(self):
        """
        Returns the first value of all defined values or None, if no values are defined.
        :return:
        """
        if len(self.mValues) > 0:
            return self.mValues[0]
        else:
            return None


    def childCount(self)->int:
        """Returns the number of child nones"""
        return len(self.mChildren)


    def childNodes(self)->list:
        """
        Returns the child nodes
        :return: [list-of-TreeNodes]
        """
        return self.mChildren[:]

    def findChildNodes(self, type, recursive=True):
        """
        Returns a list of child nodes with node-type `type`.
        :param type: node-class
        :param recursive: if True (default), will search for nodes of type `type` also in child and child-child nodes.
        :return: [list-of-TreeNodes]
        """
        results = []
        for node in self.mChildren:
            if isinstance(node, type):
                results.append(node)
            if recursive:
                results.extend(node.findChildNodes(type, recursive=True))
        return results


class TreeModel(QAbstractItemModel):
    """
    A QAbstractItemModel implementation to be used in QTreeViews
    """
    def __init__(self, parent=None, rootNode=None):
        super(TreeModel, self).__init__(parent)

        self.mColumnNames = ['Node', 'Value']
        self.mRootNode = rootNode if isinstance(rootNode, TreeNode) else TreeNode(None)
        self.mRootNode.sigWillAddChildren.connect(self.onNodeWillAddChildren)
        self.mRootNode.sigAddedChildren.connect(self.onNodeAddedChildren)
        self.mRootNode.sigWillRemoveChildren.connect(self.onNodeWillRemoveChildren)
        self.mRootNode.sigRemovedChildren.connect(self.onNodeRemovedChildren)
        self.mRootNode.sigUpdated.connect(self.onNodeUpdated)

        self.mTreeView = None
        if isinstance(parent, QTreeView):
            self.connectTreeView(parent)
        s = ""

    def rootNode(self)->TreeNode:
        """
        Returns the (invisible) root node
        :return: TreeNode
        """
        return self.mRootNode


    def onNodeWillAddChildren(self, node, idx1, idxL):
        idxNode = self.node2idx(node)
        self.beginInsertRows(idxNode, idx1, idxL)

    def onNodeAddedChildren(self, *args):
        self.endInsertRows()
        # for i in range(idx1, idxL+1):


    def onNodeWillRemoveChildren(self, node, idx1, idxL):
        idxNode = self.node2idx(node)
        self.beginRemoveRows(idxNode, idx1, idxL)

    def onNodeRemovedChildren(self, node, idx1, idxL):
        self.endRemoveRows()

    def onNodeUpdated(self, node):
        idxNode = self.node2idx(node)
        self.dataChanged.emit(idxNode, idxNode)


    def headerData(self, section, orientation, role):
        assert isinstance(section, int)

        if orientation == Qt.Horizontal and role == Qt.DisplayRole:

            if len(self.mColumnNames) > section:
                return self.mColumnNames[section]
            else:
                return ''

        else:
            return None

    def parent(self, index:QModelIndex)->QModelIndex:
        """
        Returns the parent index of a QModelIndex `index`
        :param index: QModelIndex
        :return: QModelIndex
        """
        if not index.isValid():
            return QModelIndex()
        node = self.idx2node(index)
        if not isinstance(node, TreeNode):
            return QModelIndex()

        parentNode = node.parentNode()
        if not isinstance(parentNode, TreeNode):
            return QModelIndex()

        return self.node2idx(parentNode)

        if node not in parentNode.mChildren:
            return QModelIndex
        row = parentNode.mChildren.index(node)
        return self.createIndex(row, 0, parentNode)

    def rowCount(self, index:QModelIndex)->int:
        """
        Return the row-count, i.e. number of child node for a TreeNode as index `index`.
        :param index: QModelIndex
        :return: int
        """
        if index is None:
            return len(self.rootNode().mChildren)
        node = index.internalPointer()
        if isinstance(node, TreeNode):
            return node.childCount()
        else:
            return len(self.mRootNode)
        if not index.isValid():
            return 0
        #assert isinstance(index, QModelIndex)
        return index.internalPointer().childCount()

        node = self.idx2node(index)
        #node = index.internalPointer()
        return len(node.mChildren) if isinstance(node, TreeNode) else 0

    def hasChildren(self, index=QModelIndex())->bool:
        """
        Returns True if a TreeNode at index `index` has child nodes.
        :param index: QModelIndex
        :return: bool
        """
        node = self.idx2node(index)
        return isinstance(node, TreeNode) and len(node.mChildren) > 0

    def columnNames(self)->list:
        """
        Returns the column names
        :return: [list-of-string]
        """
        return self.mColumnNames[:]

    def idx2columnName(self, index:QModelIndex)->str:
        """
        Returns the column name related to a QModelIndex
        :param index: QModelIndex
        :return: str, column name
        """
        if not index.isValid():
            return None
        else:
            return self.mColumnNames[index.column()]

    def columnCount(self, index= QModelIndex())->int:
        """
        Returns the number of columns
        :param index: QModelIndex
        :return:
        """
        return len(self.mColumnNames)

    def connectTreeView(self, treeView):
        self.mTreeView = treeView



    def index(self, row:int, column:int, parent:QModelIndex=None)->QModelIndex:
        """
        Returns the QModelIndex
        :param row: int
        :param column: int
        :param parent: QModelIndex
        :return: QModelIndex
        """
        if parent is None:
            parentNode = self.mRootNode
        else:
            parentNode = self.idx2node(parent)

        if row < 0 or row >= parentNode.childCount():
            return QModelIndex()
        if column < 0 or column >= len(self.mColumnNames):
            return QModelIndex()

        if isinstance(parentNode, TreeNode) and row < len(parentNode.mChildren):
            return self.createIndex(row, column, parentNode.mChildren[row])
        else:
            return QModelIndex()

    def findParentNode(self, node, parentNodeType)->TreeNode:
        """
        finds the next parent TreeNode of type `parentNodeType`
        :param node: TreeNode
        :param parentNodeType: cls
        :return: TreeNode instance
        """
        assert isinstance(node, TreeNode)
        while True:
            if isinstance(node, parentNodeType):
                return node
            if not isinstance(node.parentNode(), TreeNode):
                return None
            node = node.parentNode()

    def indexes2nodes(self, indexes:list):
        """
        Returns the TreeNodes related to a list of QModelIndexes
        :param indexes: [list-of-QModelIndex]
        :return: [list-of-TreeNodes]
        """
        assert isinstance(indexes, list)
        nodes = []
        for idx in indexes:
            n = self.idx2node(idx)
            if n not in nodes:
                nodes.append(n)
        return nodes

    def nodes2indexes(self, nodes:list):
        """
        Converts a list of TreeNodes into the corresponding list of QModelIndexes
        Set indexes2nodes
        :param nodes: [list-of-TreeNodes]
        :return: [list-of-QModelIndex]
        """
        return [self.node2idx(n) for n in nodes]


    def expandNode(self, node, expand=True, recursive=True):
        assert isinstance(node, TreeNode)
        if isinstance(self.mTreeView, QTreeView):
            idx = self.node2idx(node)
            self.mTreeView.setExpanded(idx, expand)

            if recursive:
                for n in node.childNodes():
                    self.expandNode(n, expand=expand, recursive=recursive)


    def idx2node(self, index:QModelIndex)->TreeNode:
        """
        Returns the TreeNode related to an QModelIndex `index`.
        :param index: QModelIndex
        :return: TreeNode
        """

        if index.row() == -1 and index.column() == -1:
            return self.mRootNode
        elif not index.isValid():
            return self.mRootNode
        else:
            node = index.internalPointer()
            assert isinstance(node, TreeNode)
            return node

    def node2idx(self, node:TreeNode)->QModelIndex:
        """
        Returns a TreeNode's QModelIndex
        :param node: TreeNode
        :return: QModelIndex
        """
        assert isinstance(node, TreeNode)
        if node == self.mRootNode:
            return QModelIndex()
            return self.createIndex(-1, -1, node)
        else:
            parentNode = node.parentNode()
            assert isinstance(parentNode, TreeNode)
            if node not in parentNode.mChildren:
                return QModelIndex()
            r = parentNode.mChildren.index(node)
            return self.createIndex(r, 0, node)

    def data(self, index, role):
        """

        :param index: QModelIndex
        :param role: Qt.ItemRole
        :return: object
        """
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return None

        node = self.idx2node(index)
        #node = self.idx2node(index)
        node = index.internalPointer()
        assert isinstance(node, TreeNode)
        col = index.column()
        if role == Qt.UserRole:
            return node

        col = index.column()
        if col == 0:
            if role in [Qt.DisplayRole, Qt.EditRole]:
                return node.name()
            if role == Qt.DecorationRole:
                return node.icon()
            if role == Qt.ToolTipRole:
                return node.toolTip()
        if col > 0:
            i = col - 1
            if role in [Qt.DisplayRole, Qt.EditRole] and len(node.values()) > i:
                return str(node.values()[i])

    def flags(self, index):
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return Qt.NoItemFlags
        node = self.idx2node(index)
        #node = self.idx2node(index)
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable



class TreeView(QTreeView):
    """
    A basic QAbstractItemView implementation to realize TreeModels.
    """
    def __init__(self, *args, **kwds):
        super(TreeView, self).__init__(*args, **kwds)

        self.mModel = None

    def setModel(self, model:QAbstractItemModel):
        """
        Sets the TreeModel
        :param model: TreeModel
        """
        super(TreeView, self).setModel(model)

        self.mModel = model
        if isinstance(self.mModel, QAbstractItemModel):
            self.mModel.modelReset.connect(self.onModelReset)
            self.mModel.dataChanged.connect(self.onDataChanged)
            self.mModel.rowsInserted.connect(self.onRowsInserted)

    def onModelReset(self):
        for row in range(self.model().rowCount(QModelIndex())):
            idx = self.model().index(row, 0)
            self.setColumnSpan(idx)

    def onRowsInserted(self, parent:QModelIndex, first:int, last:int):

        for row in range(first, last+1):
            idx = self.model().index(row, 0, parent)
            self.setColumnSpan(idx)

    def onDataChanged(self, tl:QModelIndex, br:QModelIndex, roles):


        parent = tl.parent()
        for row in range(tl.row(), br.row() + 1):
            idx = self.model().index(row, 0, parent)
            self.setColumnSpan(idx)
        s = ""

    def setColumnSpan(self, idx:QModelIndex):
        """
        Sets the column span for index `idx` and all child widgets
        :param idx:
        :return:
        """
        assert isinstance(idx, QModelIndex)
        if not idx.isValid():
            return

        row = idx.row()
        nRows = self.model().rowCount(idx)
        node = self.model().data(idx, role=Qt.UserRole)
        if isinstance(node, TreeNode):
            span = len(node.values()) == 0
            if span == True and node.value() != None:
                s = ""
            self.setFirstColumnSpanned(idx.row(), idx.parent(), span)

            for row in range(self.model().rowCount(idx)):
                idx2 = self.model().index(row, 0, idx)
                self.setColumnSpan(idx2)

    def selectedNode(self)->TreeNode:
        """
        Returns the first of all selected TreeNodes
        :return: TreeNode
        """
        for i in self.selectedIndexes():
            node = self.model().data(i, Qt.UserRole)
            if isinstance(node, TreeNode):
                return node

        return None



    def selectedNodes(self)->list:
        """
        Returns all selected TreeNodes
        :return: [list-of-TreeNodes]
        """
        nodes = []
        for i in self.selectedIndexes():
            node = self.model().data(i, Qt.UserRole)
            if isinstance(node, TreeNode) and node not in nodes:
                nodes.append(node)
        return nodes


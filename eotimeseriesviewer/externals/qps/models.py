# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/models.py

    Basic QAbstractItem models to handle and visualize data
    ---------------------
    Beginning            : 2019-01-11
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import warnings
import copy
import enum
import typing
import types
import sip

import collections.abc
import numpy as np
import inspect
from qgis.PyQt.QtCore import QModelIndex, QAbstractItemModel, QAbstractListModel, \
    pyqtSignal, Qt, QObject, QAbstractListModel, QSize, pyqtBoundSignal, QMetaEnum, QMetaType
from qgis.PyQt.QtWidgets import QComboBox, QTreeView, QMenu
from qgis.PyQt.QtGui import QIcon, QContextMenuEvent


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

    def value(self) -> object:
        """
        Returns the option value
        :return: object
        """
        return self.mValue

    def name(self) -> str:
        """
        Returns the option name
        :return: str
        """
        return self.mName

    def toolTip(self) -> str:
        """
        Returns the option tooltip.
        :return: str
        """
        return self.mTooltip

    def icon(self) -> QIcon:
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
        elif isinstance(options, enum.Enum):
            options = [Option(e.value, name=str(e.name)) for e in options]
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

    def o2o(self, value):
        if not isinstance(value, Option):
            value = Option(value, '{}'.format(value))
        return value

    def options(self) -> list:
        """
        :return: [list-of-Options]
        """
        return self.mOptions[:]

    def optionValues(self) -> list:
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

    def rowCount(self, parent=None, *args, **kwargs) -> int:
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
            result = option
        return result


class TreeNode(QObject):
    sigWillAddChildren = pyqtSignal(object, int, int)
    sigAddedChildren = pyqtSignal(object, int, int)
    sigWillRemoveChildren = pyqtSignal(object, int, int)
    sigRemovedChildren = pyqtSignal(object, int, int)
    sigUpdated = pyqtSignal(object)

    def __init__(self,
                 name: str = None,
                 value: any = None,
                 values=None,
                 icon: QIcon = None,
                 toolTip: str = None,
                 statusTip: str = None,
                 **kwds):

        super().__init__()

        self.mParentNode: TreeNode = None
        self.mChildren: typing.List[TreeNode] = []
        self.mName: str = name
        self.mValues: list = []
        self.mIcon: QIcon = None
        self.mToolTip: str = None
        self.mCheckState: Qt.CheckState = Qt.Unchecked
        self.mCheckable: bool = False
        self.mStatusTip: str = ''

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

    def populateContextMenu(self, menu: QMenu):
        """
        Overwrite to provide a TreeNode specific context menu
        :param menu:
        :return:
        """
        pass

    def __iter__(self):
        return iter(self.mChildren)

    def __len__(self):
        return len(self.mChildren)

    def __contains__(self, item):
        return item in self.mChildren

    def __getitem__(self, slice):
        return self.mChildren[slice]

    def depth(self) -> int:
        d = 0
        parent = self.parentNode()
        while isinstance(parent, TreeNode):
            d += 1
            parent = parent.parentNode()
        return d

    def columnCount(self) -> int:
        """
        A node has at least one column for its name
        :return:
        :rtype:
        """
        return len(self.mValues) + 1

    def expanded(self) -> bool:
        return self.mExpanded == True

    def setStatusTip(self, statusTip: str):
        """
        Sets the nodes's status tip to the string specified by statusTip.
        :param statusTip: str
        """
        assert isinstance(statusTip, str)
        self.mStatusTip = statusTip

    def statusTip(self) -> str:
        """
        Returns the nodes's status tip.
        :return: str
        """
        return self.mStatusTip

    def setCheckState(self, checkState):
        assert isinstance(checkState, Qt.CheckState)
        self.mCheckState = checkState

    def canFetchMore(self) -> bool:
        """
        To be overwritten by TreeNodes that can fetch data.
        Need to implement .fetch() as well
        :return:
        """
        return False

    def fetch(self):
        """
        To be overwritten by TreeNodes that allow to fetch data.
        :return:
        """
        pass

    def checkState(self) -> Qt.CheckState:
        return self.mCheckState

    def checked(self) -> bool:
        return self.isCheckable() and self.mCheckState == Qt.Checked

    def isCheckable(self) -> bool:
        return self.mCheckable == True

    def setCheckable(self, b: bool):
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

    def nodeIndex(self) -> int:
        p = self.parentNode()
        if isinstance(p, TreeNode):
            return p.mChildren.index(self)
        else:
            None

    def next(self):
        p = self.parentNode()
        if isinstance(p, TreeNode):
            i = p.mChildren.index(self)
            if i < len(p.mChildren) - 1:
                return p.mChildren[i + 1]
        return None

    def previous(self):
        p = self.parentNode()
        if isinstance(p, TreeNode):
            i = p.mChildren.index(self)
            if i > 0:
                return p.mChildren[i - 1]
        return None

    def detach(self):
        """
        Detaches this TreeNode from its parent TreeNode
        :return:
        """
        p = self.parent()
        if isinstance(p, TreeNode):
            p.removeChildNodes(self)

    def hasChildren(self) -> bool:
        return len(self.mChildren) > 0

    def appendChildNodes(self, child_nodes):
        self.insertChildNodes(len(self.mChildren), child_nodes)

    def insertChildNodes(self, index: int, child_nodes):
        assert index <= len(self.mChildren)
        if isinstance(child_nodes, TreeNode):
            child_nodes = [child_nodes]
        assert isinstance(child_nodes, list)
        child_nodes = [l for l in child_nodes if l not in self.mChildren]

        l = len(child_nodes)
        if l == 0:
            return
        idxLast = index + l - 1
        self.sigWillAddChildren.emit(self, index, idxLast)

        for i, node in enumerate(child_nodes):
            assert isinstance(node, TreeNode)
            # connect node signals
            node.sigWillAddChildren.connect(self.sigWillAddChildren)
            node.sigAddedChildren.connect(self.sigAddedChildren)
            node.sigWillRemoveChildren.connect(self.sigWillRemoveChildren)
            node.sigRemovedChildren.connect(self.sigRemovedChildren)
            node.sigUpdated.connect(self.sigUpdated)

            node.setParentNode(self)
            self.mChildren.insert(index + i, node)

        self.sigAddedChildren.emit(self, index, idxLast)

    def removeAllChildNodes(self):
        self.removeChildNodes(self.childNodes())

    def removeChildNodes(self, child_nodes):
        """
        Removes child-nodes
        :param child_nodes:
        :type child_nodes:
        :return:
        :rtype:
        """
        if isinstance(child_nodes, TreeNode):
            child_nodes = [child_nodes]
        child_nodes: typing.List[TreeNode]
        for node in child_nodes:
            assert isinstance(node, TreeNode)
            assert node in self.mChildren
            assert node.parentNode() == self

        child_nodes = sorted(child_nodes, key=lambda node: node.nodeIndex())
        removed = []
        while len(child_nodes) > 0:
            # find neighbored nodes to remove
            nextNode = child_nodes[0]
            toRemove = []
            while isinstance(nextNode, TreeNode) and nextNode in child_nodes:
                toRemove.append(nextNode)
                nextNode = nextNode.next()

            first = toRemove[0].nodeIndex()
            last = toRemove[-1].nodeIndex()

            self.sigWillRemoveChildren.emit(self, first, last)

            for node in reversed(toRemove):
                # disconnect node signals
                node.sigWillAddChildren.disconnect(self.sigWillAddChildren)
                node.sigAddedChildren.disconnect(self.sigAddedChildren)
                node.sigWillRemoveChildren.disconnect(self.sigWillRemoveChildren)
                node.sigRemovedChildren.disconnect(self.sigRemovedChildren)
                node.sigUpdated.disconnect(self.sigUpdated)

                self.mChildren.remove(node)

                node.setParentNode(None)

                child_nodes.remove(node)
                removed.append(node)

            self.sigRemovedChildren.emit(self, first, last)

    def setToolTip(self, toolTip: str):
        """
        Sets the tooltip
        :param toolTip: str
        """
        self.mToolTip = toolTip

    def toolTip(self) -> str:
        """
        Returns a tooltip
        :return: str
        """
        return self.mToolTip

    def setParentNode(self, node):
        self.mParentNode: TreeNode = node

    def parentNode(self):
        return self.mParentNode

    def setIcon(self, icon: QIcon):
        """
        Sets the TreeNode icon
        :param icon: QIcon
        """
        if icon != self.mIcon:
            self.mIcon = icon
            self.sigUpdated.emit(self)

    def icon(self) -> QIcon:
        """
        Returns the TreeNode icon
        :return: QIcon
        """
        return self.mIcon

    def setName(self, name: str):
        """
        Sets the TreeNodes name
        :param name: str
        """
        if name != self.mName:
            self.mName = str(name)
            self.sigUpdated.emit(self)

    def name(self) -> str:
        """
        Returns the TreeNodes name
        :return: str
        """
        return self.mName

    def populateContextMenu(self, menu: QMenu):
        """
        Implement this to add a TreeNode specific context menu
        :param menu:
        :return:
        """
        pass

    def setValue(self, value):
        """
        Same as setValues([value])
        :param value: any
        """
        if value == None:
            self.setValues(None)
        else:
            self.setValues([value])

    def setValues(self, values: list):
        """
        Sets the values show by this TreeNode
        :param values: [list-of-values]
        """
        if not isinstance(values, list):
            values = [values]

        if self.mValues != values:
            self.mValues.clear()
            self.mValues.extend(values)
            self.sigUpdated.emit(self)

    def values(self) -> list:
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

    def childCount(self) -> int:
        """Returns the number of child nodes"""
        return len(self.mChildren)

    def childNodes(self) -> list:
        """
        Returns the child nodes
        :return: [list-of-TreeNodes]
        """
        return self.mChildren[:]

    def findParentNode(self, nodeType):
        """
        Returns the next upper TreeNode of type "nodeType"
        :param nodeType:
        :return: TreeNode of type "nodeType" or None
        """

        parent = self.parentNode()
        if not isinstance(parent, TreeNode):
            return None
        elif isinstance(parent, nodeType):
            return parent
        else:
            return parent.findParentNode(nodeType)

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


class PyObjectTreeNode(TreeNode):

    def __init__(self, *args, obj=None, **kwds):
        super().__init__(*args, **kwds)

        self.mPyObject = obj
        self.mFetched: bool = False

        # end-nodes which cannot be fetched deeper
        if isinstance(obj, (int, float, str)):
            self.setValue(obj)
            self.mFetched = True
            """
            elif isinstance(obj, (np.ndarray,)):
                value = np.array2string(obj, threshold=25)
                self.setValue(value)
                self.mFetched = True
            elif isinstance(obj, tuple):
                value = '{:1.25}'.format(str(obj)).strip()
                self.setValue(value)
            """
        else:
            if hasattr(obj, '__name__'):
                value = obj.__name__
            else:
                value = type(obj).__name__
            self.setValue(value)
            self.setToolTip(f'{self.name()} {str(obj)}')

    def canFetchMore(self) -> bool:
        return self.mFetched is False

    @staticmethod
    def valueAndTooltip(obj) -> typing.Tuple[str, str]:
        pass

    def hasChildren(self) -> bool:
        return self.mFetched is False or len(self.mChildren) > 0

    def fetch(self):
        self.mFetched = True
        candidates = []
        newNodes: typing.List[PyObjectTreeNode] = []
        obj = self.mPyObject
        if isinstance(obj, (list, tuple)):
            for i, o in enumerate(obj):
                candidates.append((f'{i}', o))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                candidates.append((k, v))
        elif isinstance(obj, object):
            for m, v in sorted(inspect.getmembers(obj)):
                candidates.append((m, v))

        candidates = sorted(candidates, key=lambda t: t[0])

        while len(candidates) > 0:
            a, v = candidates.pop(0)
            if not isinstance(a, str) or a.startswith('__'):
                continue
            if isinstance(v, (types.BuiltinFunctionType,
                                pyqtSignal,
                                pyqtBoundSignal,
                                sip.wrappertype)
                          ) or \
                    inspect.isfunction(v) or \
                    inspect.ismethod(v):
                continue
            if isinstance(v, QMetaEnum):
                s = ""
            # create a new node
            newNodes.append(PyObjectTreeNode(name=a, obj=v))

        if len(newNodes) > 0:
            self.appendChildNodes(newNodes)


class TreeModel(QAbstractItemModel):
    """
    A QAbstractItemModel implementation to be used in QTreeViews
    """

    def __init__(self, parent: QObject = None, rootNode: TreeNode = None):
        super().__init__(parent)

        self.mRootNode: TreeNode
        if isinstance(rootNode, TreeNode):
            self.mRootNode = rootNode
        else:
            self.mRootNode = TreeNode(name='<root node>')

        self.mRootNode.setValues(['Name', 'Value'])
        self.mRootNode.sigWillAddChildren.connect(self.onNodeWillAddChildren)
        self.mRootNode.sigAddedChildren.connect(self.onNodeAddedChildren)
        self.mRootNode.sigWillRemoveChildren.connect(self.onNodeWillRemoveChildren)
        self.mRootNode.sigRemovedChildren.connect(self.onNodeRemovedChildren)
        self.mRootNode.sigUpdated.connect(self.onNodeUpdated)

    def setColumnNames(self, names):
        assert isinstance(names, list)
        self.mRootNode.setValues(names)

    def __contains__(self, item):
        return item in self.mRootNode

    def __getitem__(self, slice):
        return self.mRootNode[slice]

    def rootNode(self) -> TreeNode:
        """
        Returns the (invisible) root node
        :return: TreeNode
        """
        return self.mRootNode

    def onNodeWillAddChildren(self, node: TreeNode, first: int, last: int):
        parent = self.node2idx(node)
        if not node == self.mRootNode:
            assert parent.internalPointer() == node
        self.beginInsertRows(parent, first, last)

    def onNodeAddedChildren(self, node: TreeNode, first: int, last: int):
        self.endInsertRows()
        parent = self.node2idx(node)
        idx1 = self.index(first, 0, parent)
        idx2 = self.index(last, 0, parent)
        self.dataChanged.emit(idx1, idx2)

    def maxColumnCount(self, index: QModelIndex) -> int:
        assert isinstance(index, QModelIndex)
        cnt = self.columnCount(index)
        for row in range(self.rowCount(index)):
            idx = self.index(row, 0, index)
            cnt = max(cnt, self.maxColumnCount(idx))
        return cnt

    def onNodeWillRemoveChildren(self, node: TreeNode, first: int, last: int):
        idxNode = self.node2idx(node)
        self.beginRemoveRows(idxNode, first, last)

    def onNodeRemovedChildren(self, node: TreeNode, first: int, last: int):
        self.endRemoveRows()

    def onNodeUpdated(self, node: TreeNode):
        idx = self.node2idx(node)
        idx2 = self.index(idx.row(), node.columnCount() - 1, parent=idx.parent())
        self.dataChanged.emit(idx, idx2)

    def headerData(self, section, orientation, role):
        assert isinstance(section, int)
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section < len(self.mRootNode.values()):
                return self.mRootNode.values()[section]
            else:
                return f'Column {section + 1}'
        return None

    def parent(self, index: QModelIndex) -> QModelIndex:
        """
        Returns the parent index of a QModelIndex `index`
        :param index: QModelIndex
        :return: QModelIndex
        """
        if not index.isValid():
            return QModelIndex()
        childNode: TreeNode = index.internalPointer()
        if not isinstance(childNode, TreeNode) or \
                sip.isdeleted(childNode):
            return QModelIndex()

        parentNode: TreeNode = childNode.parentNode()
        if not isinstance(parentNode, TreeNode) or \
                sip.isdeleted(parentNode) \
                or parentNode == self.mRootNode:
            return QModelIndex()
        else:
            idx = self.node2idx(parentNode)
            return self.createIndex(idx.row(), idx.column(), parentNode)

    def rowCount(self, parent: QModelIndex = None) -> int:
        """
        Return the row-count, i.e. number of child node for a TreeNode at index `index`.
        :param index: QModelIndex
        :return: int
        """
        if parent is None:
            parent = QModelIndex()

        parentNode: TreeNode = self.idx2node(parent)
        assert isinstance(parentNode, TreeNode)
        return parentNode.childCount()

    def hasChildren(self, index=None) -> bool:
        """
        Returns True if a TreeNode at index `index` has child nodes.
        :param index: QModelIndex
        :return: bool
        """
        if index is None:
            index = QModelIndex()
        node = self.idx2node(index)
        if not isinstance(node, TreeNode):
            return False
        else:
            return node.hasChildren()

    def columnNames(self) -> list:
        """
        Returns the column names
        :return: [list-of-string]
        """
        return self.mColumnNames[:]

    def printModel(self, index: QModelIndex, prefix=''):
        """
        Prints the model oder a sub-node specified by index
        :param index:
        :type index:
        :param prefix:
        :type prefix:
        :return:
        :rtype:
        """
        if index is None:
            index = QModelIndex()
        if isinstance(index, TreeNode):
            index = self.node2idx(index)
        print(f'{prefix} {self.data(index, role=Qt.DisplayRole)}')
        for r in range(self.rowCount(index)):
            idx = self.index(r, 0, parent=index)
            self.printModel(idx, prefix=f'{prefix}-')

    def span(self, idx) -> QSize():

        return super(TreeModel, self).span(idx)

    def canFetchMore(self, parent: QModelIndex) -> bool:

        if not parent.isValid() or parent.column() > 0:
            return False

        node = parent.internalPointer()

        if isinstance(node, TreeNode):
            return node.canFetchMore()
        else:
            return False

    def fetchMore(self, index: QModelIndex):
        """
        Fetches node content, if implemented with TreeNode.fetch()
        :param index:
        :return:
        """
        node = index.internalPointer()
        if isinstance(node, TreeNode):
            node.fetch()

    def columnCount(self, parent: QModelIndex = None) -> int:
        """
        Returns the number of columns
        :param index: QModelIndex
        :return:
        """
        return len(self.mRootNode.values())

        """
        if not isinstance(parent, QModelIndex):
            parent = QModelIndex()
        if not parent.isValid():
            return len(self.rootNode().values())

        parentNode: TreeNode = parent.internalPointer()
        assert isinstance(parentNode, TreeNode)

        return parentNode.columnCount()
        """

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        """
        Returns the QModelIndex
        :param row: int
        :param column: int
        :param parent: QModelIndex
        :return: QModelIndex
        """
        if parent is None:
            parent = QModelIndex()

        if not parent.isValid():
            parentNode: TreeNode = self.mRootNode
        else:
            parentNode: TreeNode = parent.internalPointer()

        if parentNode.childCount() > 0:
            if row < len(parentNode.mChildren):
                return self.createIndex(row, column, parentNode.mChildren[row])
            else:
                return QModelIndex()
        else:
            return QModelIndex()

    def findParentNode(self, node: TreeNode, nodeType) -> TreeNode:
        """
        finds the next parent TreeNode of type `parentNodeType`
        :param node: TreeNode
        :param parentNodeType: cls
        :return: TreeNode instance
        """
        assert isinstance(node, TreeNode)
        return node.findParentNode(nodeType)

    def indexes2nodes(self, indexes: list):
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

    def removeNodes(self, nodes):
        """
        Removes nodes from the model
        :param nodes:
        :type nodes:
        :return:
        :rtype:
        """
        if isinstance(nodes, TreeNode):
            nodes = [nodes]

        for n in nodes:
            idx = self.node2idx(n)
            if idx.isValid():
                n.parentNode().removeChildNodes(n)

    def nodes2indexes(self, nodes: list):
        """
        Converts a list of TreeNodes into the corresponding list of QModelIndexes
        Set indexes2nodes
        :param nodes: [list-of-TreeNodes]
        :return: [list-of-QModelIndex]
        """
        return [self.node2idx(n) for n in nodes]

    def expandNode(self, node, expand=True, recursive=True):
        assert isinstance(node, TreeNode)
        if False and isinstance(self.mTreeView, QTreeView):
            idx = self.node2idx(node)
            self.mTreeView.setExpanded(idx, expand)

            if recursive:
                for n in node.childNodes():
                    self.expandNode(n, expand=expand, recursive=recursive)

    def idx2node(self, index: QModelIndex) -> TreeNode:
        """
        Returns the TreeNode related to an QModelIndex `index`.
        :param index: QModelIndex
        :return: TreeNode
        """

        if not index.isValid():
            return self.mRootNode
        else:
            node = index.internalPointer()
            assert isinstance(node, TreeNode)
            return node

    def node2idx(self, node: TreeNode) -> QModelIndex:
        """
        Returns a TreeNode's QModelIndex
        :param node: TreeNode
        :return: QModelIndex
        """
        if not isinstance(node, TreeNode):
            return QModelIndex()
        if node == self.mRootNode:
            #return self.createIndex(-1, -1, self.mRootNode)
            return QModelIndex()
        else:
            row: int = node.nodeIndex()
            if not isinstance(row, int):
                return QModelIndex()
            parentIndex = self.node2idx(node.parentNode())
            return self.index(row, 0, parent=parentIndex)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        """

        :param index: QModelIndex
        :param role: Qt.ItemRole
        :return: object
        """
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            if role == Qt.UserRole:
                return self.rootNode()
            else:
                return None

        node = index.internalPointer()
        assert isinstance(node, TreeNode)

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
            # first column is for the node name, other columns are for node values
            i = col - 1

            if len(node.values()) > i:

                if role == Qt.DisplayRole:
                    return str(node.values()[i])
                if role == Qt.EditRole:
                    return node.values()[i]
                if role == Qt.ToolTipRole:
                    tt = [f'{i + 1}: {v}' for i, v in enumerate(node.values())]
                    return '\n'.join(tt)
        return None

    def flags(self, index):
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class TreeView(QTreeView):
    """
    A basic QAbstractItemView implementation to realize TreeModels.
    """
    populateContextMenu = pyqtSignal(QMenu)

    def __init__(self, *args, **kwds):
        super(TreeView, self).__init__(*args, **kwds)

        self.mAutoExpansionDepth: int = 1
        self.mModel = None
        self.mNodeExpansion: typing.Dict[str, bool] = dict()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Default implementation. Emits populateContextMenu to create context menu
        :param event:
        :return:
        """

        menu: QMenu = QMenu()
        menu.setToolTipsVisible(True)
        nodes = self.selectedNodes()
        if len(nodes) == 1:
            node: TreeNode = nodes[0]
            node.populateContextMenu(menu)
        self.populateContextMenu.emit(menu)

        if not menu.isEmpty():
            menu.exec_(self.viewport().mapToGlobal(event.pos()))


    def setAutoExpansionDepth(self, depth: int):
        """
        Sets the depth until which new TreeNodes will be opened
        0 = Top nodes not expanded
        1 = Top nodes expanded
        2 = Top and Subnodes expanded
        :param depth: int
        """
        assert isinstance(depth, int)
        self.mAutoExpansionDepth = depth

    def updateNodeExpansion(self, restore: bool,
                            index: QModelIndex = None, prefix='') -> typing.Dict[str, bool]:
        """
        Allows to save and restore the state of node expansion
        :param restore: bool, set True to save the state, False to restore it
        :param index: QModelIndex()
        :param prefix: string to identify the parent nodes
        :return: Dict[str, bool] that stores the node expansion states
        """
        assert isinstance(restore, bool)

        if not isinstance(index, QModelIndex):
            index = QModelIndex()
        if False and not (restore or index.isValid()):
            self.mNodeExpansion.clear()

        model: QAbstractItemModel = self.model()
        if isinstance(model, QAbstractItemModel):
            rows = model.rowCount(index)
            if rows > 0:
                nodeName = f'{prefix}:{model.data(index, role=Qt.DisplayRole)}'
                nodeDepth: int = self.nodeDepth(index)

                if restore:
                    # restore expansion state, if stored in mNodeExpansion
                    self.setExpanded(index, self.mNodeExpansion.get(nodeName, nodeDepth < self.mAutoExpansionDepth))
                else:
                    # save expansion state
                    self.mNodeExpansion[nodeName] = self.isExpanded(index)

                for row in range(rows):
                    idx = model.index(row, 0, index)
                    self.updateNodeExpansion(restore, index=idx, prefix=nodeName)

        return self.mNodeExpansion

    def setModel(self, model: QAbstractItemModel):
        """
        Sets the TreeModel
        :param model: TreeModel
        """
        super().setModel(model)

        self.mModel = model
        if isinstance(self.mModel, QAbstractItemModel):
            self.mModel.modelReset.connect(self.onModelReset)
            self.mModel.dataChanged.connect(self.onDataChanged)
            #self.mModel.rowsAboutToBeInserted.connect(self.onAboutRowsInserted)
            self.mModel.rowsInserted.connect(self.onRowsInserted)

        # update column spans
        #self.onModelReset()

    def onModelReset(self):
        self.setColumnSpan(QModelIndex(), None, None)

    def nodeDepth(self, index: QModelIndex) -> int:
        if not index.isValid():
            return 0
        return 1 + self.nodeDepth(index.parent())

    def onRowsInserted(self, parent: QModelIndex, first: int, last: int):

        node = self.model().data(parent, Qt.UserRole)
        if True:
            self.setColumnSpan(parent, first, last)
        if True:
            level = self.nodeDepth(parent)
            if level < self.mAutoExpansionDepth:
                self.setExpanded(parent, True)

    def onDataChanged(self, tl: QModelIndex, br: QModelIndex, roles):

        parent = tl.parent()

        for row in range(tl.row(), br.row() + 1):
            idx = self.model().index(row, 0, parent)
            self.setColumnSpan(idx, None, None)
        s = ""

    def setColumnSpan(self, parent: QModelIndex, first:int, last:int):
        """
        Sets the column span for index `idx` and all child widgets
        :param idx:
        :return:
        """

        model: QAbstractItemModel = self.model()
        if not isinstance(model, QAbstractItemModel):
            return

        rows = model.rowCount(parent)
        if rows == 0:
            return
        if not isinstance(first, int):
            first = 0
        if not isinstance(last, int):
            last = rows-1

        assert last < rows
        for r in range(first, last+1):
            idx: QModelIndex = model.index(r, 0, parent)
            idx2: QModelIndex = model.index(r, 1, parent)

            if idx2.isValid():
                txt = idx2.data(Qt.DisplayRole)
                spanned = txt in [None, '']
                #if spanned:
                #    print(f'set spanned:: {idx.data(Qt.DisplayRole)}')
                self.setFirstColumnSpanned(r, parent, spanned)

            self.setColumnSpan(idx, None, None)
        return

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
        """

    def selectedNode(self) -> TreeNode:
        """
        Returns the first of all selected TreeNodes
        :return: TreeNode
        """
        for i in self.selectedIndexes():
            node = self.model().data(i, Qt.UserRole)
            if isinstance(node, TreeNode):
                return node

        return None

    def selectedNodes(self) -> list:
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

from timeseriesviewer.ui.docks import TsvDockWidgetBase, load


class LabelingDockUI(TsvDockWidgetBase, load('labelingdock.ui')):
    def __init__(self, parent=None):
        super(LabelingDockUI, self).__init__(parent)
        self.setupUi(self)

        self.btnClearLabelList.clicked.connect(self.tbCollectedLabels.clear)





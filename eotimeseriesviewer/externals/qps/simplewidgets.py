from qgis.PyQt.QtCore import pyqtSignal, Qt

from qgis.PyQt.QtWidgets import QWidget, QAbstractSpinBox, QSpinBox, QDoubleSpinBox, \
    QHBoxLayout, QVBoxLayout, QSlider


class SliderSpinBox(QWidget):
    sigValueChanged = pyqtSignal(int)

    def __init__(self, *args,
                 spinbox: QAbstractSpinBox = None,
                 spinbox_position: Qt.Alignment = Qt.AlignLeft,
                 **kwds):

        if not isinstance(spinbox, QAbstractSpinBox):
            spinbox = QSpinBox()
        assert isinstance(spinbox, QAbstractSpinBox)
        assert isinstance(spinbox_position, Qt.AlignmentFlag)

        super().__init__(*args, **kwds)

        self.spinbox: QAbstractSpinBox = spinbox
        self.slider: QSlider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self.onSliderValueChanged)
        self.spinbox.valueChanged.connect(self.onSpinboxValueChanged)

        if spinbox_position in [Qt.AlignLeft, Qt.AlignRight]:
            l = QHBoxLayout()
        elif spinbox_position in [Qt.AlignTop, Qt.AlignBottom]:
            l = QVBoxLayout()
        else:
            raise NotImplementedError()

        if spinbox_position in [Qt.AlignLeft, Qt.AlignTop]:
            l.addWidget(self.spinbox)
            l.addWidget(self.slider)
        else:
            l.addWidget(self.slider)
            l.addWidget(self.spinbox)

        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        self.setLayout(l)

    def onSliderValueChanged(self, value):
        v = self.slider2spinboxvalue(value)
        self.spinbox.setValue(v)

    def onSpinboxValueChanged(self, value):
        v = self.spinbox2slidervalue(value)
        if v != self.slider.value():
            self.slider.setValue(v)

        self.sigValueChanged.emit(value)

    def setSingleStep(self, value):
        self.spinbox.setSingleStep(value)
        self.slider.setSingleStep(value)
        self.slider.setPageStep(value * 10)

    def singleStep(self):
        return self.spinbox.singleStep()

    def setMinimum(self, value):
        self.spinbox.setMinimum(value)
        self.slider.setMinimum(self.spinbox2slidervalue(value))

    def spinbox2slidervalue(self, value):
        return value

    def slider2spinboxvalue(self, value):
        return value

    def setMaximum(self, value):
        self.spinbox.setMaximum(value)
        self.slider.setMaximum(self.spinbox2slidervalue(value))

    def maximum(self) -> int:
        return self.spinbox.maximum()

    def minimum(self) -> int:
        return self.spinbox.minimum()

    def setValue(self, value: float):
        self.spinbox.setValue(value)

    def value(self) -> float:
        return self.spinbox.value()

    def setRange(self, vmin, vmax):
        vmin = min(vmin, vmax)
        vmax = max(vmin, vmax)
        assert vmin <= vmax

        self.setMinimum(vmin)
        self.setMaximum(vmax)


class DoubleSliderSpinBox(SliderSpinBox):
    sigValueChanged = pyqtSignal(float)

    def __init__(self, *args, **kwds):
        spinbox = QDoubleSpinBox()
        super().__init__(*args, spinbox=spinbox, **kwds)

        self.spinbox: QDoubleSpinBox
        assert isinstance(self.spinbox, QDoubleSpinBox)
        self.setDecimals(2)
        self.setMinimum(0)
        self.setMaximum(1)
        self.setSingleStep(0.1)

    def spinbox2slidervalue(self, value: float) -> int:
        v = int(round(10 ** self.decimals() * value))
        return v

    def slider2spinboxvalue(self, value: int) -> float:
        v = value / (10 ** self.decimals())
        return v

    def setDecimals(self, value: int):
        self.spinbox.setDecimals(value)
        self.setSingleStep(self.spinbox.singleStep())

    def decimals(self) -> int:
        return self.spinbox.decimals()

    def setSingleStep(self, value):
        self.spinbox.setSingleStep(value)
        m = int(10 ** self.decimals() * value)
        self.slider.setSingleStep(m)
        self.slider.setPageStep(m * 10)
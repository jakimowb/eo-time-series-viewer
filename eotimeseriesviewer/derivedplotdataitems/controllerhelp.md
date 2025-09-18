Define the data to generateadditional plot curves.

# Input

| Variables | Description                                                                                                                       |
|-----------|-----------------------------------------------------------------------------------------------------------------------------------|
| `x`       | array with POSIX [time stamps](https://docs.python.org/3/library/datetime.html#datetime.datetime.timestamp) (``np.array[float]``) |
| `y`       | array with temporal profile values (``np.array[float]``)                                                                          |
| `pg`      | PyQtGraph                                                                                                                         |            
| `np`      | Numpy, as in ``import numpy as np``                                                                                               |
| `_pdi_`   | `pg.PlotDataItem` from which all data is taken                                                                                    |

# Output
The output is defined in a variable ``results``
and contains data to create PlotDataItems.  It can be of the following types:

a) dictionary:

````python
results = {
    'x': x - 0.5,
    'y': y * 0.75,
    'pen': 'red',
    'name': 'My derived profile',
}
````

b) a PyQtGraph PlotDataItem 

````python
from eotimeseriesviewer.qgispluginsupport.qps.pyqtgraph.pyqtgraph import PlotDataItem
results = 
````   

c) A list of (a) or (b). This allows defining multiple plot segments

````python
results = [{'x':x, 'y':y * 0.75, 'name': 'profile1'},
           PlotDataItem(x=x, y=y*1.25, name = 'profile2')
           ]
````

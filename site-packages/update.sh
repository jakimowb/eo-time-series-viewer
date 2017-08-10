#!/bin/bash
#git remote add pyqtgraph https://github.com/pyqtgraph/pyqtgraph.git
#mkdir pyqtgraph
git fetch pyqtgraph
git read-tree --prefix=site-packages/pyqtgraph -u pyqtgraph/master
git commit -m "updated pyqtgraph"
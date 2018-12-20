from IPython import embed
import numpy as np

from PyQt5 import QtCore, QtWidgets

# import PyQtGraph for fast plotting
import pyqtgraph as pg
pg.setConfigOptions(antialias=True)


class metadataTreeWidget():

    def __init__(self, metadata):
        # setup layout
        self.widget = QtWidgets.QTreeWidget()
        self.widget.setLayout(QtWidgets.QVBoxLayout())
        self.widget.setColumnCount(2)
        self.widget.setHeaderLabels(['Label', 'Value'])

        self.addMetadata(metadata)


    def addMetadata(self, metadata):

        def buildTree(section):
            secTree = QtWidgets.QTreeWidgetItem([section.name, ''])
            for sec in section.sections:
                secTree.addChild(buildTree(sec))
            for prop in section.props:
                secTree.addChild(QtWidgets.QTreeWidgetItem([prop.name, str(section[prop.name])]))

            return secTree
        
        for section in metadata.sections:
            self.widget.addTopLevelItem(buildTree(section))

        # adjust column width
        self.widget.resizeColumnToContents(0)



class CustomTableWidget(QtWidgets.QTableWidget):

    def __init__(self):
        super().__init__()


    def buildFromDict(self, dictionary):
        pass

    
    def buildFromDf(self, Df):
        self.clear()
        
        self.setRowCount(Df.shape[0])
        self.setColumnCount(Df.shape[1])

        setHHeader = True
        for rIdx in range(Df.shape[0]):
            self.setVerticalHeaderItem(rIdx, QtWidgets.QTableWidgetItem(str(Df.index[rIdx])))
            for cIdx in range(Df.shape[1]):
                if setHHeader:
                    self.setHorizontalHeaderItem(cIdx, QtWidgets.QTableWidgetItem(str(Df.columns[cIdx])))
                
                # set value text for output 
                val = Df.iloc[rIdx, cIdx]
                if isinstance(val, (list, np.ndarray)):
                    val = list(val)
                    itemVal = 'Array(%i): ' % (len(val))
                    if len(val) > 50:
                        itemVal += str(val[:10]+['......']+val[-10:])
                    else:
                        val = str(val)
                else:
                    itemVal = '%s: %s' % (val.__class__.__name__, str(val))

                # set item
                self.setItem(rIdx, cIdx, QtWidgets.QTableWidgetItem(itemVal))
            setHHEader = False
            

################################################################
## FIGURE WIDGET IMPLEMENTATIONS
        
class FigureWidget(pg.PlotWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def plotMarkers(self, x, y, **kwargs):
        return self.plot(x, y, pen=None, symbol='o', symbolSize=6, **kwargs)
        
    
class HistogramWidget(FigureWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # initialize default histogram
        self.plotDataItem = self.plot(
            [0, 1],
            [1],
            stepMode=True,
            fillLevel=0,
            brush=(0,0,255,150)
        )

        self.useYLog = False

    def useYLogScale(self, use):

        if isinstance(use, bool):
            self.useYLog = use
        else:
            return
        
        self.getPlotItem().setLogMode(y=True)
            
        
    def plotHistogram(self, data, bins):

        if len(data) == 0:
            self.plotDataItem.setData([0, 1], [int(self.useYLog)])
            return

        # if float: calculate approx. number of bins
        if isinstance(bins, float):
            bins = int(np.ceil((np.max(data)-np.min(data))/bins))

        # calc histogram
        counts, bins = np.histogram(data, bins)

        # prevent divide-by-zero warning
        if self.useYLog:
            counts[counts == 0] = 1

        # plot
        self.plotDataItem.setData(bins, counts)


class PolarPlot(FigureWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # setup grid plot data items 
        self.circGridItems = list()
        self.circNum = 5
        for i in range(self.circNum):
            circle = pg.QtGui.QGraphicsEllipseItem(0, 0, 2, 2)
            circle.setPen(pg.mkPen(0.2))
            self.plotItem.addItem(circle)
            self.circGridItems.append(circle)

        # setup plot data item
        self.plotDataItem = self.plot([], [])
        self.setAspectLocked()
        

    def plotFromCartesian(self, theta, radius):
        
        # convert to polar coordinates
        x = radius * np.cos(theta)
        x = np.append(x, x[0])
        y = radius * np.sin(theta)
        y = np.append(y, y[0])

        self.plotFromPolar(x, y)

            
    def plotFromPolar(self, x, y, maxScale=1.2):

        if len(x) == 0 or len(y) == 0:
            return

        maxRadius = np.nanmax([x, y])*maxScale
        maxRadius = 1

        self.redrawGrid(maxRadius)

        self.plotDataItem.setData(x, y)

        
    def redrawGrid(self, maxRadius):
        maxRange = [-maxRadius, maxRadius]
        
        # add scale and set range
        gridRadia = np.arange(0, maxRadius, maxRadius/(self.circNum+1))
        for circle, r in zip(self.circGridItems, gridRadia):
            circle.setRect(r, -r, -2*r, 2*r)
            
        self.setXRange(*maxRange, padding=0)
        self.setYRange(*maxRange, padding=0)
            

    def plotPhaseLock(self, periods, events):
        phases = np.empty(periods.shape[1])
        phases[:] = np.nan
        for i, period in enumerate(periods.T):
            evInPeriod = events[(events > period[0]) & (events < period[1])]
            
            if evInPeriod.shape[0] < 1:
                continue
            
            phases[i] = (evInPeriod[0] - period[0]) / np.diff(period) 

        phases = phases[np.logical_not(np.isnan(phases))]

        counts, bins = np.histogram(phases, 10)

        if np.sum(counts) == 0:
            return
        
        centers = bins[:-1] + bins[1] - bins[0]
        self.plotFromCartesian(centers*2*np.pi, counts/np.sum(counts))
        

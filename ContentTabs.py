from Base import *
from CustomWidgets import *
import nixlacs
import numpy as np
import os
import pandas as pd
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtMultimedia import *
import pyqtgraph as pg
from scipy import interpolate
import scipy.signal as spSig
from scipy.stats import norm as normDistr
import time
from thunderfish import peakdetection
import utils

from IPython import embed

################################################################
# CONTENT WINDOW

class ContentTab(QtCore.QObject):

    def __init__(self, datasetId=None, rePro=None):
        super().__init__()
        
        self.datasetId = datasetId
        self.rePro = rePro

        self.curTime = None
        self.defaultSigProcSetting = None
        
        # set up content wrapper layout
        self.contentWidget = QtWidgets.QWidget()
        self.contentLayout = QtWidgets.QVBoxLayout()
        self.contentWidget.setLayout(self.contentLayout)
        
        self.setupNavBar()

        # setup tab widget
        self.tabWidget = QtWidgets.QTabWidget()
        self.contentLayout.addWidget(self.tabWidget)
        # content tab
        self.contentTab = QtWidgets.QWidget()
        self.contentTabLayout = QtWidgets.QVBoxLayout()
        self.contentTab.setLayout(self.contentTabLayout)
        self.tabWidget.addTab(self.contentTab, 'Data')
        if self.rePro is not None: 
            # block metadata tab
            self.blockMetadataTab = utils.metadataTreeWidget(self.rePro.relacsFile.b().metadata)
            self.tabWidget.addTab(self.blockMetadataTab.widget, 'Block metadata')
            # tag metadata tab
            self.tagMetadataTab = utils.metadataTreeWidget(self.rePro.getTagData().metadata)
            self.tabWidget.addTab(self.tagMetadataTab.widget, 'Tag metadata')


    def setupNavBar(self):

        if self.rePro is None:
            return

        # set up content navigation bar
        self.naviBarWidget = QtWidgets.QFrame()
        self.naviBarWidget.setFrameStyle(QtWidgets.QFrame.StyledPanel)
        self.naviBarLayout = QtWidgets.QHBoxLayout()
        self.naviBarWidget.setLayout(self.naviBarLayout)
        self.contentLayout.addWidget(self.naviBarWidget)
        
        # add recording category combo box
        self.naviBarLayout.addWidget(QtWidgets.QLabel('|| Rec. category: '))
        self.recCategories = Config.recordingCategories
        self.comboRecCategories = QtWidgets.QComboBox()
        self.comboRecCategories.addItem('None')
        for category in self.recCategories:
            self.comboRecCategories.addItem(category)
        self.naviBarLayout.addWidget(self.comboRecCategories)

        if 'recordingCategory' in self.rePro.data().columns:
            recCats = self.rePro.data().recordingCategory.unique()
            if recCats.shape[0] > 0:
                self.comboRecCategories.setCurrentText(recCats[0])
                
        # add cell type combo box
        self.naviBarLayout.addWidget(QtWidgets.QLabel('Cell type: '))
        self.cellTypes = Config.cellTypes
        self.comboCellTypes = QtWidgets.QComboBox()
        self.comboCellTypes.addItem('None')
        for cellType in self.cellTypes:
            self.comboCellTypes.addItem(cellType)
        self.naviBarLayout.addWidget(self.comboCellTypes)

        if 'cellType' in self.rePro.data().columns:
            cellTypes = self.rePro.data().cellType.unique()
            if cellTypes.shape[0] > 0:
                self.comboCellTypes.setCurrentText(cellTypes[0])

        # receptive field guess
        self.naviBarLayout.addWidget(QtWidgets.QLabel('RF position: '))
        self.inputRfPosition = QtWidgets.QLineEdit()
        self.naviBarLayout.addWidget(self.inputRfPosition)
        if 'rfPosition' in self.rePro.data().columns:
            rfPositions = self.rePro.data().rfPosition.unique()
            if rfPositions.shape[0] > 0:
                self.inputRfPosition.setText(str(rfPositions[0]))
        
        # spacer
        self.naviBarLayout.addStretch(stretch=1)

        # add save content button
        self.naviBarSaveButton = QtWidgets.QPushButton('Save to file')
        self.naviBarSaveButton.setMaximumWidth(100)
        self.naviBarLayout.addWidget(self.naviBarSaveButton)
        
        # connect standard signals
        self.naviBarSaveButton.clicked.connect(self.saveContentData)

        
    def addContentInfo(self, series):
        contentInfo = self.getContentInfo()
        for key in contentInfo:
            series[key] = contentInfo[key]

        return series


    def getContentInfo(self):
        rfInput = self.inputRfPosition.text()
        if rfInput == '':
            rfInput = 0
            
        return {
            'recordingCategory': self.comboRecCategories.currentText(),
            'cellType': self.comboCellTypes.currentText(),
            'rfPosition': float(rfInput)
        }


    def saveMeasurementData(self):
        series = self.signalProcessor.getProcessedData()
        if series is not None:
            self.rePro.setData(series)

            
    def useCurrentSettingsAsDefault(self):
        self.signalProcessor.useCurrentSettingsAsDefault()
        
        
    def startTimer(self):
        self.curTime = time.time()

        
    def stopTimer(self):
        if self.curTime is not None:
            print('(Time: %.2f s)' % (time.time() - self.curTime))
        self.curTime = None


    def plotSTA(self, plotDataItem, spikes, signal, Fs, staTime, scalePlotTo=None):

        staRange = int(round(staTime*Fs))
        
        staMat = np.zeros((staRange, spikes.shape[0]))
        for i, s in enumerate(spikes):
            tIdx = int(np.round(s*Fs))
            if tIdx <= staRange or tIdx == signal.shape[0]:
                continue

            staMat[:,i] = signal[tIdx-staRange+1:tIdx+1]

        STA = np.mean(staMat, axis=1)
        
        scale = 1
        if scalePlotTo is not None:
            scale = scalePlotTo/(np.max(STA) - np.min(STA))
            
        plotDataItem.setData(
            staTime-np.arange(0, staRange)[::-1]/Fs*1000,
            (STA-np.mean(STA))*scale
        )

        return STA


    def saveBatchData(self):
        '''
        function iterates over all rows in Df self.rePro.data()
        and processes each row that has not previously been processed
        '''
        
        self.startTimer()
        
        # save data for last position
        self.saveMeasurementData()

        print('Starting save to file for (%s // %s)' % (self.rePro.relacsFile.filepath, self.rePro.id()))
        
        print('Processing all unmodified rows...')
        signalProcessorNoUi = SignalProcessor(
            self.rePro, 
            ui=False
        )
        # update all rows that have been modified manually
        for idx, series in self.rePro.data().iterrows():
            
            # do an automatic analysis for all rows that have not been manually modified
            if series.additionalData != True:
                signalProcessorNoUi.setSignals(series)
                series = signalProcessorNoUi.getProcessedData()
                
            self.rePro.setData(self.addContentInfo(series.copy()))

        # write to file
        self.rePro.writeToSaveFile()

        print('Dataset saved (%s // %s)' % (self.rePro.relacsFile.filepath, self.rePro.id()))
        
        self.stopTimer()

    
        
    def saveContentData(self):
        print('WARNING: Save method not connected')



################################################################
# BASELINE

class BaselineActivity(ContentTab):

    def __init__(self, *args):
        super().__init__(*args)

        # setup layout
        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout()
        self.widget.setLayout(self.layout)
        self.contentTabLayout.addWidget(self.widget)

        # load signals for this rePro
        self.rePro.loadSignals()

        # add signal Processor (provide it with the pd.Series data for the current rePro)
        self.signalProcessor = SignalProcessor(
            self.rePro, 
            self.rePro.data().loc[self.rePro.data().index[0]].copy(),
            ui=True
        )
        self.layout.addWidget(self.signalProcessor.widget)

        # set up basic analysis plots
        self.basicAnalysis = QtWidgets.QFrame()
        self.basicAnalysis.setFixedHeight(250)
        self.basicAnalysisLayout = QtWidgets.QGridLayout()
        self.basicAnalysis.setLayout(self.basicAnalysisLayout)
        self.layout.addWidget(self.basicAnalysis)

        # add histogram
        self.histogram = utils.HistogramWidget(labels={'left': 'Counts', 'bottom': 'ISIs [ms]'})
        self.basicAnalysisLayout.addWidget(self.histogram, 0, 0)

        # add phase lock plot
        self.polarPlot = utils.PolarPlot()
        self.basicAnalysisLayout.addWidget(self.polarPlot, 0, 1)
        
        self.signalProcessor.sigRunCompleteConnect(self.plotAnalysisData)
        self.plotAnalysisData()


    def plotAnalysisData(self):

        pDataEod = self.signalProcessor.signals['GlobalEOD'].tool.getProcessedData()
        pDataNeuron = self.signalProcessor.signals['Neuron'].tool.getProcessedData()

        spikeTimes = pDataNeuron['PeakTimes']
        eodTimes = pDataEod['PeakTimes']

        eodPeriods = np.array([eodTimes[:-1], eodTimes[1:]])
        mEodPeriod = np.mean(np.diff(eodPeriods, axis=0))

        self.histogram.plotHistogram(data=np.diff(spikeTimes)*1000, bins=0.1)
            
        # plot phase lock
        self.polarPlot.plotPhaseLock(eodPeriods, spikeTimes)



    def saveContentData(self):
        '''
        re-implementation of parent method
        saves all content data to file
        '''

        series = self.addContentInfo(self.signalProcessor.getProcessedData())
        self.rePro.setData(series)
        self.rePro.writeToSaveFile()

        print('Dataset saved (%s // %s)' % (self.rePro.relacsFile.filepath, self.rePro.id()))


################################################################
# RECEPTIVE FIELD

class ReceptiveField(ContentTab):

    
    def __init__(self, *args):
        super().__init__(*args)
        
        # setup layout
        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)
        self.contentTabLayout.addWidget(self.widget)

        # load signals for this rePro
        self.rePro.loadSignals()

        # load important features
        self.rePro.loadMtFeatureData('x_pos')
        self.rePro.loadMtFeatureData('y_pos')

        if self.rePro.data().shape[0] == 0:
            print('ReceptiveField multi_tags empty. Return.')
            return
        
        # group by spatial position relative to fish axis
        self.posGroups = self.rePro.data().groupby(['x_pos', 'y_pos'])

        # get position data
        positions = list(zip(*self.posGroups.groups.keys()))
        self.xPositions = np.asarray(list(positions[0]))
        self.yPositions = np.asarray(list(positions[1]))

        # set measurement list
        self.measurementListWidget = QtWidgets.QListWidget()
        self.measurementListWidget.itemClicked.connect(self.displayMeasurement)
        self.layout.addWidget(self.measurementListWidget, 3, 0)
        self.layout.setColumnStretch(0, 1)
        
        # setup plot for measurement position overview and selection
        self.posOverview = utils.FigureWidget(labels={'left': 'DV-axis [mm]', 'bottom': 'RC-axis [mm]'})
        self.posOverview.plotMarkers(self.xPositions, self.yPositions)
        self.posOverview.setFixedHeight(100)
        self.layout.addWidget(self.posOverview, 1, 0, 1, 2)

        self.posOverview.plotItem.scene().sigMouseClicked.connect(self.mouseClicked)
        self.posOverview.plotItem.scene().sigMouseMoved.connect(self.mouseMoved)

        self.posOverview.cursorVLine = pg.InfiniteLine(angle=90, movable=False)
        self.posOverview.cursorHLine = pg.InfiniteLine(angle=0, movable=False)
        self.posOverview.plotItem.addItem(self.posOverview.cursorVLine, ignoreBounds=True)
        self.posOverview.plotItem.addItem(self.posOverview.cursorHLine, ignoreBounds=True)
        self.posOverview.markerVLine = pg.InfiniteLine(angle=90, movable=False, pen=(255,0,0))
        self.posOverview.markerHLine = pg.InfiniteLine(angle=0, movable=False, pen=(255,0,0))
        self.posOverview.plotItem.addItem(self.posOverview.markerVLine, ignoreBounds=True)
        self.posOverview.plotItem.addItem(self.posOverview.markerHLine, ignoreBounds=True)

        self.posActivity = utils.FigureWidget(labels={'left': 'Modulation [sd]', 'bottom': 'RC-axis [mm]'})
        self.posActivity.setFixedHeight(200)
        self.layout.addWidget(self.posActivity, 2, 0, 1, 2)
        self.posActivityPlotData = self.posActivity.plotMarkers([], [])
        
        # setup signal processor
        self.signalProcessor = SignalProcessor(
            self.rePro, 
            ui=True
        )
        self.layout.addWidget(self.signalProcessor.widget, 3, 1)
        self.layout.setColumnStretch(1, 99)
        
        # select first position and display
        self.xPos = self.xPositions[0]
        self.yPos = self.yPositions[0]
        self.displayRfPosition()

        embed()

    def mouseMoved(self, pos):
        '''
        from PyQtGraph example 'Crosshair / Mouse interaction'
        '''
        vb = self.posOverview.plotItem.vb
        if self.posOverview.plotItem.sceneBoundingRect().contains(pos):
            mousePoint = vb.mapSceneToView(pos)
            self.posOverview.cursorVLine.setPos(mousePoint.x())
            self.posOverview.cursorHLine.setPos(mousePoint.y())


    def mouseClicked(self, evt):
        '''
        function is called when user clicks on position overview plot
        it calculates the distance to all measured spatial positions
        and calls the display function after setting the nearest x-y-position
        '''

        # find closest measurement position
        viewPositions = self.posOverview.plotItem.vb.mapSceneToView(evt.scenePos())
        xPos = viewPositions.x()
        yPos = viewPositions.y()

        distances = np.sqrt(np.square(self.xPositions-xPos)+np.square(self.yPositions-yPos))
        minDistIdx = np.argmin(distances)

        self.xPos = self.xPositions[minDistIdx]
        self.yPos = self.yPositions[minDistIdx]

        # display data for position
        self.displayRfPosition()


    def getPosTuple(self):
       return (self.xPos, self.yPos) 


    def displayRfPosition(self):
        '''
        function handles the display of the signal processor widgets
        '''
        
        # print position
        print('Pos%s' % str(self.getPosTuple()))

        # mark current position in measurement overview
        self.posOverview.markerVLine.setPos(self.xPos)
        self.posOverview.markerHLine.setPos(self.yPos)

        # set list widget with measurement indices
        self.measurementListWidget.clear()
        for idx, series in self.posGroups.get_group(self.getPosTuple()).iterrows():
            self.measurementListWidget.addItem(QtWidgets.QListWidgetItem(str(idx)))

        # display first measurement
        self.measurementListWidget.setCurrentRow(0)
        self.displayMeasurement(self.measurementListWidget.item(0))


    def plotActivity(self):

        Df = self.rePro.data()

        if 'NeuronPeakTimes' not in Df.columns:
            return
        
        mask = Df['NeuronPeakTimes'].notna()
        tagMetadata = nixlacs.getMetadataDict(self.rePro.getTagData().metadata)
        for key in tagMetadata.keys():
            if key.startswith('dataset'):
                keyDataset = key
                break        
        keyParts = keyDataset.split('-')
        keySettings = '-'.join([keyParts[0], 'settings', *keyParts[1:]])
        deltaF = tagMetadata[keyDataset][keySettings]['deltaf']
        stimDur = tagMetadata[keyDataset][keySettings]['duration']
        beatLen = 1/deltaF
        beatNum = stimDur/beatLen

        # calculate beat PSTH
        for posIdx, series in Df.loc[mask, ['x_pos', 'NeuronPeakTimes']].iterrows():
            x = series['x_pos']
            times = 1*series['NeuronPeakTimes'] # COPY ARRAY OR GET PWNED BY PASS-BY-REFERENCE!!!
            times %= beatLen
            
            counts, _ = np.histogram(times, 10)

            series['beatSpikeCounts'] = counts
            series['beatPsthSd'] = np.std(counts)
            self.rePro.setData(series)

        # plot data
        Df = self.rePro.data()
        self.posActivityPlotData.setData(Df.loc[mask,'x_pos'].values, Df.loc[mask,'beatPsthSd'].values)
        
    def displayMeasurement(self, item):
        self.saveMeasurementData()
        self.plotActivity()
        self.signalProcessor.setSignals(self.rePro.data(int(item.text())))

        
    def saveContentData(self):
        '''
        re-implementation of parent method
        saves all content data to file
        '''

        self.saveBatchData()

################################################################
# FI CURVE

class FICurve(ContentTab):
        
    def __init__(self, *args):
        super().__init__(*args)

        # setup layout
        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)
        self.contentTabLayout.addWidget(self.widget)

        # load signals for this rePro
        self.rePro.loadSignals()

        # load important features
        self.rePro.loadMtFeatureData('Contrast')
        self.rePro.loadMtFeatureData('PreContrast')
        self.rePro.loadMtFeatureData('Intensity')
        self.rePro.loadMtFeatureData('PreIntensity')

        # setup list and get groups by intensity 
        self.intGroups = dict()
        self.layout.addWidget(QtWidgets.QLabel('Mean contrast (std) / Stim intensity'), 0, 0)
        self.listIntensities = QtWidgets.QListWidget()
        for intensity, groupData in self.rePro.data().groupby('Intensity'):
            mContrast = groupData['Contrast'].mean()
            stdContrast = groupData['Contrast'].std()
            key = '%.1f (%.1f) / %.2f' % (mContrast, stdContrast, intensity)
            self.intGroups[key] = groupData
            self.listIntensities.addItem(key)
        self.listIntensities.setMaximumWidth(150)
        self.layout.addWidget(self.listIntensities, 1, 0, 2, 1)
        self.layout.setColumnStretch(0, 1)
        self.listIntensities.itemClicked.connect(self.displayIntensity)

        # set measurement list
        self.layout.addWidget(QtWidgets.QLabel('Measurements'), 0, 1)
        self.measurementListWidget = QtWidgets.QListWidget()
        self.measurementListWidget.itemClicked.connect(self.displayMeasurement)
        self.measurementListWidget.setMaximumWidth(150)
        self.layout.addWidget(self.measurementListWidget, 1, 1, 2, 1)
        self.layout.setColumnStretch(1, 1)

        # setup signal processor
        self.signalProcessor = SignalProcessor(
            self.rePro, 
            ui=True
        )
        self.layout.addWidget(self.signalProcessor.widget, 1, 2, 1, 3)
        self.layout.setColumnStretch(2, 99)
        
        # plot phase lock during baseline activity
        self.phaseLockPlotPre = utils.PolarPlot()
        self.layout.addWidget(self.phaseLockPlotPre, 2, 3)
        
        # plot phase lock during stimulation
        self.phaseLockPlotPost = utils.PolarPlot()
        self.layout.addWidget(self.phaseLockPlotPost, 2, 4)

        # select first intensity
        self.listIntensities.setCurrentRow(0)
        self.displayIntensity(self.listIntensities.currentItem())


    def getIntKey(self):
        return self._intKey

        
    def displayIntensity(self, item):

        # print intensity
        self._intKey = item.text()
        print('Intensity %s' % self.getIntKey())
        
        self.measurementListWidget.clear()
        for idx, series in self.intGroups[self.getIntKey()].iterrows():
            self.measurementListWidget.addItem(QtWidgets.QListWidgetItem(str(idx)))

        self.measurementListWidget.setCurrentRow(0)
        self.displayMeasurement(self.measurementListWidget.item(0))

        
    def displayMeasurement(self, item):
        self.saveMeasurementData()
        self.signalProcessor.setSignals(self.rePro.data(int(item.text())))
        self.signalProcessor.sigRunCompleteConnect(self.plotAnalysisData)

        self.plotAnalysisData()
        

    def plotAnalysisData(self):
        
        pDataEod = self.signalProcessor.signals['GlobalEOD'].tool.getProcessedData()
        pDataNeuron = self.signalProcessor.signals['Neuron'].tool.getProcessedData()

        spikeTimes = pDataNeuron['PeakTimes']
        eodTimes = pDataEod['PeakTimes']

        eodPeriods = np.array([eodTimes[:-1], eodTimes[1:]])
        mEodPeriod = np.mean(np.diff(eodPeriods, axis=0))

        delay = self.rePro.data(int(self.measurementListWidget.currentItem().text()))['delay']

        self.phaseLockPlotPre.plotPhaseLock(eodPeriods[:,eodTimes[:-1] < delay], spikeTimes)

        self.phaseLockPlotPost.plotPhaseLock(eodPeriods[:,eodTimes[:-1] >= delay], spikeTimes)

        
    def saveContentData(self):
        '''
        re-implementation of parent method
        saves all content data to file
        '''

        self.saveBatchData()


################################################################
# FILE STIMULUS

class FileStimulus(ContentTab):
        
    def __init__(self, *args):
        super().__init__(*args)

        # setup layout
        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)
        self.contentTabLayout.addWidget(self.widget)

        # load signals for this rePro
        self.rePro.loadSignals()
        self.rePro.loadStimulusData(baseDir=['..'])

        # set measurement list
        self.layout.addWidget(QtWidgets.QLabel('Measurements'), 0, 0)
        self.measurementListWidget = QtWidgets.QListWidget()
        self.measurementListWidget.itemClicked.connect(self.displayMeasurement)
        self.measurementListWidget.setMaximumWidth(150)
        for posIdx, series in self.rePro.data().iterrows():
            self.measurementListWidget.addItem(QtWidgets.QListWidgetItem(str(posIdx)))
        self.layout.addWidget(self.measurementListWidget, 1, 0)
        self.layout.setColumnStretch(1, 1)
        
        # add signal Processor (provide it with the pd.Series data for the current rePro)
        self.signalProcessor = SignalProcessor(
            self.rePro, 
            ui=True
        )
        self.layout.addWidget(self.signalProcessor.widget, 1, 1)

        ## analysis plots
        # add STA figure
        self.figWidget = QtWidgets.QFrame()
        self.figWidget.setLayout(QtWidgets.QHBoxLayout())
        self.staFigure = utils.FigureWidget(labels={'bottom': 'Time [ms]', 'left': 'Amplitude [norm.]'})
        self.staFigure.addLegend()
        self.staNoiseDataItem = self.staFigure.plot([], [], name='Noise AM', pen=(255, 120, 0))
        self.staREodDataItem = self.staFigure.plot([], [], name='RefEOD Envelope', pen=(0, 255, 120))
        self.staLEodDataItem = self.staFigure.plot([], [], name='LocalEOD Envelope', pen=(0, 0, 255))
        self.figWidget.layout().addWidget(self.staFigure)
        # STA settings
        self.staTime = 0.03 # s

        # add coherence figure
        self.cohFigure = utils.FigureWidget(labels={'bottom': 'Freq [Hz]', 'left': 'AM/Response Coherence'})
        self.cohDataItemStimAm = self.cohFigure.plot([], [], name='Coh NoiseAM', pen=(255, 120, 0))
        self.cohDataItemRef = self.cohFigure.plot([], [], name='Coh RefEod AM', pen=(0, 255, 120))
        self.cohDataItemLocal = self.cohFigure.plot([], [], name='Coh LocalEod AM',  pen=(0, 0, 255))
        self.cohFigure.getPlotItem().setXRange(0, 500)
        self.cohFigure.getPlotItem().setYRange(0, 1)
        self.figWidget.layout().addWidget(self.cohFigure)
        
        self.layout.addWidget(self.figWidget, 2, 1)
        
        # select first measurement
        self.measurementListWidget.setCurrentRow(0)
        self.displayMeasurement(self.measurementListWidget.currentItem())
        

    def displayMeasurement(self, item):
        self.saveMeasurementData()
        self.signalProcessor.setSignals(self.rePro.data(int(item.text())))
        self.signalProcessor.sigRunCompleteConnect(self.plotAnalysisData)

        self.plotAnalysisData()


    def plotAnalysisData(self):
        
        pDataNeuron = self.signalProcessor.signals['Neuron'].tool.getProcessedData()
        series = self.signalProcessor.series
        spikes = pDataNeuron['PeakTimes']
        envFs = 1000
        
        # plot STA of noise stimulus
        stimAmInterFun = interpolate.interp1d(series['stimTimes'], series['stimAmps'], fill_value='extrapolate')
        stimAmEnv = stimAmInterFun(np.arange(0, spikes[-1], 1/envFs))
        stimAmEnv -= np.mean(stimAmEnv)

        stimSTA = self.plotSTA(
            plotDataItem=self.staNoiseDataItem,
            spikes=spikes,
            signal=stimAmEnv,
            Fs=envFs,
            staTime=self.staTime,
            scalePlotTo=1
        )

        # plot STA of reference EOD
        pDataRefEod = self.signalProcessor.signals['RefEOD'].tool.getProcessedData()
        rEodPeakTimes = pDataRefEod['PeakTimes']
        rEodPeaks = pDataRefEod['PeakAmps']
        rEodInterFun = interpolate.interp1d(rEodPeakTimes, rEodPeaks, fill_value='extrapolate')
        rEodEnv = rEodInterFun(np.arange(0, spikes[-1], 1/envFs))
        rEodEnv -= np.mean(rEodEnv)
        
        rEodSTA = self.plotSTA(
            plotDataItem=self.staREodDataItem,
            spikes=spikes,
            signal=rEodEnv,
            Fs=envFs,
            staTime=self.staTime,
            scalePlotTo=1
        )

        # plot STA of local EOD
        pDataLocalEod = self.signalProcessor.signals['LocalEOD'].tool.getProcessedData()
        lEodPeakTimes = pDataLocalEod['PeakTimes']
        if len(lEodPeakTimes) == 0:
            self.staLEodDataItem.setData([], [])
            return
        
        lEodPeaks = pDataLocalEod['PeakAmps']
        lEodInterFun = interpolate.interp1d(lEodPeakTimes, lEodPeaks, fill_value='extrapolate')
        lEodEnv = lEodInterFun(np.arange(0, spikes[-1], 1/envFs))
        lEodEnv -= np.mean(lEodEnv)
        
        lEodSTA = self.plotSTA(
            plotDataItem=self.staLEodDataItem,
            spikes=spikes,
            signal=lEodEnv,
            Fs=envFs,
            staTime=self.staTime,
            scalePlotTo=1
        )
        
        ## plot coherence
        params = dict(fs=envFs, nperseg=2**10, noverlap=2**9)
        stdKernelWidth = 0.002

        # reference
        t = np.arange(-5*stdKernelWidth, 5*stdKernelWidth, 1/envFs)
        kernel = normDistr.pdf(t, loc=0, scale=stdKernelWidth)
        spikeConv = np.zeros(rEodEnv.shape[0]+1)
        spikeConv[(spikes*envFs).astype(int)] = 1
        spikeConv = np.convolve(spikeConv, kernel, mode='same')
        spikeConv -= np.mean(spikeConv)

        # stimulus AM
        Pxx = spSig.csd(stimAmEnv, stimAmEnv, **params)[1]
        Pyy = spSig.csd(spikeConv, spikeConv, **params)[1]
        Pxy = spSig.csd(stimAmEnv, spikeConv, **params)
        freq = Pxy[0]
        coh = np.abs(Pxy[1])**2/(np.abs(Pxx)*np.abs(Pyy))

        self.cohDataItemStimAm.setData(freq[freq <= 500], coh[freq <= 500])


        # reference Eod
        Pxx = spSig.csd(rEodEnv, rEodEnv, **params)[1]
        Pyy = spSig.csd(spikeConv, spikeConv, **params)[1]
        Pxy = spSig.csd(rEodEnv, spikeConv, **params)
        freq = Pxy[0]
        coh = np.abs(Pxy[1])**2/(np.abs(Pxx)*np.abs(Pyy))

        self.cohDataItemRef.setData(freq[freq <= 500], coh[freq <= 500])

        
        # local Eod
        Pxx = spSig.csd(lEodEnv, lEodEnv, **params)[1]
        Pyy = spSig.csd(spikeConv, spikeConv, **params)[1]
        Pxy = spSig.csd(lEodEnv, spikeConv, **params)
        freq = Pxy[0]
        coh = np.abs(Pxy[1])**2/(np.abs(Pxx)*np.abs(Pyy))

        self.cohDataItemLocal.setData(freq[freq <= 500], coh[freq <= 500])

        

    def saveContentData(self):
        '''
        re-implementation of parent method
        saves all content data to file
        '''

        self.saveBatchData()
        

################################################################
# DATASET COMBINATION

class DatasetCombination(ContentTab):

    def __init__(self):
        super().__init__()

        self.setupUi()
        
        self.getLists()


    def setupUi(self):
        
        # setup layout
        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)
        self.contentTabLayout.addWidget(self.widget)

        # block property selection
        self.layout.addWidget(QtWidgets.QLabel('Block properties'), 0, 0)
        self.propertyList = QtWidgets.QListWidget()
        self.layout.addWidget(self.propertyList, 1, 0)

        # repro selection
        self.reProList = QtWidgets.QComboBox()
        self.reProList.currentTextChanged.connect(self.updateLists)
        self.layout.addWidget(self.reProList, 0, 1)

        # repro frame
        self.reProFrame = QtWidgets.QFrame()
        self.reProFrame.clayout = QtWidgets.QGridLayout()
        self.reProFrame.setLayout(self.reProFrame.clayout)
        self.layout.addWidget(self.reProFrame, 1, 1)
        
        # feature selection
        self.reProFrame.clayout.addWidget(QtWidgets.QLabel('Features'), 0, 0)
        self.featureList = QtWidgets.QListWidget()
        self.reProFrame.clayout.addWidget(self.featureList, 1, 0)
        # tag property selection
        self.reProFrame.clayout.addWidget(QtWidgets.QLabel('Tag properties'), 0, 1)
        self.tagPropertyList = QtWidgets.QListWidget()
        self.reProFrame.clayout.addWidget(self.tagPropertyList, 1, 1)
        # reference selection
        self.reProFrame.clayout.addWidget(QtWidgets.QLabel('References (!caution!)'), 0, 2)
        self.referenceList = QtWidgets.QListWidget()
        self.reProFrame.clayout.addWidget(self.referenceList, 1, 2)
        
        # button process all
        self.btnProcessAll = QtWidgets.QPushButton('Process all datasets and save summary DataFrames...')
        self.layout.addWidget(self.btnProcessAll)
        self.btnProcessAll.clicked.connect(self.processAll, 2, 0)

        # check boxes
        self.checkCalcCoherence = QtWidgets.QCheckBox('Calculate Local coherences')
        self.checkCalcCoherence.setCheckState(QtCore.Qt.CheckState(2))
        #self.reProFrame.clayout.addWidget(self.checkCalcCoherence, 3, 0,)
                            
                
        
    def getLists(self):

        datasetList = os.listdir(Config.getDataPath())

        self.dataLists = dict()
        self.nixFiles = dict()
        self.properties = dict()
        self.tagProperties = dict()
        self.features = dict()
        self.references = dict()

        for dataset in datasetList:
            
            datasetId = dataset[:-4]
            if not datasetId.startswith('20'):
                continue

            print('Loading datasets %s' % (datasetId))
            
            self.nixFiles[datasetId] = nixlacs.RelacsFile(
                filepath=Config.getDataPath(datasetId), 
                savepath=Config.getJsonPath()
            )


            # add block properties
            for propStr in self.getPropStrings(self.nixFiles[datasetId].b().metadata):
                propName = '_#_'.join(propStr.split('_#_')[1:])

                if propName not in self.properties.keys():
                    item = QtWidgets.QListWidgetItem(propName)
                    item.setCheckState(QtCore.Qt.CheckState(0))
                    self.properties[propName] = item
                    self.propertyList.addItem(item)
            
            for rePro in self.nixFiles[datasetId].rePros():
                if rePro.data().shape[0] == 0:
                    continue
            
                reProName = rePro.__class__.__name__
                if reProName not in self.dataLists.keys():

                    self.dataLists[reProName] = list()
                    self.tagProperties[reProName] = dict()
                    self.features[reProName] = dict()
                    self.references[reProName] = dict()
                    
                # add repro data
                self.dataLists[reProName].append(rePro.data())

                # add rePro (tag) properties
                for propStr in self.getPropStrings(rePro.getTagData().metadata):
                    propName = '_#_'.join(propStr.split('_#_')[2:])
                    propName = propName.replace('-%s-%s' % (datasetId, rePro.id().replace('_', '-')), '')

                    if propName not in self.tagProperties[reProName].keys():
                        item = QtWidgets.QListWidgetItem(propName)
                        item.setCheckState(QtCore.Qt.CheckState(0))
                        self.tagProperties[reProName][propName] = item
                        self.tagPropertyList.addItem(item)
                
                # add features
                if rePro.getMtData() is not None:
                    for feat in rePro.getMtData().features:
                        featName = feat.data.name 
                        if featName not in self.features[reProName].keys():
                            item = QtWidgets.QListWidgetItem(featName)
                            item.setCheckState(QtCore.Qt.CheckState(0))
                            item.setHidden(True)
                            self.featureList.addItem(item)
                            self.features[reProName][featName] = item

                # add references
                for ref in rePro.getTagData().references:
                    refName = ref.data.name
                    if refName not in self.references[reProName].keys():
                        item = QtWidgets.QListWidgetItem(refName)
                        item.setCheckState(QtCore.Qt.CheckState(0))
                        item.setHidden(True)
                        self.referenceList.addItem(item)
                        self.references[reProName][refName] = item

        self.constructReProList()
        

    def getPropStrings(self, section):
        properties = list()
        for prop in section.props:
            properties.append('%s_#_%s' % (section.name, prop.name))
        for sec in section.sections:
            for prop in self.getPropStrings(sec):
                properties.append('%s_#_%s' % (section.name, prop))

        return properties

    
    def getPropByString(self, metadata, string):

        def getNext(dictionary, keyList):
            if len(keyList) > 1:
                return getNext(dictionary[keyList[0]], keyList[1:])
            return dictionary[keyList[0]]

        return getNext(metadata, string.split('_#_'))

    
    def getTagPropByName(self, metadata, name):
        keyList = name.split('_#_')        

        def findProperty(metadata, keyList):

            # exit criterion
            if not isinstance(metadata, dict):
                return metadata

            # search for key
            for key in metadata.keys():
                if key.startswith(keyList[0]):
                    return findProperty(metadata[key], keyList[1:])

            # fallback if key was not found: try next level if there is only one
            if len(list(metadata.keys())) == 1:
                return findProperty(metadata[list(metadata.keys())[0]], keyList)

            return None

        return findProperty(metadata, keyList)
            
        
    
    def constructReProList(self):
        for reProName in self.dataLists.keys():
            self.reProList.addItem(reProName)
    

    def updateLists(self, reProName):
        self.constructFeatureList(reProName)
        self.constructReferenceList(reProName)
        self.constructTagPropertyList(reProName)
        
    def constructFeatureList(self, reProName):
        for name in self.features.keys():
            for featName in self.features[name].keys():
                self.features[name][featName].setHidden(True)
        
        for featName in self.features[reProName].keys():
            self.features[reProName][featName].setHidden(False)

            
    def constructReferenceList(self, reProName):
        for name in self.references.keys():
            for refName in self.references[name].keys():
                self.references[name][refName].setHidden(True)
        
        for refName in self.references[reProName].keys():
            self.references[reProName][refName].setHidden(False)

                
    def constructTagPropertyList(self, reProName):
        for name in self.tagProperties.keys():
            for propName in self.tagProperties[name].keys():
                self.tagProperties[name][propName].setHidden(True)
        
        for propName in self.tagProperties[reProName].keys():
            self.tagProperties[reProName][propName].setHidden(False)

            
    def processAll(self):

        self.dataLists = dict()
        for datasetId in self.nixFiles:
            for rePro in self.nixFiles[datasetId].rePros():
                reProName = rePro.__class__.__name__

                if rePro.data().shape[0] == 0:
                    continue


                if reProName not in self.dataLists.keys():
                    self.dataLists[reProName] = list()                
                
                for featName in self.features[reProName].keys():
                    if self.features[reProName][featName].checkState() == QtCore.Qt.CheckState(2):
                        rePro.loadMtFeatureData(featName)

                for refName in self.references[reProName].keys():
                    if self.references[reProName][refName].checkState() == QtCore.Qt.CheckState(2):
                        rePro.loadReferenceData(refName)

                Df = rePro.data()
                Df['datasetId'] = datasetId

                print('Loading properties for %s' % (datasetId))
                for propName in self.properties.keys():

                    if self.properties[propName].checkState() != QtCore.Qt.CheckState(2):
                        continue
                        
                    propVal = self.getPropByString(rePro.relacsFile.metadata(), propName)
                    
                    if propVal is None:
                        continue

                    # add property
                    if isinstance(propVal, list):
                        propVal = propVal[0]
                    if isinstance(propVal, str):
                        propVal = propVal.lower()

                    Df[propName] = propVal
                    print('%s > %s' % (propName, str(propVal)))
                    
                        
                print('Loading tagProperties for %s' % (datasetId)) 
                tagPropStrings = list()
                for s in self.getPropStrings(rePro.getTagData().metadata):
                    tagPropStrings.append('_#_'.join(s.split('_#_')[1:]))
                    
                for propName in self.tagProperties[reProName].keys():

                    if self.tagProperties[reProName][propName].checkState() != QtCore.Qt.CheckState(2):
                        continue

                    propKeys = propName.split('_#_')
                    propVal = None
                    for s in tagPropStrings:
                        for key in propKeys:
                            if key not in s:
                                s = ''
                        if len(s) > 0:
                            propVal = self.getPropByString(nixlacs.getMetadataDict(rePro.getTagData().metadata), s)
                    
                    if propVal is None:
                        continue
                    
                    # add property
                    if isinstance(propVal, list):
                        propVal = propVal[0]
                    if isinstance(propVal, str):
                        propVal = propVal.lower()

                    Df[propName] = propVal
                    print('%s > %s' % (propName, str(propVal)))

                Df = Df[Df.excludeTrial == 0]
                    
                # create new Df with appropriate indices
                newDf = pd.DataFrame()
                for name, series in Df.iterrows():

                    series.name = '%s_%i' % (series.datasetId, series.name)
                    newDf = newDf.append(series)

                # append new Df
                self.dataLists[reProName].append(newDf)


        # save to file
        print('Saving to RePro summary files...')
        for reProName in self.dataLists.keys():
            FileInteractions.writeDfToFile(
                pd.concat(self.dataLists[reProName], sort=False),
                'Summary_%s' % (reProName)
            )


################################################################
# EXPLORE JSON FILE

class ExploreJsonFile(ContentTab):

    def __init__(self):
        super().__init__()

        self.setupUi()

        
    def setupUi(self):

        # setup layout
        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)
        self.contentTabLayout.addWidget(self.widget)

        # open button
        self.openBtn = QtWidgets.QPushButton('Open JSON file...')
        self.openBtn.clicked.connect(self.openJsonFile)
        self.layout.addWidget(self.openBtn, 0, 0)

        # filename label
        self.filenameLbl = QtWidgets.QLabel('Filename')
        self.layout.addWidget(self.filenameLbl, 1, 0)
        
        # table widget
        self.tableWidget = utils.CustomTableWidget()
        self.layout.addWidget(self.tableWidget, 2, 0)

        
    def openJsonFile(self):
        filepath = QtWidgets.QFileDialog.getOpenFileName(
            self.widget,
            "Open JSON file",
            Config.getJsonPath(),
            ("JSON Files (*.json *.JSON)")
        )[0]

        relpath = os.path.relpath(
            filepath,
            Config.getJsonPath()
        ).replace('.json', '').replace('.JSON', '')

        Df = FileInteractions.loadDfFromFile(relpath, ftype='json')
        self.tableWidget.buildFromDf(Df)

        self.filenameLbl.setText(relpath)

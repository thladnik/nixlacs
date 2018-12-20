import json
import numpy as np
from PyQt5 import QtCore, QtWidgets
import pyqtgraph as pg
from scipy import signal as spSig
from thunderfish import peakdetection
import utils

        
from IPython import embed

################################################################
# SIGNAL PROCESSOR


class SignalProcessor():

    def __init__(self, rePro, series=None, ui=True):
        self.rePro = rePro
        self.ui = ui
        self.defaultSigProcSetting = None
        
        if self.ui:
            self.signalView = SignalView(self)
            self.widget = self.signalView.widget

        self.setSignals(series)

            
    def setSignals(self, series):
        self.series = series
        if self.series is None:
            return

        self.excludeTrial = 0 # by default: use trial
        
        # set signal data
        self.signals = dict()
        for alias, stype in zip(self.rePro.signalAliases, self.rePro.signalTypes):

            useFilter = True
            #useFilter = False
            if stype == 'neuronal':
                useFilter = True
            
            # set signal data
            self.signals[alias] = SignalData(
                alias,
                stype,
                self.series[alias],
                self.series['%sDim' % alias], 
                useFilter=useFilter
            )
                
            # check if previous configurations exist for signal processing
            if '%s_toolconfig' % alias in series.index:
                config = self.series['%s_toolconfig' % alias]
                if isinstance(config, dict):
                    self.signals[alias].setSignalConfig(config)
            elif stype == 'eod':
                self.signals[alias].setSignalConfig(
                    {self.signals[alias].tool.threshFactorN: 0.25}
                )
                    
            
            # run main analysis function of selected tool by default
            self.signals[alias].tool.run()

        # overwrite exclude flag if set
        if 'excludeTrial' in series.index and series['excludeTrial'] is not None:
            self.excludeTrial = series['excludeTrial']

        # provide view with signal data
        if self.ui:
            self.signalView.setSignals(self.signals)
            self.signalView.checkExcludeTrial.setCheckState(QtCore.Qt.CheckState(self.excludeTrial))

            
    def sigRunCompleteConnect(self, fun):
        for alias in self.rePro.signalAliases:
            self.signals[alias].tool.sigRunComplete.connect(fun)

            
    def useCurrentSettingsAsDefault(self):
        
        # get current config parameters
        defaultSeries = self.getProcessedData()
        configKeys = [key for key in defaultSeries.index if key.endswith('_toolconfig')]
        
        print('New default settings:\n%s' % str(defaultSeries[configKeys]))

        # add columns to Df if they dont exist yet
        for key in configKeys:
            if key not in self.rePro.data().columns:
                self.rePro._data.loc[:,key] = None

        # add configuration parameters to each row of Df
        for posIdx, series in self.rePro.data().iterrows():
            # set new config parameters and RESET series to force re-evaluation
            series[configKeys] = defaultSeries[configKeys]
            series['additionalData'] = False
            self.rePro.setData(series, additionalData=False)
            
        
    def getProcessedData(self):
        '''
        packs processed data into original series object and returns it
        '''

        if self.series is None:
            return None
        
        for alias, stype in zip(self.rePro.signalAliases, self.rePro.signalTypes):

            # set processed data
            processedData = self.signals[alias].tool.getProcessedData()
            for key in processedData:
                self.series['%s%s' % (alias, key)] = processedData[key]
            
            # set tool configuration
            self.series['%s_toolconfig' % alias] = self.signals[alias].tool.getConfigParams()

        self.series['excludeTrial'] = self.excludeTrial
            
        return self.series


################
# SIGNAL DATA

class SignalData():
    def __init__(self, signalAlias, signalType, signal, Fs, useFilter=False, signalConfig=None):
        self.signalAlias = signalAlias
        self.signalType = signalType
        
        # setup tool
        self.tool = SignalTool()

        # set trace data
        self.setSignalData(signal, Fs, useFilter=useFilter)
        
        self.setSignalConfig(signalConfig)
        

    def setSignalData(self, sig, Fs, useFilter=False):

        self.time = np.arange(0, sig.shape[0])/Fs
        self.signal = sig
        self.Fs = Fs

        if useFilter:
            if self.signalType == 'eod':
                self.filterSignal(Wn=[250])
            else:
                self.filterSignal()

        self.tool.setSignalData(self.signal, self.Fs)
            

    def filterSignal(self, btype='highpass', Wn=[50]):
        # pad signal
        padLen = int(np.round(0.05*len(self.signal)))        
        self.signal = np.concatenate((
            np.ones(padLen)*np.mean(self.signal[:padLen]),
            self.signal,
            np.ones(padLen)*np.mean(self.signal[-padLen:]),
        ))
        #filter
        b, a = spSig.butter(N=2, Wn=np.array(Wn)/(self.Fs/2), btype=btype)
        self.signal = spSig.filtfilt(b, a, self.signal)
        # remove padding
        self.signal = self.signal[padLen:-padLen]

        
    def setSignalConfig(self, config):
        self.signalConfig = config
        if self.signalConfig is not None:
            self.tool.setConfigParams(config)

            
################
# SIGNAL VIEW


class SignalView():
    def __init__(self, signalProcessor):
        self.signalProcessor = signalProcessor
        self.signals = None
        
        self.excludeTrial = 0

        # setup layout
        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)

        # set exclude check box
        self.checkExcludeTrial = QtWidgets.QCheckBox('Exclude trial')
        self.layout.addWidget(self.checkExcludeTrial, 0, 0)
        self.checkExcludeTrial.stateChanged.connect(self.updateExcludeTrial)
                        
        # set signal list
        self.signalListWidget = QtWidgets.QListWidget()
        self.signalListWidget.itemClicked.connect(self.signalSelected)
        self.layout.addWidget(self.signalListWidget, 1, 0)
        self.layout.setColumnStretch(0, 1)

        # default setting button
        self.setAsDefaultBtn = QtWidgets.QPushButton('Use settings as default')
        self.setAsDefaultBtn.setMaximumWidth(200)
        self.setAsDefaultBtn.clicked.connect(self.signalProcessor.useCurrentSettingsAsDefault)
        self.layout.addWidget(self.setAsDefaultBtn, 0, 1)
        
        # set tool interface
        self.toolWidget = QtWidgets.QWidget() # tool widget
        self.toolWidgetLayout = QtWidgets.QGridLayout()
        self.toolWidget.setLayout(self.toolWidgetLayout)
        self.layout.addWidget(self.toolWidget, 1, 1)
        self.layout.setColumnStretch(1, 1)
        
        # create signal figure widget and add to layout
        self.figure = utils.FigureWidget(labels={'bottom': 'Time [s]', 'left': 'Amplitude [mV]'})
        self.signalPlotDataItem = self.figure.plot([],[])
        self.peakPlotDataItem = self.figure.plotMarkers([],[])
        self.layout.addWidget(self.figure, 0, 2, 2, 1)
        self.layout.setColumnStretch(2, 90)

        # create psd figure widget and add to layout
        self.figPSD = utils.FigureWidget(labels={'bottom': 'Freq [Hz]', 'left': '<font>ASD [mV/&radic;Hz]</font>'})
        self.figPSD.getPlotItem().setLogMode(y=True)
        self.powerPlotDataItem = self.figPSD.plot([],[])
        self.layout.addWidget(self.figPSD, 0, 3, 2, 1)
        self.layout.setColumnStretch(3, 40)
        
            
    def updateExcludeTrial(self, state):
        self.signalProcessor.excludeTrial = state

    
    def setSignals(self, signals):
        # hide all old tool UIs to correctly display plots
        if self.signals is not None:
            for alias in signals.keys():
                self.signals[alias].tool.ui.widget.setVisible(False)
        
        self.signals = signals

        # remove previous toolboxes
        for i in list(range(self.toolWidgetLayout.count()))[::-1]:
            self.toolWidgetLayout.itemAt(i).widget().deleteLater()
    
        # update signal list and set toolbox display options
        self.signalListWidget.clear()
        for alias in signals.keys():
            self.signals[alias].tool.setupUi(peakPlotDataItem=self.peakPlotDataItem)
            
            self.signalListWidget.addItem(QtWidgets.QListWidgetItem(alias))
            self.toolWidgetLayout.addWidget(self.signals[alias].tool.ui.widget)
            self.signals[alias].tool.ui.widget.setVisible(False)

        self.signalListWidget.setCurrentRow(0)
        self.signalSelected(self.signalListWidget.item(0))
        
            
    def signalSelected(self, item):
        # hide all toolboxes
        for key in self.signals.keys():
            signalData = self.signals[key]
            signalData.tool.ui.widget.setVisible(False)
            
        # show newly selected toolboxes
        signalData = self.signals[item.text()]
        signalData.tool.ui.widget.setVisible(True)
        
        signalData.tool.ui.plotPeaks()
        signalData.tool.ui.plotHistogram()
        
        # plot signal
        self.signalPlotDataItem.setData(signalData.time, signalData.signal)
        # plot PSD
        self.powerPlotDataItem.setData(
            signalData.tool.PSDfreq[signalData.tool.PSDfreq < 1000],
            signalData.tool.PSD[signalData.tool.PSDfreq < 1000]
        )
    


################################################################
# PEAK DETECTOR

################
# PROGRAM

class SignalTool(QtCore.QObject):

    sigRunComplete = QtCore.pyqtSignal()

    
    threshFactorN = 'threshFactor'
    minThreshN = 'minThresh'
    tauN = 'tau'
    skipPeaksN = 'skipPeaks'
    skipPeakOffsetN = 'skipPeakOffset'
    
    def __init__(self, signal=None, Fs=None, config=None):
        super().__init__()

        if signal is not None:
            self.setSignalData(signal, Fs)

        self.peakIndices = np.asarray([])
        self.peakTimes = np.asarray([])
        self.peakAmps = np.asarray([])

        self.ui = None

        self.name = 'signalTool'
        
        
    def setupUi(self, peakPlotDataItem=None):
        self.ui = SignalToolUi(self, peakPlotDataItem)


    def setConfigParams(self, config):
        if self.threshFactorN in config.keys():
            self.updateThresholdFactor(config[self.threshFactorN])
        if self.minThreshN in config.keys():
            self.updateMinThreshold(config[self.minThreshN])
        if self.tauN in config.keys():
            self.updateTau(config[self.tauN])
        if self.skipPeaksN in config.keys():
            self.updateSkipPeaks(config[self.skipPeaksN])
        if self.skipPeakOffsetN in config.keys():
            self.updateSkipPeakOffset(config[self.skipPeakOffsetN])
        

    def getConfigParams(self):
        return {
            self.threshFactorN: self.threshFactor,
            self.tauN: self.tau/self.Fs*1000,
            self.skipPeaksN: self.skipPeaks,
            self.skipPeakOffsetN: self.skipPeakOffset
        }


    def updateThresholdFactor(self, val):
        self.threshFactor = val
        if self.ui is not None:
            self.ui.updateThresholdFactor()
        
        # update threshold
        self.updateMinThreshold(peakdetection.minmax_threshold(self.signal, th_factor=self.threshFactor))
        
    
    def updateMinThreshold(self, val):
        self.minThresh = val
        if self.ui is not None:
            self.ui.updateMinThreshold()

            
    def updateTau(self, val):
        # internally self.tau has unit 'index'
        self.tau = val/1000*self.Fs
        if self.ui is not None:
            self.ui.updateTau()

            
    def updateSkipPeaks(self, val):
        self.skipPeaks = int(val) # check state
        if self.ui is not None:
            self.ui.updateSkipPeaks()            

            
    def updateSkipPeakOffset(self, val):
        # internally self.tau has unit 'index'
        self.skipPeakOffset = val
        if self.ui is not None:
            self.ui.updateSkipPeakOffset()

            
    def setSignalData(self, signal, Fs):
        self.time = np.arange(0, signal.shape[0])/Fs
        self.signal = signal
        self.Fs = Fs

        # set defaults
        self.updateThresholdFactor(0.4)
        self.updateTau(20)
        self.updateSkipPeaks(0)
        self.updateSkipPeakOffset(0)

        # calculate PSD
        params = dict(fs=self.Fs, nperseg=2**14, noverlap=2**13)
        freq, Pxx = spSig.csd(self.signal, self.signal, **params)
        self.PSDfreq = freq[freq <= 2000]
        self.PSD = Pxx[freq <= 2000]

    def run(self):

        self.peakIndices, _ = peakdetection.detect_dynamic_peaks(
            data=self.signal,
            threshold=self.minThresh,
            min_thresh=self.minThresh,
            tau=self.tau,
            check_peak_fun=peakdetection.accept_peak_size_threshold
        )
        
        # get time and amp arrays corresponding to peakIndices
        if self.skipPeaks == 2:
            self.peakIndices = self.peakIndices[self.skipPeakOffset::2]
            
        self.peakTimes = self.time[self.peakIndices.astype(int)]
        self.peakAmps = self.signal[self.peakIndices.astype(int)]
        
        if self.ui is not None:
            self.ui.plotPeaks()
            self.ui.plotHistogram()
            
        self.sigRunComplete.emit()


    def getProcessedData(self):
        return dict(
            PeakIdcs=self.peakIndices,
            PeakTimes=self.peakTimes,
            PeakAmps=self.peakAmps,
            PSDfreq=self.PSDfreq,
            PSD=self.PSD
        )



################
# UI

class SignalToolUi(QtCore.QObject):

    def __init__(self, tool, peakPlotDataItem):
        super().__init__()

        self.tool = tool
        self.peakPlotDataItem = peakPlotDataItem

        self.setupUi()

        self.updateThresholdFactor()
        self.updateMinThreshold()
        self.updateTau()
        self.updateSkipPeaks()
        self.updateSkipPeakOffset()
        
        self.btnDetectPeaks.setStyleSheet('color:#000000')
        

    def setupUi(self):
        self.widget = QtWidgets.QGroupBox(self.tool.name)
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)
        self.widget.setMaximumHeight(300)

        # histogram
        self.histogram = utils.HistogramWidget()
        self.histogram.useYLogScale(True)
        self.layout.addWidget(self.histogram, 0, 0, 1, 2)
                
        # input threshold factor
        self.layout.addWidget(QtWidgets.QLabel('<b>Thresh. factor [0,1]:<b> '), 1, 0)
        self.inputThreshFactor = QtWidgets.QDoubleSpinBox()
        self.inputThreshFactor.setSingleStep(0.01)
        self.inputThreshFactor.valueChanged.connect(self.tool.updateThresholdFactor)
        self.layout.addWidget(self.inputThreshFactor, 1, 1)
        
        # input mininum threshold
        self.layout.addWidget(QtWidgets.QLabel('Min. thresh. [mV]: '), 2, 0)
        self.inputMinThresh = QtWidgets.QDoubleSpinBox()
        self.inputMinThresh.setMinimum(0.05)
        self.inputMinThresh.setSingleStep(0.1)
        self.inputMinThresh.valueChanged.connect(self.tool.updateMinThreshold)
        self.inputMinThresh.setDisabled(True)
        self.layout.addWidget(self.inputMinThresh, 2, 1)

        # input time constant
        self.layout.addWidget(QtWidgets.QLabel('Tau [ms]: '), 3, 0)
        self.inputTau = QtWidgets.QDoubleSpinBox()
        self.inputTau.setMinimum(0.1)
        self.inputTau.setSingleStep(0.1)
        self.inputTau.valueChanged.connect(self.tool.updateTau)
        self.layout.addWidget(self.inputTau, 3, 1)

        # check skip peak
        self.checkSkipPeaks = QtWidgets.QCheckBox('Skip 2nd peaks / offset: ')
        self.checkSkipPeaks.stateChanged.connect(self.tool.updateSkipPeaks)
        self.layout.addWidget(self.checkSkipPeaks, 4, 0)
                
        # input mininum threshold
        self.inputSkipPeakOffset = QtWidgets.QSpinBox()
        self.inputSkipPeakOffset.setMinimum(0)
        self.inputSkipPeakOffset.setMaximum(1)
        self.inputSkipPeakOffset.setSingleStep(1)
        self.inputSkipPeakOffset.valueChanged.connect(self.tool.updateSkipPeakOffset)
        self.layout.addWidget(self.inputSkipPeakOffset, 4, 1)
        
        # detect peaks button
        self.btnDetectPeaks = QtWidgets.QPushButton('Detect peaks')
        self.btnDetectPeaks.clicked.connect(self.runTool)
        self.layout.addWidget(self.btnDetectPeaks, 5, 1)

        
    def updateThresholdFactor(self):
        self.btnDetectPeaks.setStyleSheet('color:#FF0000')
        self.inputThreshFactor.setValue(self.tool.threshFactor)

        
    def updateMinThreshold(self):
        self.btnDetectPeaks.setStyleSheet('color:#FF0000')
        self.inputMinThresh.setValue(self.tool.minThresh)

                
    def updateTau(self):
        self.btnDetectPeaks.setStyleSheet('color:#FF0000')
        self.inputTau.setValue(self.tool.tau/self.tool.Fs*1000)


    def updateSkipPeaks(self):
        self.btnDetectPeaks.setStyleSheet('color:#FF0000')
        self.checkSkipPeaks.setCheckState(QtCore.Qt.CheckState(self.tool.skipPeaks))

        if self.tool.skipPeaks == 0:
            self.inputSkipPeakOffset.setDisabled(True)
        else:
            self.inputSkipPeakOffset.setDisabled(False)

        
    def updateSkipPeakOffset(self):
        self.btnDetectPeaks.setStyleSheet('color:#FF0000')
        self.inputSkipPeakOffset.setValue(self.tool.skipPeakOffset)
        

    def runTool(self):
        self.btnDetectPeaks.setStyleSheet('color:#000000')
        self.tool.run()
    
            
    def plotPeaks(self):
        if self.peakPlotDataItem is None:
            return
        
        self.peakPlotDataItem.setData(self.tool.peakTimes, self.tool.peakAmps)

        
    def plotHistogram(self):
        
        # calculate histogram
        ISIs = np.diff(self.tool.peakTimes)*1000

        self.histogram.plotHistogram(ISIs, bins=0.1)

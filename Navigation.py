from Base import *
import nixlacs
import os
from PyQt5 import QtCore, QtWidgets

from IPython import embed


class Navigation(QtCore.QObject):

    def __init__(self, MainWindow):
        super().__init__()
        self.MainWindow = MainWindow

        self.setupUi()
        
        self.tabs = dict()

            
    def setupUi(self):
                
        # navigation tab widget
        self.widget = QtWidgets.QTabWidget()
        self.widget.setObjectName("naviTabWidget")
        self.widget.setMinimumSize(QtCore.QSize(0, 200))
        self.widget.setMaximumSize(QtCore.QSize(4000, 200))
        self.MainWindow.layout.addWidget(self.widget)

    
    def addTab(self, navigation, title):
        '''
        functions adds a navigation tab to the navigation tab widget
        '''

        self.tabs[title] = navigation(self.MainWindow)
        self.widget.addTab(self.tabs[title].widget, title)

        # add manual update option to navigation menu
        if hasattr(self.tabs[title], 'loadIndex') and hasattr(self.MainWindow, 'navigationMenu'):
            self.MainWindow.navigationMenu.addAction(
                'Update index for navigation <%s>' % (title),
                self.tabs[title].loadIndex
            )



class NaviDatasets():

    def __init__(self, MainWindow):
        self.main = MainWindow

        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)

        # load all datasets
        self.loadIndex(overwrite=False)

        # combo box quality
        self.comboRecordingQuality = QtWidgets.QComboBox()
        self.comboRecordingQuality.currentTextChanged.connect(self.qualitySelected)
        self.layout.addWidget(self.comboRecordingQuality, 0, 0)

        # lists
        self.listDatasets = QtWidgets.QListWidget()
        self.listDatasets.itemClicked.connect(self.datasetSelected)
        self.layout.addWidget(self.listDatasets, 1, 0)

        self.listRePros = QtWidgets.QListWidget()
        self.listRePros.itemClicked.connect(self.reProSelected)
        self.layout.addWidget(self.listRePros, 1, 1)

        self.updateRecordingQualityList()


    def qualitySelected(self, qualityItem):
        self._currentQuality = qualityItem
        self.listDatasets.clear()

        for dataset in sorted(self.datasets[self._currentQuality].keys()):
            self.listDatasets.addItem(dataset)


    def datasetSelected(self, datasetItem):
        '''
        function is called when a dataset is selected and 
        it updates the rePro list widget
        '''

        self._currentDataset = datasetItem.text()

        self.listRePros.clear()
        
        for reProName in self.datasets[self._currentQuality][self._currentDataset]:
            self.listRePros.addItem(QtWidgets.QListWidgetItem(reProName))
        

    def reProSelected(self, reProItem):
        self.main.content.openTab(self._currentDataset, reProItem.text())


    ################################
    # UPDATE INDEX

    def loadIndex(self, overwrite=True):        
        print('Loading dataset list...')

        self.datasets = FileInteractions.loadJsonData('naviDatasetsIndex')
        if self.datasets is not None and not overwrite:
            print('...from file')
            return

        print('.. from data')

        # load all nix files
        nixList = list(filter(
            lambda x: x.startswith('20') and x.endswith('.nix'), 
            os.listdir(Config.getDataPath())
        ))
        
        self.datasets = dict()
        for entry in nixList:
            print(entry)
            entry = entry.replace('.nix', '')
                        
            # open file
            nixFile = nixlacs.RelacsFile(Config.getDataPath(entry), Config.getJsonPath())

            # quality
            recQuality = nixFile.metadata()['Recording']['Recording quality'][0].lower()
            if not recQuality in self.datasets.keys():
                self.datasets[recQuality] = dict()

            # dataset
            self.datasets[recQuality][entry] = list()
            
            # rePros
            for reProName in nixFile.rePros(returnName=True):
                self.datasets[recQuality][entry].append(reProName)
            
            # close file
            nixFile.close()
            
        
        print('Saving index to file...')
        FileInteractions.jsonData('naviDatasetsIndex', self.datasets, overwriteFile=True)
        print('... saved')

        self.updateRecordingQualityList()
        
    def updateRecordingQualityList(self):
        self.comboRecordingQuality.clear()
        self.listDatasets.clear()
        self.listRePros.clear()

        for quality in sorted(list(self.datasets.keys())):
            self.comboRecordingQuality.addItem(quality)


class NaviSubjects():

    def __init__(self, MainWindow):
        self.main = MainWindow

        self.widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.widget.setLayout(self.layout)

        # load all datasets
        self.loadIndex(overwrite=False)

        self.layout.addWidget(QtWidgets.QLabel('Subjects'), 0, 0)
        self.listSubjects = QtWidgets.QListWidget()
        self.listSubjects.itemClicked.connect(self.subjectSelected)
        self.layout.addWidget(self.listSubjects, 1, 0, 2, 1)

        self.layout.addWidget(QtWidgets.QLabel('Quality'), 0, 1)
        self.comboRecordingQuality = QtWidgets.QComboBox()
        self.comboRecordingQuality.currentTextChanged.connect(self.qualitySelected)
        self.layout.addWidget(self.comboRecordingQuality, 0, 2)

        self.layout.addWidget(QtWidgets.QLabel('Datasets'), 1, 1)
        self.listDatasets = QtWidgets.QListWidget()
        self.listDatasets.itemClicked.connect(self.datasetSelected)
        self.layout.addWidget(self.listDatasets, 2, 1, 1, 2)

        self.layout.addWidget(QtWidgets.QLabel('RePros'), 0, 3)
        self.btnOpenAllRePros = QtWidgets.QPushButton('Open all')
        self.btnOpenAllRePros.clicked.connect(self.openAllRePros)
        self.layout.addWidget(self.btnOpenAllRePros, 0, 4)
        self.listRePros = QtWidgets.QListWidget()
        self.listRePros.itemClicked.connect(self.reProSelected)
        self.layout.addWidget(self.listRePros, 1, 3, 2, 2)

        self.layout.setColumnStretch(5, 1)
        
        self.updateSubjectList()

        
    def updateSubjectList(self):
        self.listSubjects.clear()
        self.comboRecordingQuality.clear()
        self.listDatasets.clear()
        
        for subject in sorted(self.datasets.keys()):
            self.listSubjects.addItem(subject)


    def subjectSelected(self, subjectItem):
        self._currentSubject = subjectItem.text()
        self.listRePros.clear()
        self.comboRecordingQuality.clear()

        for quality in sorted(list(self.datasets[self._currentSubject].keys())):
            self.comboRecordingQuality.addItem(quality)

        self.qualitySelected(self.comboRecordingQuality.itemText(0))
            
    def qualitySelected(self, qualityItem):
        if qualityItem == '':
            return
        self.listRePros.clear()
        self._currentQuality = qualityItem
        self.listDatasets.clear()
        
        for dataset in sorted(self.datasets[self._currentSubject][self._currentQuality].keys()):
            self.listDatasets.addItem(dataset)


    def datasetSelected(self, datasetItem):
        '''
        function is called when a dataset is selected and 
        it updates the rePro list widget
        '''

        self._currentDataset = datasetItem.text()

        self.listRePros.clear()

        for reProName in self.datasets[self._currentSubject][self._currentQuality][self._currentDataset]:
            self.listRePros.addItem(QtWidgets.QListWidgetItem(reProName))

    def openAllRePros(self):
        for i in range(self.listRePros.count()):
            reProItem = self.listRePros.item(i)
            print('Opening RePro %s' % reProItem.text())
            self.reProSelected(reProItem)

    def reProSelected(self, reProItem):
        self.main.content.openTab(self._currentDataset, reProItem.text())

    ################################
    # UPDATE INDEX

    def loadIndex(self, overwrite=True):        
        print('Loading dataset list...')

        self.datasets = FileInteractions.loadJsonData('naviSubjectsIndex')
        if self.datasets is not None and not overwrite:
            print('...from file')
            return

        print('.. from data')

        # load all nix files
        nixList = list(filter(
            lambda x: x.startswith('20') and x.endswith('.nix'), 
            os.listdir(Config.getDataPath())
        ))
        
        self.datasets = dict()
        for entry in nixList:
            print(entry)
            entry = entry.replace('.nix', '')
            
            # open file
            nixFile = nixlacs.RelacsFile(Config.getDataPath(entry), Config.getJsonPath())
                
            # missing identifiers for january recordings:
            #subject = nixFile.metadata()['Recording']['Subject']['Identifier'].lower()
            subject = entry[:-3]
            if not subject in self.datasets.keys():
                self.datasets[subject] = dict()

            # quality
            recQuality = nixFile.metadata()['Recording']['Recording quality'][0].lower()
            if not recQuality in self.datasets[subject].keys():
                self.datasets[subject][recQuality] = dict()

            
            # dataset
            self.datasets[subject][recQuality][entry] = list()
            
            # rePros
            for reProName in nixFile.rePros(returnName=True):
                self.datasets[subject][recQuality][entry].append(reProName)
            
            # close file
            nixFile.close()
            
        
        print('Saving index to file...')
        FileInteractions.jsonData('naviSubjectsIndex', self.datasets, overwriteFile=True)
        print('... saved')

        self.updateSubjectList()


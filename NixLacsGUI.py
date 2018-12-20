from Base import *
from Content import *
from ContentTabs import *
from Navigation import *
from PyQt5 import QtCore, QtGui, QtWidgets
import sys

from IPython import embed


################################################################
# APPLICATION WINDOW

class NixLacsGUI(QtWidgets.QMainWindow):

    status = QtCore.pyqtSignal(str)
    sigConfirmDialog = QtCore.pyqtSignal(bool)
    
    def __init__(self):
        super().__init__()

        self.title = 'NixLacs GUI - Relacs > Nix > GUI'
        
        # set MainWindow instance in config / fileInteractions
        Config.setMainWindow(self)
        FileInteractions.setMainWindow(self)

        self.setupUi()
  
        self.navigation = Navigation(self)
        self.content = Content(self)
        
        self.sigConfirmDialog.connect(self.displayConfirmDialog)


    def setupUi(self):

        self.setWindowTitle(self.title)
        
        # central widget and layout
        self.centralWidget = QtWidgets.QWidget()
        self.centralWidget.setObjectName("centralWidget")
        self.layout = QtWidgets.QVBoxLayout(self.centralWidget)
        self.layout.setObjectName("layout")
        NixLacsGUI.setCentralWidget(self, self.centralWidget)

        ## set menubar
        self.menubar = QtWidgets.QMenuBar()
        self.setMenuBar(self.menubar)

        # file
        self.fileMenu = QtWidgets.QMenu('File')
        self.menubar.addMenu(self.fileMenu)
        
        # navigation
        self.navigationMenu = QtWidgets.QMenu('Navigation')
        self.menubar.addMenu(self.navigationMenu)
        
        # analysis
        self.analysisMenu = QtWidgets.QMenu('Analysis')
        self.analysisMenu.addAction(
            'Combine datasets...',
            lambda: self.content.openTab(tabCls=DatasetCombination)
        )
        self.analysisMenu.addAction(
            'Inspect JSON file...',
            lambda: self.content.openTab(tabCls=ExploreJsonFile)
        )
        self.menubar.addMenu(self.analysisMenu)

        
    def moveToConsole(self):
        '''
        function opens an IPython console
        '''
        embed()


    ################################
    # Dialogs

    def displayConfirmDialog(self, header='Confirmation', message='Are your sure?'):
        result = QtWidgets.QMessageBox.question(self,
                        header,
                        message,
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        
        if result == QtWidgets.QMessageBox.Yes:
            return True
        return False



if __name__ == '__main__':
    # set up application window
    app = QtWidgets.QApplication(sys.argv)
    window = NixLacsGUI()
    window.showMaximized()
    #window.show()
    
    # load configuration and check data paths
    Config.loadConfiguration()
    Config.checkDataPaths()

    # add default navigation(s) to application window
    window.navigation.addTab(NaviDatasets, 'Datasets')
    window.navigation.addTab(NaviSubjects, 'Subjects')
    window.navigation.widget.setCurrentWidget(window.navigation.tabs['Subjects'].widget)
    
    sys.exit(app.exec_())

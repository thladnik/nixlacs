import json
import os
import pandas as pd
import pickle


################################################################
# CONFIG

class Config():
    
    configFile = ['.', 'main.cfg']
    
    dataRootPath = ['..', 'data']
    dataDirectory = None
    pickleRootPath = ['..', 'pickled']
    jsonRootPath = ['..', 'json']

    recordingCategories = ['BaselineRecording',
                           'LocalEODRecording',
                           'BaselineAndLocalEOD',
                           'FICurve',
                           'FICurveWithLocalEOD',
                           'ReceptiveFieldMap',
                           'EFieldMap',
                           'EFieldMapWithPUnitLock',
                           'NoiseAM',
                           'NoiseAMWithLocalEOD']

    cellTypes = ['SingleSpike',
                 'Burster',
                 'RythmicBurster']
    
    @classmethod
    def setMainWindow(cls, MainWindow):
        cls.MainWindow = MainWindow
    

    @classmethod
    def loadConfiguration(cls):
        '''
        function loads the configuration file at the default location
        and sets the program parameters accordingly
        '''

        configPath = os.path.join(*cls.configFile)
        if not os.path.exists(configPath):
            return

        with open(configPath, 'r') as fObj:
            config = fObj.read()
            config = config.replace('\n', '').split(';')
            configData = dict()
            for line in config:
                line = line.split('=')
                if len(line) < 2:
                    continue
                configData[line[0]] = line[1]
            fObj.close()

        if 'dataRootPath' in list(configData.keys()):
            cls.dataRootPath = configData['dataRootPath'].split(os.sep)
        if 'dataDirectory' in list(configData.keys()):
            cls.dataDirectory = configData['dataDirectory'].split(os.sep)



    @classmethod
    def checkDataPaths(cls):
        '''
        function checks if the specified data are valid (exist)
        and calls functions that prompt the user to select valid directories
        if that is NOT the case
        '''

        if cls.dataRootPath is not None and not os.path.exists(os.path.join(*cls.dataRootPath)):
            cls.dataRootPath = None

        if cls.dataDirectory is not None and not os.path.exists(cls.getDataPath()):
            cls.dataDirectory = None

        while cls.dataRootPath is None:
            cls.setDataRootPath()

        while cls.dataDirectory is None:
            cls.setDataDirectory()


    @classmethod
    def setDataRootPath(cls):
        '''
        function prompts the user to select the data root directory
        in a popup file dialog
        '''

        filepath = str(QtWidgets.QFileDialog.getExistingDirectory(
            cls.MainWindow, 
            'Select data root path', 
            '.', 
            QtWidgets.QFileDialog.ShowDirsOnly))
        if filepath:
            directory = os.path.relpath(filepath).split(os.sep)

            cls.dataRootPath = directory
            cls.MainWindow.status.emit('Set data root path to %s' % os.path.join(*cls.dataRootPath))

            cls.setDataDirectory()


    @classmethod
    def setDataDirectory(cls):
        '''
        function prompts the user to select the data directory
        within the data root path in a popup file dialog
        '''

        filepath = str(QtWidgets.QFileDialog.getExistingDirectory(
            cls.MainWindow, 
            'Select data directory', 
            os.path.join(*cls.dataRootPath), 
            QtWidgets.QFileDialog.ShowDirsOnly))
        if filepath:
            directory = os.path.relpath(filepath, os.path.join(*cls.dataRootPath)).split(os.sep)
            if directory[0] == '..':
                QtWidgets.QMessageBox.warning(cls.MainWindow, 
                    'Invalid selection', 
                    'Data directory needs to be within data root path.'
                )
                return

            cls.dataDirectory = directory
            cls.MainWindow.status.emit('Set data directory to %s' % os.path.join(*cls.dataDirectory))


    @classmethod        
    def getDataPath(cls, filename=None):
        path = os.path.join(*cls.dataRootPath, *cls.dataDirectory)
        if filename is not None:
            path = os.path.join(path, filename)
        return path


    @classmethod
    def getPicklePath(cls, filename=None):
        path = os.path.join(*cls.pickleRootPath, *cls.dataDirectory)
        if filename is not None:
            path = os.path.join(path, filename)
        return path


    @classmethod
    def getJsonPath(cls, filename=None):
        path = os.path.join(*cls.jsonRootPath, *cls.dataDirectory)
        if filename is not None:
            path = os.path.join(path, filename)
        return path


################################################################
# FILE INTERACTIONS

class FileInteractions():

    @classmethod
    def setMainWindow(cls, MainWindow):
        cls.MainWindow = MainWindow


    @classmethod
    def pickleData(cls, filepath, data, overwriteFile=False, defaultPath=True):
        if defaultPath:
            filepath = os.path.join(Config.getPicklePath(), filepath)

        if not overwriteFile and os.path.exists(filepath):
            overwriteFile = cls.MainWindow.confirmationDialog(
                header='Overwrite existing pickle file', 
                message='Are you sure you want to overwrite the existing pickle file?'
            )

        if overwriteFile or not os.path.exists(filepath):
            print('Saving to %s' % (filepath))
            with open(filepath, 'wb') as fObj:
                pickle.dump(data, fObj)
                fObj.close()

    @classmethod
    def jsonData(cls, filepath, data, overwriteFile=False, defaultPath=True):
        if defaultPath:
            filepath = os.path.join(Config.getJsonPath(), '%s.json' % filepath)
            
        if not overwriteFile and os.path.exists(filepath):
            overwriteFile = cls.MainWindow.confirmationDialog(
                header='Overwrite existing JSON file', 
                message='Are you sure you want to overwrite the existing JSON file?'
            )

        if overwriteFile or not os.path.exists(filepath):
            print('Saving to %s' % (filepath))
            with open(filepath, 'w') as fObj:
                json.dump(data, fObj)
                fObj.close()
                

    @classmethod      
    def loadJsonData(cls, filepath, defaultPath=True):
        if defaultPath:
            filepath = os.path.join(Config.getJsonPath(), '%s.json' % filepath)

        if os.path.exists(filepath):
            with open(filepath, 'r') as fObj:
                data = json.load(fObj)
                fObj.close()
        else:
            data = None
        
        return data

                
    @classmethod      
    def loadPickledData(cls, filepath, defaultPath=True):
        if defaultPath:
            filepath = os.path.join(Config.getPicklePath(), filepath)

        if os.path.exists(filepath):
            with open(filepath, 'rb') as fObj:
                data = pickle.load(fObj)
                fObj.close()
        else:
            data = None
        
        return data


    @classmethod
    def loadDfFromFile(cls, filename, ftype=None):
        if ftype is None:
            ftype = 'json'
        ftype = ftype.lower()

        filepath = Config.getJsonPath(('%s.%s') % (filename, ftype))

        if not os.path.exists(filepath):
            return pd.DataFrame()

        if ftype == 'json':
            return pd.read_json(filepath)

        return None


    @classmethod
    def writeDfToFile(cls, Df, filename, ftype=None):

        if ftype is None:
            ftype = 'json'
        ftype = ftype.lower()

        if ftype == 'json':
            Df.to_json(Config.getJsonPath(('%s.%s') % (filename, ftype)))

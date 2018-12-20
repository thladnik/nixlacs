# nixlacs scipt for opening and organizing nix files that re produced by RELACS
## Tim Hladnik

import nixio as nix
import numpy as np
import os
import pandas as pd

from IPython import embed


def getMetadataDict(metadata):
    def unpackMetadata(sec):
        metadata = dict()
        metadata = {prop.name: sec[prop.name] for prop in sec.props}
        if hasattr(sec, 'sections') and len(sec.sections) > 0:
            metadata.update({subsec.name: unpackMetadata(subsec) for subsec in sec.sections})
        return metadata

    return unpackMetadata(metadata)



################################################################
# REPRO

class RePro():

    _tagMultiTagMap = {
        'ReceptiveField': 'ReceptiveField-1',
        'FICurve': 'FICurve-1',
        'FileStimulus': 'FileStimulus-file-gaussian noise-white noise psd(f) ~ 1 f<fc-1'
    }

    def __init__(self, relacsFile, id):
        self.relacsFile = relacsFile
        self._id = id
        self.savename = '%s_%s.%s' % (
            os.path.join(self.relacsFile.savepath, self.relacsFile.id()),
            self.id(),
            self.relacsFile.savetype
        )

        # open save file or create new Df to be saved
        self.openSaveFile()

        # tag (tags mark the start of a RePro
        self._tagData = self.relacsFile.b().tags[self.id()]

        # multi tag (multiTags mark the beginning of a stimulus) 
        self._multiTagId = None
        self._multiTagData = None
        self._multiTagIdcs = None
        for kw in self._tagMultiTagMap.keys():
            if self.getTagData().name.startswith(kw):
                self._multiTagId = self._tagMultiTagMap[kw]
                self._multiTagData = self.relacsFile.b().multi_tags[self.getMtId()]
                startPos = endPos = self.getTagData().position[0]
                endPos += self.getTagData().extent[0]
                self._multiTagIdcs = np.where(
                    (self.getMtData().positions >= startPos)
                    & (self.getMtData().positions < endPos)
                )[0]
                break


    def id(self):
        return self._id


    def getTagData(self):
        return self._tagData


    def getMtData(self):
        return self._multiTagData


    def getMtIdcs(self):
        return self._multiTagIdcs


    def getMtId(self):
        return self._multiTagId


    def openSaveFile(self):
        self._data = self.relacsFile.openSaveFile(self.savename)


    def writeToSaveFile(self):
        # remove raw signals to avoid redundancies and SAVE STORAGE SPACE
        data = self.data().drop(self.signalAliases, axis='columns')
        data = data[data.additionalData == True]
        self.relacsFile.writeToSaveFile(data, self.savename)


    def data(self, rowIdx=None):
        if rowIdx is None:
            return self._data
        else:
            return self._data.loc[rowIdx].copy()


    def setData(self, series, additionalData=True):
        '''
        function takes a modified series from the Df as provided by self.data().
        It overwrites the columns specified in 'series.index' 
        for the row in self._data given by 'series.position'

        <bool> additionData is a flag which determines whether values
        in this row will be saved to file in case that function is called 
        '''

        # add rePro id
        series['rePro'] = self.id()
        # set flag to true, if series contains additional data
        if additionalData:
            series['additionalData'] = True

        # add missing keys to Df
        for idx in series.index:
            if idx not in self.data().columns:
                self._data[idx] = None

        # set data
        self._data.loc[series.name, series.index] = series


    def loadReferenceData(self, refName, refAlias=None, useDelay=False):
        '''
        takes the name of a tag/multi_tag reference and adds the values associated
        with it as a new column to the RelacsFile._data Df 
        along with the dimensions of the reference
        '''

        print('>Loading reference %s... (%s // %s)' % (refName, self.relacsFile.filepath, self.id()))

        if refAlias is None:
            refAlias = refName

        def getDimData(dim):
            if dim.dimension_type == 'sample':
                return 1./dim.sampling_interval
            else:
                return None

        # load reference data
        si = self.getTagData().references[0].dimensions[0].sampling_interval

        ref = self.getTagData().references[refName]
        tagStartIdx = tagEndIdx = int(self.getTagData().position[0]/si)
        tagEndIdx += int(self.getTagData().extent[0]/si)
        refData = ref[:][tagStartIdx:tagEndIdx]
        dim = getDimData(ref.dimensions[0])

        # if there is NO corresponding multiTag data: return data referenced in tag
        if self.getMtData() is None:
            
            posIdx = int(self.getTagData().position[0]/si)

            series = pd.Series(
                {
                    refAlias: refData, 
                    '%sDim' % refAlias: dim
                },
                name=posIdx
            )

            self.setData(series, additionalData=False)

            return

        # if there is corresponding multiTag data: return datasets references in multiTag

        # set delays (delay is the time BEFORE stimlus onset, i.e. before multiTag.position)
        if useDelay:
            if 'delay' not in self.data().columns:
                self.loadMtFeatureData('delay')
            delays = self.data().delay.values
        else:
            delays = np.zeros(len(self.getMtIdcs()))

        # iterate thorugh multiTags
        for idx, delay in zip(self.getMtIdcs(), delays):

            posIdx = int(self.getMtData().positions[idx][0]/si)

            # calculate indices within tag reference
            mtStartIdx = mtEndIdx = posIdx - int((self.getTagData().position[0] + delay)/si)
            mtEndIdx += int(self.getMtData().extents[idx][0]/si)

            # make sure index does not exceed reference data dimensions
            if mtStartIdx < 0:
                mtStartIdx = 0
            while mtEndIdx >= refData.shape[0]:
                mtEndIdx -= 1

            series = pd.Series(
                { 
                    refAlias: refData[mtStartIdx:mtEndIdx], 
                    '%sDim' % refAlias: dim
                },
                name=posIdx
            )

            self.setData(series, additionalData=False)


    def loadMtFeatureData(self, featureName):
        # if there is no corresponding multiTag data: return data referenced in tag
        if self.getMtData() is None:
            return None

        print('>Loading feature %s... (%s // %s)' % (featureName, self.relacsFile.filepath, self.id()))

        if featureName.startswith(self.getMtId()):
            featId = featureName
        else:
            featId = '%s_%s' % (self.getMtId(), featureName)
            
        featureData = self.getMtData().features[featId].data
        featureDataTrace = featureData[:]

        for idx in self.getMtIdcs():

            posIdx = int(self.getMtData().positions[idx][0]/self.getTagData().references[0].dimensions[0].sampling_interval)
            feature = featureDataTrace[idx]
            series = pd.Series(
                { 
                    featureName: feature
                },
                name=posIdx
            )
            self.setData(series, additionalData=False)

################################################################
# BASELINE ACTIVITY REPRO

class BaselineActivityRePro(RePro):

    signalList =    ['V-1',      'EOD',       'LocalEOD-1', 'LocalEOD-2']
    signalAliases = ['Neuron',   'GlobalEOD', 'RefEOD',     'LocalEOD'  ]
    signalTypes =   ['neuronal', 'eod',       'eod',        'eod'       ]

    def __init__(self, *args):
        super().__init__(*args)

    
    def loadSignals(self):
        for signal, alias in zip(self.signalList, self.signalAliases):
            self.loadReferenceData(signal, alias)


################################################################
# RECEPTIVE FIELD REPRO

class ReceptiveFieldRePro(RePro):

    signalList =    ['V-1',      'EOD',       'LocalEOD-1', 'LocalEOD-2']
    signalAliases = ['Neuron',   'GlobalEOD', 'RefEOD',     'LocalEOD'  ]
    signalTypes =   ['neuronal', 'eod',       'eod',        'eod'       ]


    def __init__(self, *args):
        super().__init__(*args)


    def loadSignals(self):
        for signal, alias in zip(self.signalList, self.signalAliases):
            self.loadReferenceData(signal, alias)

        
################################################################
# FI CURVE REPRO

class FICurveRePro(RePro):

    signalList =    ['V-1',      'EOD',       'LocalEOD-1', 'LocalEOD-2', 'GlobalEFieldStimulus']
    signalAliases = ['Neuron',   'GlobalEOD', 'RefEOD',     'LocalEOD',   'GlobalStim']
    signalTypes =   ['neuronal', 'eod',       'eod',        'eod',        'stim']


    def __init__(self, *args):
        super().__init__(*args)

    def loadSignals(self):
        self.loadMtFeatureData('delay')
        for signal, alias in zip(self.signalList, self.signalAliases):
            self.loadReferenceData(signal, alias, useDelay=True)

        
################################################################
# NOISE AM REPRO

class FileStimulusRePro(RePro):

    signalList =    ['V-1',      'EOD',       'LocalEOD-1', 'LocalEOD-2', 'GlobalEFieldStimulus']
    signalAliases = ['Neuron',   'GlobalEOD', 'RefEOD',     'LocalEOD',   'GlobalStim']
    signalTypes =   ['neuronal', 'eod',       'eod',        'eod',        'stim']


    def __init__(self, *args):
        super().__init__(*args)

        
    def loadSignals(self):
        self.loadMtFeatureData('delay')
        for signal, alias in zip(self.signalList, self.signalAliases):
            self.loadReferenceData(signal, alias, useDelay=True)


    def loadStimulusData(self, baseDir=None):
        
        # load stimulus
        tagMetadata = getMetadataDict(self.getTagData().metadata)
        datasetName = self.relacsFile.id()
        reProName = '-'.join(self.id().split('_'))
        datasetKey = 'dataset-%s-%s' % (datasetName, reProName)
        settingsKey = 'dataset-settings-%s-%s' % (datasetName, reProName)

        filePath = tagMetadata[datasetKey][settingsKey]['file'].split(os.sep)
        idx = [i for i, s in enumerate(filePath) if 'stimuli' in s]
        if len(idx) > 0:
            filePath = filePath[idx[0]:]

        if baseDir is not None:
            filePath = baseDir + filePath
            
        filePath = os.sep.join(filePath)
            
        self.stimulus = np.loadtxt(filePath)

        for posIdx, series in self.data().iterrows():
        
            series['stimContrast'] = tagMetadata[datasetKey][settingsKey]['contrast']
            series['stimMeanAmp'] = tagMetadata[datasetKey][settingsKey]['amplitude']
            series['stimPause'] = tagMetadata[datasetKey][settingsKey]['pause']
            series['stimTimes'] = self.stimulus[:,0]
            series['stimAmps'] = self.stimulus[:,1]

            self.setData(series, additionalData=False)


################################################################
# RELACS FILE

class RelacsFile():

    # dictionary of currently existing rePro implementations
    _reProClasses = {
        'ReceptiveField': ReceptiveFieldRePro,
        'BaselineActivity': BaselineActivityRePro,
        'FICurve': FICurveRePro,
        'FileStimulus': FileStimulusRePro
    }


    def __init__(self, filepath, savepath, savetype='json'):
        self.filepath = filepath
        self.savepath = savepath
        self.savetype = savetype
        self._id = self.filepath.split(os.sep)[-1]

        # open .nix file and select block
        self._f = nix.File.open('%s.nix' % (self.filepath), nix.FileMode.ReadOnly)
        self._b = self._f.blocks[0]

        # initialize RePro classes that correspond to tags of type 'relacs.repro_run'
        def fun(x):
            if x[1].type != 'relacs.repro_run':
                return None
            return self.getReProCls(x[1].name)
        self._rePros = list(filter(None, map(fun, self._b.tags.items())))

        self.data = pd.DataFrame()


    def getReProCls(self, reProId):
        '''
        function returns the appropriate RePro subclass if it is registered
        Example: reProId 'BaselineActivity_2' will return 
        an object of the class BaselineActivityRePro
        '''

        for key in self._reProClasses.keys():
            if reProId.startswith(key):
                return self._reProClasses[key](self, reProId) # return RePro subclass-object
        return None


    def metadata(self):
        return getMetadataDict(self.b().metadata)


    def rePros(self, id=None, returnName=False):
        if id is None:
            if returnName:
                return [rePro.id() for rePro in self.rePros()]
            return self._rePros
        elif isinstance(id, int):
            if returnName:
                return self.rePros(id=id).id()
            return self._rePros[id]
        elif isinstance(id, str):
            for rePro in self._rePros:
                if rePro.id() == id:
                    return rePro

                
    def unifyRePros(self, savepath=None):
        if savepath is None:
            savepath = self.savepath

        frames = list()
        for rePro in self.rePros():
            frames.append(rePro.data())
        self.data = pd.concat(frames)

        self.writeToSaveFile(self.data, os.path.join(self.savepath, '%s.%s' % (self.id(), self.savetype)))


    def openSaveFile(self, savename):

        readfun = None
        if self.savetype == 'json':
            readfun = pd.read_json

        if readfun is None:
            print('Unknown savetype for RelacsFile')
            exit()

        if os.path.exists(savename):
            Df = readfun(savename)
        else:
            # initialize new Df
            Df = pd.DataFrame(columns=['rePro', 'additionalData'])
            Df.additionalData = Df.additionalData.astype(bool)
            Df.additionalData = False

        return Df

    def writeToSaveFile(self, Df, savename):

        writefun = None
        if self.savetype == 'json':
            writefun = pd.DataFrame.to_json

        if writefun is None:
            print('Unknown savetype for RelacsFile')
            exit()

        print('Saving to %s...' % savename)

        writefun(Df, savename)


    def id(self):
        return self._id


    def f(self):
        return self._f


    def b(self):
        return self._b


    def close(self):
        return self._f.close()


if __name__ == '__main__':
    rFile = RelacsFile('../data/pALLN/2018-01-17-ao', '../json/pALLN/')
    embed()

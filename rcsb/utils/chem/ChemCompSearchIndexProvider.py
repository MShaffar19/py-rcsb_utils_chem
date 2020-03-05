##
# File:    ChemCompSearchIndexProvider.py
# Author:  J. Westbrook
# Date:    3-Mar-2020
#
# Updates:
#
##
"""
Utilities to read and process an index of PDB chemical component definitions.
"""
__docformat__ = "restructuredtext en"
__author__ = "John Westbrook"
__email__ = "john.westbrook@rcsb.org"
__license__ = "Apache 2.0"

import logging
import os
import time

from rcsb.utils.chem.ChemCompMoleculeProvider import ChemCompMoleculeProvider
from rcsb.utils.chem.OeMoleculeFactory import OeMoleculeFactory
from rcsb.utils.io.IoUtil import getObjSize
from rcsb.utils.io.MarshalUtil import MarshalUtil
from rcsb.utils.io.SingletonClass import SingletonClass
from rcsb.utils.multiproc.MultiProcUtil import MultiProcUtil


logger = logging.getLogger(__name__)


class ChemCompSearchIndexWorker(object):
    """  A skeleton class that implements the interface expected by the multiprocessing
         for calculating search index candidates --
    """

    def __init__(self, ccObjD, **kwargs):
        self.__ccObjD = ccObjD
        _ = kwargs

    def buildRelatedList(self, dataList, procName, optionsD, workingDir):
        """  Build search candidates for the input list of chemical component definitions
             and return index feature data.
        """
        _ = optionsD
        _ = workingDir
        # fetchLimit = optionsD.get("fetchLimit", None)
        limitPerceptions = optionsD.get("limitPerceptions", True)
        successList = []
        failList = []
        retList = []
        diagList = []
        #
        try:
            retList, failList = self.__buildChemCompSearchIndex(procName, dataList, limitPerceptions=limitPerceptions)
            successList = sorted(set(dataList) - set(failList))
            logger.info("%s built %d search candidates from %d definitions with failures %d", procName, len(retList), len(dataList), len(failList))
        except Exception as e:
            logger.exception("Failing %s for %d data items %s", procName, len(dataList), str(e))
        #
        return successList, retList, diagList

    def __buildChemCompSearchIndex(self, procName, ccIdList, limitPerceptions=True):
        """Internal method return a dictionary of extracted chemical component descriptors and formula.
        """
        rL = []
        fL = []
        try:
            for ccId in ccIdList:
                if ccId not in self.__ccObjD:
                    logger.error("%s missing chemical definition for %s", procName, ccId)
                    fL.append(ccId)
                    continue
                dataContainer = self.__ccObjD[ccId]
                # ----
                oemf = OeMoleculeFactory()
                oemf.setQuiet()
                tId = oemf.setChemCompDef(dataContainer)
                if tId != ccId:
                    logger.error("%s %s chemical component definition import error", procName, ccId)
                    fL.append(ccId)
                    continue
                relD = oemf.buildRelated(limitPerceptions=limitPerceptions)
                logger.info("%s %s related molecular forms %d", procName, ccId, len(relD))
                if relD:
                    rL.extend([relD[v] for v in relD])
                else:
                    fL.append(ccId)
        except Exception as e:
            logger.exception("%s failing with %s", procName, str(e))
        return rL, fL


class ChemCompSearchIndexProvider(SingletonClass):
    """Utilities to read and process the index of chemical component definitions search targets
    """

    def __init__(self, **kwargs):
        #
        self.__cachePath = kwargs.get("cachePath", ".")
        self.__dirPath = os.path.join(self.__cachePath, "chem_comp")
        self.__mU = MarshalUtil(workPath=self.__dirPath)
        self.__searchIdx = self.__reload(**kwargs)

    def testCache(self, minCount=29000, logSizes=False):
        if logSizes and self.__searchIdx:
            logger.info("searchIdxD (%.2f MB)", getObjSize(self.__searchIdx) / 1000000.0)
        ok = self.__searchIdx and len(self.__searchIdx) >= minCount if minCount else self.__searchIdx is not None
        return ok

    def getIndex(self):
        return self.__searchIdx

    def getIndexEntry(self, searchCcId):
        try:
            return self.__searchIdx[searchCcId]
        except Exception as e:
            logger.debug("Get index entry %r failing with %s", searchCcId, str(e))
        return None

    def __reload(self, **kwargs):
        """Reload or created index of PDB chemical components.

        Args:
            cachePath (str): path to the directory containing cache files
            ccIdxFileName (str): serialized chemical component data index file name


         Returns:
            (list): chemical component data containers
        """
        #
        searchIdxD = {}
        useCache = kwargs.get("useCache", True)
        molLimit = kwargs.get("molLimit", 0)
        numProc = kwargs.get("numProc", 1)
        maxChunkSize = kwargs.get("maxChunkSize", 20)
        limitPerceptions = kwargs.get("limitPerceptions", True)
        ccFileNamePrefix = kwargs.get("ccFileNamePrefix", "cc")
        searchIdxFilePath = os.path.join(self.__dirPath, "%s-search-idx-components.json" % ccFileNamePrefix)
        #
        if useCache and self.__mU.exists(searchIdxFilePath):
            _, fExt = os.path.splitext(searchIdxFilePath)
            searchIdxFormat = "json" if fExt == ".json" else "pickle"
            rdCcIdxD = self.__mU.doImport(searchIdxFilePath, fmt=searchIdxFormat)
            searchIdxD = {k: rdCcIdxD[k] for k in sorted(rdCcIdxD.keys())[:molLimit]} if molLimit else rdCcIdxD
        else:
            cmpKwargs = {k: v for k, v in kwargs.items() if k not in ["cachePath", "useCache", "molLimit"]}
            ccmP = ChemCompMoleculeProvider(cachePath=self.__cachePath, useCache=True, molLimit=molLimit, **cmpKwargs)
            ok = ccmP.testCache(minCount=molLimit, logSizes=True)
            if ok:
                searchIdxD = self.__updateChemCompSearchIndex(ccmP.getMolD(), searchIdxFilePath, molLimit, limitPerceptions, numProc, maxChunkSize)
                logger.info("Storing %s with data for %d search candidates (status=%r) ", searchIdxFilePath, len(searchIdxD), ok)
        #
        return searchIdxD

    def __updateChemCompSearchIndex(self, ccObjD, filePath, molLimit, limitPerceptions, numProc, maxChunkSize):
        searchIdxD = {}
        try:
            # Serialized index of chemical component search targets
            startTime = time.time()
            _, fExt = os.path.splitext(filePath)
            fileFormat = "json" if fExt == ".json" else "pickle"
            if numProc <= 1:
                searchIdxD = self.__buildChemCompSearchIndex(ccObjD, limitPerceptions=limitPerceptions, molLimit=molLimit)
            else:
                searchIdxD = self.__buildChemCompSearchIndexMulti(ccObjD, limitPerceptions=limitPerceptions, molLimit=molLimit, numProc=numProc, maxChunkSize=maxChunkSize)

            ok = self.__mU.doExport(filePath, searchIdxD, fmt=fileFormat)
            endTime = time.time()
            logger.info("Storing %s (%s) with %d search definitions (status=%r) (%.4f seconds)", filePath, fileFormat, len(searchIdxD), ok, endTime - startTime)
        #
        except Exception as e:
            logger.exception("Failing with %s", str(e))
        #
        return searchIdxD

    def __buildChemCompSearchIndex(self, ccObjD, limitPerceptions=True, molLimit=None):
        """Internal method return a dictionary of extracted chemical component descriptors and formula.
        """
        rD = {}
        try:
            for ii, ccId in enumerate(ccObjD, 1):
                if molLimit and ii > molLimit:
                    break
                # ----
                oemf = OeMoleculeFactory()
                oemf.setQuiet()
                tId = oemf.setChemCompDef(ccObjD[ccId])
                if tId != ccId:
                    logger.error("%s chemical component definition import error", ccId)
                smiD = oemf.buildRelated(limitPerceptions=limitPerceptions)
                logger.info("%s related molecular forms %d", ccId, len(smiD))
                rD.update(smiD)
        except Exception as e:
            logger.exception("Failing with %s", str(e))

        return rD

    def __buildChemCompSearchIndexMulti(self, ccObjD, limitPerceptions=True, molLimit=None, numProc=2, maxChunkSize=20):
        #
        ccIdList = sorted(ccObjD.keys())[:molLimit] if molLimit else sorted(ccObjD.keys())
        logger.info("Input definition length %d numProc %d limitPerceptions %r", len(ccIdList), numProc, limitPerceptions)
        #
        rWorker = ChemCompSearchIndexWorker(ccObjD)
        mpu = MultiProcUtil(verbose=True)
        optD = {"maxChunkSize": maxChunkSize, "limitPerceptions": limitPerceptions}
        mpu.setOptions(optD)
        mpu.set(workerObj=rWorker, workerMethod="buildRelatedList")
        ok, failList, resultList, _ = mpu.runMulti(dataList=ccIdList, numProc=numProc, numResults=1, chunkSize=maxChunkSize)
        logger.info("Multi-proc status %r failures %r result length %r", ok, len(failList), len(resultList[0]))
        #
        rD = {vD["name"]: vD for vD in resultList[0]}
        return rD
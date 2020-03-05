##
# File:    ChemCompIndexProvider.py
# Author:  J. Westbrook
# Date:    16-Feb-2020
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
from collections import defaultdict

from rcsb.utils.chem.ChemCompMoleculeProvider import ChemCompMoleculeProvider
from rcsb.utils.chem.PdbxChemComp import PdbxChemCompDescriptorIt
from rcsb.utils.chem.PdbxChemComp import PdbxChemCompIt
from rcsb.utils.chem.PdbxChemComp import PdbxChemCompAtomIt
from rcsb.utils.io.IoUtil import getObjSize
from rcsb.utils.io.MarshalUtil import MarshalUtil
from rcsb.utils.io.SingletonClass import SingletonClass

logger = logging.getLogger(__name__)


class ChemCompIndexProvider(SingletonClass):
    """Utilities to read and process an index of PDB chemical component definitions.
    """

    def __init__(self, **kwargs):
        #
        self.__cachePath = kwargs.get("cachePath", ".")
        self.__dirPath = os.path.join(self.__cachePath, "chem_comp")
        self.__mU = MarshalUtil(workPath=self.__dirPath)
        self.__ccIdxD = self.__reload(**kwargs)

    def testCache(self, minCount=29000, logSizes=False):
        if logSizes and self.__ccIdxD:
            logger.info("ccIdxD (%.2f MB)", getObjSize(self.__ccIdxD) / 1000000.0)
        ok = self.__ccIdxD and len(self.__ccIdxD) >= minCount if minCount else self.__ccIdxD is not None
        return ok

    def getIndex(self):
        return self.__ccIdxD

    def getMol(self, ccId):
        try:
            return self.__ccIdxD[ccId]
        except Exception as e:
            logger.debug("Get molecule %r failing with %s", ccId, str(e))
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
        ccIdxD = {}
        useCache = kwargs.get("useCache", True)
        molLimit = kwargs.get("molLimit", 0)
        ccFileNamePrefix = kwargs.get("ccFileNamePrefix", "cc")
        ccIdxFilePath = os.path.join(self.__dirPath, "%s-idx-components.pic" % ccFileNamePrefix)
        #
        if useCache and self.__mU.exists(ccIdxFilePath):
            _, fExt = os.path.splitext(ccIdxFilePath)
            ccIdxFormat = "json" if fExt == ".json" else "pickle"
            rdCcIdxD = self.__mU.doImport(ccIdxFilePath, fmt=ccIdxFormat)
            ccIdxD = {k: rdCcIdxD[k] for k in sorted(rdCcIdxD.keys())[:molLimit]} if molLimit else rdCcIdxD
        else:
            cmpKwargs = {k: v for k, v in kwargs.items() if k not in ["cachePath", "useCache", "molLimit"]}
            ccmP = ChemCompMoleculeProvider(cachePath=self.__cachePath, useCache=True, molLimit=molLimit, **cmpKwargs)
            ok = ccmP.testCache(minCount=molLimit, logSizes=True)
            if ok:
                ccIdxD = self.__updateChemCompIndex(ccmP.getMolD(), ccIdxFilePath)
                logger.info("Storing %s with data for %d definitions (status=%r) ", ccIdxFilePath, len(ccIdxD), ok)
        #
        return ccIdxD

    def __updateChemCompIndex(self, ccObjD, filePath):
        idxD = {}
        try:
            # Serialized chemical component data index file
            startTime = time.time()
            _, fExt = os.path.splitext(filePath)
            fileFormat = "json" if fExt == ".json" else "pickle"
            idxD = self.__buildChemCompIndex(ccObjD)
            ok = self.__mU.doExport(filePath, idxD, fmt=fileFormat)
            endTime = time.time()
            logger.info("Storing %s with %d raw indexed definitions (status=%r) (%.4f seconds)", filePath, len(idxD), ok, endTime - startTime)
        #
        except Exception as e:
            logger.exception("Failing with %s", str(e))
        #
        return idxD

    def __buildChemCompIndex(self, cD):
        """Internal method return a dictionary of extracted chemical component descriptors and formula.
        """
        rD = {}
        try:
            for _, dataContainer in cD.items():
                ccIt = iter(PdbxChemCompIt(dataContainer))
                cc = next(ccIt, None)
                ccId = cc.getId()
                formula = str(cc.getFormula()).replace(" ", "")
                ambiguousFlag = cc.getAmbiguousFlag().upper() in ["Y", "YES"]
                tch = cc.getFormalCharge()
                fcharge = int(tch) if tch and tch not in [".", "?"] else 0
                #
                logger.debug("ccId %r formula %r ambiguous %r fcharge %r", ccId, formula, ambiguousFlag, fcharge)
                if fcharge:
                    sign = "+" if fcharge > 0 else "-"
                    mag = str(abs(fcharge)) if abs(fcharge) > 1 else ""
                    formula = formula + sign + mag
                #
                atIt = PdbxChemCompAtomIt(dataContainer)
                typeCounts = defaultdict(int)
                for at in atIt:
                    aType = at.getType().upper()
                    typeCounts[aType] += 1
                #
                rD[ccId] = {
                    "formula": formula,
                    "type_counts": typeCounts,
                    "ambiguous": ambiguousFlag,
                }
                desIt = PdbxChemCompDescriptorIt(dataContainer)
                for des in desIt:
                    desBuildType = des.getMolBuildType()
                    tS = des.getDescriptor()
                    descr = tS.strip() if tS else None
                    if not descr:
                        continue
                    if desBuildType in ["oe-iso-smiles", "oe-smiles", "acdlabs-smiles", "cactvs-iso-smiles", "cactvs-smiles", "inchi", "inchikey"]:
                        rD[ccId][desBuildType] = descr
                    else:
                        logger.error("%s unexpected descriptor build type %r", ccId, desBuildType)

        except Exception as e:
            logger.exception("Failing with %s", str(e))

        return rD
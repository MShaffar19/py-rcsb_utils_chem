##
# File:    ChemCompIndexProviderTests.py
# Author:  J. Westbrook
# Date:    17-Feb-2020
# Version: 0.001
#
# Update:
#
#
##
"""
Tests for utilities to read and process the dictionary of PDB chemical component definitions.

"""

__docformat__ = "restructuredtext en"
__author__ = "John Westbrook"
__email__ = "jwest@rcsb.rutgers.edu"
__license__ = "Apache 2.0"

import logging
import os
import platform
import resource
import time
import unittest


from rcsb.utils.chem import __version__
from rcsb.utils.chem.ChemCompIndexProvider import ChemCompIndexProvider

HERE = os.path.abspath(os.path.dirname(__file__))
TOPDIR = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]-%(module)s.%(funcName)s: %(message)s")
logger = logging.getLogger()


class ChemCompIndexProviderTests(unittest.TestCase):
    skipFlag = True

    def setUp(self):
        self.__startTime = time.time()
        self.__dataPath = os.path.join(HERE, "test-data")
        self.__cachePath = os.path.join(HERE, "test-output")
        self.__ccUrlTarget = os.path.join(self.__dataPath, "components-abbrev.cif")
        self.__birdUrlTarget = os.path.join(self.__dataPath, "prdcc-abbrev.cif")
        #
        logger.debug("Running tests on version %s", __version__)
        logger.info("Starting %s at %s", self.id(), time.strftime("%Y %m %d %H:%M:%S", time.localtime()))

    def tearDown(self):
        unitS = "MB" if platform.system() == "Darwin" else "GB"
        rusageMax = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logger.info("Maximum resident memory size %.4f %s", rusageMax / 10 ** 6, unitS)
        endTime = time.time()
        logger.info("Completed %s at %s (%.4f seconds)", self.id(), time.strftime("%Y %m %d %H:%M:%S", time.localtime()), endTime - self.__startTime)

    def testChemCompIndexCacheFilesAbbrev(self):
        """ Test construction of full chemical component resource files.
        """
        self.__testBuildMoleculeCacheFiles(ccUrlTarget=self.__ccUrlTarget, birdUrlTarget=self.__birdUrlTarget, logSizes=False, useCache=False, ccFileNamePrefix="cc-abbrev")

    @unittest.skipIf(skipFlag, "Long test")
    def testChemCompIndexCacheFilesFull(self):
        """ Test construction of full chemical component resource files.
        """
        self.__testBuildMoleculeCacheFiles(useCache=False, ccFileNamePrefix="cc-full")

    @unittest.skipIf(skipFlag, "Long test")
    def testChemCompIndexCacheFilesFiltered(self):
        """ Test construction of a filtered subset of chemical component definitions.
        """
        self.__testBuildMoleculeCacheFiles(useCache=False, ccFileNamePrefix="cc-filtered")

    def __testBuildMoleculeCacheFiles(self, **kwargs):
        """ Test build chemical component cache files from the input component dictionaries
        """
        molLimit = kwargs.get("molLimit", None)
        useCache = kwargs.get("useCache", True)
        logSizes = kwargs.get("logSizes", False)
        ccFileNamePrefix = kwargs.get("ccFileNamePrefix", "cc")
        ccUrlTarget = kwargs.get("ccUrlTarget", None)
        birdUrlTarget = kwargs.get("birdUrlTarget", None)
        #
        ccidxP = ChemCompIndexProvider(
            ccUrlTarget=ccUrlTarget, birdUrlTarget=birdUrlTarget, cachePath=self.__cachePath, useCache=useCache, molLimit=molLimit, ccFileNamePrefix=ccFileNamePrefix
        )
        ok = ccidxP.testCache(minCount=molLimit, logSizes=logSizes)
        self.assertTrue(ok)
        logger.info(" ******* Completed operation ******** ")
        #
        return ccidxP

    def testFormulaMatch(self):
        """Test formula match   ...
        """
        ccidxP = self.__testBuildMoleculeCacheFiles(logSizes=False, useCache=True, ccFileNamePrefix="cc-abbrev")
        ccidxD = ccidxP.getIndex()
        logger.info("Matching formula for %d definitions", len(ccidxD))
        for ccId, idxD in ccidxD.items():
            startTime = time.time()
            fQueryD = {el: {"min": eCount, "max": eCount} for el, eCount in idxD["type-counts"].items()}
            if fQueryD:
                rL = ccidxP.matchMolecularFormula(fQueryD)
                logger.debug("%s formula matches %r (%.4f seconds)", ccId, rL, time.time() - startTime)
                if not self.__resultContains(ccId, rL):
                    logger.info("%s formula not matched %r %r  (%.4f seconds)", ccId, rL, fQueryD, time.time() - startTime)

    def __resultContains(self, ccId, matchResultList):
        for matchResult in matchResultList:
            if ccId in matchResult.ccId:
                return True
        return False


def buildCacheFiles():
    suiteSelect = unittest.TestSuite()
    suiteSelect.addTest(ChemCompIndexProviderTests("testChemCompIndexCacheFilesFull"))
    suiteSelect.addTest(ChemCompIndexProviderTests("testChemCompIndexCacheFilesFiltered"))
    suiteSelect.addTest(ChemCompIndexProviderTests("testChemCompIndexCacheFilesAbbrev"))
    return suiteSelect


if __name__ == "__main__":

    mySuite = buildCacheFiles()
    unittest.TextTestRunner(verbosity=2).run(mySuite)

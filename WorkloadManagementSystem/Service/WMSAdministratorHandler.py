########################################################################
# $Id: WMSAdministratorHandler.py,v 1.21 2008/03/07 17:17:03 atsareg Exp $
########################################################################
"""
This is a DIRAC WMS administrator interface.
It exposes the following methods:

Site mask related methods:
    setMask(<site mask>)
    getMask()

User proxy related methods:
    getProxy(DN)

Access to the pilot data:
    getWMSStats()

"""

__RCSID__ = "$Id: WMSAdministratorHandler.py,v 1.21 2008/03/07 17:17:03 atsareg Exp $"

import os, sys, string, uu, shutil, datetime
from types import *

from DIRAC.Core.DISET.RequestHandler import RequestHandler
from DIRAC import gConfig, gLogger, S_OK, S_ERROR
from DIRAC.WorkloadManagementSystem.DB.JobDB import JobDB
from DIRAC.WorkloadManagementSystem.DB.ProxyRepositoryDB import ProxyRepositoryDB
from DIRAC.WorkloadManagementSystem.DB.PilotAgentsDB import PilotAgentsDB
from DIRAC.Core.Utilities.GridCredentials import restoreProxy, setupProxy, renewProxy, getProxyTimeLeft, setDIRACGroupInProxy
from DIRAC.WorkloadManagementSystem.Service.WMSUtilities import *
import DIRAC.Core.Utilities.Time as Time

# This is a global instance of the database classes
jobDB = False
proxyRepository = False
pilotDB = False

# In memory proxy store
proxyStore = {}

def initializeWMSAdministratorHandler( serviceInfo ):
  """  WMS AdministratorService initialization
  """

  global jobDB
  global proxyRepository
  global pilotDB

  jobDB = JobDB()
  proxyRepository = ProxyRepositoryDB()
  pilotDB = PilotAgentsDB()
  return S_OK()

class WMSAdministratorHandler(RequestHandler):

  def __init__(self,*args,**kargs):

    self.servercert = gConfig.getValue('/DIRAC/Security/CertFile',
                              '/opt/dirac/etc/grid-security/hostcert.pem')
    self.serverkey = gConfig.getValue('/DIRAC/Security/KeyFile',
                              '/opt/dirac/etc/grid-security/hostkey.pem')
    if os.environ.has_key('X509_USER_CERT'):
      self.servercert = os.environ['X509_USER_CERT']
    if os.environ.has_key('X509_USER_KEY'):
      self.serverkey = os.environ['X509_USER_KEY']

    RequestHandler.__init__(self,*args,**kargs)

###########################################################################
  types_setMask = [StringType]
  def export_setSiteMask(self, siteList):
    """ Set the site mask for matching. The mask is given in a form of Classad
        string.
    """

    maskList = [ (site,'Active') for site in siteList ]
    result = jobDB.setSiteMask(maskList)
    return result

##############################################################################
  types_getSiteMask = []
  def export_getSiteMask(self):
    """ Get the site mask
    """

    result = jobDB.getSiteMask('Active')
    return result

    if result['Status'] == "OK":
      active_list = result['Value']
      mask = []
      for i in range(1,len(tmp_list),2):
        mask.append(tmp_list[i])

      return S_OK(mask)
    else:
      return S_ERROR('Failed to get the mask from the Job DB')

##############################################################################
  types_banSite = [StringType]
  def export_banSite(self, site,comment='No comment'):
    """ Ban the given site in the site mask
    """

    result = self.getRemoteCredentials()
    dn = result['DN']
    result = jobDB.banSiteInMask(site,dn)
    return result

##############################################################################
  types_allowSite = [StringType]
  def export_allowSite(self,site,comment='No comment'):
    """ Allow the given site in the site mask
    """

    result = self.getRemoteCredentials()
    dn = result['DN']
    result = jobDB.allowSiteInMask(site,dn)
    return result

##############################################################################
  types_clearMask = []
  def export_clearMask(self):
    """ Clear up the entire site mask
    """

    return jobDB.removeSiteFromMask("All")

##############################################################################
  types_getProxy = [StringType,StringType,IntType]
  def export_getProxy(self,ownerDN,ownerGroup,validity=1):
    """ Get a short user proxy from the central WMS repository for the user
        with DN ownerDN with the validity period of <validity> hours
    """

    global proxyStore
    key = ownerDN+':::'+ownerGroup
    gLogger.verbose('Getting proxy for %s for %d hours' % (key,validity))
    if proxyStore.has_key(key):
      expirationTime = proxyStore[key]['ExpirationTime']
      exTime = Time.fromString(expirationTime)
      validityDelta = datetime.timedelta(0,3600*validity)
      print "============= getProxy: deltas",exTime - datetime.datetime.now(),validityDelta
      if (exTime - datetime.datetime.now()) > validityDelta:
        proxy = proxyStore[key]["Proxy"]
        gLogger.info('Proxy for %s served from memory' % key)
        return S_OK(proxy)

    result = proxyRepository.getProxy(ownerDN,ownerGroup)
    if not result['OK']:
      return result
    new_proxy = None
    user_proxy = result['Value']

    d_validity = validity*0.1
    if d_validity < 1.:
      d_validity = 1.

    result = renewProxy(user_proxy,validity+d_validity,
                        server_cert=self.servercert,
                        server_key=self.serverkey)

    if result["OK"]:
      new_proxy = result["Value"]
      new_exTime = (datetime.datetime.now()+datetime.timedelta(0,3600*(validity+d_validity))).strftime('%Y-%m-%d %H:%M:%S')
      proxyStore[key] = {'Proxy':new_proxy,'ExpirationTime':new_exTime}
      gLogger.info('Updated proxy for %s saved in memory' % key)
      return S_OK(new_proxy)
    else:
      resTime = getProxyTimeLeft(user_proxy)

      if resTime['OK']:
        timeLeft = resTime['Value']
        if timeLeft/3600. > validity:
          result = S_OK(user_proxy)
          result['Message'] = 'Could not get myproxy delegation'
          result['TimeLeft'] = timeLeft
          return result
        else:
          result = S_OK(user_proxy)
          result['Message'] = 'WARNING: a shorter than requested proxy is returned'
          result['TimeLeft'] = timeLeft
          return result
          #return S_ERROR('Could not get proxy delegation and the stored proxy is not sufficient')
      else:
        return S_ERROR("Could not get proxy delegation and the stored proxy is not valid")

##############################################################################
  types_uploadProxy = [StringType]
  def export_uploadProxy(self,proxy,DN=None,group=None):
    """ Upload a proxy to the WMS Proxy Repository
    """

    # If the group is given, then replace it in the proxy
    if group:
      tmp_proxy = setDIRACGroupInProxy(proxy,None)
      proxy_to_send = setDIRACGroupInProxy(tmp_proxy,group)
    else:
      proxy_to_send = proxy

    result = self.getRemoteCredentials()
    userDN = DN
    if not DN:
      userDN = result['DN']
    userGroup = group
    if not group:
      userGroup = result['group']

    gLogger.info('Uploading proxy of %s, group %s' %(userDN,userGroup))

    result = proxyRepository.storeProxy(proxy_to_send,userDN,userGroup)
    return result

 ##############################################################################
  types_destroyProxy = [StringType]
  def export_destroyProxy(self,DN=None,group=None):
    """ Destroy proxy in the proxy repository
    """
    userDN = DN
    if not DN:
      userDN = result['DN']
    userGroup = group
    if not group:
      userGroup = result['group']

    gLogger.info('Destroying proxy of %s, group %s' %(userDN,userGroup))

    result = proxyRepository.destroyProxy(userDN,userGroup)
    return result

##############################################################################
  types_setProxyPersistencyFlag = [BooleanType]
  def export_setProxyPersistencyFlag(self,flag,DN=None,group=None):
    """ Upload a proxy to the WMS Proxy Repository
    """

    result = self.getRemoteCredentials()
    userDN = DN
    if not DN:
      userDN = result['DN']
    userGroup = group
    if not group:
      userGroup = result['group']

    result = proxyRepository.setProxyPersistencyFlag(userDN,userGroup,flag)
    return result

##############################################################################
  types_getPilotOutput = [StringType]
  def export_getPilotOutput(self,pilotReference):
    """ Get the pilot job standard output and standard error files for the Grid
        job reference
    """

    return self.__getGridJobOutput(pilotReference)

  ##############################################################################
  types_getJobPilotOutput = [IntType]
  def export_getJobPilotOutput(self,jobID):
    """ Get the pilot job standard output and standard error files for the DIRAC
        job reference
    """

    # Get the pilot grid reference first
    result = jobDB.getJobParameter(jobID,'Pilot_Reference')
    if not result['OK']:
      return result

    pilotReference = result['Value']
    if pilotReference:
      return self.__getGridJobOutput(pilotReference)
    else:
      return S_ERROR('No pilot job reference found')

  ##############################################################################
  def __getGridJobOutput(self,pilotReference):
    """ Get the pilot job standard output and standard error files for the Grid
        job reference
    """

    result = pilotDB.getPilotInfo(pilotReference)
    if not result['OK']:
      return S_ERROR('Failed to determine owner for pilot ' + pilotReference)

    pilotDict = result['Value']
    owner = pilotDict['OwnerDN']
    group = pilotDict['OwnerGroup']

    result = pilotDB.getPilotOutput(pilotReference)
    if result['OK']:
      stdout = result['Value']['StdOut']
      error = result['Value']['StdError']
      if stdout or error:
        resultDict = {}
        resultDict['StdOut'] = stdout
        resultDict['StdError'] = error
        resultDict['OwnerDN'] = owner
        resultDict['OwnerGroup'] = group
        resultDict['FileList'] = []
        return S_OK(resultDict)

    result = proxyRepository.getProxy(owner,group)
    if not result['OK']:
      return S_ERROR("Failed to get the pilot's owner proxy")

    proxy = result['Value']
    result = setupProxy(proxy)
    if not result['OK']:
      return S_ERROR("Failed to setup the pilot's owner proxy")

    new_proxy,old_proxy = result['Value']

    gridType = pilotDict['GridType']
    result = eval('get'+gridType+'PilotOutput("'+pilotReference+'")')
    resProxy = restoreProxy(new_proxy,old_proxy)
    if not result['OK']:
      return S_ERROR('Failed to get pilot output: '+result['Message'])

    stdout = result['StdOut']
    error = result['StdError']
    fileList = result['FileList']
    result = pilotDB.storePilotOutput(pilotReference,stdout,error)

    resultDict = {}
    resultDict['StdOut'] = stdout
    resultDict['StdError'] = error
    resultDict['OwnerDN'] = owner
    resultDict['OwnerGroup'] = group
    resultDict['FileList'] = fileList
    return S_OK(resultDict)

  ##############################################################################
  types_getPilotSummary = []
  def export_getPilotSummary(self,startdate='',enddate=''):
    """ Get summary of the status of the LCG Pilot Jobs
    """

    result = pilotDB.getPilotSummary(startdate,enddate)
    return result

  ##############################################################################
  types_getPilots = [IntType]
  def export_getPilots(self,jobID):
    """ Get pilot references and their statuses for those submitted for the given job
    """

    result = pilotDB.getPilotsForJob(jobID)
    if not result['OK']:
      return S_ERROR('Failed to get pilots: '+result['Message'])

    pilots = result['Value']
    result = pilotDB.getPilotInfo(pilots)
    return result

  ##############################################################################
  types_setJobForPilot = [IntType, StringType]
  def export_setJobForPilot(self,jobID,pilotRef):
    """ Report the DIRAC job ID which is executed by the given pilot job
    """

    result = pilotDB.setJobForPilot(jobID,pilotRef)
    if not result['OK']:
      return result
    result = pilotDB.setCurrentJobID(pilotRef,jobID)
    return result  

  ##########################################################################################
  types_setPilotBenchmark = [StringType, FloatType]
  def setPilotBenchmark(self,pilotRef,mark):
    """ Set the pilot agent benchmark
    """
    result = pilotDB.setPilotBenchmark(pilotRef,mark)
    return result



from DIRAC import S_OK, S_ERROR, gLogger
from DIRAC.Core.Utilities import DEncode, List
from DIRAC.Core.Base.Executor import Executor
from DIRAC.WorkloadManagementSystem.Client.JobState.CachedJobState import CachedJobState

class OptimizerExecutor( Executor ):

  def initialize( self ):
    opName = self.am_getModuleParam( 'fullName' )
    opName = "/".join( opName.split( "/" )[1:] )
    if opName.find( "Agent" ) == len( opName ) - 5:
      opName = opName[ :-5]
    self.__optimizerName = opName
    maxTasks = self.am_getOption( 'Tasks', 1 )
    result = self.connect( "WorkloadManagement/OptimizationMind", maxTasks = maxTasks, name = self.__optimizerName )
    if not result[ 'OK' ]:
      return result
    self.am_setOption( "ReconnectRetries", 10 )
    self.am_setOption( "ReconnectWaitTime", 10 )
    self.am_setModuleParam( 'optimizerName', self.__optimizerName )
    return self.initializeOptimizer()

  def am_optimizerName( self ):
    return self.__optimizerName

  def initializeOptimizer( self ):
    return S_OK()

  def processTask( self, jid, jobState ):
    self.log.info( "Job %s: Processing" % jid )
    result = self.optimizeJob( jid, jobState )
    if not result[ 'OK' ]:
      return result
    #If the manifest is dirty, update it!
    result = jobState.getManifest()
    if not result[ 'OK' ]:
      return result
    manifest = result[ 'Value' ]
    if manifest.isDirty():
      jobState.setManifest( manifest )
    #Did it go as expected? If not Failed!
    if not result[ 'OK' ]:
      self.log.info( "Job %s: Set to Failed/%s" % ( jid, result[ 'Message' ] ) )
      return jobState.setStatus( "Failed", result[ 'Message' ] )
    return S_OK()


  def optimizeJob( self, jid, jobState ):
    raise Exception( "You need to overwrite this method to optimize the job!" )

  def setNextOptimizer( self, jobState ):
    result = jobState.getOptParameter( 'OptimizerChain' )
    if not result['OK']:
      return result
    opChain = List.fromChar( result[ 'Value' ], "," )
    opName = self.__optimizerName
    try:
      opIndex = opChain.index( opName )
    except ValueError:
      return S_ERROR( "Optimizer %s is not in the chain!" % opName )
    chainLength = len( opChain )
    if chainLength - 1 == opIndex:
      #This is the last optimizer in the chain!
      jobState.setState( self.am_getOption( 'WaitingStatus', 'Waiting' ),
                         self.am_getOption( 'WaitingMinorStatus', 'Pilot Agent Submission' ) )
      return S_OK()
    nextOp = opChain[ opIndex + 1 ]
    self.log.info( "Job %s: Set to Checking/%s" % ( jobState.jid, nextOp ) )
    return jobState.setStatus( "Checking", nextOp )


  def deserializeTask( self, taskStub ):
    return CachedJobState.deserialize( taskStub )

  def serializeTask( self, cjs ):
    return S_OK( cjs.serialize() )

#!/usr/bin/env python2.4
# $Header: /tmp/libdirac/tmp.stZoy15380/dirac/DIRAC3/DIRAC/Core/scripts/dirac-service.py,v 1.2 2007/05/03 18:59:48 acasajus Exp $
__RCSID__ = "$Id: dirac-service.py,v 1.2 2007/05/03 18:59:48 acasajus Exp $"

import sys
from dirac import DIRAC
from DIRAC.ConfigurationSystem.Client.UserConfiguration import UserConfiguration
from DIRAC.LoggingSystem.Client.Logger import gLogger
from DIRAC.Core.DISET.Server import Server

userConfiguration = UserConfiguration()

positionalArgs = userConfiguration.getPositionalArguments()
if len( positionalArgs ) == 0:
  gLogger.initialize( "NOT SPECIFIED", "/" )
  gLogger.fatal( "You must specify which server to run!" )
  sys.exit(1)

serverName = positionalArgs[0]
serverSection = userConfiguration.setServerSection( serverName )
userConfiguration.addMandatoryEntry( "Port" )
userConfiguration.addMandatoryEntry( "HandlerPath" )
userConfiguration.addMandatoryEntry( "/DIRAC/Setup" )
resultDict = userConfiguration.loadUserData()
if not resultDict[ 'OK' ]:
  sys.exit(1)


serverToLaunch = Server( serverName )
serverToLaunch.serve()

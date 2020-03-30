#!/usr/bin/env python

# This module creates a dBus tank 'repeater' for handling SeeLevel the NMEA2000 tank sensor system
# The Venus NMEA2000 dBus services assume only one tank (aka sensor aka fluid type) per external device
# so all tanks end up in the same dBus service resulting in each tank overwriting the others
# To avoid this, individual dBus "repeater' services for each tank are created
# data for each tank is extracted from the SeeLevel dBus service and published it to a separate repeater service
# 
# Currently the SeeLevel N2K sensor system supports from 1 to 3 tanks (1 = fresh, 2 = gray, 5 = black)
# This module handles all 6 tanks
# A /FluidType outside of the known range is ignored

# Displays should hide the NMEA2000 tank service because it will display constantly changing information

# Modifications to OverviewMobile.qml and TileTank.qml in the GUI are needed so the /Connected flag can modify the display
# and hide the N2K dBus object that combines tank data

# The service daemon insures this repeater module runs at startup and restarts it should it crash 
# To run this module, a link to the SeeLevelRepeater directory is created in the /service directory

# The Repeater services are created in the order in which data is received from SeeLevel
# The GUI must organize information in a predictable order that does not rely on SeeLevel data order

# A timeout mechanism control's the repeater's /Connected flag to indicate if the Repeater service is active or not
# when SeeLevel stops reporting data for a specific tank, it's /Connected flag will eventually be cleared by this timeout mechanism
# The GUI can then hide test /Connected to hide stale information from the Tanks column

# SeeLevel reports information for one tank about every 1-2 seconds even if no changes have occurred for that tank
# It cycles through active tanks so a complete update of all tanks is sent approximately every 3-4 seconds
# Note: SeeLevel can get into a mode where all tanks are sent very quickly, then no activity for ~ 3 seconds
# Polling for changes even as often as every 50 mS can miss SeeLevel messages, resulting in a no response error for a specific tank
# For this reason, a signal handler triggers processing of tank info based on a change to /FluidType
# SeeLevel sends /FluidType, /Level and /Capacity
# /FluidType is enumerated consistently with other Victron tanks
# /Level is in percentage (100 = full)
# /Level is used to report a sensor error, however the NMEA2000 tank driver truncates these values to 0-100%
# so there is no way to display a sensor error (such as an open in the wiring)
# The code assumes -1 is a generic error
# SeeLevel reports capacity in liters * 10 and the tank driver converts this to cubic meters used elsewhere in the Venus code
# so SeeLevel's capacity is passed on to the repeater services.
# /Remaining is calculated locally


import gobject
import platform
import argparse
import logging
import sys
import os
import dbus
import time

# add the path to our own packages for import
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from vedbus import VeDbusService

# SeeLevelServiceName is the name of the SeeLevel dBus service we need to separate
# the name is determined by examining the system once the SeeLevel N2K sensor system is attached
# NOTE: MUST BE SET MANUALLY IN THE CODE AFTER ACTUAL SERVICE NAME IS DETERMINED (use dbus-spy)

SeeLevelServiceName = 'com.victronenergy.tank.socketcan_can0_vi0_uc855'

# RepeaterServiceName is the name of the dBus service where data is sent
# instance number is filled in when the service is created

RepeaterServiceName = 'com.victronenergy.tank.Repeater%02d'
ProductName = 'SeeLevel Tank %d Repeater'

# timer periods and watchdog timeout are defined here for convenience

# If a repater service is not updated at least every 5 seconds
# it is marked as disconnected so the GUI can alert the user that
# the level should not be trusted

RepeaterTimeoutInSeconds = 5.0

# the update loop in the Repeater only manages timeouts so runs infrequently
RepeaterTimerPeriodInSeconds = 1.0

# the SeeLevel scan period is only used to detect presence of the SeeLevel dBus object
# actual processing of information from SeeLevel is done in a dBus signal handler

SeeLevelScanPeriodInSeconds = 1.0

SeeLevelScanPeriod = int (SeeLevelScanPeriodInSeconds * 1000)		# in timer ticks
RepeaterTimerPeriod = int (RepeaterTimerPeriodInSeconds * 1000)		# in timer ticks
RepeaterTimeout = int (RepeaterTimeoutInSeconds / RepeaterTimerPeriodInSeconds)	# in passes through update loop


# These methods permit creation of a separate connection for each Repeater
# overcoming the one service per process limitation
# requires updated vedbus -- see https://github.com/victronenergy/dbus-digitalinputs for new imports 

class SystemBus(dbus.bus.BusConnection):
	def __new__(cls):
		return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)

class SessionBus(dbus.bus.BusConnection):
	def __new__(cls):
		return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)

def dbusconnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()


# repeater bus services are created from this class
# one Repeater instance is created for each tank (aka fluid type)
# a corresponding dBus service is created when the Repeater is instantiated.

class Repeater:

    global RepeaterServiceName
    global ProductName
    global RepeaterTimeout
    global RepeaterTimerPeriod

    RepeaterService = None

    DbusBus = None
    ServiceName = ""

    Tank = 0
    TimeoutCount = 0


    def __init__(self, tank):

	self.Tank = tank
	self.RepeaterTimeout = RepeaterTimeout
	self.TimeoutCount = 0

# set up unique dBus connection
# The Repeater dBus service is not created until SeeLevel messages for that tank are received
	self.DbusBus = dbusconnection()

# gobject.timeout_add uses a 1 mS timer (1000 ticks per second)
# _update is called periodically with the following call

	gobject.timeout_add(RepeaterTimerPeriod, self._update)


# check watchdog -- mark service off line if it has timed out
# RepeaterService may not yet be set up yet if so don't attempt to mark it off line

    def _update(self):

	if self.TimeoutCount > self.RepeaterTimeout:
		if self.RepeaterService != None:
			self.RepeaterService['/Connected'] = 0
	else:
		self.TimeoutCount += 1

	return True


# process value change from external source
# actual value changes have already occurred 
# just update /Remaining and restart the watchdog

    def _handlechangedvalue(self, path, value):

	self.RepeaterService['/Remaining'] = self.RepeaterService['/Capacity'] * self.RepeaterService['/Level'] / 100

	self.TimeoutCount = 0;
        return True 


# create tank Repeater service

    def CreateDbusRepeaterService (self):

# create a unique service name that puts tanks in the desired order (see note at top of this module)
	self.ServiceName = RepeaterServiceName % self.Tank

# updated version of VeDbusService -- see https://github.com/victronenergy/dbus-digitalinputs for new imports
	self.RepeaterService = VeDbusService (self.ServiceName, bus = self.DbusBus)

# Create the objects

	self.RepeaterService.add_path ('/Mgmt/ProcessName', __file__)
	self.RepeaterService.add_path ('/Mgmt/ProcessVersion', '2.0')
        self.RepeaterService.add_path ('/Mgmt/Connection', 'dBus')

        self.RepeaterService.add_path ('/DeviceInstance', self.Tank)
        self.RepeaterService.add_path ('/ProductName', ProductName % self.Tank)
        self.RepeaterService.add_path ('/ProductId', 0)
        self.RepeaterService.add_path ('/FirmwareVersion', 0)
        self.RepeaterService.add_path ('/HardwareVersion', 0)
        self.RepeaterService.add_path ('/Serial', '')
# use numeric values (1/0) not True/False to make GUI display correct state
	self.RepeaterService.add_path ('/Connected', 0)
 
	self.RepeaterService.add_path ('/Level', 0, writeable = True, onchangecallback = self._handlechangedvalue)
	self.RepeaterService.add_path ('/FluidType', self.Tank, writeable = True, onchangecallback = self._handlechangedvalue)
	self.RepeaterService.add_path ('/Capacity', 0, writeable = True, onchangecallback = self._handlechangedvalue)
	self.RepeaterService.add_path ('/Remaining', 0, writeable = True, onchangecallback = self._handlechangedvalue)

	self.TimeoutCount = 0;

	return True


# method that is called from the SeeLevel loop to update repeater values
# the first call to this method creates the service for this Repeater instance
# preventing unnecessary dBus services from hanging around
# update repeater service only if values change

    def UpdateRepeater (self, level, capacity):

	if self.RepeaterService == None:
	    self.CreateDbusRepeaterService ()

	self.RepeaterService['/Level'] = level
	self.RepeaterService['/Capacity'] = capacity
	self.RepeaterService['/Remaining'] = capacity * level / 100
	self.RepeaterService['/Connected'] = 1

	self.TimeoutCount = 0;
	return True



# CheckSeeLevel is the main processing loop to extract SeeLevel information
# it collects and validates information from SeeLevel and forwards it to the tank repeater objects
# Data from SeeLevel is read as quickly as possible followed by a second read of the first parameter (tank number)
# if that second read matches the first, we assume the intermediate reads are valid
# if not, a second attemt to read all values is made followed by a third read of the tank number
# if the third read does not match the second, processing is skipped until the next pass
#
# this method runs even if a SeeLevel sensor system isn't attached to Venus. In this case, the SeeLevel service won't exist
# Read attempts to that service will generate an exception which is trapped here to skip processing.
#
# This method runs frequently to avoid missed tanks, however normally, the same tank persists through multiple passes
# to avoid excessive CPU load, tank information is only processed once per second
#
# persistent storage for SeeLevel data are created
# so objects don't have to be fetched each time this process runs

SeeLevelTankObject = None
SeeLevelFluidLevelObject = None
SeeLevelCapacityObject = None
LastTank = 0

# this is the dBus bus (system in this case)
TheBus = None

# RepeaterList provides persistent storage for a repeater instance so that it may be called from CheckSeeLevel 
# This list is indexed by fluid type and needs to be expanded if additional fluid types are added in the future

RepeaterList =  [None,  None, None, None, None, None ]

# check to see if SeeLevel dBus object exists
# innitialize object pointers if so
# invalidate object pointers if not

def CheckForSeeLevel():

	global SeeLevelServiceName		# defined at top of the module for ease of maintanence

	global SeeLevelTankObject
	global SeeLevelFluidLevelObject
	global SeeLevelCapacityObject

	global RepeaterList
	global LastTank
	global TheBus

	try:
		if SeeLevelTankObject == None:
			SeeLevelTankObject = TheBus.get_object(SeeLevelServiceName, '/FluidType')
			SeeLevelFluidLevelObject = TheBus.get_object(SeeLevelServiceName, '/Level')
			SeeLevelCapacityObject = TheBus.get_object (SeeLevelServiceName, '/Capacity')
	
	except dbus.DBusException:
		SeeLevelTankObject = None
		SeeLevelFluidLevelObject = None
		SeeLevelCapacityObject = None
		LastTank = 0

	return True

# main () registers this as the dBus signal handler for /FluidType changes
# the only one that should be occurring is SeeLevel

# read fluid level and capacity using GetValue()
# read fluid type using GetValue() and check for a match with the one passed to the signal handler
# pass the tank infomation to the repeater object if these two values match
# silently reject the information if not
# rejecting based on tank mismatch should prevent other objects reporting /FluidType changes from
# messing up processing
 
def FluidTypeHandler (changes):
	tank = int (changes.get ("Value"))
    
# ignore signals until we have detected the SeeLevel dBus object and set up property pointers
	if SeeLevelTankObject == None:
		return

# quickly grab a set of values
# range check tank to avoid out of bounds indexing
	if tank < 0 or tank >= len(RepeaterList):
		logging.info ("tank %d out of range", tank)
		return
		
	level = SeeLevelFluidLevelObject.GetValue()
	capacity = SeeLevelCapacityObject.GetValue ()
	tank2 = SeeLevelTankObject.GetValue()

# if not on the same tank, skip processing
	if tank != tank2:
		logging.info ("tank mismatch %d from signal %d from object read", tank, tank2)
		return

# if no repeater service for this tank yet, create it first
	if RepeaterList [tank] == None:
		RepeaterList [tank] = Repeater (tank)

# forward SeeLevel values to the repeater
	RepeaterList [tank].UpdateRepeater (level, capacity)
	return



def main():

	from dbus.mainloop.glib import DBusGMainLoop

	global TheBus
     
# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)

# install a signal handler for /FluidType
# it is hoped the only object reporting changes will be the SeeLevel object
	TheBus = dbus.SystemBus()
	TheBus.add_signal_receiver (FluidTypeHandler, path = "/FluidType",
                dbus_interface='com.victronenergy.BusItem', signal_name='PropertiesChanged')

# periodically look for SeeLevel service to innitialize pointers
	gobject.timeout_add(SeeLevelScanPeriod, CheckForSeeLevel)

	mainloop = gobject.MainLoop()
	mainloop.run()

# Always run our main loop so we can process updates
main()

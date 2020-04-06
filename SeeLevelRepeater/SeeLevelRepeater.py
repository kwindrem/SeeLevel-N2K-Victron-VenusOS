#!/usr/bin/env python

# This module creates a dBus tank 'repeater' for handling SeeLevel the NMEA2000 tank sensor system
# The Venus NMEA2000 dBus services assume only one tank (aka sensor aka fluid type) per external device
# so all SeeLevel tanks end up in the same dBus service resulting in each tank overwriting the others
# To avoid this, individual dBus "repeater' services for each tank are created
# data for each tank is extracted from the SeeLevel dBus service and published to a separate repeater service
# 
# This module handles all 6 defined tanks. The SeeLevel N2K sensor system supports 
# at most 3 tanks (1 = fresh, 2 = gray, 5 = black)

# Modifications to OverviewMobile.qml and TileTank.qml in the GUI are needed to hide the SeeLevel dBus object that rotates between tank data
# GUI modifications have also been made to alert the operatorto loss of communciaitons with SeeLevel tank

# The service daemon insures this repeater module runs at startup and restarts it should it crash 
# To run this module, a link to the SeeLevelRepeater directory is created in the /service directory

# The Repeater services are created only after data is received from SeeLevel for the related tank
# to minimize GUI clutter

# A timeout mechanism control's the repeater's /Connected flag to indicate if the Repeater service is active or not
# when SeeLevel stops reporting data for a specific tank, it's /Connected flag will eventually be cleared by this timeout mechanism
# The GUI can then test /Connected to hide stale information from the Tanks column

# SeeLevel sends /FluidType, /Level and /Capacity
# /FluidType is enumerated consistently with other Victron tanks
# /Level is in percentage (100 = full)
# /Level is used to report a sensor error, however the NMEA2000 tank driver truncates these values to 0-100%
# so there is no way to display a sensor error (such as an open in the wiring)
# SeeLevel reports capacity in liters * 10 and the tank driver converts this to cubic meters used elsewhere in the Venus code
# /Remaining is calculated locally

# SeeLevel reports information for all tanks about every 3-4 seconds
# However, it can get into a mode where info for all tanks is sent very quickly, then no activity for ~ 3 seconds
# Polling for changes can miss data for a specific tank which makes it appear that the tank is not being reported (timeout)
# For this reason, signal handlers for /FluidType and /Level PropertiesChanged are used to collect tank info
# But this also is tricky since a signal for a level change may not be issued for every tank.
# For example, if all tanks are empty, the level signal handler is never called! The same would be true for /FluidLevel if there was only one tank.
# The signal handlers for /FluidType and /Level store the values received, but processing is deferred for later when the chance is best that they represent
# a stable type/level pair. Since /FluidType changes with every new message from SeeLevel, that signal is used as the trigger for processing the LAST known values.
# A background polling task also collects information in the absence of signals but as mentioned above, polling alone can't capture all the data.
# /Capacity changes infrequently, so it is handled in the polling task only (no signal handler).
# The signal handlers are called from another thread/process so the amount of time spent in these routines is kept to a minimum.

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

# If a repater service is not updated at least every 8 seconds
# (approximately twice the SeeLevel reporting period)
# it is marked as disconnected so the GUI can alert the user that
# the level should not be trusted

RepeaterTimeoutInSeconds = 4.0 #############################

# the update loop in the Repeater only manages timeouts so runs infrequently
RepeaterTimerPeriodInSeconds = 1.0

# This period defines how often the SeeLevel dBus object is checked
# for existence and to pull /Capacity values for each tank
# 1 second is frequent enough for these tasks 

SeeLevelScanPeriodInSeconds = 1.0

SeeLevelScanPeriod = int (SeeLevelScanPeriodInSeconds * 1000)		# in timer ticks
RepeaterTimerPeriod = int (RepeaterTimerPeriodInSeconds * 1000)		# in timer ticks
RepeaterTimeout = int (RepeaterTimeoutInSeconds / RepeaterTimerPeriodInSeconds)	# in passes through update loop


# These methods permit creation of a separate connection for each Repeater
# overcoming the one service per process limitation
# requires updated vedbus, originally obtained from https://github.com/victronenergy/dbus-digitalinputs
# updates are incorporated in the ext directory of this package

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
# log message only once
		if self.RepeaterService != None and self.RepeaterService['/Connected'] == 1:
			self.RepeaterService['/Connected'] = 0
			logging.warning ("Tank %d is NOT responding", self.Tank)
	else:
		self.TimeoutCount += 1

	return True


# process value change from external source
# actual value changes have already occurred 
# just update /Remaining and restart the watchdog

    def _resetWatchdog (self):
	if self.RepeaterService['/Connected'] == 0:
		self.RepeaterService['/Connected'] = 1
		logging.info ("Tank %d is responding", self.Tank)
	self.TimeoutCount = 0;

	return

    def _updateRemaining (self):
	self.RepeaterService['/Remaining'] = self.RepeaterService['/Capacity'] * self.RepeaterService['/Level'] / 100
	return True

    def _handlechangedvalue(self, path, value):

	self._updateRemaining ()
	self._resetWatchdog()
        return True 


# create tank Repeater service if it doesn't yet exist

    def _createDbusRepeaterService (self):

	if self.RepeaterService != None:
		return True

# create a unique service name that puts tanks in the desired order (see note at top of this module)
	self.ServiceName = RepeaterServiceName % self.Tank

# updated version of VeDbusService (in ext directory) -- see https://github.com/victronenergy/dbus-digitalinputs for new imports
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
# use numeric values (1/0) not True/False for /Connected to make GUI display correct state
	self.RepeaterService.add_path ('/Connected', 0)
 
	self.RepeaterService.add_path ('/Level', 0, writeable = True, onchangecallback = self._handlechangedvalue)
	self.RepeaterService.add_path ('/FluidType', self.Tank, writeable = True, onchangecallback = self._handlechangedvalue)
	self.RepeaterService.add_path ('/Capacity', 0, writeable = True, onchangecallback = self._handlechangedvalue)
	self.RepeaterService.add_path ('/Remaining', 0, writeable = True, onchangecallback = self._handlechangedvalue)

	self.TimeoutCount = 0;

	return True

# methods called from the SeeLevel processing to update repeater values
# the first call to any of these methods creates the service for this Repeater instance
# preventing unnecessary dBus services from hanging around

    def UpdateRepeater (self, level, capacity):

	self._createDbusRepeaterService ()

	self.RepeaterService['/Level'] = level
	self.RepeaterService['/Capacity'] = capacity

	self._updateRemaining ()
	self._resetWatchdog()
	return True
 
    def UpdateLevel (self, level):

	self._createDbusRepeaterService ()

	if level != -99:
		self.RepeaterService['/Level'] = level
		self._updateRemaining ()
		self._resetWatchdog()
	return True

    def UpdateCapacity (self, capacity):

	self._createDbusRepeaterService ()

	if capacity != -99:
		self.RepeaterService['/Capacity'] = capacity
		self._updateRemaining ()
		self._resetWatchdog()
	return True
 


# CheckSeeLevel is the polling loop to extract SeeLevel information
# it collects and validates information from SeeLevel and forwards it to the tank repeater objects if for whatever reason
# the signal handlers are not called. This would be the case if there is only one tank, or level doesn't change between messages.
# Data from SeeLevel is read as quickly as possible followed by a second read of the first parameter (tank number)
# if that second read matches the first, we assume the intermediate reads are valid
#
# this method runs even if a SeeLevel sensor system isn't attached to Venus. In this case, the SeeLevel service won't exist
# Read attempts to that service will generate an exception which is trapped here to skip processing.
# note also that if the GUI isn't running or crashes, the SeeLevel dBus object goes away
#
# This method runs once per second to manage SeeLevel service object pointers and to read /Capacity
# The SeeLevel service can switch to a different tank quickly and this polling loop will miss some tanks
# /FluidType  and /Level signal handlers (below) are used for updates to minimize the chance of a missed tank
# Only /Level is processed in the signal handler for speed.
# FluidTLevelHandler will not be called when SeeLevel switches to a new tank if it has the same level as the previous tank
# Values from the two handlers (tank and level) are saved in persistent storage so they can be processed together at the next /FluidType change
#
# persistent storage for SeeLevel data are created
# so objects don't have to be fetched each time this process runs
# GetValue() calls using these pointers sometimes fail for some reason and cause dBus exceptions
# the exception is trapped and the pointers are reinitialized

SeeLevelTankObject = None
SeeLevelFluidLevelObject = None
SeeLevelCapacityObject = None
SeeLevelUniqueName = ""
LastTank = -99
LastLevel = -99
TankNeedsRepeater = -99
InitNeeded = True
StuckLevelCount = 0

# this is the dBus bus (system in this case)
TheBus = None

# RepeaterList provides persistent storage for a repeater instance so that it may be called from CheckSeeLevel 
# This list is indexed by fluid type and needs to be expanded if additional fluid types are added in the future

RepeaterList =  [None,  None, None, None, None, None ]

# check to see if SeeLevel dBus object exists
# innitialize object pointers if so
# invalidate object pointers if not


def CheckSeeLevel():

	global SeeLevelServiceName		# defined at top of the module for ease of maintanence

	global SeeLevelTankObject
	global SeeLevelFluidLevelObject
	global SeeLevelCapacityObject
	global SeeLevelUniqueName

	global RepeaterList
	global LastTank
	global LastLevel
	global TheBus
	global SeeLevelUniqueName
	global TankNeedsRepeater
	global InitNeeded
	global StuckLevelCount

	try:
# innitialize object pointers if not done already
# dbus exceptions will occur if SeeLevel object doesn't exist (normal)
# or if the GUI isn't running (a bug?)
		if InitNeeded:
			SeeLevelTankObject = TheBus.get_object(SeeLevelServiceName, '/FluidType')
			SeeLevelFluidLevelObject = TheBus.get_object(SeeLevelServiceName, '/Level')
			SeeLevelCapacityObject = TheBus.get_object (SeeLevelServiceName, '/Capacity')
			SeeLevelUniqueName = TheBus.get_name_owner(SeeLevelServiceName)
			logging.info ("SeeLevel dBus connection setup/restored") 
			InitNeeded = False
	
# do a background update to the associated repeater
# signal handlers are the primary update for level unless there is only one tank
# but this is the ONLY update for capacity
		tank = SeeLevelTankObject.GetValue()
		level = SeeLevelFluidLevelObject.GetValue()
		capacity = SeeLevelCapacityObject.GetValue ()
		tank2 = SeeLevelTankObject.GetValue()

# range check tank before using it as an array index
		if tank >= 0 and tank < len(RepeaterList):

# if no repeater service for this tank yet, create it
			if RepeaterList [tank] == None:
				RepeaterList [tank] = Repeater (tank)

# update the repeater's level and capacity values from the poll
			if tank == tank2:
				RepeaterList [tank].UpdateRepeater (level, capacity)

# if level change signals are not being received but tank number signals ARE being received
# the level of all tanks is probalby the same, so jam a polled value into LastLevel
# wait 10 passes before jaming value to give signals a chance to be received
				if (LastLevel == -99 and LastTank != -99):
					StuckLevelCount += 1					
					if StuckLevelCount >= 10:
						LastLevel = level
						logging.info ("No /Level signals have been received - setting LastLevel from polled data") 
				else:
					StuckLevelCount = 0

	except dbus.DBusException:
		if InitNeeded == False:
			logging.warning ("dBus exception after SeeLevel had previously been resonding") 
			LastTank = -99
			StuckLevelCount = 0
			InitNeeded = True

# Create a repeater service for a tank received via a signal
	if (TankNeedsRepeater != -99):
		if RepeaterList [TankNeedsRepeater] == None:
			RepeaterList [TankNeedsRepeater] = Repeater (TankNeedsRepeater)
		TankNeeedsRepeater = -99
	return True


# signal handlers

def FluidTypeHandler (changes, sender):

	global SeeLevelUniqueName
	global LastTank
	global LastLevel
	global TankNeedsRepeater

# ignore signal if it's not from the SeeLevel service
	if sender != SeeLevelUniqueName:
		return

# Update the repeater based on last tank and level before saving the new tank value
# (level values may not change between tanks)
# range check tank and level before processing
# wait until CheckSeeLevel has actually created the reperter service
	if LastTank >= 0 and LastTank < len(RepeaterList):
		if RepeaterList [LastTank] != None:
			RepeaterList [LastTank].UpdateLevel (LastLevel)
		else:
# ask CheckSeeLevel to crate a repeater for this tank
# this is not done in-line to save time in the handler
			if TankNeedsRepeater == -99:
				TankNeedsRepeater = LastTank

# save new fluid type for processing on next call to this handler
	LastTank = int (changes.get ("Value"))

	return


def FluidLevelHandler (changes, sender):

	global SeeLevelUniqueName
	global LastLevel

# ignore signal if it's not from the SeeLevel service
	if sender != SeeLevelUniqueName:
		return

# save fluid level for processing during next call of FluidTypeHandler
	LastLevel = int (changes.get ("Value"))

	return



def main():

	from dbus.mainloop.glib import DBusGMainLoop

	global TheBus

# set logging level to include info level entries
	logging.basicConfig(level=logging.INFO)

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)

        logging.info (">>>>>>>>>>>>>>>> SeeLevel Repeater Starging <<<<<<<<<<<<<<<<")

# install a signal handler for /FluidType and /Level
	TheBus = dbus.SystemBus()
	TheBus.add_signal_receiver (FluidTypeHandler, path = "/FluidType",
                dbus_interface='com.victronenergy.BusItem', signal_name='PropertiesChanged',
		sender_keyword="sender")
	TheBus.add_signal_receiver (FluidLevelHandler, path = "/Level",
                dbus_interface='com.victronenergy.BusItem', signal_name='PropertiesChanged',
		sender_keyword="sender")

# periodically look for SeeLevel service
	gobject.timeout_add(SeeLevelScanPeriod, CheckSeeLevel)

	mainloop = gobject.MainLoop()
	mainloop.run()

# Always run our main loop so we can process updates
main()

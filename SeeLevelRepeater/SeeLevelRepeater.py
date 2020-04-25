#!/usr/bin/env python

# This module creates a dBus tank 'repeater' for handling SeeLevel the NMEA2000 tank sensor system
# While written for the SeeLevel system, it may work for other CanBus sensors.
# The Venus NMEA2000 dBus services assume only one tank (aka sensor aka fluid type) per external device
# so all SeeLevel tanks end up in the same dBus service resulting in each tank overwriting the others
# To avoid this, individual dBus "repeater' services for each tank are created
# data for each tank is extracted from the SeeLevel dBus service and published to a separate repeater service
# 
# This module handles all 6 defined tanks. 
# The SeeLevel N2K sensor system supports at most 3 tanks (1 = fresh, 2 = gray, 5 = black)
# Other N2K systems may report more and this repeater should be able to handle them as long as
# the tank number is unique

# Modifications to OverviewMobile.qml in the GUI arr needed to hide the SeeLevel dBus object that rotates between tank data
# Modificaitons to TileTank.qml have also been made to:
#  alert the operatortor of loss of communciaitons with SeeLevel tank
#  display custom tank names
#  remove flashing and add error messages, replacing the tank fullness percentage
#  squeeze the tile height when necessary to fit more tanks into the available space

# The service daemon insures this repeater module runs at startup and restarts it should it crash 
# To run this module, a link to the SeeLevelRepeater directory is created in the /service directory

# The Repeater dBus services are created only after data is received from SeeLevel for the related tank
# to GUI clutter

# A timeout mechanism control's the repeater's /Connected flag to indicate if the Repeater service is active or not
# when SeeLevel stops reporting data for a specific tank, The repeater's /Connected flag will eventually be cleared by this timeout mechanism
# The GUI (TileTank) then tests /Connected to hide report "No Response" in the Tanks column

# SeeLevel sends /FluidType, /Level and /Capacity
# /FluidType is enumerated consistently with other Victron tanks
# /Level is in percentage (100 = full)
# /Level is used to report a sensor error, however the Venus NMEA2000 tank driver limits these values to 0-100%
# so there is no way to display a sensor error (such as an open in the wiring)
# SeeLevel reports capacity in liters * 10 and the tank driver converts this to cubic meters used elsewhere in the Venus code
# /Remaining is calculated in the Repeater

# SeeLevel reports information for all tanks about every 3-4 seconds
# However, it can get into a mode where info for all tanks is sent very quickly, then no activity for ~ 3 seconds
# Polling for changes can miss data for a specific tank which makes it appear that the tank is not being reported (timeout)
# For this reason, PropertiesChanged signal handlers for /FluidType and /Level are used to collect tank info
# But this also is tricky since a signal for a level change may not be issued for every tank.
# For example, if all tanks are empty, the level signal handler is never called! 
# The same would be true for /FluidLevel if there was only one tank.
# The signal handlers for /FluidType and /Level store the values received,
# but processing is deferred for later when the chance is best that they represent a stable type/level pair.
# Since /FluidType changes with every new message from SeeLevel, 
# that signal is used as the trigger for processing the LAST known /FluidType and /Level values.
# A background task performe the actual dBus service updates and also collects information in the absence of signals.
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
from settingsdevice import SettingsDevice

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

RepeaterTimeoutInSeconds = 8.0

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

    DbusService = None
    StartupDelay = True

    DbusBus = None
    ServiceName = ""

# local tank values
# the dBus service is not created until messages are received
# so the SeeLevel signal handler and background loop set these,
# triggering service cration in the repeater's background loop
# repeater background loop then updates the dBus values

    Tank = 0
    Level = 0
    Capacity = 0
    UpdateReceived = False

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


# flag value change from external source

    def _handlechangedvalue (self, path, value):

	self.UpdateReceived = True
        return True 


# create tank Repeater service

    def _createDbusService (self):

# create a unique service name that puts tanks in the desired order (see note at top of this module)
	self.ServiceName = RepeaterServiceName % self.Tank

# updated version of VeDbusService (in ext directory) -- see https://github.com/victronenergy/dbus-digitalinputs for new imports
	self.DbusService = VeDbusService (self.ServiceName, bus = self.DbusBus)

# make custom name non-volatile
        settingsPath = '/Settings/Devices/TankRepeater%d' % self.Tank

        SETTINGS = { 'customname': [settingsPath + '/CustomName', '', 0, 0] }

        self.settings = SettingsDevice(self.DbusBus, SETTINGS, self.setting_changed)

# Create the objects

	self.DbusService.add_path ('/Mgmt/ProcessName', __file__)
	self.DbusService.add_path ('/Mgmt/ProcessVersion', '2.0')
        self.DbusService.add_path ('/Mgmt/Connection', 'dBus')

        self.DbusService.add_path ('/DeviceInstance', self.Tank)
        self.DbusService.add_path ('/ProductName', ProductName % self.Tank)
        self.DbusService.add_path ('/ProductId', 0)
        self.DbusService.add_path ('/FirmwareVersion', 0)
        self.DbusService.add_path ('/HardwareVersion', 0)
        self.DbusService.add_path ('/Serial', '')
# use numeric values (1/0) not True/False for /Connected to make GUI display correct state
	self.DbusService.add_path ('/Connected', 0)
 
	self.DbusService.add_path ('/Level', 0, writeable = True, onchangecallback = self._handlechangedvalue)
	self.DbusService.add_path ('/FluidType', self.Tank, writeable = True, onchangecallback = self._handlechangedvalue)
	self.DbusService.add_path ('/Capacity', 0, writeable = True, onchangecallback = self._handlechangedvalue)
	self.DbusService.add_path ('/Remaining', 0, writeable = True, onchangecallback = self._handlechangedvalue)

	self.DbusService.add_path ('/CustomName', self.get_customname(), writeable = True, onchangecallback = self.customname_changed)

	self.TimeoutCount = 0;
	self.StartupDelay = True

	return


    def get_customname(self):
        return self.settings['customname']
            
    def set_customname (self, val):
	self.settings['customname'] = val

    def setting_changed (self, name, old, new):
        if name == 'customname':
	    self.DbusService['/CustomName'] = new
	return

    def customname_changed (self, path, val):
        self.set_customname (val)
        return True


# do background processing for this repeater
# SeeLevel updates Repeater local variables
# those values are passed to the dBus service as a background operation here
# the dBus service is created here when the first update for this tank is received
# the /Connected flag is managed here: True if updates are being received,
# False if no updates have been received in the timeout period

    def _update(self):

# update has been received - create dBus service if not done previously
# then update dBus values from local storage
	if self.UpdateReceived:
		if self.DbusService == None:
			self._createDbusService ()
# do nothing this pass if just created dBus service
# update flag isn't cleared so the update is processed next pass
			return True

# update servcie values from local storage
		self.DbusService['/Level'] = self.Level
		self.DbusService['/Capacity'] = self.Capacity
		self.DbusService['/Remaining'] = self.Capacity * self.Level / 100
		self.UpdateReceived = False
		self.TimeoutCount = 0

# skip timeout processing if dBus service does not exist
	if self.DbusService == None:
		return True

# update connected flag
	if self.TimeoutCount == 0:
		if self.DbusService['/Connected'] == 0:
			self.DbusService['/Connected'] = 1
			logging.info ("Tank %d is responding", self.Tank)

	if self.TimeoutCount > self.RepeaterTimeout:
		if self.DbusService['/Connected'] == 1:
			self.DbusService['/Connected'] = 0
			logging.warning ("Tank %d is NOT responding", self.Tank)
	else:
		self.TimeoutCount += 1

	return True


# methods called from the SeeLevel processing to update repeater values

    def UpdateRepeater (self, level, capacity):

	self.Level = level
	self.Capacity = capacity
	self.UpdateReceived = True
	return True
 
    def UpdateLevel (self, level):

	if level != -99:
		self.Level = level
		self.UpdateReceived = True
	return True

    def UpdateCapacity (self, capacity):

	if capacity != -99:
		self.Capacity = capacity
		self.UpdateReceived = True
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
# GetValue() calls using these pointers fails if the SeeLevel messages aren't being received or processed
# The CanBus processing is tied to the GUI process so if the GUI process dies, SeeLevel messages will not be received.
# When the SeeLevel dBus service is again present, the connection to it is reset and tank info forwarding continues
# During this time, a no response error will be displayed.

SeeLevelTankObject = None
SeeLevelFluidLevelObject = None
SeeLevelCapacityObject = None
SeeLevelUniqueName = ""
LastTank = -99
LastLevel = -99
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
	global InitNeeded
	global StuckLevelCount

	tank = -99
	tank2 = -999
	level = -99
	capacity = -99

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

	except dbus.DBusException:
		if InitNeeded == False:
			logging.warning ("No response from SeeLevel after it had been resonding") 
			LastTank = -99
			StuckLevelCount = 0
			InitNeeded = True


# update the repeater's level and capacity values from the poll
# range check tank before using it as an array index
	if tank >= 0 and tank < len(RepeaterList) and tank == tank2:
		RepeaterList [tank].UpdateRepeater (level, capacity)

# if level change signals are not being received but tank number signals ARE being received
# the level of all tanks is probalby the same, so jam a polled value into LastLevel
# wait 10 passes before jaming value to give signals a chance to be received
	if (LastLevel == -99 and LastTank != -99 and level != -99):
		StuckLevelCount += 1					
		if StuckLevelCount >= 10:
			LastLevel = level
			logging.info ("No /Level signals have been received - setting LastLevel from polled data") 
	else:
		StuckLevelCount = 0

	return True


# signal handlers

def FluidTypeHandler (changes, sender):

	global SeeLevelUniqueName
	global LastTank
	global LastLevel

# ignore signal if it's not from the SeeLevel service
	if sender != SeeLevelUniqueName:
		return

	tank = int (changes.get ("Value"))

# Update the repeater based on PREVIOUS tank and level before saving the new tank value
# (level values may not change between tanks)
# range check tank and level before processing
# wait until CheckSeeLevel has actually created the reperter service
	if LastTank >= 0 and LastTank < len(RepeaterList) and LastLevel != -99 and RepeaterList [LastTank] != None:
		RepeaterList [LastTank].UpdateLevel (LastLevel)

# save new fluid type for processing on next call to this handler
	LastTank = tank

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

        logging.info (">>>>>>>>>>>>>>>> SeeLevel Repeater Starting <<<<<<<<<<<<<<<<")

# create repeaters for all tanks
# dBus services are NOT created at this time to save GUI clutter
	for tank in range (len(RepeaterList)):
		RepeaterList [tank] = Repeater (tank)


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

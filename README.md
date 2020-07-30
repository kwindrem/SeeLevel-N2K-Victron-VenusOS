This software will allow the SeeLevel NMEA2000 tank sensor system to be used with
Victron Energy Venus devices (Color Control GX, Venus Gx, etc.).
Functionality has been verified on Venus version 2.33, 2.42, 2.52, 2.54 and 2.60 release candidates through ~37. Recent changes made setup independent of version so it is likely the GUI changes will work with many more system versions.

Setup:

You will need root access to the Venus device. Instructions can be found here:
https://www.victronenergy.com/live/ccgx:root_access
The root password needs to be reentered following a Venus update.
Setting up an authorization key (see documentation referenced above) will save time and avoid having to reset the root password after each update.

A setup script is provided that runs on either the host or on the Venus device. It supports the following actions:
    Activate installs GUI modificaitons then starts the repeater
    Deactivate stops the repeater, leaving GUI modifications in place
    Uninstall deactivates the repeater, restors GUI to stock and removes all repeater files
    Reinstall installs previously installed GUI modifications and starts the repeater
        Reinstall is used by boot code to reactivate the repeater following a Venus software update
        It can also be choosen manually to bypass the GUI prompts after deactivating the repeater

Additional functionality is provided when running from the host:
    Install copies files to the Venus device then Activates the repeater
    Copy just copise the files without furter actions

Installing from a non-unix host requires some additional steps since the setup script won't run there.
I suggest that the GitHub repository be downloaded as a zip file and copied to the Venus target.
From there, it can be unzipped and the entire directory structure moved to /data/TankRepeater.
Then, cd to that directory and run ./setup. This will help the install run smoothly.

You have the choice of installing an OPTIONAL enhanced Mobile Overview page. Enhancements:

1) Tiles are arranged to more cloesly follow the power flow through the system.
2) Voltage, current and frequency values are added to the AC in and out tiles.
3) Battery remaining time is added to the Battery tile
4) ESS reason codes are replaced with a text version to make them more meaningful
5) ESS reason text and other notifications are combined into a single "marquee" line
6) The pump switch is hidden unless the Venus relay is configured for pump control. The extra space is available for tanks
7) AC Mode switch includes INVERTER ONLY mode

You also have the choice to install an OPTIONAL enhanced Tank Tile. Enhancements:

1) Tank information is displayed in a box sized so that 3 of them fill the column. More tanks require smaller boxes. The changes made permit up to 6 tanks to be displayed comfortably. The box size is adjusted so that all tanks fill the tanks column. In the event more than 6 tanks are found in the system, the display will bunch up and may not be readable.
2) The tank bar graph turns red when the tank is within 20% of full (for waste and black tanks) and 20% of empty for other tanks. This provides a visual alert to a situation that needs attention soon. In addition, tanks that are very close to empty show now bar so the red warning could easily be missed. In this case, the bar graph's text indicting tank fullness also turns red.
3) The GUI reports errors for tank sensors as follows":
  If a tank is not responding "NO RESPONSE" will replace level percentage
  Garnet says they report sensor errors with out of range tank levels, however the CAN-bus driver in Venus OS apparently
  truncates these values. There is code to display sensor errors (short, open, etc.) however I never saw any < 0 or > 100/
4) Previous implementation of the TANKS display blinked some information. The blinking has been removed.
5) Displays custom tank names

The repeater will work with the stock tank tile, or the modified tank tile will work without the Repeater.

Deactivating will shut down the Repeater and unhide the SeeLevel tank, but leave other GUI modifications in place.
Uninstalling will return the Venus Device to it's stock configuration.

A setup option is also provided to display the Repeater log without making any changes. After displaying the log, setup returns to the action selection.
setup again following the update to reactivate the Repeater. Choose the Activate action.

The GUI on the Venus device will be restarted at the end of setup.


Setup command line interface:

setup has a command line interface that allows bypassing some or all of the user prompts.

Each parameter is optional and may occur in any order.
A missing parameter results in a user prompt for it's value.
The complete set is:

./setup [ip venusIp] [action] [eo y|n] [et y\n] [dl y|n]

ip provides the IP address of the veus device
This opiton is only meaningful if setup is running on the host.

action is one of the following:
    install or in or i (host only)
    copy or c (host only)
    activate or a
    reactivate or r
    deactivate or d
    uninstall or u
    log or l
    quit or q

eo specifies whether the enhanced mobile overview or modified mobile overview is installed during activation

et specifies whether the enhanced tank tile will be installed - if not the stock tank tile will be used

dl specifies wheter to delete delete the logs

The above three parameters require a y or n after them

Examples:

./setup ip 192.168.3.162 activate eo y et y dl n

activates the repeater on 192.168.3.162, installing the enhanced overview and tank tiles, preserving logs

./setup uninstall dl y

deactivates the repeater, restoring GUI to stock and removing repeater files

./setup ip 192.168.3.162 log

displays the last 100 lines of the repeater log from Venus device at 192.168.3.162

Configuration:

The program attempts to discover the SeeLevel service name by looking for a com.victronenergy.tank service with a ProductId of 41312.
If this is the proper ProductId, no configuration is necessary and the Mobile Overview screen should populate with the repeater tanks. If not, the default ProductId may need to be changed. (Other CanBus tank systems would have a different ProductId.)
The ProductId can be changed using dbus-spy after the repeater is running. (Before the repeater has run the first time, the settings parameter will not exist.)

To determine the correct ProductId, run dbus-spy on the Venus device and look for the SeeLevel service.
It will be something like: com.victronenergy.tank.socketcan_can0_di0_uc855
Inspect that service and make note of the ProductId.
If you need to change the ProductId, return to the main dbus-spy page and access the com.victronenergy.settings service
Change /Settings/Devices/TankRepeater/SeeLevelProductId.
(When the correct ProductId has been entered, the value of /Settings/Devices/TankRepeater/SeeLevelService should change to match the SeeLevel service.)

You may need to exit the Mobile Overview screen, then come back to it in order for the tanks column to populate properly.

The repeater can be disabled by setting /Settings/Devices/TankRepeater/SeeLevelProductId to -1. The repeater will still run but is completely benign in that state, including unhiding the SeeLevel tank tile that constanly switches tanks.

Activation saves the GUI selections (via flag files /data/TankRepeater/useEnhanced...) for later reactivation. Reactivation can be done manually by choosing it from the menu or on the command line, OR it will run automatically when Venus software is updated. When the repeater is activated, it creates a flag file (/data/TankRepeater/reactivate) that is tested by /data/rc.local to decide if reactivation should be attempted.

/data/rc.local is called during boot to facilitate actions such as reinstalling this repeater.


File organization:

The Repeater files are stored in /data/TankRepeater on Venus because the /data file system survives a software update (most other file systems are overwritten).

All folders and files in this GitHub should be copied to a unix host computer with access to the Venus device. The file hierarchy must be preserved.

One GUI file (OverviewMobile.qml) is modified or (replaced during setup if the Enhanced Overview is selected).
One file (TileTank.qml) is optionally replaced during setup.
The original files are moved to files ending in .orig for easy uninstall in the future.
The enhanced Mobile Overview page installs a new file to display ESS reason codes as text: SystemReasonMessage.qml

rc.SeeLevel is used to create/modify /data/rc.local for automatic reactivation following a Venus software update. rc.SeeLevel is copied to /data/rc.local if that file doesn't exist. If it does not exist, the contents of rc.SeeLevel following the intro are appended to /data/rc.local. 

useEnhancedOverview, useEnhancedTankTile and reactivate are flag files to control reactivation.


Background/operation:

Venus software only supports one tank per CAN-bus device and SeeLevel reports up to 3 tanks on the same connection. The result is a constantly changing display as data. That is, the same tank tile would show fresh water status for a couple of seconds, then waste water then black water, etc. A stable display with separate tiles for each tank is necessary.

In order to provide a set of stable tank displays, the user interface (aka GUI) must be modified to hide the actual SeeLevel information.  A Repeater process monitors the SeeLevel dBus service and "repeats" stable information to separate dBus services, one for each tank.

When SeeLevel reports information for a specific tank, SeeLevelRepeater updates the Repeater's values with the latest from SeeLevel. The GUI displays only the Repeated tank information.

To avoid screen clutter, the Repeater holds off creating dBus Repeater services until it detects tank information from SeeLevel. SeeLevel may report 1, 2 or 3 tanks so we only want to populate the TANKs column in the GUI with valid tanks. A tank that disappears while the system is running is displayed in the TANKs column as "NO RESPONSE". If the Venus device is reset, tanks that are no longer responding will not reappear. When the SeeLevel system is being set up, the installer should disable messaging for any tanks that don't exist, then reboot the Venus device. Refer to Garnet's documentation for the NEMA2000 version of their sensor which describes how to disable specific tanks.

Innitially, I was told that SeeLevel reports one tank approximately every 1-2 seconds. A complete scan of all tanks takes up to 3-8 seconds. However I discovered tanks can be reported much more rapidly. Too fast actually for my original design, so it's been rewritten to use a dBus signal handler to process each tank (aka /FluidType), /Level and /Capacity update from the SeeLevel dBus object.

While not tested with other tank sensors, SeeLevelRepeater may work with them as well. The NMEA2000 tank system would need to report multiple tanks on the same connection for the Repeater to be of value. The tank system's productId would most likely need to be entered manually using dbus-spy (see below).


Debugging aids:

You can view logs using the unix 'tail' command:

GUI log:

tail /var/log/gui/current | tai64nlocal

SeeLevelRepeater log:

tail /var/log/SeeLevelRepeater/current | tai64nlocal

tai64nlocal converts the timestamp at the beginning of each log entry to a human readable date and time (as UTC/GMT because Venus runs with system local time set to UTC).

dbus-spy can also be used to examine dBus services to aid in troubleshooting problems.


New versions of Venus software:

When Venus software is updated, the Repeaer will be reactivated automatically via the /data/rc.local mechanisim described above

If you experience problems with the Mobile Overview page after a Venus software update, the Repeater will need to be updated. Until such time as the GitHub files are updated, you may need to revert to a previous verison of Venus software, or uninstall the Repeater.


Hardware:

This package relies on an NEMA2000 version of the Garnet SeeLevel sensor system. It will not work with the standard or RV-C versions. Garnet's number for this version is 709-N2K NLP. It MAY work with other NMEA2000 tank sensor systems that report multiple tanks.

This version of the SeeLevel system uses a propriatary connector for the CAN-bus connection.
This connector mates with the connector on the back of the SeeLevel control unit: 3M 37104-2165-000 FL 100
And is available from DigiKey: https://www.digikey.com/product-detail/en/3m/37104-2165-000-FL-100/3M155844-ND/1238214

A cable can be made up with this connector on one end and an RJ-45 on the other to plug into a VE.Can connector on the Venus device. You can alternatively make up a cable from this connector to a standard CAN-bus connector then use the VE.Can to CAN-bus adapter cable. If you are not using standard CAN-bus cabling, be sure to terminate the SeeLevel end of the cable, especially if it is long. I was able to crimp a 1/4 watt 120 ohm resister into the pins of the 3M connector along with the wires from the CAT 5/6 cable.

I have included a PDF of the various pinouts. The 3M connector pins are numbered on the housing.

You need to connect CAN-H, CAN-L and -Voltage (aka NET-C (V-), aka grond). I left +Voltage disconnected. Ground is required since the VE.Can connection on Venus is floating.


I must give credit to Ben Brantley for providing his code that evolved into this package. You can find him on the Victron community forum.


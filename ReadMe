# SeeLevel-N2K-Victron-VenusOS

This enhancment works on 2.33 and 2.42-2.60 (as of release candidate ~14 at least so far).
The GUI files are different for 2.33 and are in a separate directory.

Allows connection of a Garnet SeeLevel NMEA2000 tank sensor system to Victron Venus OS (e.g, Color Control GX) controller

This software will allow the SeeLevel NMEA2000 tank sensor system to be used with
Victron Energy Venus devices (Color Control GX, Venus Gx, etc.).

Why this is needed:

Venus software only supports one tank per CAN-bus device and SeeLevel reports up to 3 tanks on the same connection. The result is a constantly changing display as data for each tank is received. That is, the same display would show fresh water status for a couple of seconds, then waste water then black water, etc. A stable display with separate regions for each tank is necessary.

The solution:

The first access to the SeeLevel tank information is its dBus service.
A process monitors the SeeLevel dBus service and "repeats" stable information using separate dBus services for each tank.
Further, the user interface (aka GUI) must be modified to hide the actual SeeLevel information.

SeeLevelRepeater is a python script than runs in the background.

When SeeLevel reports information for a specific tank, SeeLevelRepeater updates the Repeater's values with the latest from SeeLevel. The GUI then displays the Repeater's information.

To avoid screen clutter, SeeLevelRepeater holds off creating dBus Repeater services until it detects tank information from SeeLevel. SeeLevel may report 1, 2 or 3 tanks so we only want to populate the TANKs column in the GUI with valid tanks. A tank that disappears while the system is running is displayed in the TANKs column as "NO RESPONSE". If the Venus device is reset, tanks that are no longer responding will not reappear. When the SeeLevel system is being set up, the installer should disable messaging for any tanks that don't exist, then reboot the Venus device. Refer to Garnet's documentation for the NEMA2000 version of their sensor which describes how to disable specific tanks.

While not tested with other tank sensors, SeeLevelRepeater should work well with them as long as the TANKS display doesn't get too crowded.

Innitially, I was told that SeeLevel reports one tank approximately every 1-2 seconds. A complete scan of all tanks takes up to 3-8 seconds. However I discovered tanks can be reported much more rapidly. Too fast actually for my original design, so it's been rewritten to use a dBus signal handler to process each tank (aka /FluidType) from the SeeLevel dBus object.
The latest change added a second signal handler for /Level changes.

The GUI also needs changes in order to hide the SeeLevel tank information. The files are OverviewMobile.qml and TileTank.qml 

GUI Changes:

1) Tank information is displayed in a box sized so that 3 of them fill the column. More tanks require smaller boxes. The changes made permit up to 6 tanks to be displayed comfortably. The box size is adjusted so that all tanks fill the tanks column. In the event more than 6 tanks are found in the system, the display will bunch up and may not be readable.

2) The tank bar graph turns red when the tank is within 20% of full (for waste and black tanks) and 20% of empty for other tanks. This provides a visual alert to a situation that needs attention soon. In addition, tanks that are very close to empty show now bar so the red warning could easily be missed. In this case, the bar graph's text indicting tank fullness also turns red.

4) The GUI reports errors for tank sensors as follows":
  If a tank is not responding "NO RESPONSE" will replace level percentage
  Garnet says they report sensor errors with out of range tank levels, however the CAN-bus driver in Venus OS apparently
  truncates these values. There is code to display sensor errors (short, open, etc.) however I never saw any < 0 or > 100/  

5) Previous implementation of the TANKS display blinked some information. The blinking has been removed.

6) Displays custom tank names


Installation:

You will need root access to the Venus device. Instructions can be found here:
https://www.victronenergy.com/live/ccgx:root_access

Note: The SeeLevel service name was determined by monitoring an active system with dbus-spy. This name WILL be different on each system. 
The name is stored in non-volatile settings, accessible via dbus-spy.
The settings service is: com.victronenergy.settings
The value to change is: /Settings/Devices/TankRepeater/SeeLevelService
The easiest way to set the value is to copy the service name from the main dbus-spy screen. It will look something like:

com.victronenergy.tank.socketcan_can0_di0_uc855

After copying the string, enter the settings service and scroll down to Settings/Devices/TankRepeater/SeeLevelService

press enter, then paste the clipbord and enter again

You may need to exit the OverviewMobile screen, then come back to it in order for the tanks column to populate properly.

Note, you will NOT see Settings/Devices/TankRepeater/SeeLevelService if you have not already run SeeLevelRepeater at least once. After that, the setting persists through reboots and system updates.

I tried to automate this but there isn't enough information provided by SeeLevel to uniquely identify it relative to other CanBus tank sensors. At least this is better than editing the code as it was in earlier versions.

SeeLevelRepeater must be set up to run at system boot. The Venus service starter provides a simple mechanism: simply create a symbolic link to the actual code. 

The /data directory on Venus is a convenient location for apps like SeeLevelRepeater since the entire /data directory survives a firmware update. Most other directories are overwritten! All folders and files in this GitHub should be copied to /data, preserving the file hierarchy.

The unix command 'scp' can be used from a computer on the same network as the Venus hardware to copy files. 'ssh' can be used to log in and make changes. From Mac OS, these can be issued from Terminal. Not sure about Windows.

Note: Automatic firmware updates to the Venus device should be disabled. When an update occurs, several files installed to support SeeLevelRepeater are overwritten and must be reinstalled. These are flagged below

Copy all files included in this package to the /data directory on the Venus device.

E.g., from a host unix machine, change to the directory where TankRepeater lives, then execute

scp -r TankRepeater root@<venus ip address>:/data

Then ssh root@<venus ip address> to do the other needed activities:

Create the symbolic link that runs SeeLevelRepeater.
You will need to repeat this after a firmware update.

cd /service
ln -s /data/TankRepeater/SeeLevelRepeater .

Replace the GUI components, retaining the old copies in case you need to back out the change. 
You will need to repeat this after a firmware update.

cd /opt/victronenergy/gui/qml
mv OverviewMobile.qml OverviewMobile.qml.old
mv TileTank.qml TileTank.qml.old
cp /data/TankRepeater/GuiUpdaetsForxxx/*.qml .
xxx is either 2.33 or 2.42-2.60 depending on your system version

Reboot the Venus system:

reboot from the command line or use the GUI to reboot

You can view logs using the unix 'tail' command:

GUI log:

tail /var/log/gui/current

SeeLevelRepeater log:

tail /data/TankRepeater/SeeLevelRepeater/log/main/current

dbus-spy can also be used to examine dBus services to aid in troubleshooting problems.


Migrating changes to new versions of the system

When Venus software is updated, it may be necessary to migrate these changes into new versions of the QML files. 

Changes in OverviewMobile.qml included in this package has been marked to easily search for the changed areas making it fairly easy to migrate the changes into new versions of the venus system.

Changes to TileTank.qml are extensive. Most likely, you will simply be able to overwrite TileTank.qml after the firmware update. If not, a carefull study of the two versions will be necessary to how best to merge the versions. Many of the changes made to TileTank.qml support display of more than 3-4 tanks and may not be necessary for your system. On the other hand, the changes to support no response and errors from the tank may be desired.

Hardware:

This package relies on an NEMA2000 version of the Garnet SeeLevel repeater. It will not work with the standart or RV-C versions. Garnet's number for this version is 709-K2K NLP. It MAY work with other NMEA2000 tank sensor systems that report multiple tanks. 

This version of the SeeLevel system uses a propriatary connector for the CAN-bus connection.
This connector mates with the connector on the back of the SeeLevel control unit: 3M 37104-2165-000 FL 100
And is available from DigiKey: https://www.digikey.com/product-detail/en/3m/37104-2165-000-FL-100/3M155844-ND/1238214

A cable can be made up with this connector on one end and an RJ-45 on the other to plug into a VE.Can connector on the Venus device. You can alternatively make up a cable from this connector to a standard CAN-bus connector then use the VE.Can to CAN-bus adapter cable. Be sure to terminate the SeeLevel end of the cable, especially if it is long. I was able to crimp a 1/4 watt 120 ohm resister into the pins of the 3M connector along with the wires from the RJ-45.

I have included a PDF of the various pinouts. The 3M connector pins are numbered.

You need to connect CAN-H, CAN-L and -Voltage low (aka NET-C (V-), aka grond). I left +Voltage disconnected. Ground is required since the VE.Can connection on Venus is floating.


I must give credit to Ben Brantley for providing his code that evolved into this package. You can find him on the Victron community forum.


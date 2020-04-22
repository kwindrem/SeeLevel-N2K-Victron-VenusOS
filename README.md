# SeeLevel-N2K-Victron-VenusOS
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

Note: The SeeLevel service name was determined by monitoring an active system with dbus-spy. This name WILL be different on each system. So the name needs to be changed in the code. If dbus-spy shows a SeeLevel service but NOT any Repeater services, check the name. It is currently coded as:

'com.victronenergy.tank.socketcan_can0_di0_uc855' in three places that will need to be changed:

SeeLevelServiceName in SeeLevelRepeater.py

seeLevelServiceName in OverviewMobile.qml

SeeLevelRepeater must be set up to run at system boot. The Venus service starter provides a simple mechanism: simply create a symbolic link to the actual code. 

The /data directory on Venus is a convenient location for apps like SeeLevelRepeater since the entire /data directory survives a firmware update. Most other directories are overwritten! All folders and files in this GitHub should be copied to /data, preserving the file hierarchy. It may be easier to download the included .zip file, unzip that to a directory on your host then copy the entire directory to the Venus device.

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
cp /data/TankRepeater/GuiUpdaetsFor2.33/*.qml .

Reboot the Venus system:

reboot from the command line or use the GUI to reboot

You can view logs using the unix 'tail' command:

GUI log:

tail /var/log/gui/current

SeeLevelRepeater log:

tail /data/TankRepeater/SeeLevelRepeater/log/main/current

dbus-spy can also be used to examine dBus services to aid in troubleshooting problems.


A SeeLevel simulator is also included with this package.
It was extremely useful in debutting this code but may also be useful to verify that SeeLevelRepeater.py is installed and running properly. The simulator can be run from the Venus command line:

cd /data/TankRepeater
./SimulateSeeLevel.py

In this basic form, the simulator will create a virtual SeeLevel dBus service. dbus-spy can be used to poke values into this service to see if they propagate to Repeater services.

The simulator can also emulate the SeeLevel hardware sending out data for 3 tanks:

./SimulateSeeLevel.py simulate

This should result in Fresh Water, Waste Water and Black Water tank information showing up on the GUI

./SimulateSeeLevel.py auto

Will vary the levels for the three tanks so you can watch the displays change in the GUI

Do NOT run the simulator with an actual SeeLevel sensor system connected to the Venus device. The two will conflict as both try to create the same dBus service.


Migrating changes to new versions of the system

When Venus software is updated, it may be necessary to migrate these changes into new versions of the QML files. 

Changes in OverviewMobile.qml included in this package has been marked to easily search for the changed areas making it fairly easy to migrate the changes into new versions of the venus system.

Changes to TileTank.qml are extensive. Most likely, you will simply be able to overwrite TileTank.qml after the firmware update. If not, a carefull study of the two versions will be necessary to how best to merge the versions. Many of the changes made to TileTank.qml support display of more than 3-4 tanks and may not be necessary for your system. On the other hand, the changes to support no response and errors from the tank will most likely be necessary.

Hardware:

This package relies on an NEMA2000 version of the Garnet SeeLevel repeater. It will not work with the standart or RV-C versions. Garnet's number for this version is 709-K2K NLP.

This version of the senor system uses a propriatary connector for the CAN-bus connection.
This connector mates with the connector on the back of the SeeLevel control unit: 3M 37104-2165-000 FL 100
And is available from DigiKey: https://www.digikey.com/product-detail/en/3m/37104-2165-000-FL-100/3M155844-ND/1238214

A cable can be made up with this connector on one end and an RJ-45 on the other to plug into a VE.Can connector on the Venus device. You can alternatively make up a cable from this connector to a standard CAN-bus connector then use the VE.Can to CAN-bus adapter cable. Be sure to terminate the SeeLevel end of the cable, especially if it is long. I was able to crimp a 1/4 watt 120 ohm resister into the pins of the 3M connector along with the wires from the RJ-45.

I have included a PDF of the various pinouts. The 3M connector pins are numbered.

You need to connect CAN-H, CAN-L and -Voltage low (aka NET-C (V-), aka grond). I left +Voltage disconnected. Ground is required since the VE.Can connection on Venus is floating.


I must give credit to Ben Brantley for providing his code that evolved into this package. You can find him on the Victron community forum.


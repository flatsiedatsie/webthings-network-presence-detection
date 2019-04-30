# Webthings network presence detection
Using this add-on, devices on your local network can be added as a 'thing' in the Mozilla WebThings Gateway. Automations can then respond to their presence. For example, turn on the lights at night when your mobile phone connects to the wireless network. Or turn of the heater when none of your phones or laptops are on the network.

## Features
- You can change how many minutes a device must 'disappear' from the network before it is marked as being away. The add-on scans the network once a minute.

## Limitations
- This add-on uses 'arp' which is a standard tool to figure out what is on the local network. This tool isn't always great at spotting mobile devices, especially modern iphones.
- A thing is linked to a mac-address of a device. Nowadays some devices, like iphones, change their mac-address once in a while to make tracking difficult. This is a great privacy feature, but it may also hinder this add-ons ability to track (i)phone presence.

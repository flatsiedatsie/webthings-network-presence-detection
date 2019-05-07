# Webthings network presence detection
Using this add-on, devices on your local network can be added as a 'thing' in the Mozilla WebThings Gateway. Automations can then respond to their presence. For example, turn on the lights at night when your mobile phone connects to the wireless network. Or turn of the heater when none of your phones or laptops are on the network.

![A screenshot of a presence detection thing](https://raw.githubusercontent.com/flatsiedatsie/webthings-network-presence-detection/master/presence-detection-screenshot.png)

## Features
- You can change how many minutes a device must 'disappear' from the network before it is marked as being away. The add-on scans the network once every few minutes.
- If the human-readable name of a device is not known, then it will try to look-up the device manufacturer, and use that as a name. The add-on does _not_ connect to the internet to do this. It is done locally, on the gateway, so your privacy is protected.

## Limitations
- This add-on uses 'ping', 'arping' and 'arp' to scan the local network. Arping can spot more devices, but requires you to install it on your system manually.
- A thing is linked to a mac-address of a device. Nowadays some devices, like iphones, change their mac-address once in a while to make tracking difficult. This is a great privacy feature, but it may also hinder this add-ons ability to track (i)phone presence.

## Thanks to

Michael Stegeman of the Mozilla Foundation helped a lot in getting this add-on to work optimally.
https://github.com/mrstegeman

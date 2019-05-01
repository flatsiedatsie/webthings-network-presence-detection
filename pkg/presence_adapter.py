"""Presence Detection adapter for Mozilla WebThings Gateway."""

from datetime import datetime, timedelta
from gateway_addon import Adapter, Database
import json
import os
import subprocess
import threading
import time

from .presence_device import PresenceDevice
from .util import valid_ip, valid_mac, clamp

OUI_FILE = 'oui.txt'
SEPARATORS = ('-', ':')
BUFFER_SIZE = 1024 * 8

__location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))


_POLL_INTERVAL = 60   # 60 seconds between polling

_CONFIG_PATHS = [
    os.path.join(os.path.expanduser('~'), '.mozilla-iot', 'config'),
]

if 'MOZIOT_HOME' in os.environ:
    _CONFIG_PATHS.insert(0, os.path.join(os.environ['MOZIOT_HOME'], 'config'))


class PresenceAdapter(Adapter):
    """Adapter for network presence detection"""

    def __init__(self, verbose=True):
        """
        Initialize the object.

        verbose -- whether or not to enable verbose logging
        """
        print("Initialising adapter from class")
        self.pairing = False
        self.name = self.__class__.__name__
        Adapter.__init__(self, 'presence-adapter', 'presence-adapter', verbose=verbose)
        print("Adapter ID = " + self.get_id())

        self.memory_in_weeks = 10
        self.time_window = 60
        self.add_from_config()

        self.filename = None

        for path in _CONFIG_PATHS:
            if os.path.isdir(path):
                self.filename = os.path.join(
                    path,
                    'network-presence-detection-adapter-devices.json'
                )

        # make sure the file exists:
        if self.filename:
            try:
                with open(self.filename) as file_object:
                    print("Loading json..")
                    self.previously_found = json.load(file_object)

                    #print("Previously found items: = " + str(self.previously_found))
            except (IOError, ValueError):
                self.previously_found = {}
                print("Failed to load JSON file")
                with open(self.filename, 'w') as f:
                    f.write('{}')
        else:
            self.previously_found = {}

        # Remove devices that have not been seen in a long time
        self.prune()

        # Present all devices to the gateway
        for key in self.previously_found:
            item = self.previously_found[key]
            self._add_device(str(key), str(item['name']), str('...')) # adding the device



        # Once a minute start the scan process
        self.thread = threading.Thread(target=self.poll)
        self.thread.daemon = True
        self.thread.start()



    def unload(self):
        print("adapter is being unloaded")
        self.save_to_json()
        self.thread.stop()




    def poll(self):
        """Poll the device for changes."""
        while True:
            self.scan()
            time.sleep(_POLL_INTERVAL)



    def scan(self):
        print()
        print("Scanning..")

        shouldSave = False # should the found_devices list be saves to a file? We only do this if new devices have been found during this scan.
        now = datetime.now()

        #print(str( self.previously_found.values() ))

        # First we add any new devices on the network.
        try:
            output = subprocess.check_output("arp -a", shell=True).decode()

            print(output)
            for line in output.splitlines():
                if not line:
                    continue

                print()
                #print("line: " + line)

                ip_address = line.split(' ')[1][1:-1]
                if not valid_ip(ip_address):
                    continue

                print("ip address found: " + ip_address)

                mac_address = line.split(' ')[3]
                mac_address = ':'.join([
                    # Left pad the MAC address parts with '0' in case of
                    # invalid output (as on macOS)
                    '0' * (2 - len(x)) + x for x in mac_address.split(':')
                ])

                if not valid_mac(mac_address):
                    continue

                print("mac address found: " + mac_address)

                vendor = get_vendor(mac_address)
                if vendor:
                    # Remove everything after the comma. Thus "Apple, inc"
                    # becomes "Apple"
                    vendor = vendor.split(',', 1)[0]
                else:
                    # The first piece of the `arp -a` output is the hostname
                    vendor = '{} ({})'.format(line.split(' ')[0], mac_address)

                found_device_name = "Presence - " + vendor

                print("Initial name: " + found_device_name)

                mac_address = mac_address.replace(":", "")
                #print("cleaned mac: " + str(mac_address))

                try:
                    # We've seen this device before.
                    if mac_address in self.previously_found:
                        print(" -mac address already known")
                        #print(str( self.previously_found[mac_address]['lastseen'] ))
                        self.previously_found[mac_address]['lastseen'] = datetime.timestamp(now)
                        # should now update the last seen time stamp.
                        print(" -last seen date updated")

                    # We found a completely new device on the network.
                    else:
                        shouldSave = True

                        i = 2 # We skip "1" as a number. So we will get names like "Apple" and then "Apple 2", "Apple 3", and so on.
                        possibleName = found_device_name
                        could_be_same_same = True

                        while could_be_same_same is True: # We check if this name already exists in the list of previously found devices.
                            could_be_same_same = False
                            for item in self.previously_found.values():
                                if possibleName == item['name']: # The name already existed in the list, so we change it a little bit and compare again.
                                    could_be_same_same = True
                                    #print("names collided")
                                    possibleName = found_device_name + " " + str(i)
                                    i += 1

                        self.previously_found[mac_address] = {
                            'name': possibleName,
                            'lastseen': datetime.timestamp(now),
                        }

                        # The device did not exist yet, so we're creating it.
                        self._add_device(mac_address, possibleName, ip_address)

                        print("Added new device:" + possibleName)

                except Exception as ex:
                    print("Error comparing to previous mac addresses list: " + str(ex))

                # Update the Details property. The device may have a new IP address.
                try:
                    _id = 'presence-{}'.format(mac_address)
                    if 'details' in self.devices[_id].properties:
                        if ip_address != '':
                            print("UPDATING DETAILS for " + mac_address)
                            self.devices[_id].properties['details'].update(ip_address)
                        else:
                            print("ip_address was empty, so not updating the details property.")
                    else:
                        print("The details property did not exist? Does the device even exist?")
                except Exception as ex:
                    print("Not turned into a device object yet? Error: " + str(ex))


        except Exception as ex:
            print("Error while scanning: " + str(ex))

        #print(str(self.previously_found))
        if shouldSave is True:
            self.save_to_json()


        # Secondly, we go over the list of all previously found devices, and update them.
        try:
            print()
            #past = datetime.now() - timedelta(hours=1)
            past = datetime.now() - timedelta(minutes=self.time_window)
            #print("An hour ago: " + str(past))
            paststamp = datetime.timestamp(past)

            for key in self.previously_found:
                #print("Updating: " + str(key))# + "," + str(item))

                item = self.previously_found[key]

                if key not in self.devices:
                    continue

                try:
                    # Check if the device already has a property.
                    if 'recently1' not in self.devices[key].properties:
                        # add the property
                        print("While updating, noticed device did not yet have the recently spotted property. Adding now.")
                        self.devices[key].add_boolean_child('recently1', "Recently spotted", True)

                    else:
                        print("UPDATING LAST SEEN for " + str(key))
                        if paststamp > item['lastseen']:
                            print("BYE! " + str(key) + " was last seen over " + str(self.time_window) + " ago")
                            self.devices[key].properties['recently1'].update(False)
                        else:
                            print("HI!  " + str(key) + " was spotted less than " + str(self.time_window) + " minutes ago")
                            self.devices[key].properties['recently1'].update(True)

                except Exception as ex:
                    print("Could not create or update property. Error: " + str(ex))


        except Exception as ex:
            print("Error while updating device: " + str(ex))

        # Here we remove devices that haven't been spotted in a long time.
        self.prune()

    def _add_device(self, mac, name, details):
        """Add the given device, if necessary."""
        try:
            print("adapter._add_device: " + name)
            device = PresenceDevice(self, mac, name, details)
            self.handle_device_added(device)
            print("-Adapter has finished adding new device")

        except Exception as ex:
            print("Error adding new device: " + str(ex))

    def prune(self):
        # adding already known devices back into the system. Maybe only devices seen in the last few months?

        try:
            print()
            too_old = datetime.now() - timedelta(weeks=self.memory_in_weeks)
            #print("Too old threshold: " + str(too_old))
            too_old_timestamp = datetime.timestamp(too_old)

            items_to_remove = []

            for key in self.previously_found:
                #print("Updating: " + str(key))# + "," + str(item))

                item = self.previously_found[key]

                #lastSpottedTime = datetime.strptime('Jun 1 2005  1:33PM', '%b %d %Y %I:%M%p')

                if too_old_timestamp > item['lastseen']:
                    print(str(key) + " was too old")
                    items_to_remove.append(key)
                else:
                    #print(str(key) + " was not too old")
                    pass

            if len(items_to_remove):
                for remove_me in items_to_remove:
                    self.previously_found.pop(remove_me, None)
                    #del self.previously_found[remove_me]

        except Exception as ex:
            print("Error pruning: " + str(ex))



    def add_from_config(self):
        """Attempt to add all configured devices."""

        try:
            database = Database('presence-adapter')


            if not database.open():
                return

            config = database.load_config()
            database.close()

            if not config or 'Memory' not in config or 'Time window' not in config:
                print("Required variables not found in config database?")
                return

            self.memory_in_weeks = clamp(int(config['Memory']), 1, 50) # The variable is clamped: it is forced to be between 1 and 50.
            self.time_window = clamp(int(config['Time window']), 1, 1380) # 'Grace period' could also be a good name.
            print("CONFIG LOADED OK")

        except:
            print("Error getting config data from database")



    def save_to_json(self):
        try:
            print()
            print("Saving updated list of found devices to json file")
            if self.previously_found and self.filename:
                with open(self.filename, 'w') as fp:
                    json.dump(self.previously_found, fp)
        except:
            print("Saving to json file failed")



    def cancel_pairing(self):
        """Cancel the pairing process."""
        self.pairing = False
        self.save_to_json()




# I couldn't get the import to work, so I just copied some of the code here:
# It was made by Victor Oliveira (victor.oliveira@gmx.com)


def get_vendor(mac, oui_file=OUI_FILE):
    mac_clean = mac
    for separator in SEPARATORS:
        mac_clean = ''.join(mac_clean.split(separator))

    try:
        int(mac_clean, 16)
    except ValueError:
        raise ValueError('Invalid MAC address.')

    mac_size = len(mac_clean)
    if mac_size > 12 or mac_size < 6:
        raise ValueError('Invalid MAC address.')

    with open(os.path.join(__location__, oui_file)) as file:
        mac_half = mac_clean[0:6]
        mac_half_upper = mac_half.upper()
        while True:
            line = file.readline()
            if line:
                if line.startswith(mac_half_upper):
                    vendor = line.strip().split('\t')[-1]
                    return vendor
            else:
                break

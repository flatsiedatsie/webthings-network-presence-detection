"""Presence Detection adapter for Mozilla WebThings Gateway."""

from datetime import datetime, timedelta
from gateway_addon import Adapter, Database
import json
import os
import re
import threading

from .presence_device import PresenceDevice
from .util import valid_ip, valid_mac, clamp, get_ip, ping, arping, arp

OUI_FILE = 'oui.txt'
SEPARATORS = ('-', ':')
BUFFER_SIZE = 1024 * 8

__location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))

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
        #print("Adapter ID = " + self.get_id())

        self.memory_in_weeks = 10 # How many weeks a device will be remembered as a possible device.
        self.time_window = 60 # How many minutes should a device be away before we concider it away?

        self.add_from_config() # Here we get data from the settings in the Gateway interface.

        self.own_ip = 'unknown' # We scan only scan if the device itself has an IP address.
        self.ip_range = {} # we remember which IP addresses had a device. This makes them extra interesting, and they will get extra attention during scans.
        self.deep_scan_frequency = 10 # once every 10 scans we do a deep scan.
        self.scan_count = 0 # Used by the deep scan system.
        self.filename = None

        for path in _CONFIG_PATHS:
            if os.path.isdir(path):
                self.filename = os.path.join(
                    path,
                    'network-presence-detection-adapter-devices.json'
                )

        self.should_save = False

        # make sure the file exists:
        if self.filename:
            try:
                with open(self.filename) as file_object:
                    #print("Loading json..")
                    try:
                        self.previously_found = json.load(file_object)
                    except:
                        #print("Empty json file")
                        self.previously_found = {}
                    #print("Previously found items: = " + str(self.previously_found))

            except (IOError, ValueError):
                self.previously_found = {}
                print("Failed to load JSON file, generating new one.")
                with open(self.filename, 'w') as f:
                    f.write('{}')
        else:
            self.previously_found = {}

        # Remove devices that have not been seen in a long time
        self.prune()

        # Present all devices to the gateway
        for key in self.previously_found:
            self._add_device(str(key), str(self.previously_found[key]['name']), str('...')) # Adding the device

            _id = 'presence-{}'.format(key)
            self.devices[_id].add_boolean_child('recently1', "Recently spotted", False)
            self.devices[_id].add_integer_child('minutes_ago', "Minutes ago last seen", 99999)


        # Start the thread that updates the 'minutes ago' countdown on all lastseen properties.
        #t = threading.Thread(target=self.update_minutes_ago)
        #t.daemon = True
        #t.start()


        # We continuously scan for new devices, in an endless loop.
        self.own_ip = get_ip()
        if valid_ip(self.own_ip):
            while True:
                #def split_processing(items, num_splits=4):
                old_previous_found_count = len(self.previously_found)
                thread_count = 5
                split_size = 255 // thread_count
                threads = []
                for i in range(thread_count):
                    # determine the indices of the list this thread will handle
                    start = i * split_size
                    #print("thread start = " + str(start))
                    # special case on the last chunk to account for uneven splits
                    end = 255 if i+1 == thread_count else (i+1) * split_size
                    #print("thread end = " + str(end))
                    # Create the thread
                    threads.append(
                        threading.Thread(target=self.scan, args=(start, end)))
                    threads[-1].daemon = True
                    threads[-1].start() # start the thread we just created

                # Wait for all threads to finish
                for t in threads:
                    t.join()

                # If new devices were found, save the JSON file.
                if len(self.previously_found) > old_previous_found_count:
                    self.save_to_json()

                self.update_the_rest()
                #self.scan()
                #time.sleep(60)

    '''
    def update_minutes_ago(self):
        t = threading.Timer(60.0, self.update_minutes_ago)
        t.daemon = True
        t.start()

        print("~~thread minutes ago updater")
        #time.sleep(300)
        for key in self.devices:
            print("~~thread is checking out a device: " + str(key))

            if 'minutes_ago' in self.devices[key].properties:
                print("~~thread is updating minutes ago: " + str(key))
                current_minutes_ago_value = self.devices[key].properties['minutes_ago'].value
                self.devices[key].properties['minutes_ago'].update(current_minutes_ago_value + 1)

        #time.sleep(10)
    '''

    def unload(self):
        print("Presence detector is being unloaded")
        self.save_to_json()




    def scan(self, start, end):
        self.scan_count += 1
        if self.scan_count == self.deep_scan_frequency:
            self.scan_count = 0

        self.should_save = False # We only save found_devices to a file if new devices have been found during this scan.

        for ip_byte4 in range(start, end):

            # when halfway through, start a new thread.



            ip_address = str(self.own_ip[:self.own_ip.rfind(".")]) + "." + str(ip_byte4)
            #print()
            #print(ip_address)

            # Skip our own IP address.
            if ip_address == self.own_ip:
                continue

            # IP Addresses that have been populated before get extra scrutiny.
            if ip_address in self.ip_range:
                ping_count = 4
            else:
                ping_count = 1

            # Once in a while we do a deep scan of the entire network, and give each IP address a larger number of tries before moving on.
            if self.scan_count == 0:
                ping_count = 4

            #print("-scan intensity: " + str(ping_count))
            alive = False   # holds whether we got any response.
            if ping(ip_address, ping_count) == 0: # 0 means everything went ok, so a device was found.
                alive = True
            elif arping(ip_address, ping_count) == 0: # 0 means everything went ok, so a device was found.
                alive = True

            # If either ping or arping found a device:
            if alive:
                self.ip_range[ip_address] = 1000 # This IP address is of high interest. For the next 1000 iterations is will get extra attention.
                #print("-ALIVE")
                output = arp(ip_address)
                #print(str(output))
                mac_addresses = re.findall(r'(([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})', output)

                now = datetime.timestamp(datetime.now())

                if len(mac_addresses) > 0:
                    mac_address = mac_addresses[0][0]
                    mac_address = ':'.join([
                        # Left pad the MAC address parts with '0' in case of
                        # invalid output (as on macOS)
                        '0' * (2 - len(x)) + x for x in mac_address.split(':')
                    ])

                    if not valid_mac(mac_address):
                        continue

                    mac_address = mac_address.replace(":", "")
                    _id = 'presence-{}'.format(mac_address)
                    #print("early mac = " + mac_address)

                    # Get the basic variables
                    found_device_name = output.split(' ')[0]
                    #print("early found device name = " + found_device_name)

                    if found_device_name == '?' or valid_ip(found_device_name):
                        vendor = 'unnamed'
                        try:
                            # Get the vendor name, and shorten it. It removes
                            # everything after the comma. Thus "Apple, inc"
                            # becomes "Apple"
                            vendor = get_vendor(mac_address)
                            if vendor is not None:
                                vendor = vendor.split(' ', 1)[0]
                                vendor = vendor.split(',', 1)[0]
                            else:
                                vendor = 'unnamed'
                        except ValueError:
                            pass

                        found_device_name = "Presence - " + vendor
                    else:
                        found_device_name = "Presence - " + found_device_name



                        
                    #print("--mac:  " + mac_address)
                    #print("--name: " + found_device_name)
                    #print("--_id: " + _id)
                    
                    # Create or update items in the previously_found dictionary
                    try:
                        possibleName = ''
                        if mac_address not in self.previously_found:

                            self.should_save = True

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

                            self.previously_found[str(mac_address)] = {
                                'name': str(possibleName),
                                'lastseen': now,
                            }
                        else:
                            #print(" -mac address already known")

                            self.previously_found[mac_address]['lastseen'] = now
                            possibleName = self.previously_found[mac_address]['name']
                    except Exception as ex:
                        print("Error updating items in the previously_found dictionary: " + str(ex))


                    #print("--_id is now: " + _id)
                    # Present new device to the WebThings gateway, or update them.
                    
                    #print("propos: " + str( self.get_devices() ))
                    
                    try:
                        if _id not in self.devices:
                            # Present new device to the WebThings gateway
                            #print("not _id in self.devices")
                            self._add_device(str(mac_address), str(possibleName), str(ip_address)) # The device did not exist yet, so we're creating it.
                            #print("Presented new device to gateway:" + str(possibleName))
                        else:
                            if 'details' in self.devices[_id].properties:
                                if ip_address != '':
                                    #print("UPDATING DETAILS for " + _id)
                                    self.devices[_id].properties['details'].update(str(ip_address))
                                else:
                                    pass
                                    #print("ip_address was empty, so not updating the details property.")
                            else:
                                pass
                                #print("The details property did not exist? Does the device even exist?")
                    except Exception as ex:
                        print("Error presenting new device to the WebThings gateway, or updating them.: " + str(ex))

                    # Present new device properties to the WebThings gateway, or update them.
                    try:
                        if 'recently1' not in self.devices[_id].properties:
                            # add the property
                            print()
                            print("While updating, noticed device did not yet have the recently spotted property. Adding now.")
                            self.devices[_id].add_boolean_child('recently1', "Recently spotted", True)
                        else:
                            self.devices[_id].properties['recently1'].update(True)

                        if 'minutes_ago' not in self.devices[_id].properties:
                            # add the property
                            print()
                            print("While updating, noticed device did not yet have the minutes ago property. Adding now.")
                            self.devices[_id].add_integer_child('minutes_ago', "Minutes ago last seen", 0)
                        else:
                            self.devices[_id].properties['minutes_ago'].update(0)
                    except Exception as ex:
                        print("Error presenting new device properties to the WebThings gateway, or updating them.: " + str(ex))


            # If no device was found at this IP address:
            else:
                if ip_address in self.ip_range:
                    if self.ip_range[ip_address] == 0:
                        self.ip_range.pop(ip_address)
                    else:
                        self.ip_range[ip_address] = self.ip_range[ip_address] - 1


    def update_the_rest(self):
        # We go over the list of ALL previously found devices, including the ones not found in the scan, and update them.
        try:
            #print()
            #past = datetime.now() - timedelta(hours=1)
            nowstamp = datetime.timestamp(datetime.now())
            #past = datetime.now() - timedelta(minutes=self.time_window)
            #paststamp = datetime.timestamp(past) # A moment in the past that we compare against.



            for key in self.previously_found:
                #print()
                
                _id = 'presence-{}'.format(key)
                #print("Updating: " + str(_id))

                try:
                    # Make sure all devices and properties exist. Should be superfluous really.
                    if _id not in self.devices:
                        self._add_device(key, self.previously_found[key]['name'], '...') # The device did not exist yet, so we're creating it.
                    if 'recently1' not in self.devices[_id].properties:
                        self.devices[_id].add_boolean_child('recently1', "Recently spotted", False)
                    if 'minutes_ago' not in self.devices[_id].properties:
                        self.devices[_id].add_integer_child('minutes_ago', "Minutes ago last seen", 99999)

                    # Update devices
                    self.previously_found[key]['lastseen']

                    minutes_ago = int((nowstamp - self.previously_found[key]['lastseen']) / 60)
                    #minutes_ago = int( ( - paststamp) / 60 )
                    if minutes_ago > self.time_window:
                        #print("BYE! " + str(key) + " was last seen over " + str(self.time_window) + " ago")
                        self.devices[_id].properties['recently1'].update(False)
                        self.devices[_id].properties['minutes_ago'].update(99999) # It's not great, but what other options are there?
                    else:
                        #print("HI!  " + str(key) + " was spotted less than " + str(self.time_window) + " minutes ago")
                        self.devices[_id].properties['recently1'].update(True)
                        self.devices[_id].properties['minutes_ago'].update(minutes_ago)

                except Exception as ex:
                    print("Could not create or update property. Error: " + str(ex))

        except Exception as ex:
            print("Error while updating device: " + str(ex))

        # Here we remove devices that haven't been spotted in a long time.
        self.prune()



    def _add_device(self, mac, name, details):
        """
        Add the given device, if necessary.

        """
        try:
            #print("adapter._add_device: " + str(name))
            device = PresenceDevice(self, mac, name, details)
            self.handle_device_added(device)
            #print("-Adapter has finished adding new device for mac " + str(mac))

        except Exception as ex:
            print("Error adding new device: " + str(ex))

        return




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
                    print(str(key) + " was pruned from the list of all found devices")
                    items_to_remove.append(key)
                else:
                    #print(str(key) + " was not too old")
                    pass

            if len(items_to_remove):
                for remove_me in items_to_remove:
                    self.previously_found.pop(remove_me, None)
                    #del self.previously_found[remove_me]
                self.save_to_json()

        except Exception as ex:
            print("Error pruning found devices list: " + str(ex))



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
            print("Config loaded ok")

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

"""Presence Detection adapter for Mozilla WebThings Gateway."""

from datetime import datetime, timedelta
from gateway_addon import Adapter, Database
import json
import os
import re
import threading
import time

from .presence_device import PresenceDevice
from .util import valid_ip, valid_mac, clamp, get_ip, ping, arping, arp, arpa, get_vendor





_CONFIG_PATHS = [
    os.path.join(os.path.expanduser('~'), '.mozilla-iot', 'config'),
]

if 'MOZIOT_HOME' in os.environ:
    _CONFIG_PATHS.insert(0, os.path.join(os.environ['MOZIOT_HOME'], 'config'))


class PresenceAdapter(Adapter):
    """Adapter for network presence detection"""

    def __init__(self, verbose=False):
        """
        Initialize the object.

        verbose -- whether or not to enable verbose logging
        """
        #print("Initialising adapter from class")

        self.addon_name = 'network-presence-detection-adapter'
        self.name = self.__class__.__name__
        Adapter.__init__(self,
                         self.addon_name,
                         self.addon_name,
                         verbose=verbose)
        #print("Adapter ID = " + self.get_id())

        self.DEBUG = True
        #self.memory_in_weeks = 10 # How many weeks a device will be remembered as a possible device.
        self.time_window = 10 # How many minutes should a device be away before we consider it away?

        self.own_ip = 'unknown' # We scan only scan if the device itself has an IP address.
        
        self.add_from_config() # Here we get data from the settings in the Gateway interface.
           
        try:
            if self.own_ip == 'unknown':
                self.own_ip = get_ip()
        except:
            print("Could not get actual own IP address")
        
     
        self.should_brute_force_scan = True
        self.busy_doing_brute_force_scan = False
        self.last_brute_force_scan_time = 0             # Allows the add-on to start a brute force scan right away.
        self.seconds_between_brute_force_scans = 1800  # 30 minutes     
        
        self.running = True
        self.saved_devices = []

        self.addon_path =  os.path.join(os.path.expanduser('~'), '.mozilla-iot', 'addons', self.addon_name)
        self.persistence_file_path = os.path.join(os.path.expanduser('~'), '.mozilla-iot', 'data', self.addon_name,'persistence.json')

        if self.DEBUG:
            print("self.persistence_file_path = " + str(self.persistence_file_path))
        self.should_save = False


        try:
            with open(self.persistence_file_path) as file_object:
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
            try:
                with open(self.filename, 'w') as f:
                    f.write('{}')
            except Exception as ex:
                print("failed to create empty persistence file: " + str(ex))
        self.previous_found_devices_length = len(self.previously_found)

        # First scan
        self.arpa_scan() # get initial list of devices from arp -a

        if self.DEBUG:
            print("Starting the continous scan clock")
        try:
            t = threading.Thread(target=self.clock)
            t.daemon = True
            t.start()
        except:
            print("Error starting the continous light scan thread")

        #done = self.brute_force_scan()

        if self.DEBUG:
            print("Starting the periodic brute force scan thread")
        try:
            b = threading.Thread(target=self.brute_force_scan)
            b.daemon = True
            b.start()
        except:
            print("Error starting the brute force scan thread")

        
        while self.running:
            time.sleep(1)
        
        
        
        
    def arpa_scan(self):
        if self.DEBUG:
            print("Initiating light scan using arp -a")
        try:
            arpa_list = arpa()
            if self.DEBUG:
                print(str(arpa_list))
                print("arpa list length: " + str(len(arpa_list)))
            for key in arpa_list:
                if self.DEBUG:
                    print("arpa list key: " + str(key))
                if key not in self.previously_found:
                    self.previously_found[str(_id)] = {} # adding empty device to the internal object
            
                    if self.DEBUG:
                        print("-Adding to previously found list")
                    self.should_save = True # We will be adding this new device to the list, and then save that updated list.

                    i = 2 # We skip "1" as a number. So we will get names like "Apple" and then "Apple 2", "Apple 3", and so on.
                    possible_name = arpa_list[key]['name']
                    could_be_same_same = True

                    while could_be_same_same is True: # We check if this name already exists in the list of previously found devices.
                        could_be_same_same = False
                        for item in self.previously_found.values():
                            if possible_name == item['name']: # The name already existed in the list, so we change it a little bit and compare again.
                                could_be_same_same = True
                                #print("names collided")
                                possible_name = found_device_name + " " + str(i)
                                i += 1
            
                    self.previously_found[key]['name'] = possible_name
                    self.previously_found[key]['ip'] = arpa_list[key]['ip']
                    self.previously_found[key]['mac_address'] = arpa_list[key]['mac_address']
                    self.previously_found[key]['arpa_time'] = time.time() #arpa_list[key]['arpa_time'] #timestamp of initiation
        except Exception as ex:
            print("Error doing light arpa scan: " + str(ex))
        
        
        
    def brute_force_scan(self):
        """ Goes over every possible IP adddress in the local network (1-254) to check if it responds to a ping or arping request """
        while self.running:
            if self.busy_doing_brute_force_scan == False and self.should_brute_force_scan == True:
                if self.DEBUG:
                    print("Initiating a brute force scan of the entire local network")
                self.busy_doing_brute_force_scan = True
                self.should_brute_force_scan = False
                
                # Remove devices that haven't been spotted in a long time.
                for key in self.previously_found:
                    try:
                        if time.time() - self.previously_found[key]['arpa_time'] > 86400 and key not in self.saved_devices:
                            if self.DEBUG:
                                print("Removing devices from found devices list because it hasn't been spotted in a day, and it's not a device the user has imported about.")
                            del self.previously_found[key]
                    except Exception as ex:
                        if self.DEBUG:
                            print("Could not remove old device: " + str(ex))
                
                
                if valid_ip(self.own_ip):
                    #while True:
                    #def split_processing(items, num_splits=4):
                    old_previous_found_count = len(self.previously_found)
                    thread_count = 5
                    split_size = 51
                    threads = []
                    for i in range(thread_count):
                        # determine the indices of the list this thread will handle
                        start = i * split_size
                        if self.DEBUG:
                            print("thread start = " + str(start))
                        # special case on the last chunk to account for uneven splits
                        end = 255 if i+1 == thread_count else (i+1) * split_size
                        if self.DEBUG:
                            print("thread end = " + str(end))
                        # Create the thread
                        threads.append(
                            threading.Thread(target=self.scan, args=(start, end)))
                        threads[-1].daemon = True
                        threads[-1].start() # start the thread we just created

                    # Wait for all threads to finish
                    for t in threads:
                        t.join()

                    if self.DEBUG:
                        print("Deep scan: all threads are done")
                    # If new devices were found, save the JSON file.
                    if len(self.previously_found) > old_previous_found_count:
                        self.save_to_json()

                    self.busy_doing_brute_force_scan = False
                    self.last_brute_force_scan_time = time.time()
                    self.save_to_json()

                else:
                    if self.DEBUG:
                        print("own IP is not valid")



    def clock(self):
        """ Runs continuously and scans IP addresses that the user has accepted as things """
        if self.DEBUG:
            print("clock thread init")
            
        succesfully_found = 0 # If all devices the user cares about are actually present, then no deep scan is necessary.
        while self.running:

            try:
                if time.time() - self.last_brute_force_scan_time > self.seconds_between_brute_force_scans:
                    self.last_brute_force_scan_time = time.time()
                    if succesfully_found != len(self.saved_devices): # Avoid doing a deep scan if all devices are present
                        self.should_brute_force_scan = True
            except Exception as ex:
                print("Clock: error running periodic deep scan: " + str(ex))

            succesfully_found = 0
            try:
                if self.DEBUG:
                    print("")
                    print("CLOCK TICK")
                        
                for key in self.saved_devices:
                    if self.DEBUG:
                        print("")
                        print("CLOCK: key from saved devices:" + str(key))

                    if self.DEBUG:
                        print("Saved device ID " + str(key) + " was also in previously found list. Trying scan.")
                    
                    # Try doing an ARPING request if there is a valid IP Address
                    try:
                        if self.DEBUG:
                            print("IP from previously found list: " + str(self.previously_found[key]['ip']))
                        if arping(self.previously_found[key]['ip'],1):
                            if self.DEBUG:
                                print(">> Arping could not find device at " + str(self.previously_found[key]['ip']) + ". Maybe Ping can.")
                            if ping(self.previously_found[key]['ip'], 1) == 0:
                                self.previously_found[key]['lastseen'] = int(time.time())
                                if self.DEBUG:
                                    print(">> Ping found it.")
                                succesfully_found += 1
                            else:
                                if self.DEBUG:
                                    print(">> Ping also could not find the device.")
                        else:
                            if self.DEBUG:
                                print(">> Arping found device")
                            self.previously_found[key]['lastseen'] = int(time.time())
                            succesfully_found += 1
                        
                    except Exception as ex:
                        print("Was not able to scan device from saved_devices list: " + str(ex))
                   
                    
                    # Update device's last seen properties
                    try:
                        # Make sure all devices and properties exist. Should be superfluous really.
                        if key not in self.devices:
                            detail = "..."
                            try:
                                detail = self.previously_found[key]['ip']
                            except:
                                if self.DEBUG:
                                    print("No IP address in previously found list")
                                
                            new_name = "Unknown"
                            try:
                                new_name = self.previously_found[key]['name']
                            except:
                                if self.DEBUG:
                                    print("No name present in previously found list")
                            
                            self._add_device(key, new_name, detail) # The device did not exist yet, so we're creating it.

                        try:
                            if self.previously_found[key]['lastseen'] != 0:
                                minutes_ago = int((time.time() - self.previously_found[key]['lastseen']) / 60)
                            else:
                                minutes_ago = 99999
                        except Exception as ex:
                            minutes_ago = 99999
                            if self.DEBUG:
                                print("Minutes ago issue: " + str(ex))
                        
                        try:
                            if 'minutes_ago' not in self.devices[key].properties:
                                self.devices[key].add_integer_child('minutes_ago', "Minutes ago last seen", minutes_ago)
                            else:
                                self.devices[key].properties['minutes_ago'].update(minutes_ago)
                        except Exception as ex:
                            print("Could not add minutes_ago property" + str(ex))
                            
                        try:
                            if minutes_ago > self.time_window:
                                recently = False
                            else:
                                recently = True
                            if 'recently1' not in self.devices[key].properties:
                                self.devices[key].add_boolean_child('recently1', "Recently spotted", recently)
                            else:
                                self.devices[key].properties['recently1'].update(recently)
                        except Exception as ex:
                            print("Could not add recently spotted property" + str(ex))

                    except Exception as ex:
                        print("Could not create or update property. Error: " + str(ex))    
                    
            except Exception as ex:
                print("Clock error: " + str(ex))

            if len(self.previously_found) != self.previous_found_devices_length:
                self.previous_found_devices_length = len(self.previously_found)
                self.save_to_json()
            
            time.sleep(2)



    def handle_device_saved(self, device_id, device):
        """User saved a thing. Also called when the add-on starts."""
        if device_id.startswith('presence'):
            if self.DEBUG:
                print("handle_device_saved. device_id = " + str(device_id) + ", device = " + str(device))

            if device_id not in self.saved_devices:
                #print("Adding to saved_devices list: " + str(device_id.split("-")[1]))
                if self.DEBUG:
                    print("Added to devices list")
                self.saved_devices.append(device_id)
                try:
                    if device_id not in self.previously_found:
                        self.previously_found[device_id] = {}
                    
                    self.previously_found[device_id]['lastseen'] = 0    
                    self.previously_found[device_id]['arpa_time'] = time.time()
                    self.previously_found[device_id]['name'] = str(device['title'])
                except Exception as ex:
                    print("Error adding to found devices list: " + str(ex))




    def unload(self):
        """Add-on is shutting down."""
        if self.DEBUG:
            print("Network presence detector is being unloaded")
        self.save_to_json()
        self.running = False



    def remove_thing(self, device_id):
        """User removed a thing from the interface."""
        if self.DEBUG:
            print("-----REMOVING------")

        try:
            #print("THING TO REMOVE:" + str(self.devices[device_id]))
            del self.previously_found[device_id]
            #print("2")
            obj = self.get_device(device_id)
            #print("3")
            self.handle_device_removed(obj)
            if self.DEBUG:
                print("Removed presence detection device")
        except:
            print("REMOVING PRESENCE DETECTION THING FAILED")
        #del self.devices[device_id]
        self.should_save = True # saving changes to the json persistence file



    def scan(self, start, end):
        """Part of the brute force scanning function, which splits out the scanning over multiple threads."""
        self.should_save = False # We only save found_devices to a file if new devices have been found during this scan.

        # skip broadcast addresses
        if start == 0:
            start = 1
        if end == 255:
            end = 254
            
        for ip_byte4 in range(start, end):

            ip_address = str(self.own_ip[:self.own_ip.rfind(".")]) + "." + str(ip_byte4)
            if self.DEBUG:
                print(ip_address)

            # Skip our own IP address.
            if ip_address == self.own_ip:
                continue

            ping_count = 1

            alive = False   # holds whether we got any response.
            if ping(ip_address, ping_count) == 0: # 0 means everything went ok, so a device was found.
                alive = True
                
            elif arping(ip_address, ping_count) == 0: # 0 means everything went ok, so a device was found.
                alive = True
                
            # If either ping or arping found a device:
            if alive:
                output = arp(ip_address)
                if self.DEBUG:
                    print("-ALIVE: " + str(output))
                mac_addresses = re.findall(r'(([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})', output)

                now = int(time.time())

                if len(mac_addresses) > 0:
                    mac_address = mac_addresses[0][0]
                    mac_address = ':'.join([
                        # Left pad the MAC address parts with '0' in case of
                        # invalid output (as on macOS)
                        '0' * (2 - len(x)) + x for x in mac_address.split(':')
                    ])

                    if not valid_mac(mac_address):
                        continue

                    mac_short = mac_address.replace(":", "")
                    _id = 'presence-{}'.format(mac_short)
                    if self.DEBUG:
                        print("early mac = " + mac_address)

                    # Get the basic variables
                    found_device_name = output.split(' ')[0]
                    if self.DEBUG:
                        print("early found device name = " + found_device_name)

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
                       
                    if self.DEBUG: 
                        print("--mac:  " + mac_address)
                        print("--name: " + found_device_name)
                        print("--_id: " + _id)
                    
                    # Create or update items in the previously_found dictionary
                    try:
                        possible_name = ''
                        if _id not in self.previously_found:
                            if self.DEBUG:
                                print("Adding")
                            self.should_save = True # We will be adding this new device to the list, and then save that updated list.

                            i = 2 # We skip "1" as a number. So we will get names like "Apple" and then "Apple 2", "Apple 3", and so on.
                            possible_name = found_device_name
                            could_be_same_same = True

                            while could_be_same_same is True: # We check if this name already exists in the list of previously found devices.
                                could_be_same_same = False
                                for item in self.previously_found.values():
                                    if possible_name == item['name']: # The name already existed in the list, so we change it a little bit and compare again.
                                        could_be_same_same = True
                                        #print("names collided")
                                        possible_name = found_device_name + " " + str(i)
                                        i += 1

                            self.previously_found[str(_id)] = {} # adding it to the internal object
                            self.previously_found[key]['arpa_time'] = now # creation time
                     
                        self.previously_found[_id]['lastseen'] = now
                        self.previously_found[_id]['name'] = str(possible_name)
                        self.previously_found[_id]['ip'] = ip_address
                        self.previously_found[_id]['mac_address'] = ip_address
                        
                            
                        #possible_name = self.previously_found[_id]['name']
                    except Exception as ex:
                        print("Brute force scan: error updating items in the previously_found dictionary: " + str(ex))





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





    def add_from_config(self):
        """Attempt to add all configured devices."""

        try:
            database = Database(self.addon_name)

            if not database.open():
                return

            config = database.load_config()
            database.close()

            if not config or 'Time window' not in config:
                print("Required variables not found in config database?")
                return

            try:
                self.DEBUG = bool(config['Debugging']) # The variable is clamped: it is forced to be between 1 and 50.
            except:
                print("No debugging preference was found in the settings")
            
            try:
                if str(config['Target IP']) != "":
                    self.own_ip = str(config['Target IP']) # Can be used to override normal behaviour (which is to scan the controller's neighbours), and target a very different group of IP addresses.
            except:
                if self.DEBUG:
                    print("No target IP address was found in the settings")
            
            try:
                self.time_window = clamp(int(config['Time window']), 1, 10800) # In minutes. 'Grace period' could also be a good name.
            except:
                print("No time window preference was found in the settings. Will use default.")
            
            if self.DEBUG:
                print("Time window value from settings page: " + str(self.time_window))
            
            #if 'Arping' in config:
            #    self.arping = config['Arping'] # boolean.

            print("Config loaded ok")

        except:
            print("Error getting config data from database")



    def save_to_json(self):
        """Save found devices to json file."""
        try:
            print("Saving updated list of found devices to json file")
            #if self.previously_found:
            with open(self.persistence_file_path, 'w') as fp:
                json.dump(self.previously_found, fp)
        except:
            print("Saving to json file failed")


    def start_pairing(self, timeout):
        """Starting the pairing process."""
        self.arpa_scan()
        self.should_brute_force_scan = True

    def cancel_pairing(self):
        """Cancel the pairing process."""
        self.save_to_json()





"""Presence Detection adapter for WebThings Gateway."""



import os
import re
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))
import json
import time
import socket
from datetime import datetime, timedelta
import threading
import subprocess
from gateway_addon import Adapter, Database

from .presence_device import PresenceDevice
from .util import *


_TIMEOUT = 3

_CONFIG_PATHS = [
    os.path.join(os.path.expanduser('~'), '.webthings', 'config'),
]

if 'WEBTHINGS_HOME' in os.environ:
    _CONFIG_PATHS.insert(0, os.path.join(os.environ['WEBTHINGS_HOME'], 'config'))


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


        #print("self.user_profile['baseDir'] = " + self.user_profile['baseDir'])

        self.DEBUG = True
        #self.memory_in_weeks = 10 # How many weeks a device will be remembered as a possible device.
        self.time_window = 10 # How many minutes should a device be away before we consider it away?

        self.own_ip = None # We scan only scan if the device itself has an IP address.
        
        self.add_from_config() # Here we get data from the settings in the Gateway interface.
           
        #self.DEBUG = False
           
        try:
            if self.own_ip == None:
                self.own_ip = get_ip()
        except:
            print("Could not get actual own IP address")
        
     
        self.should_brute_force_scan = True
        self.busy_doing_brute_force_scan = False
        self.last_brute_force_scan_time = 0             # Allows the add-on to start a brute force scan right away.
        self.seconds_between_brute_force_scans = 1800  #1800  # 30 minutes     
        
        self.running = True
        self.saved_devices = []

        self.addon_path =  os.path.join(self.user_profile['addonsDir'], self.addon_name)
        self.persistence_file_path = os.path.join(self.user_profile['dataDir'], self.addon_name,'persistence.json')

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
                with open(self.persistence_file_path, 'w') as f:
                    f.write('{}')
            except Exception as ex:
                print("failed to create empty persistence file: " + str(ex))
        
        self.previous_found_devices_length = len(self.previously_found)

        # Reset all the lastseen data from the persistence file, since it could be out of date.
        for key in self.previously_found:
            try:
                if 'lastseen' in self.previously_found[key]:
                    self.previously_found[key]['lastseen'] = None
            except Exception as ex:
                print("Error setting lastseen of previously_found devices from persistence to None: " + str(ex))

        
        # First scan
        time.sleep(2) # wait a bit before doing the quick scan. The gateway will pre-populate based on the 'handle-device-saved' method.
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
            arpa_list = self.arpa()
            if self.DEBUG:
                print("Arpa light scan results: " + str(arpa_list))
                print("arpa list length: " + str(len(arpa_list)))
                
            for key in arpa_list:
                if self.DEBUG:
                    print("Analyzing ARPA item: " + str(arpa_list[key]))
                
                try:
                    if key not in self.previously_found:
                        if self.DEBUG:
                            print("-Adding to previously found list")
            
                        self.previously_found[key] = {} # adding empty device to the previously found dictionary
                        self.previously_found[key]['name'] = arpa_list[key]['name']
                        self.previously_found[key]['arpa_time'] = time.time() #arpa_list[key]['arpa_time'] #timestamp of initiation
                        self.previously_found[key]['lastseen'] = None #arpa_list[key]['arpa_time'] #timestamp of initiation
                        self.previously_found[key]['ip'] = arpa_list[key]['ip']
                        self.previously_found[key]['mac_address'] = arpa_list[key]['mac_address']
                        
                        self.should_save = True # We will be adding this new device to the list, and then save that updated list.
                        
                    else:
                        # Maybe we found a better name this time.
                        if arpa_list[key]['name'] not in ("","?","unknown"): # superfluous?
                            if self.DEBUG:
                                print("ARPA scan may have found a better hostname, adding it to the previously_found devices dictionary")
                            self.previously_found[key]['name'] = arpa_list[key]['name']
                        
                        try:
                            self.previously_found[key]['ip'] = arpa_list[key]['ip']
                        except:
                            print("Error, could not update IP from arpa scan")
                        
                except Exception as ex:
                    print("Error while analysing ARPA scan result item: " + str(ex))
                    
        except Exception as ex:
            print("Error doing light arpa scan: " + str(ex))
        if self.DEBUG:
            print("light scan using arp -a is done")
        
        
    def brute_force_scan(self):
        """ Goes over every possible IP adddress in the local network (1-254) to check if it responds to a ping or arping request """
        #while self.running:
        if self.busy_doing_brute_force_scan == False and self.should_brute_force_scan == True:
            self.busy_doing_brute_force_scan = True
            self.should_brute_force_scan = False
            self.last_brute_force_scan_time = time.time()
            if self.DEBUG:
                print("Initiating a brute force scan of the entire local network")
                
            try:
            
                if self.DEBUG:
                    print("OWN IP = " + str(self.own_ip))
                if valid_ip(self.own_ip):
                    #while True:
                    #def split_processing(items, num_splits=4):
                    old_previous_found_count = len(self.previously_found)
                    thread_count = 3 #2 #5
                    split_size = 85 #127 #51
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
                    if len(self.previously_found) != old_previous_found_count:
                        self.should_save = True
                
                    if self.should_save: # This is the only time the json file is stored.    
                        self.save_to_json()
                
                # Remove devices that haven't been spotted in a long time.
                #list(fdist1.keys())
                
                current_keys = [None] * len(list(self.previously_found.keys()));    
 
                #Copying all elements of one array into another    
                for a in range(0, len(list(self.previously_found.keys()))):    
                    current_keys[a] = list(self.previously_found.keys())[a];
                
                #current_keys = self.previously_found.keys()
                for key in current_keys:
                    try:
                        if time.time() - self.previously_found[key]['arpa_time'] > 86400 and key not in self.saved_devices:
                            if self.DEBUG:
                                print("Removing devices from found devices list because it hasn't been spotted in a day, and it's not a device the user has imported.")
                            del self.previously_found[key]
                    except Exception as ex:
                        if self.DEBUG:
                            print("Could not remove old device: " + str(ex))


            except Exception as ex:
                print("Error doing brute force scan: " + str(ex))
                self.busy_doing_brute_force_scan = False
                self.should_brute_force_scan = False
                self.last_brute_force_scan_time = time.time()



    def clock(self):
        """ Runs continuously and scans IP addresses that the user has accepted as things """
        if self.DEBUG:
            print("clock thread init")
            
        succesfully_found = 0 # If all devices the user cares about are actually present, then no deep scan is necessary.
        while self.running:

            try:
                if time.time() - self.last_brute_force_scan_time > self.seconds_between_brute_force_scans:
                    if self.DEBUG:
                        print("30 minutes have passed since the last brute force scan.")
                    self.last_brute_force_scan_time = time.time()
                    if succesfully_found != len(self.saved_devices): # Avoid doing a deep scan if all devices are present
                        if self.busy_doing_brute_force_scan == False:
                            if self.DEBUG:
                                print("Should brute force scan is now set to true.")
                            self.should_brute_force_scan = True
                        else:
                            if self.DEBUG:
                                print("Should brute force scan, but already doing brute force scan")
                    else:
                        if self.DEBUG:
                            print("all devices present and accounted for. Will skip brute force scan.")
            except Exception as ex:
                print("Clock: error running periodic deep scan: " + str(ex))

            succesfully_found = 0
            try:
                #if self.DEBUG:
                    #print("")
                    #print("CLOCK TICK")
                        

                
                for key in self.previously_found:
                    # Update device's last seen properties
                    try:
                        # Make sure all devices and properties exist. Should be superfluous really.
                        #print("clock - str(key) = " + str(key) + " has " + str(self.previously_found[key]))
                        if str(key) not in self.devices:
                            
                            #print(str(self.previously_found[str(key)]) + " was not turned into an internal devices object yet.")
                            detail = "..."
                            try:
                                detail = self.previously_found[key]['ip']
                            except:
                                if self.DEBUG:
                                    print("No IP address in previously found list (yet)")
                                continue
                                
                            new_name = "Unknown"
                            try:
                                new_name = self.previously_found[key]['name']
                            except:
                                if self.DEBUG:
                                    print("No name present in previously found list")
                            
                            if new_name == "Unknown" or new_name == "?" or new_name == "":
                                if self.DEBUG:
                                    print("No good name found yet, skipping device generation and update")
                                continue
                                
                            self._add_device(key, new_name, detail) # The device did not exist yet, so we're creating it.

                        try:
                            if self.previously_found[key]['lastseen'] != 0 and self.previously_found[key]['lastseen'] != None:
                                minutes_ago = int((time.time() - self.previously_found[key]['lastseen']) / 60)
                            else:
                                minutes_ago = None
                        except Exception as ex:
                            minutes_ago = None
                            if self.DEBUG:
                                print("Minutes ago issue: " + str(ex))
                        
                        try:
                            if 'minutes_ago' not in self.devices[key].properties:
                                if self.DEBUG:
                                    print("+ Adding minutes ago property to presence device")
                                self.devices[key].add_integer_child('minutes_ago', "Minutes ago last seen", minutes_ago)
                            elif minutes_ago != None:
                                self.devices[key].properties['minutes_ago'].update(minutes_ago)
                        except Exception as ex:
                            print("Could not add minutes_ago property" + str(ex))
                            
                        try:
                            if minutes_ago != None:
                                if minutes_ago > self.time_window:
                                    recently = False
                                else:
                                    recently = True
                                if 'recently1' not in self.devices[key].properties:
                                    if self.DEBUG:
                                        print("+ Adding recently spotted property to presence device")
                                    self.devices[key].add_boolean_child('recently1', "Recently spotted", recently)
                                else:
                                    self.devices[key].properties['recently1'].update(recently)
                        except Exception as ex:
                            print("Could not add recently spotted property" + str(ex))

                    except Exception as ex:
                        print("Could not create or update property. Error: " + str(ex))    
                    
                    
                # Scan the devices the user cares about
                for key in self.saved_devices:
                    if str(key) not in self.previously_found:
                        if self.DEBUG:
                            print("Saved thing was not found through scanning yet (not yet added to previously_found), skipping update attempt")
                        continue
                    if self.DEBUG:
                        print("")
                        print("CLOCK: key from saved devices:" + str(key))

                    if self.DEBUG:
                        print("Saved device ID " + str(key) + " was also in previously found list. Trying scan.")
                    
                    # Try doing a Ping and then optionally an Arping request if there is a valid IP Address
                    try:
                        if self.DEBUG:
                            print("IP from previously found list: " + str(self.previously_found[key]['ip']))
                        if 'ip' in self.previously_found[key]:
                            if ping(self.previously_found[key]['ip'],1):
                                if self.DEBUG:
                                    print(">> Ping could not find device at " + str(self.previously_found[key]['ip']) + ". Maybe Arping can.")
                                try:
                                    if not self.previously_found[key]['ip'] in self.devices_excluding_arping and not self.previously_found[key]['mac_address'] in self.devices_excluding_arping and arping(self.previously_found[key]['ip'], 1) == 0:
                                        self.previously_found[key]['lastseen'] = int(time.time())
                                        if self.DEBUG:
                                            print(">> Arping found it.")
                                        succesfully_found += 1
                                    else:
                                        if self.DEBUG:
                                            print(">> Ping also could not find the device.")
                                except Exception as ex:
                                    print("Error trying Arping: " + str(ex))
                            else:
                                if self.DEBUG:
                                    print(">> Ping found device")
                                self.previously_found[key]['lastseen'] = int(time.time())
                                succesfully_found += 1
                        
                    except Exception as ex:
                        if self.DEBUG:
                            print("Was not able to scan device from saved_devices list: " + str(ex))
                    
                    
            except Exception as ex:
                print("Clock thread error: " + str(ex))
            
            if self.DEBUG:
                print("Waiting 5 seconds before scanning all devices again")
            time.sleep(5)



    def handle_device_saved(self, device_id, device):
        """User saved a thing. Also called when the add-on starts."""
        if device_id.startswith('presence'):
            if self.DEBUG:
                print("handle_device_saved. device_id = " + str(device_id) + ", device = " + str(device))

            if device_id not in self.saved_devices:
                #print("Adding to saved_devices list: " + str(device_id.split("-")[1]))
                if self.DEBUG:
                    print("Added " + str(device['title']) + " to saved devices list")
                    
                original_title = "Unknown"
                try:
                    if str(device['title']) != "":
                        original_title = str(device['title'])
                except:
                    print("Error getting original_title from data provided by the Gateway")
                    
                #self.saved_devices.append({device_id:{'name':original_title}})
                self.saved_devices.append(device_id)
                
                try:
                    #pass
                    if device_id not in self.previously_found:
                        if self.DEBUG:
                            print("Populating previously_found from handle_device_saved")
                        self.previously_found[device_id] = {}
                        self.previously_found[device_id]['name'] = str(device['title'])
                        self.previously_found[device_id]['lastseen'] = None   
                        self.previously_found[device_id]['arpa_time'] = int(time.time())
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
            print("Removing presence detection device")

        try:
            #print("THING TO REMOVE:" + str(self.devices[device_id]))
            del self.previously_found[device_id]
            #print("2")
            obj = self.get_device(device_id)
            #print("3")
            self.handle_device_removed(obj)
            if self.DEBUG:
                print("Succesfully removed presence detection device")
        except:
            print("Removing presence detection thing failed")
        #del self.devices[device_id]
        self.should_save = True # saving changes to the json persistence file



    def scan(self, start, end):
        """Part of the brute force scanning function, which splits out the scanning over multiple threads."""
        #self.should_save = False # We only save found devices to a file if new devices have been found during this scan.

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
            else:
                try:
                    if arping(ip_address, ping_count) == 0: # 0 means everything went ok, so a device was found.
                        alive = True
                except Exception as ex:
                    print("Error trying Arping: " + str(ex))
                
            # If either ping or arping found a device:
            try:
                if alive:
                    output = arp(ip_address)
                    if self.DEBUG:
                        print(str(ip_address) + " IS ALIVE: " + str(output))
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
                            if self.DEBUG:
                                print("Deep scan: MAC address was not valid")
                            continue

                        mac_short = mac_address.replace(":", "")
                        _id = 'presence-{}'.format(mac_short)
                        if self.DEBUG:
                            print("early mac = " + mac_address)

                        # Get the basic variables
                        found_device_name = output.split(' ')[0]
                        if self.DEBUG:
                            print("early found device name = " + found_device_name)
                        
                        try:
                            possible_name = self.get_optimal_name(ip_address, found_device_name, mac_address)
                        except:
                            if self.DEBUG:
                                print("Reverting to found_device_name instead of optimal name")
                            possible_name = "Presence - " + str(found_device_name)
                            
                        if self.DEBUG:
                            print("optimal possible name = " + possible_name)

                        if _id not in self.previously_found:
                            self.previously_found[str(_id)] = {} # adding it to the internal object
                            

                        if self.DEBUG:
                            print("--mac:  " + mac_address)
                            print("--name: " + possible_name)
                            print("--_id: " + _id)
                     
                        self.previously_found[_id]['arpa_time'] = now # creation time
                        self.previously_found[_id]['mac_address'] = mac_address
                     
                        self.previously_found[_id]['lastseen'] = now    
                        self.previously_found[_id]['name'] = str(possible_name) # The name may be better, or it may have changed.
                        self.previously_found[_id]['ip'] = ip_address
                        
                    
                
                    
            except Exception as ex:
                print("Brute force scan: error updating items in the previously_found dictionary: " + str(ex))

            time.sleep(5)



    def get_optimal_name(self,ip_address,found_device_name="",mac_address=""):

        # Try to get hostname
        nmb_result = ""
        
        #try:
            #nmb_result = socket.gethostbyaddr(ip_address)
            #nmb_result = hostname_lookup(ip_address)
        #    nmb_result,alias,addresslist = hostname_lookup(ip_address)
        #    print("socket.gethostbyaddr(ip_address) gave: " + str(nmb_result))
        #except Exception as ex:
        #    print("socket.gethostbyaddr(ip_address) error: " + str(ex))
        
        
        try:
            nmb_result = nmblookup(ip_address)
            if self.DEBUG:
                print("nmblookup result = " + str(nmb_result))
        except Exception as ex:
            if self.DEBUG:
                print("Error doing nmblookup: " + str(ex))
        
        if nmb_result == "":
            if self.DEBUG:
                print("NMB lookup result was an empty string")
                
            # Round 2: analyse MAC address
            if found_device_name == '?' or found_device_name == '' or valid_ip(found_device_name):
            
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

                found_device_name = vendor
                
        else:
            found_device_name = nmb_result
               
        # At this point we definitely have something.
        
        found_device_name = "Presence - " + found_device_name
        possible_name = found_device_name
        if self.DEBUG: 
            print("--possible name (may be duplicate):  " + str(found_device_name))
        
        # Create or update items in the previously_found dictionary
        try:
            
            mac_short = mac_address.replace(":", "")
            _id = 'presence-{}'.format(mac_short)
            
            #for item in self.previously_found:
                #if self.DEBUG:
                #    print("ADDING NEW FOUND DEVICE TO FOUND DEVICES LIST")
                #self.should_save = True # We will be adding this new device to the list, and then save that updated list.

            i = 2 # We skip "1" as a number. So we will get names like "Apple" and then "Apple 2", "Apple 3", and so on.
            #possible_name = found_device_name
            could_be_same_same = True

            while could_be_same_same is True: # We check if this name already exists in the list of previously found devices.
                could_be_same_same = False
                try:
                    for key in self.previously_found:
                        if self.DEBUG:
                            print("-checking possible name '" + str(possible_name) + "' against: " + str(self.previously_found[key]['name']))
                            print("--prev found device key = " + str(key))
                        
                        # We skip checking for name duplication if the potential new device is the exact same device, so it would be logical if they had the same name.
                        if str(key) == str(_id):
                            if self.DEBUG:
                                print("key == _id")
                            if possible_name == str(self.previously_found[key]['name']):
                                if self.DEBUG:
                                    print("the new name is the same as the old for this mac-address")
                                #continue
                                break
                        
                        if possible_name == str(self.previously_found[key]['name']): # The name already existed somewhere in the list, so we change it a little bit and compare again.
                            could_be_same_same = True
                            if self.DEBUG:
                                print("-names collided: " + str(possible_name))
                            possible_name = found_device_name + " " + str(i)
                            if self.DEBUG:
                                print("-now testing new name: " + str(possible_name))
                            i += 1 # up the count for a potential next round
                            if i > 200:
                                if self.DEBUG:
                                    print("Reached 200 limit in while loop") # if the user has 200 of the same device, that's incredible.
                                break
                except Exception as ex:
                    print("Error doing name check in while loop: " + str(ex))
        except Exception as ex:
            print("Error in name duplicate check: " + str(ex))
        
        return possible_name
        
        
        

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
                print("Error: required variables not found in config database. Check the addon's settings.")
                return

            try:
                self.DEBUG = bool(config['Debugging']) # The variable is clamped: it is forced to be between 1 and 50.
            except:
                print("No debugging preference was found in the settings")
            
            
            # Target IP
            # Can be used to override normal behaviour (which is to scan the controller's neighbours), and target a very different group of IP addresses.
            if 'Target IP' in config:
                try:
                    if str(config['Target IP']) != "":
                        potential_ip = str(config['Target IP'])
                        if valid_ip(potential_ip):
                            self.own_ip = potential_ip
                            print("A target IP was in settings")
                        else:
                            print("This addon does not understand '" + str(potential_ip) + "' as a valid IP address. Go to the add-on settings page to fix this. For now, the addon will try to detect and use the system's IP address as a base instead.")
                except:
                    print("Error handling Target IP setting")
            else:
                if self.DEBUG:
                    print("No target IP address was available in the settings data")


            if 'Time window' in config:
                try:
                    self.time_window = clamp(int(config['Time window']), 1, 10800) # In minutes. 'Grace period' could also be a good name.
                    print("Time window value from settings page: " + str(self.time_window))
                except:
                    print("No time window preference was found in the settings. Will use default.")


            if 'Devices excluding arping' in config:
                try:
                    self.devices_excluding_arping = config['Devices excluding arping']    
                    print("Devices excluding ARPing from settings page: " + str(self.devices_excluding_arping))
                except:
                    print("No ping devices were found in the settings.")
            


        except:
            print("Error getting config data from database. Check the add-on's settings page for any issues.")



    def save_to_json(self):
        """Save found devices to json file."""
        try:
            if self.DEBUG:
                print("Saving updated list of found devices to json file")
            #if self.previously_found:
            #with open(self.persistence_file_path, 'w') as fp:
                #json.dump(self.previously_found, fp)
                
            j = json.dumps(self.previously_found, indent=4) # Pretty printing to the file
            f = open(self.persistence_file_path, 'w')
            print(j, file=f)
            f.close()
                
        except Exception as ex:
            print("Saving to json file failed: " + str(ex))
        self.should_save = False


    def start_pairing(self, timeout):
        """Starting the pairing process."""
        self.arpa_scan()
        if self.busy_doing_brute_force_scan == False:
            self.should_brute_force_scan = True

    def cancel_pairing(self):
        """Cancel the pairing process."""
        self.save_to_json()



    #
    #  This gives a quick first initial impression of the network.
    #
    def arpa(self):
        command = "arp -a"
        device_list = {}
        try:
            result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
            for line in result.stdout.split('\n'):
                if not "<incomplete>" in line and len(line) > 10:
                    name = "?"
                    mac_short = ""
                    try:
                        mac_address_list = re.findall(r'(([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})', str(line))[0]
                        #print(str(mac_address_list))
                        mac_address = str(mac_address_list[0])
                        #print(str(mac_address))
                        mac_short = str(mac_address.replace(":", ""))
                        _id = 'presence-{}'.format(mac_short)
                    except Exception as ex:
                        print("getting mac from arp -a line failed: " + str(ex))
                    
                    try:
                        ip_address_list = re.findall(r'(?:\d{1,3}\.)+(?:\d{1,3})', str(line))
                        #print("ip_address_list = " + str(ip_address_list))
                        ip_address = str(ip_address_list[0])
                        if not valid_ip(ip_address):
                            continue
                    except Exception as ex:
                        print("no IP address in line: " + str(ex))
                        
                    try:
                        found_device_name = str(line.split(' (')[0])
                        
                        possible_name = self.get_optimal_name(ip_address, found_device_name, mac_address)
                        
                        
                    except Exception as ex:
                        print("Error: could not get name from arp -a line: " + str(ex))
                        
                    if mac_short != "":
                        #print("util: arp: mac in line: " + line)
                        #item = {'ip':ip_address,'mac':mac_address,'name':name, 'mac_short':mac_address.replace(":", "")}
                        #return str(line)
                        
                        device_list[_id] = {'ip':ip_address,'mac_address':mac_address,'name':possible_name,'arpa_time':int(time.time()),'lastseen':None}
                        #print("device_list = " + str(device_list))
            #return str(result.stdout)

        except Exception as ex:
            print("Arp -a error: " + str(ex))
            #result = 'error'
        return device_list
        #return str(subprocess.check_output(command, shell=True).decode())





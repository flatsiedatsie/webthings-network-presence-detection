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
from gateway_addon import Adapter, Database, Action

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
        
        self.DEBUG = False

        #print("self.user_profile['baseDir'] = " + self.user_profile['baseDir'])
     
        #self.memory_in_weeks = 10 # How many weeks a device will be remembered as a possible device.
        self.time_window = 10 # How many minutes should a device be away before we consider it away?

        self.own_ip = None # We scan only scan if the device itself has an IP address.
        
        self.prefered_interface = "eth0"
        self.selected_interface = "eth0"
        
        self.busy_doing_arpa_scan = False
        self.devices_excluding_arping = ""
        
        self.use_brute_force_scan = False; # was used for continuous brute force scanning. This has been deprecated.
        self.should_brute_force_scan = True
        self.busy_doing_brute_force_scan = False
        self.last_brute_force_scan_time = 0             # Allows the add-on to start a brute force scan right away.
        self.seconds_between_brute_force_scans = 1800  #1800  # 30 minutes     

        # AVAHI
        self.last_avahi_scan_time = 0
        self.avahi_lookup_table = {}
        
        
        self.running = True
        self.saved_devices = []
        self.not_seen_since = {} # used to determine if a device hasn't responded for a long time

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
            print("Failed to load persistent data JSON file, generating new one.")
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
                self.not_seen_since[key] = None
            except Exception as ex:
                print("Error setting lastseen of previously_found devices from persistence to None: " + str(ex))
        
        
        self.add_from_config() # Here we get data from the settings in the Gateway interface.

        if not self.DEBUG:
            time.sleep(5) # give it a few more seconds to make sure the network is up
           
        self.selected_interface = "wlan0"
        self.select_interface() # checks if the preference is possible.
        
        if self.DEBUG:
            print("selected interface = " + str(self.selected_interface))
        
        #self.DEBUG = False
           
        try:
            if self.own_ip == None:
                self.own_ip = get_ip()
        except:
            print("Could not get actual own IP address")
        
        # First scan
        time.sleep(2) # wait a bit before doing the quick scan. The gateway will pre-populate based on the 'handle-device-saved' method.
        self.arpa_scan() # get initial list of devices from arp -a

        if self.DEBUG:
            print("Starting the clock thread")
        try:
            t = threading.Thread(target=self.clock)
            t.daemon = True
            t.start()
        except:
            print("Error starting the continous light scan thread")

        #done = self.brute_force_scan()

        """
        # This is no longer a continously running thread. Brute force scan only runs when the user clicks on the pair button.
        if self.use_brute_force_scan:
            if self.DEBUG:
                print("Starting the brute force scan thread")
            try:
                b = threading.Thread(target=self.brute_force_scan)
                b.daemon = True
                b.start()
            except:
                print("Error starting the brute force scan thread")
        """
        
        
        

    def add_from_config(self):
        """Attempt to load addon settings."""

        try:
            database = Database(self.addon_name)

            if not database.open():
                return

            config = database.load_config()
            database.close()


        except Exception as ex:
            print("Error getting config data from database. Check the add-on's settings page for any issues. Error: " + str(ex))
            self.close_proxy()

        
        try:
            if not config:
                print("Error: required variables not found in config database. Check the addon's settings.")
                return


            if 'Debugging' in config:
                self.DEBUG = bool(config['Debugging'])
            
            
            # Target IP
            # Can be used to override normal behaviour (which is to scan the controller's neighbours), and target a very different group of IP addresses.
            if 'Target IP' in config:
                try:
                    potential_ip = str(config['Target IP'])
                    if potential_ip != "":
                        if valid_ip(potential_ip):
                            self.own_ip = potential_ip
                            print("Using target IP from addon settings")
                        else:
                            if self.DEBUG:
                                print("This addon does not understand '" + str(potential_ip) + "' as a valid IP address. Go to the add-on settings page to fix this. For now, the addon will try to detect and use the system's IP address as a base instead.")
                        
                except exception as ex:
                    print("Error handling Target IP setting: " + str(ex))
            else:
                if self.DEBUG:
                    print("No target IP address was available in the settings data")

            # Network interface preference
            if 'Network interface' in config:
                if str(config['Network interface']) != "":
                    if str(config['Network interface']) == "prefer wired":
                        self.prefered_interface = "eth0"
                    if str(config['Network interface']) == "prefer wireless":
                        self.prefered_interface = "wlan0"

            # how many minutes should "not recently spotted" be?
            if 'Time window' in config:
                try:
                    if config['Time window'] != None and config['Time window'] != '':
                        self.time_window = clamp(int(config['Time window']), 1, 10800) # In minutes. 'Grace period' could also be a good name.
                        if self.DEBUG:
                            print("Using time window value from settings: " + str(self.time_window))
                except:
                    print("No time window preference was found in the settings. Will use default.")

            # Should brute force scans be attempted?
            if 'Use brute force scanning' in config:
                self.use_brute_force = bool(config['Use brute force scanning'])

            if 'Addresses to not arping' in config:
                try:
                    self.devices_excluding_arping = str(config['Devices excluding arping'])  
                    if self.DEBUG:
                        print("Devices excluding ARPing from settings: " + str(self.devices_excluding_arping))
                except:
                    if self.DEBUG:
                        print("No addresses to not arping were found in the settings.")

        except Exception as ex:
            print("Error getting config data from database. Check the add-on's settings page for any issues. Error: " + str(ex))
            self.close_proxy()
            
            





    def clock(self):
        """ Runs continuously and scans IP addresses that the user has accepted as things """
        if self.DEBUG:
            print("clock thread init")
        time.sleep(5)
        last_run = 0
        succesfully_found = 0 # If all devices the user cares about are actually present, then no deep scan is necessary.
        while self.running:
            last_run = time.time()
            
            if self.DEBUG:
                print("Clock TICK")
            
            if self.use_brute_force_scan:
                try:
                
                    if time.time() - self.last_brute_force_scan_time > self.seconds_between_brute_force_scans:
                        if self.DEBUG:
                            print("enough time has passed since the last brute force scan.")
                        self.last_brute_force_scan_time = time.time()
                        if succesfully_found != len(self.saved_devices): # Avoid doing a deep scan if all devices are present
                            if self.busy_doing_brute_force_scan == False:
                                if self.DEBUG:
                                    print("Should brute force scan is now set to true.")
                                self.should_brute_force_scan = True
                                #self.brute_force_scan()
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
                for key in self.previously_found:
                    if self.DEBUG:
                        print("clock -> " + str(key))
                    # Update device's last seen properties
                    try:
                        # Make sure all devices and properties exist. Should be superfluous really.
                        if self.DEBUG:
                            print("clock - str(key) = " + str(key) + " has " + str(self.previously_found[key]))
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

                        #
                        #  MINUTES AGO
                        #

                        try:
                            if self.previously_found[key]['lastseen'] != 0 and self.previously_found[key]['lastseen'] != None:
                                if self.DEBUG:
                                    print("-adding a minute to minutes_ago variable")
                                minutes_ago = int( (time.time() - self.previously_found[key]['lastseen']) / 60 )
                            else:
                                minutes_ago = None
                                if self.DEBUG:
                                    print("                             --> MINUTES AGO IS NONE <--")
                                    
                            #should_update_last_seen = True
                            #if 'data_mute_end_time' in self.previously_found[key]:
                            #    if self.DEBUG:
                            #        print("data_mute_end_time spotted")
                            #    if self.previously_found[key]['data_mute_end_time'] > time.time():
                            #        if self.DEBUG:
                            #            print("clock: skipping last_seen increment of muted device " + str(self.previously_found[key]['name']))
                            #        minutes_ago = None
                                    #should_update_last_seen = False
                            
                                    
                        except Exception as ex:
                            minutes_ago = None
                            if self.DEBUG:
                                print("Clock: minutes ago issue: " + str(ex))
                        
                        
                        try:
                            #if should_update_last_seen:
                            if 'minutes_ago' not in self.devices[key].properties:
                                if self.DEBUG:
                                    print("+ Adding minutes ago property to presence device, with value: " + str(minutes_ago))
                                self.devices[key].add_integer_child("minutes_ago", "Minutes ago last seen", minutes_ago)
                            elif minutes_ago != None:
                                if self.DEBUG:
                                    print("Minutes_ago of " + str(self.previously_found[key]['name']) + " is: " + str(minutes_ago))
                            
                            if self.DEBUG:
                                print("updating minutes ago")
                            self.devices[key].properties["minutes_ago"].update(minutes_ago)
                                    
                        except Exception as ex:
                            print("Could not add minutes_ago property" + str(ex))
                        
                        
                        #
                        #  RECENTLY SPOTTED
                        #
                        
                        try:
                            recently = None
                            if minutes_ago != None:
                                if self.DEBUG:
                                    print("minutes_ago was not None, it was: " + str(minutes_ago))
                                if minutes_ago > self.time_window:
                                    recently = False
                                else:
                                    recently = True
                                    
                            else:
                                if self.DEBUG:
                                    print("minutes_ago was None, so not determining recently state (will be None too)")
                                    
                            if 'recently1' not in self.devices[key].properties:
                                if self.DEBUG:
                                    print("+ Adding recently spotted property to presence device")
                                self.devices[key].add_boolean_child("recently1", "Recently spotted", recently, True, "BooleanProperty") # name, title, value, readOnly, @type
                            else:
                                self.devices[key].properties["recently1"].update(recently)
                        except Exception as ex:
                            print("Could not add recently spotted property" + str(ex))



                        #
                        #  DATA COLLECTION
                        #
                        
                        if 'data-collection' not in self.devices[key].properties:
                            if self.DEBUG:
                                print("+ Adding data-collection property to presence device")
                                
                            data_collection_state = True
                            if 'data-collection' in self.previously_found[key]:
                                if self.DEBUG:
                                    print("+ Found a data-collection preference in the previously_found data")
                                data_collection_state = self.previously_found[key]['data-collection']
                            
                            self.devices[key].add_boolean_child("data-collection", "Data collection", data_collection_state, False, "") # name, title, value, readOnly, @type


                        #if 'data-temporary-mute' not in self.devices[key].properties:
                        #    if self.DEBUG:
                        #        print("+ Adding recently spotted property to presence device")
                        #    
                        #    self.devices[key].add_boolean_child("data-temporary-mute", "Temporary data mute", False, False, "PushedProperty") # name, title, value, readOnly, @type
                        
            

                    except Exception as ex:
                        print("Could not create or update property. Error: " + str(ex))    
                    
                
                
                
                # Scan the devices the user cares about (once a minute)
                for key in self.saved_devices:
                    if self.DEBUG:
                        print("")
                        print("clock: scanning every minute: key in saved_devices: " + str(key))
                    
                    if str(key) not in self.previously_found:
                        if self.DEBUG:
                            print("Saved thing was not found through scanning yet (not yet added to previously_found), skipping update attempt")
                        continue
                        
                    if self.DEBUG:
                        print("clock: scanning every minute: human readable name: " + str(self.previously_found[key]['name']))


                    #if self.DEBUG:
                    #    print("Saved device ID " + str(key) + " was also in previously found list. Trying scan.")
                    
                    # Try doing a Ping and then optionally an Arping request if there is a valid IP Address
                    try:
                        #if self.DEBUG:
                        #    print("IP from previously found list: " + str(self.previously_found[key]['ip']))
                            
                        #self.DEBUG = True
                            
                            
                        #
                        #  LOOKING FOR REASONS TO SKIP PINGING
                        #
                        
                        should_ping = True
                        
                        # Data collection disabled?
                        if 'data-collection' in self.previously_found[key]:
                            if self.previously_found[key]['data-collection'] == False:
                                if self.DEBUG:
                                    print("clock: skipping pinging of " + str(self.previously_found[key]['name']) + " because data collection is disabled")
                                should_ping = False
                        else:
                            if self.DEBUG:
                                print("clock: data-collection value did not exist yet in this thing, adding it now.")
                            self.previously_found[key]['data-collection'] = True
                            self.should_save = True
                        
                                
                        # Data-mute enabled?
                        if 'data_mute_end_time' in self.previously_found[key]:
                            if self.DEBUG:
                                print("data_mute_end_time spotted: " + str(self.previously_found[key]['data_mute_end_time']) + ". delta: " + str(self.previously_found[key]['data_mute_end_time'] - time.time()))
                            if self.previously_found[key]['data_mute_end_time'] > time.time():
                                if self.DEBUG:
                                    print("clock: skipping pinging of muted device " + str(self.previously_found[key]['name']))
                                
                                self.previously_found[key]['lastseen'] = None
                                self.devices[key].properties["recently1"].update(None)
                                should_ping = False
                        else:
                            if self.DEBUG:
                                print("clock: mute_end_time value did not exist yet in this thing, adding it now.")
                            self.previously_found[key]['data_mute_end_time'] = 0
                            self.should_save = True
                            
                                
                        # To ping or not to ping
                        if should_ping == True:
                            if self.DEBUG:
                                print("- Should ping is True. Will ping/arping now.")
                            if 'ip' in self.previously_found[key]:
                                if self.ping(self.previously_found[key]['ip'],1):
                                    if self.DEBUG:
                                        print(">> Ping could not find " + str(self.previously_found[key]['name']) + " at " + str(self.previously_found[key]['ip']) + ". Maybe Arping can.")
                                    try:
                                        
                                        if not self.previously_found[key]['ip'] in self.devices_excluding_arping and not self.previously_found[key]['mac_address'] in self.devices_excluding_arping and self.arping(self.previously_found[key]['ip'], 1) == 0:
                                            self.previously_found[key]['lastseen'] = int(time.time())
                                            if self.DEBUG:
                                                print(">> Arping found it.")
                                            succesfully_found += 1
                                            self.not_seen_since[key] = None
                                        else:
                                            if self.DEBUG:
                                                print(">> Arping also could not find the device.")
                                            if key not in self.not_seen_since:
                                                self.not_seen_since[key] = int(time.time())
                                            
                                            if self.not_seen_since[key] == None:
                                                self.not_seen_since[key] = int(time.time())
                                                if self.DEBUG:
                                                    print("- Remembering first not-seen-since time")
                                            elif self.not_seen_since[key] + (60 * (self.time_window + 1)) < time.time():
                                                if self.DEBUG:
                                                    print("NOT SPOTTED AT ALL DURATION IS NOW LONGER THAN THE TIME WINDOW!")
                                                recently = False
                                                if 'recently1' not in self.devices[key].properties:
                                                    if self.DEBUG:
                                                        print("+ Adding recently spotted property to presence device")
                                                    self.devices[key].add_boolean_child("recently1", "Recently spotted", recently, True, "BooleanProperty") # name, title, value, readOnly, @type
                                                else:
                                                    self.devices[key].properties["recently1"].update(recently)
                                                
                                                
                                    except Exception as ex:
                                        print("Error trying Arping: " + str(ex))
                                else:
                                    if self.DEBUG:
                                        print(">> Ping found device")
                                    self.previously_found[key]['lastseen'] = int(time.time())
                                    succesfully_found += 1
                                    self.not_seen_since[key] = None
                            else:
                                if self.DEBUG:
                                    print("- Should ping, but no IP")
                                    
                        else:
                            if self.DEBUG:
                                print("-data-collection is not allowed for " + str(self.previously_found[key]['name']) + ", skipping ping.")
                                        
                        
                        
                    except Exception as ex:
                        if self.DEBUG:
                            print("Error while scanning device from saved_devices list: " + str(ex))
                    
                    #self.DEBUG = False
                    
            except Exception as ex:
                print("Clock thread error: " + str(ex))
            
            saved_devices_count = len(self.saved_devices)
            scan_time_delta = time.time() - last_run
            if self.DEBUG:
                print("pinging all " + str(saved_devices_count) + " devices took " + str(scan_time_delta) + " seconds.")
                
            if scan_time_delta < 55:
                if self.DEBUG:
                    print("clock: scan took less than a minute. Will wait " + str(scan_time_delta + 5 ) + " seconds before starting the next round")
                delay = 55 - scan_time_delta
                time.sleep(delay)
            time.sleep(5)

        
        
        

#
#  BRUTE FORCE SCAN
#
        
    def brute_force_scan(self):
        
        #if not self.use_brute_force_scan:
        #    return        
            
        """ Goes over every possible IP adddress in the local network (1-254) to check if it responds to a ping or arping request """
        #while self.running:
        if self.busy_doing_brute_force_scan == False: # and self.should_brute_force_scan == True:
            self.busy_doing_brute_force_scan = True
            
            # Make sure the prefered interface still has an IP address (e.g. if network cable was disconnected, this will be fixed)
            self.select_interface()
            
            
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
                print("Error while doing brute force scan: " + str(ex))
                self.busy_doing_brute_force_scan = False
                self.should_brute_force_scan = False
                self.last_brute_force_scan_time = time.time()


            self.busy_doing_brute_force_scan = False
            if self.DEBUG:
                print("\nBRUTE FORCE SCAN DONE\n")

        else:
            if self.DEBUG:
                print("\nWarning, Brute force scan was already running. Aborting starting another brute force scan.\n")
                

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
            if self.ping(ip_address, ping_count) == 0: # 0 means everything went ok, so a device was found.
                alive = True
            else:
                try:
                    if self.arping(ip_address, ping_count) == 0: # 0 means everything went ok, so a device was found.
                        alive = True
                except Exception as ex:
                    print("Error trying Arping: " + str(ex))
                
            # If either ping or arping found a device:
            try:
                if alive:
                    output = self.arp(ip_address)
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








    def handle_device_saved(self, device_id, device):
        """User saved a thing. Also called when the add-on starts."""
        try:
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
                    
                    data_collection = True
                    try:
                        if 'data-collection' in device['properties']:
                            data_collection = bool(device['properties']['data-collection']['value'])
                    except Exception as ex:
                        print("Error getting data collection preference from saved device update info: " + str(ex))
                
                    #print("Data_collection value is now: " + str(data_collection))
                    
                    try:
                        #pass
                        if device_id not in self.previously_found:
                            if self.DEBUG:
                                print("Populating previously_found from handle_device_saved")
                            self.previously_found[device_id] = {}
                            self.previously_found[device_id]['name'] = str(device['title'])
                            self.previously_found[device_id]['lastseen'] = None   
                            self.previously_found[device_id]['arpa_time'] = int(time.time())
                            self.previously_found[device_id]['data-collection'] = bool(data_collection)
                    except Exception as ex:
                        print("Error adding to found devices list: " + str(ex))
                        
        except Exception as ex:
            print("Error dealing with existing saved devices: " + str(ex))



    def unload(self):
        """Add-on is shutting down."""
        if self.DEBUG:
            print("Network presence detector is being unloaded")
        self.save_to_json()
        self.running = False



    def remove_thing(self, device_id):
        """User removed a thing from the interface."""
        if self.DEBUG:
            print("Removing presence detection device: " + str(device_id))

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




    def get_optimal_name(self,ip_address,found_device_name="unnamed",mac_address=""):


        if self.last_avahi_scan_time < (time.time() - 3600):
            if self.DEBUG:
                print("getting fresh avahi data, it's been at least an hour")
            
            command = ["avahi-browse","-p","-l","-a","-r","-k","-t"]
            gateway_list = []
            satellite_targets = {}
            try:
            
                result = subprocess.run(command, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
                for line in result.stdout.split('\n'):
            
                    if  "IPv4;CandleMQTT-" in line:
                        if self.DEBUG:
                            print(str(line))
                        # get name
                        try:
                            before = 'IPv4;CandleMQTT-'
                            after = ';_mqtt._tcp;'
                            name = line[line.find(before)+16 : line.find(after)]
                        except Exception as ex:
                            #print("invalid name: " + str(ex))
                            continue
                        
                        # get IP
                        #pattern = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')
                        #ip = pattern.search(line)[0]
                        #lst.append(pattern.search(line)[0])
                        
                        try:
                            ip_address_list = re.findall(r'(?:\d{1,3}\.)+(?:\d{1,3})', str(line))
                            if self.DEBUG:
                                print("ip_address_list = " + str(ip_address_list))
                            if len(ip_address_list) > 0:
                                ip_address = str(ip_address_list[0])
                                if not valid_ip(ip_address):
                                    continue
                
                                if ip_address not in gateway_list:
                                    gateway_list.append(ip_address)
                                    satellite_targets[ip_address] = name
                                    
                        except Exception as ex:
                            if self.DEBUG:
                                print("no IP address in line: " + str(ex))
                
                self.avahi_lookup_table = satellite_targets
           
            
            except Exception as ex:
                print("Arp -a error: " + str(ex))
            
                
                
                
            
            

        # Try to get hostname
        nmb_result = ""
        
        try:
            nbtscan_command = 'nbtscan -q -e ' + str(self.own_ip) + '/24'
            nbtscan_results = subprocess.run(nbtscan_command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
            if self.DEBUG:
                print("nbtscan_results: \n" + str(nbtscan_results.stdout))
                
            if ip_address in nbtscan_results.stdout:
                if self.DEBUG:
                    print("get_optimal_name: spotted IP address in nbtscan_results, so extracting name from there")
                
                for nbtscan_line in nbtscan_results.stdout.split('\n'):
                    if ip_address in nbtscan_line:
                        #line = line.replace("#PRE","")
                        nbtscan_line = nbtscan_line.rstrip()
                        nbtscan_parts = nbtscan_line.split("\t")
                        if len(nbtscan_parts) > 0:
                            #possible_name = "Presence - " + str(nbtscan_parts[1])
                            nmb_result = str(nbtscan_parts[1])
                            if self.DEBUG:
                                print("name extracted from nbtscan_result: " + str(nmb_result))
        
        except Exception as ex:
            print("Error: could not get name from arp -a line: " + str(ex))
            
        #try:
            #nmb_result = socket.gethostbyaddr(ip_address)
            #nmb_result = hostname_lookup(ip_address)
        #    nmb_result,alias,addresslist = hostname_lookup(ip_address)
        #    print("socket.gethostbyaddr(ip_address) gave: " + str(nmb_result))
        #except Exception as ex:
        #    print("socket.gethostbyaddr(ip_address) error: " + str(ex))
        
        
        # This only works if Samba is installed, and it isn't installed by default
        #try:
        #    nmb_result = nmblookup(ip_address)
        #    if self.DEBUG:
        #        print("nmblookup result = " + str(nmb_result))
        #except Exception as ex:
        #    if self.DEBUG:
        #        print("Error doing nmblookup: " + str(ex))
        
        if nmb_result == "":
            #if self.DEBUG:
            #    print("NMB lookup result was an empty string")
            
            if ip_address in self.avahi_lookup_table:
                
                found_device_name = str(self.avahi_lookup_table[ip_address]) # + ' (' + str(ip_address) + ')'
            
            else:
                # Round 2: analyse MAC address
                if found_device_name == '?' or found_device_name == '' or valid_ip(found_device_name):
                    if self.DEBUG: 
                        print("Will try to figure out a vendor name based on the mac address")
                    vendor = ip_address
                    try:
                        # Get the vendor name, and shorten it. It removes
                        # everything after the comma. Thus "Apple, inc"
                        # becomes "Apple"
                        vendor = get_vendor(mac_address)
                        if self.DEBUG:
                            print("get_vendor mac lookup result: " + str(vendor))
                        if vendor is not None:
                            vendor = vendor.split(' ', 1)[0]
                            vendor = vendor.split(',', 1)[0]
                        else:
                            vendor = ip_address
                    except ValueError:
                        pass

                    found_device_name = vendor
                
        else:
            found_device_name = nmb_result
               
        # At this point we definitely have something.
        
        if found_device_name == 'unnamed':
            found_device_name = str(ip_address)
        
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
                        #if self.DEBUG:
                        #    print("-checking possible name '" + str(possible_name) + "' against: " + str(self.previously_found[key]['name']))
                        #    print("--prev found device key = " + str(key))
                        
                        # We skip checking for name duplication if the potential new device is the exact same device, so it would be logical if they had the same name.
                        if str(key) == str(_id):
                            #if self.DEBUG:
                            #    print("key == _id")
                            if possible_name == str(self.previously_found[key]['name']):
                                #if self.DEBUG:
                                #    print("the new name is the same as the old for this mac-address")
                                #continue
                                break
                        
                        if possible_name == str(self.previously_found[key]['name']): # The name already existed somewhere in the list, so we change it a little bit and compare again.
                            could_be_same_same = True
                            if self.DEBUG:
                                print("-names collided: " + str(possible_name))
                            possible_name = found_device_name + " " + str(i) + "  (" + str(ip_address) + ")"
                            #if self.DEBUG:
                            #    print("-now testing new name: " + str(possible_name))
                            i += 1 # up the count for a potential next round
                            if i > 20:
                                #if self.DEBUG:
                                #    print("Reached 200 limit in while loop") # if the user has 200 of the same device, that's incredible.
                                break
                                
                except Exception as ex:
                    print("Error doing name check in while loop: " + str(ex))
                    break
                    
        except Exception as ex:
            print("Error in name duplicate check: " + str(ex))
        
        
        if self.DEBUG:
            print("         FINAL NAME: " + str(possible_name))
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



    # saves to persistence file
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
        self.brute_force_scan()
        #if self.busy_doing_brute_force_scan == False:
        #    self.should_brute_force_scan = True
        #    self.brute_force_scan()

    def cancel_pairing(self):
        """Cancel the pairing process."""
        self.save_to_json()




#
#  LIGHT SCAN
#


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
                        self.previously_found[key]['data-collection'] = True
                        self.should_save = True # We will be adding this new device to the list, and then save that updated list.
                        
                    else:
                        # Maybe we found a better name this time.
                        if key not in self.saved_devices and arpa_list[key]['name'] not in ("","?","unknown"): # superfluous?
                            if self.DEBUG:
                                print("ARPA scan may have found a better hostname: " + str(arpa_list[key]['name']) + ", instead of " + str(self.previously_found[key]['name']) + " adding it to the previously_found devices dictionary")
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
            print("light scan is done\n")




    #
    #  This gives a quick impression of the network. Quicker than the brute force scan, which goes over every possible IP and tests them all.
    #
    def arpa(self):
        
        device_list = {}
        
        if self.busy_doing_arpa_scan == False:
            self.busy_doing_arpa_scan = True
            
            try:
                nbtscan_command = 'nbtscan -q -e ' + str(self.own_ip) + '/24'
                nbtscan_results = subprocess.run(nbtscan_command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
                if self.DEBUG:
                    print("nbtscan_results: \n" + str(nbtscan_results.stdout))
            except Exception as ex:
                print("arpa: error running nbtscan command: " + str(ex))
            #os.system('nbtscan -q ' + str(self.own_ip))
        
            command = "arp -a"
            
            try:
                result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
                
                if self.DEBUG:
                    print("arp -a results: \n" + str(result.stdout))
                
                for line in result.stdout.split('\n'):
                    #print("arp -a line: " + str(line))
                    if not "<incomplete>" in line and len(line) > 10:
                        if self.DEBUG:
                            print("checking arp -a line: " + str(line))
                        name = "?"
                        mac_short = ""
                        found_device_name = "unnamed"
                        possible_name = "Presence - unnamed"
                        
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
                                if self.DEBUG:
                                    print("Error: not a valid IP address?")
                                continue
                            found_device_name = ip_address
                        except Exception as ex:
                            print("no IP address in line: " + str(ex))
                        
                        try:
                            if ip_address in nbtscan_results.stdout:
                                if self.DEBUG:
                                    print("spotted IP address in nbtscan_results, so extracting name form there")
                                try:
                                    for nbtscan_line in nbtscan_results.stdout.split('\n'):
                                        if ip_address in nbtscan_line:
                                            #line = line.replace("#PRE","")
                                            nbtscan_line = nbtscan_line.rstrip()
                                            nbtscan_parts = nbtscan_line.split("\t")
                                            if len(nbtscan_parts) > 0:
                                                possible_name = "Presence - " + str(nbtscan_parts[1])
                                                if self.DEBUG:
                                                    print("name extracted from nbtscan_result: " + str(found_device_name))
                                except Exception as ex:
                                    if self.DEBUG:
                                        print("Error getting nice name from nbtscan_results: " + str(ex))
                            
                            else:
                                found_device_name = str(line.split(' (')[0])
                                
                                if _id not in self.previously_found:
                                    possible_name = self.get_optimal_name(ip_address, found_device_name, mac_address)
                                else:
                                    possible_name = self.previously_found[_id]['name']
                        
                        except Exception as ex:
                            print("Error: could not get name from arp -a line: " + str(ex))
                        
                        if mac_short != "" and possible_name != 'unknown':
                            #print("util: arp: mac in line: " + line)
                            #item = {'ip':ip_address,'mac':mac_address,'name':name, 'mac_short':mac_address.replace(":", "")}
                            #return str(line)
                        
                            device_list[_id] = {'ip':ip_address,'mac_address':mac_address,'name':possible_name,'arpa_time':int(time.time()),'lastseen':None}
                        else:
                            if self.DEBUG:
                                print("Skipping an arop -a result because of missing mac or name")
                            #print("device_list = " + str(device_list))
                #return str(result.stdout)

            except Exception as ex:
                print("Arp -a error: " + str(ex))
                #result = 'error'
            
            
            # This is a little tacked-on here, but it can give some more quick results
            try:
                if self.DEBUG:
                    print("\n\nneighbour scan:")
            
                # Also try getting IPv6 addresses from "ip neighbour"
            
                ip_neighbor_output = subprocess.check_output(['ip', 'neighbor']).decode('utf-8')
                #print(ip_neighbor_output)
                for line in ip_neighbor_output.splitlines():
                    if self.DEBUG:
                        print("ip_neighbor line: " + str(line))
                    if line.endswith("REACHABLE") or line.endswith("STALE") or line.endswith("DELAY"):
                        if self.DEBUG:
                            print("stale or reachable")
                        neighbor_mac = extract_mac(line)
                        neighbor_ip = line.split(" ", 1)[0]
                        possible_name = "unknown"
                
                        if neighbor_ip == self.own_ip:
                            if self.DEBUG:
                                print("ip neighbor was own IP address, skipping")
                            continue
                
                        if self.DEBUG:
                            print("neighbor mac: " + str(neighbor_mac) + ", and ip: " + neighbor_ip)
                        if valid_mac(neighbor_mac):
                    
                            neighbor_mac_short = str(neighbor_mac.replace(":", ""))
                            neighbor_id = 'presence-{}'.format(neighbor_mac_short)
                            if self.DEBUG:
                                print("- valid mac. Proposed neighbour id: " + str(neighbor_id))
                            if neighbor_id not in self.previously_found and neighbor_id not in device_list:
                                if self.DEBUG:
                                    print("not previously found, adding new device from neighbourhood data")
                            
                                possible_name = self.get_optimal_name(neighbor_ip, 'unnamed', neighbor_mac)
                        
                                device_list[neighbor_id] = {'ip':neighbor_ip,'mac_address':neighbor_mac,'name':possible_name,'arpa_time':int(time.time()),'lastseen':None}
                            else:
                                if self.DEBUG:
                                    print("neighbor ID existed already in detected devices list")
                #o = run("python q2.py",capture_output=True,text=True)
                #print(o.stdout)
            
                if self.DEBUG:
                    print("\narpa scan found devices list: " + str(device_list))
            
            except Exception as ex:
                print("arpa: error while doing ip neighbour scan: " + str(ex))
            
            
            self.busy_doing_arpa_scan = False
                
        else:
            if self.DEBUG:
                print("Warning, was already busy doing a light scan. Returning empty list..")
                
        return device_list
        #return str(subprocess.check_output(command, shell=True).decode())
        


    def select_interface(self):
        try:
            eth0_output = subprocess.check_output(['ifconfig', 'eth0']).decode('utf-8')
            #print("eth0_output = " + str(eth0_output))
            wlan0_output = subprocess.check_output(['ifconfig', 'wlan0']).decode('utf-8')
            #print("wlan0_output = " + str(wlan0_output))
            if "inet " in eth0_output and self.prefered_interface == "eth0":
                self.selected_interface = "eth0"
            if not "inet " in eth0_output and self.prefered_interface == "eth0":
                self.selected_interface = "wlan0"
            if "inet " in wlan0_output and self.prefered_interface == "wlan0":
                self.selected_interface = "wlan0"
        except Exception as ex:
            print("Error in select_interface: " + str(ex))
            self.selected_interface = "wlan0"
        
            
    def ping(self, ip_address, count):
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        #command = ["ping", param, count, "-i", 1, str(ip_address)]
        command = "ping -I " + str(self.selected_interface) + " " + str(param) + " " + str(count) + " -i 0.5 " + str(ip_address)
        #print("command: " + str(command))
        #return str(subprocess.check_output(command, shell=True).decode())
        try:
            result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.DEVNULL) #.decode())
            #print("ping done")
            return result.returncode
        except Exception as ex:
            print("error pinging! Error: " + str(ex))
            return 1


    def arping(self, ip_address, count):
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = "sudo arping -i " + str(self.selected_interface) + " " + str(param) + " " + str(count) + " " + str(ip_address)
        #print("command: " + str(command))
        try:
            result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.DEVNULL) #.decode())
            return result.returncode
        except Exception as ex:
            print("error arpinging! Error: " + str(ex))
            return 1


    def arp(self, ip_address):
        if valid_ip(ip_address):
            command = "arp -i " + str(self.selected_interface) + " " + str(ip_address)
            try:
                result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
                for line in result.stdout.split('\n'):
                    mac_addresses = re.findall(r'(([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})', str(line))
                    if len(mac_addresses):
                        #print("util: arp: mac in line: " + line)
                        return str(line)
                
                return str(result.stdout)

            except Exception as ex:
                print("Arp error: " + str(ex))
                result = 'error'
            return result
            #return str(subprocess.check_output(command, shell=True).decode())
        
    
    



class presenceAction(Action):
    """An Action represents an individual action on a device."""

    def __init__(self, id_, device, name, input_):
        """
        Initialize the object.
        id_ ID of this action
        device -- the device this action belongs to
        name -- name of the action
        input_ -- any action inputs
        """
        self.id = id_
        self.device = device
        self.name = name
        self.input = input_
        self.status = 'created'
        self.time_requested = timestamp()
        self.time_completed = None

    def as_action_description(self):
        """
        Get the action description.
        Returns a dictionary describing the action.
        """
        description = {
            'name': self.name,
            'timeRequested': self.time_requested,
            'status': self.status,
        }

        if self.input is not None:
            description['input'] = self.input

        if self.time_completed is not None:
            description['timeCompleted'] = self.time_completed

        return description

    def as_dict(self):
        """
        Get the action description.
        Returns a dictionary describing the action.
        """
        d = self.as_action_description()
        d['id'] = self.id
        return d

    def start(self):
        """Start performing the action."""
        self.status = 'pending'
        self.device.action_notify(self)

    def finish(self):
        """Finish performing the action."""
        self.status = 'completed'
        self.time_completed = timestamp()
        self.device.action_notify(self)

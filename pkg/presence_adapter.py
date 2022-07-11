"""Presence Detection adapter for Candle Controller / WebThings Gateway."""



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
        self.ready = False
        self.addon_name = 'network-presence-detection-adapter'
        self.name = self.__class__.__name__
        Adapter.__init__(self,
                         self.addon_name,
                         self.addon_name,
                         verbose=verbose)
        #print("Adapter ID = " + self.get_id())
        
        self.mayor_version = 2
        #self.meso_version = 0
        
        self.DEBUG = False
        self.ready = False
        #print("self.user_profile['baseDir'] = " + self.user_profile['baseDir'])
     
        #self.memory_in_weeks = 10 # How many weeks a device will be remembered as a possible device.
        self.time_window = 10 # How many minutes should a device be away before we consider it away?

        self.own_ip = None # We scan only scan if the device itself has an IP address.
        
        self.prefered_interface = "eth0"
        self.selected_interface = "eth0"
        
        self.busy_doing_light_scan = False
        self.devices_excluding_arping = ""
        
        self.use_brute_force_scan = False; # was used for continuous brute force scanning. This has been deprecated.
        self.should_brute_force_scan = True
        self.busy_doing_brute_force_scan = False
        self.last_brute_force_scan_time = 0             # Allows the add-on to start a brute force scan right away.
        self.seconds_between_brute_force_scans = 1800  #1800  # 30 minutes     

        # AVAHI
        self.last_avahi_scan_time = 0
        self.raw_avahi_scan_result = ""
        self.avahi_lookup_table = {}
        self.candle_controllers_ip_list = set()
        self.ignore_candle_controllers = True
        
        self.nbtscan_results = ""
        
        self.running = True
        self.saved_devices = []
        self.not_seen_since = {} # used to determine if a device hasn't responded for a long time

        self.addon_path =  os.path.join(self.user_profile['addonsDir'], self.addon_name)
        self.persistence_file_path = os.path.join(self.user_profile['dataDir'], self.addon_name,'persistence.json')

        if self.DEBUG:
            print("self.persistence_file_path = " + str(self.persistence_file_path)) # debug will never be true here unless set in the code above
        
        self.should_save = False
        
        self.previous_data = {} # will hold data loaded from persistence file
        self.previously_found = {} # will hold the previously found devices recovered from persistence data
        
        try:
            with open(self.persistence_file_path) as file_object:
                #print("Loading json..")
                try:
                    self.previous_data = json.load(file_object)
                    if 'mayor_version' in self.previous_data:
                        if self.DEBUG:
                            print("Persistent data was loaded succesfully") # debug will never be true here unless set in the code above
                        if 'devices' in self.previous_data:
                            self.previously_found = self.previously_data['devices']
                        else:
                            self.previously_found = self.previous_data
                    else:
                        print("loaded json was from version 1.0, clearing incompatible persistent data")
                        
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

        # Reset all the last_seen data from the persistence file, since it could be out of date.
        for _id in self.previously_found:
            try:
                if 'last_seen' in self.previously_found[_id]:
                    self.previously_found[_id]['last_seen'] = None
                self.not_seen_since[_id] = None
            except Exception as ex:
                print("Error setting last_seen of previously_found devices from persistence to None: " + str(ex))
        
        time.sleep(.3) # avoid swamping the sqlite database
        
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
                self.own_ip = get_own_ip()
        except:
            if self.DEBUG:
                print("Error, could not get actual own IP address")
        
        # First scan
        time.sleep(2) # wait a bit before doing the quick scan. The gateway will pre-populate based on the 'handle-device-saved' method.

        self.quick_scan() # get initial list of devices

        if self.DEBUG:
            print("Starting the clock thread")
        try:
            t = threading.Thread(target=self.clock)
            t.daemon = True
            t.start()
        except:
            if self.DEBUG:
                print("Error starting the continous light scan thread")
        
        #done = self.brute_force_scan()
        
        self.ready = True
        
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
            
            
            if 'Show Candle controllers' in config:
                self.ignore_candle_controllers = not bool(config['Show Candle controllers'])
                if self.DEBUG:
                    print("self.ignore_candle_controllers: " + str(self.ignore_candle_controllers))
            
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
                        print("No addresses to exclude from arping were found in the settings.")

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
                    if self.DEBUG:
                        print("Clock: error running periodic deep scan: " + str(ex))

            succesfully_found = 0
            try:
                for _id in self.previously_found:
                    if self.DEBUG:
                        print("")
                        print("clock -> _id : " + str(_id))
                        print("clock -> name: " + str(self.previously_found[_id]['name']))
                        print("clock -> ip  : " + str(self.previously_found[_id]['ip']))
                        print("clock -> prev_found full: " + str(self.previously_found[_id]))
                        
                        print("")
                    # Update device's last seen properties
                    try:
                        # Make sure all devices and properties exist. Should be superfluous really.
                        #if self.DEBUG:
                        #    print("clock - str(_id) = " + str(_id) + " has " + str(self.previously_found[_id]))
                        if str(_id) not in self.devices:
                            
                            if self.DEBUG:
                                print(str(self.previously_found[str(_id)]) + " was not turned into an internal devices object yet.")
                            
                            """
                            detail = "..."
                            try:
                                detail = self.previously_found[_id]['ip']
                            except:
                                if self.DEBUG:
                                    print("No IP address in previously found list (yet)")
                                continue
                                
                            new_name = "unnamed"
                            try:
                                new_name = self.previously_found[_id]['name']
                            except:
                                if self.DEBUG:
                                    print("No name present in previously found list")
                                continue
                            
                            if new_name == "unnamed" or new_name == "?" or new_name == "": # TODO: isn't the name "Presence - unnamed (ip address)" ?
                                if self.DEBUG:
                                    print("No good name found yet, skipping device generation and update")
                                continue
                            
                                
                            if self.DEBUG:
                                print("clock: adding thing")
                            """
                            
                            if self.ignore_candle_controllers and self.previously_found[_id]['candle'] == True:
                                if self.DEBUG:
                                    print("clock: ignoring a Candle controller")
                
                            else:
                                if self.DEBUG:
                                    print("clock: adding a thing")
                                self._add_device(_id, self.previously_found[_id]['name'], self.previously_found[_id]['ip']) # The device did not exist yet, so we're creating it.
                            
                                
                            #self._add_device(_id, new_name, detail) # The device did not exist yet, so we're creating it.

                        #
                        #  MINUTES AGO
                        #

                        try:
                            if self.previously_found[_id]['last_seen'] != 0 and self.previously_found[_id]['last_seen'] != None:
                                if self.DEBUG:
                                    print("-adding a minute to minutes_ago variable")
                                minutes_ago = int( (time.time() - self.previously_found[_id]['last_seen']) / 60 )
                            else:
                                minutes_ago = None
                                if self.DEBUG:
                                    print("                             --> MINUTES AGO IS NONE <--")
                                    
                            #should_update_last_seen = True
                            #if 'data_mute_end_time' in self.previously_found[_id]:
                            #    if self.DEBUG:
                            #        print("data_mute_end_time spotted")
                            #    if self.previously_found[_id]['data_mute_end_time'] > time.time():
                            #        if self.DEBUG:
                            #            print("clock: skipping last_seen increment of muted device " + str(self.previously_found[_id]['name']))
                            #        minutes_ago = None
                                    #should_update_last_seen = False
                            
                                    
                        except Exception as ex:
                            minutes_ago = None
                            if self.DEBUG:
                                print("Clock: minutes ago issue: " + str(ex))
                        
                        
                        try:
                            #if should_update_last_seen:
                            if 'minutes_ago' not in self.devices[_id].properties:
                                if self.DEBUG:
                                    print("+ Adding minutes ago property to presence device, with value: " + str(minutes_ago))
                                self.devices[_id].add_integer_child("minutes_ago", "Minutes ago last seen", minutes_ago)
                            elif minutes_ago != None:
                                if self.DEBUG:
                                    print("Minutes_ago of " + str(self.previously_found[_id]['name']) + " is: " + str(minutes_ago))
                            else:
                                if self.DEBUG:
                                    print("eh? minutes ago fell through")
                                    
                            if self.DEBUG:
                                print("updating minutes ago")
                            self.devices[_id].properties["minutes_ago"].update(minutes_ago)
                                    
                        except Exception as ex:
                            if self.DEBUG:
                                print("Clock: Could not add/update minutes_ago property" + str(ex))
                        
                        
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
                                    
                            if 'recently1' not in self.devices[_id].properties:
                                if self.DEBUG:
                                    print("+ Adding recently spotted property to presence device")
                                self.devices[_id].add_boolean_child("recently1", "Recently spotted", recently, True, "BooleanProperty") # name, title, value, readOnly, @type
                            else:
                                self.devices[_id].properties["recently1"].update(recently)
                        except Exception as ex:
                            if self.DEBUG:
                                print("Clock: Could not add recently spotted property" + str(ex))



                        #
                        #  DATA COLLECTION
                        #
                        
                        if 'data-collection' not in self.devices[_id].properties:
                            if self.DEBUG:
                                print("+ Adding data-collection property to presence device")
                                
                            data_collection_state = True
                            if 'data-collection' in self.previously_found[_id]:
                                if self.DEBUG:
                                    print("+ Found a data-collection preference in the previously_found data")
                                data_collection_state = self.previously_found[_id]['data-collection']
                            
                            self.devices[_id].add_boolean_child("data-collection", "Data collection", data_collection_state, False, "") # name, title, value, readOnly, @type


                        #if 'data-temporary-mute' not in self.devices[_id].properties:
                        #    if self.DEBUG:
                        #        print("+ Adding recently spotted property to presence device")
                        #    
                        #    self.devices[_id].add_boolean_child("data-temporary-mute", "Temporary data mute", False, False, "PushedProperty") # name, title, value, readOnly, @type
                        
            

                    except Exception as ex:
                        if self.DEBUG:
                            print("Clock: Could not create or update property. Error: " + str(ex))    
                    
                
                
                if self.DEBUG:
                    print("\n\nself.saved_devices: " + str(self.saved_devices))
                    
                # Scan the devices the user cares about (once a minute)
                for _id in self.saved_devices:
                    if self.DEBUG:
                        print("_\n__\n___")
                        print("clock: scanning every minute: _id in saved_devices: " + str(_id))
                    
                    if str(_id) not in self.previously_found:
                        if self.DEBUG:
                            print("Saved thing was not found through scanning yet (not yet added to previously_found), skipping update attempt: " + str(_id))
                        continue
                        
                    if self.DEBUG:
                        print("clock: scanning every minute: human readable name: " + str(self.previously_found[_id]['name']))


                    #if self.DEBUG:
                    #    print("Saved device ID " + str(_id) + " was also in previously found list. Trying scan.")
                    
                    # Try doing a Ping and then optionally an Arping request if there is a valid IP Address
                    try:
                        #if self.DEBUG:
                        #    print("IP from previously found list: " + str(self.previously_found[_id]['ip']))
                            
                        #self.DEBUG = True
                            
                            
                        #
                        #  LOOKING FOR REASONS TO SKIP PINGING
                        #
                        
                        should_ping = True
                        
                        # Data collection disabled?
                        if 'data-collection' in self.previously_found[_id]:
                            if self.previously_found[_id]['data-collection'] == False:
                                if self.DEBUG:
                                    print("clock: skipping pinging of " + str(self.previously_found[_id]['name']) + " because data collection is disabled")
                                should_ping = False
                        else:
                            if self.DEBUG:
                                print("clock: data-collection value did not exist yet in this thing, adding it now.")
                            self.previously_found[_id]['data-collection'] = True
                            self.should_save = True
                        
                                
                        # Data-mute enabled?
                        if 'data_mute_end_time' in self.previously_found[_id]:
                            if self.DEBUG:
                                print("data_mute_end_time: " + str(self.previously_found[_id]['data_mute_end_time']) + ". delta: " + str(self.previously_found[_id]['data_mute_end_time'] - time.time()))
                            if self.previously_found[_id]['data_mute_end_time'] > time.time():
                                if self.DEBUG:
                                    print("clock: skipping pinging of muted device " + str(self.previously_found[_id]['name']))
                                
                                self.previously_found[_id]['last_seen'] = None
                                self.devices[_id].properties["recently1"].update(None)
                                should_ping = False
                        else:
                            if self.DEBUG:
                                print("clock: mute_end_time value did not exist yet in this thing, adding it now.")
                            self.previously_found[_id]['data_mute_end_time'] = 0
                            self.should_save = True
                            
                                
                        # To ping or not to ping
                        if should_ping == True:
                            if self.DEBUG:
                                print("- Should ping is True. Will ping/arping now.")
                            if 'ip' in self.previously_found[_id]:
                                if self.ping(self.previously_found[_id]['ip'],1):
                                    if self.DEBUG:
                                        print("Clock: >> Ping could not find " + str(self.previously_found[_id]['name']) + " at " + str(self.previously_found[_id]['ip']) + ". Maybe Arping can.")
                                    try:
                                        if 'mac_address' in self.previously_found[_id]:
                                            if not self.previously_found[_id]['ip'] in self.devices_excluding_arping and not self.previously_found[_id]['mac_address'] in self.devices_excluding_arping and self.arping(self.previously_found[_id]['ip'], 1) == 0:
                                                self.previously_found[_id]['last_seen'] = int(time.time())
                                                if self.DEBUG:
                                                    print("Clock: >> Arping found it. last_seen updated.")
                                                succesfully_found += 1
                                                self.not_seen_since[_id] = None
                                            else:
                                                if self.DEBUG:
                                                    print("Clock: >> Arping also could not find the device.")
                                                if _id not in self.not_seen_since:
                                                    if self.DEBUG:
                                                        print("--adding first not_seen_since time")
                                                    self.not_seen_since[_id] = int(time.time())
                                            
                                                if self.not_seen_since[_id] == None:
                                                    if self.DEBUG:
                                                        print("--not_seen_since time was None. Setting current time instead.")
                                                    self.not_seen_since[_id] = int(time.time())
                                                    if self.DEBUG:
                                                        print("- Clock: Remembering fresh not-seen-since time")
                                                elif self.not_seen_since[_id] + (60 * (self.time_window + 1)) < time.time():
                                                    if self.DEBUG:
                                                        print("NOT SPOTTED AT ALL DURATION IS NOW LONGER THAN THE TIME WINDOW!")
                                                    recently = False
                                                    if _id in self.devices:
                                                        if 'recently1' not in self.devices[_id].properties:
                                                            if self.DEBUG:
                                                                print("+ Clock: Adding recently spotted property to presence device")
                                                            self.devices[_id].add_boolean_child("recently1", "Recently spotted", recently, True, "BooleanProperty") # name, title, value, readOnly, @type
                                                        else:
                                                            if self.DEBUG:
                                                                print("+ Clock: updating recently spotted property")
                                                            self.devices[_id].properties["recently1"].update(recently)
                                                    else:
                                                        if self.DEBUG:
                                                            print("warning, that is was not yet in self.devices?")
                                        else:
                                            if self.DEBUG:
                                                print("Should arping, but missing mac address: " + str(self.previously_found[_id]))
                                                
                                                
                                    except Exception as ex:
                                        if self.DEBUG:
                                            print("Error trying last_seen arping: " + str(ex))
                                else:
                                    if self.DEBUG:
                                        print(">> Ping found device")
                                    self.previously_found[_id]['last_seen'] = int(time.time())
                                    succesfully_found += 1
                                    self.not_seen_since[_id] = None
                            else:
                                if self.DEBUG:
                                    print("- Should ping, but no IP: " + str(self.previously_found[_id]))
                                    
                        else:
                            if self.DEBUG:
                                print("-data-collection is not allowed for " + str(self.previously_found[_id]['name']) + ", skipping ping.")
                                        
                        
                        
                    except Exception as ex:
                        if self.DEBUG:
                            print("Error while scanning device from saved_devices list: " + str(ex))
                    
                    #self.DEBUG = False
                    
            except Exception as ex:
                if self.DEBUG:
                    print("Clock thread error: " + str(ex))
            
            
            if self.should_save: # This is the only time the json file is stored.    
                self.save_to_json() # also sets should_save to false again
            
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
            
        if self.DEBUG:
            print("\nSTARTING BRUTE FORCE SCAN\n")
            
        """ Goes over every possible IP adddress in the local network (1-254) to check if it responds to a ping or arping request """
        #while self.running:
        if self.busy_doing_brute_force_scan == False: # and self.should_brute_force_scan == True:
            self.busy_doing_brute_force_scan = True
            
            # Make sure the prefered interface still has an IP address (e.g. if network cable was disconnected, this will be fixed)
            self.select_interface()
            
            
            self.should_brute_force_scan = False
            self.last_brute_force_scan_time = time.time()
            if self.DEBUG:
                print("\nInitiating a brute force scan of the entire local network")
                
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
                        print("Brute force scan: all threads are done")
                    # If new devices were found, save the JSON file.
                    if len(self.previously_found) != old_previous_found_count:
                        self.should_save = True
                
                # Remove devices that haven't been spotted in a long time.
                #list(fdist1._ids())
                
                current__ids = [None] * len(list(self.previously_found._ids()));    
 
                #Copying all elements of one array into another    
                for a in range(0, len(list(self.previously_found._ids()))):    
                    current__ids[a] = list(self.previously_found._ids())[a];
                
                #current__ids = self.previously_found._ids()
                for _id in current__ids:
                    try:
                        if 'first_seen' in self.previously_found[_id]:
                            if time.time() - self.previously_found[_id]['first_seen'] > 86400 and _id not in self.saved_devices:
                                if self.DEBUG:
                                    print("Removing devices from found devices list because it hasn't been spotted in a day, and it's not a device the user has imported.")
                                del self.previously_found[_id]
                        else:
                            if self.DEBUG:
                                print("Error, first_seen not in previously found device?: " + str(self.previously_found[_id]))
                    except Exception as ex:
                        if self.DEBUG:
                            print("Could not remove old device: " + str(ex))


            except Exception as ex:
                if self.DEBUG:
                    print("Error while doing brute force scan: " + str(ex))
                self.busy_doing_brute_force_scan = False
                self.should_brute_force_scan = False
                self.last_brute_force_scan_time = time.time()


            self.busy_doing_brute_force_scan = False
            if self.DEBUG:
                print("\nBRUTE FORCE SCAN DONE\n")

        else:
            if self.DEBUG:
                print("\nWarning, Brute force scan was already running. Not starting another brute force scan.\n")
                


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
                    if self.DEBUG:
                        print("brute force: ping failed, trying arping")
                    if self.arping(ip_address, ping_count) == 0: # 0 means everything went ok, so a device was found.
                        alive = True
                except Exception as ex:
                    if self.DEBUG:
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
                        mac_address = ':'.join([ '0' * (2 - len(x)) + x for x in mac_address.split(':') ])
                        
                        

                        if not valid_mac(mac_address):
                            if self.DEBUG:
                                print("Deep scan: MAC address was not valid")
                            continue

                        _id = mac_to_id(mac_address) #mac_address.replace(":", "")
                        

                        # Get the basic variables
                        found_device_name = output.split(' ')[0]
                        if self.DEBUG:
                            print("Deep scan: early found device name = " + found_device_name)
                        
                        self.parse_found_device(ip_address, found_device_name, mac_address)
                        
                        
                        if _id in self.previously_found:
                            if self.DEBUG:
                                print("Deep scan: updating ip and last_seen")
                            # update
                            #self.previously_found[_id]['first_seen'] = now # creation time
                            #self.previously_found[_id]['mac_address'] = mac_address
                     
                            self.previously_found[_id]['last_seen'] = now    
                            #self.previously_found[_id]['name'] = str(possible_name) # The name may be better, or it may have changed.
                            self.previously_found[_id]['ip'] = ip_address
                        
                        
                
                    
            except Exception as ex:
                if self.DEBUG:
                    print("Brute force scan: scan: error updating items in the previously_found dictionary: " + str(ex))
            

            time.sleep(5)















#
#  QUICK SCAN
#


    #
    #  This gives a quick impression of the network. Quicker than the brute force scan, which goes over every possible IP and tests them all.
    #
    #  Arpa is useful because it can find mobile phones much better than ping
    #  Avahi is great for devices that want to be found
    #  NBTscan is useful for older devices that don't support mDNS
    #  IP neighbour is yet another list, this time from the OS
    
    
    def quick_scan(self):
        if self.DEBUG:
            print("\n\nInitiating quick scan of network\n")
            
        device_dict = {}
        
        if self.busy_doing_light_scan == False:
            self.busy_doing_light_scan = True
            
            nbtscan_results = ""
            try:
                nbtscan_command = 'nbtscan -q -e ' + str(self.own_ip) + '/24'
                nbtscan_results = subprocess.run(nbtscan_command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
                self.nbtscan_results = str(nbtscan_results.stdout)
                if self.DEBUG:
                    print("nbtscan_results: \n" + str(nbtscan_results.stdout))
            except Exception as ex:
                if self.DEBUG:
                    print("quick scan: error running nbtscan command: " + str(ex))
            #os.system('nbtscan -q ' + str(self.own_ip))
            
            try:
                if self.DEBUG:
                    print("getting fresh avahi-browse data")
            
                avahi_browse_command = ["avahi-browse","-p","-l","-a","-r","-k","-t"] # avahi-browse -p -l -a -r -k -t
                #avahi_network_devices_ip_list = []

                try:
            
                    avahi_scan_result = subprocess.run(avahi_browse_command, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
                    for line in avahi_scan_result.stdout.split('\n'):
                    
                        try:
                            ip_address_list = re.findall(r'(?:\d{1,3}\.)+(?:\d{1,3})', str(line))
                            #if self.DEBUG:
                            #    print("ip_address_list = " + str(ip_address_list))
                            if len(ip_address_list) > 0:
                                #if self.DEBUG:
                                #    print("avahi line with ip: " + str(line))
                                ip_address = str(ip_address_list[0])
                                if valid_ip(ip_address):
                                
                                    if self.DEBUG:
                                        print("avahi-browse line with valid IP: " + str(line))
                                    
                                    #if ip_address not in avahi_network_devices_ip_list:
                                    #    avahi_network_devices_ip_list.append(ip_address)
                                
                                    # Check if it's a Candle device
                                    if  "IPv4;CandleMQTT-" in line:
                                
                                        if ip_address not in self.candle_controllers_ip_list:
                                            if self.DEBUG:
                                                print("-it's a candle controller. Adding IP to list.")
                                            self.candle_controllers_ip_list.add(ip_address)
                                        
                                    
                                        # get name
                                        try:
                                            before = 'IPv4;CandleMQTT-'
                                            after = ';_mqtt._tcp;'
                                            found_device_name = "Candle " + line[line.find(before)+16 : line.find(after)]
                                        except Exception as ex:
                                            if self.DEBUG:
                                                print("parse_found_device: avahi: invalid name: " + str(ex))
                                            found_device_name = "Candle controller"
                                        
                                    else:
                                        line_parts = line.split(';')
                                        found_device_name = line_parts[3]
                                
                                    # Deal with possible escaped characters
                                    found_device_name = found_device_name.replace('\\032',' ')
                                    found_device_name = found_device_name.replace('\\064','-')
                                    if '\\' in found_device_name:
                                        found_device_name = found_device_name.split('\\')[0]
                                
                                    #if ip_address not in self.avahi_network_devices:
                                    if self.DEBUG:
                                        print("quick scan: avahi: adding to / updating in avahi_network_devices. IP: " + str(ip_address) + ", found_device_name: " + str(found_device_name))
                                    self.avahi_lookup_table[ip_address] = found_device_name
                                        
                                    
                                    try:
                                        mac_address_list = re.findall(r'(([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})', str(line))[0]
                                        #if self.DEBUG:
                                        #    print("avahi line: mac_address_list: " + str(mac_address_list))
                                        if len(mac_address_list) > 0:
                                            
                                            mac_address = str(mac_address_list[0])
                                            if self.DEBUG:
                                                print("mac in avahi line: " + str(mac_address))
                                            #print(str(mac_address))
                                            
                                            self.parse_found_device(ip_address, found_device_name, mac_address)
                                            
                                            #_id = mac_to_id(mac_address)
                                        else:
                                            if self.DEBUG:
                                                print("no mac address in avahi line (zero length)")
                                            continue
                                    except Exception as ex:
                                        #if self.DEBUG:
                                        #    print("getting mac from avahi line failed: " + str(ex))
                                        continue
                                        
                                
                        except Exception as ex:
                            if self.DEBUG:
                                print("avahi_browse parsing error: " + str(ex))

                        
                            # get IP
                            #pattern = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')
                            #ip = pattern.search(line)[0]
                            #lst.append(pattern.search(line)[0])
                        
                    #self.avahi_lookup_table = avahi_network_devices
                    #self.candle_controllers_ip_list = candle_controllers_ip_list
                    #self.network_devices_ip_list = network_devices_ip_list
            
                except Exception as ex:
                    if self.DEBUG:
                        print("Avahi browse error: " + str(ex))
                
                
            except Exception as ex:
                if self.DEBUG:
                    print("Error while going over avahi-browse output: " + str(ex))
            
            
            
            
            
            try:
                command = "arp -a"
                result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
                
                if self.DEBUG:
                    print("arp -a results: \n" + str(result.stdout))
                
                for line in result.stdout.split('\n'):
                    #print("arp -a line: " + str(line))
                    if not "<incomplete>" in line and len(line) > 10:
                        if self.DEBUG:
                            print("quick scan: arp -a: checking line: " + str(line))
                        #found_device_name = "?"
                        mac_short = ""
                        found_device_name = "unnamed"
                        #possible_name = "Presence - unnamed"
                        
                        try:
                            mac_address_list = re.findall(r'(([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})', str(line))[0]
                            if self.DEBUG:
                                print("quick scan: arp -a: mac_address_list" + str(mac_address_list))
                            if len(mac_address_list) > 0:
                                mac_address = str(mac_address_list[0])
                                if self.DEBUG:
                                    print("quick scan: arp -a: mac_address from arp line: " + str(mac_address))
                                #mac_short = mac_to_hash(mac_address) #str(mac_address.replace(":", ""))
                                #_id = 'presence-{}'.format(mac_short)
                            else:
                                if self.DEBUG:
                                    print("quick scan: arp -a: no mac address in arp line, skipping")
                                continue
                        except Exception as ex:
                            if self.DEBUG:
                                print("quick scan: arp -a: getting mac from arp -a line failed: " + str(ex))
                    
                        try:
                            ip_address_list = re.findall(r'(?:\d{1,3}\.)+(?:\d{1,3})', str(line))
                            if self.DEBUG:
                                print("quick scan: arp -a: ip_address_list from arp line: " + str(ip_address_list))
                            ip_address = str(ip_address_list[0])
                            if valid_ip(ip_address):
                                if self.DEBUG:
                                    print("quick scan: arp -a: valid ip")
                            else:
                                if self.DEBUG:
                                    print("quick scan: arp -a: Error: not a valid IP address?")
                                continue
                            #found_device_name = 'unnamed'
                        except Exception as ex:
                            if self.DEBUG:
                                print("quick scan: arp -a: Error getting IP address from line: " + str(ex))
                            continue
                        
                        if valid_mac(mac_address):
                            if self.DEBUG:
                                print("quick scan: arp -a: mac and ip ok")
                            
                            
                            try:
                                # FIND NAME
                                if ip_address in self.avahi_lookup_table: # It could be that the name was found by Avahi, but it did not find the mac, which arp might find instead
                                    if self.DEBUG:
                                        print("quick scan: arp -a: spotted name in avahi lookup table")
                                    found_device_name = str(self.avahi_lookup_table[ip_address])
                                    #possible_name = found_device_name #self.parse_found_device(ip_address, found_device_name, mac_address)

                                # If not in avahi, maybe the NBT scan found it
                                elif ip_address in nbtscan_results.stdout:
                                    if self.DEBUG:
                                        print("quick scan: arp -a: spotted IP address in nbtscan_results, so extracting name form there")
                                    try:
                                        for nbtscan_line in nbtscan_results.stdout.split('\n'):
                                            if ip_address in nbtscan_line:
                                                #line = line.replace("#PRE","")
                                                nbtscan_line = nbtscan_line.rstrip()
                                                nbtscan_parts = nbtscan_line.split("\t")
                                                if len(nbtscan_parts) > 0:
                                                    found_device_name = str(nbtscan_parts[1])
                                                    #possible_name =self.parse_found_device(ip_address, nbtscan_parts[1], mac_address)
                                                    if self.DEBUG:
                                                        print("quick scan: arp -a: name extracted from nbtscan_result: " + str(found_device_name))
                                    except Exception as ex:
                                        if self.DEBUG:
                                            print("quick scan: arp -a: Error getting nice name from nbtscan_results: " + str(ex))

                                # if not, get the name from the arp -a line
                                elif ' (' in line:
                                    found_device_name = str(line.split(' (')[0])
                                    if self.DEBUG:
                                        print("quick scan: arp -a: remove part after ( from line")
                                else:
                                    if self.DEBUG:
                                        print("quick scan: arp -a: no name?")
                                        
                            except Exception as ex:
                                if self.DEBUG:
                                    print("quick scan: arp -a: Error getting name from line: " + str(ex))
                            
                            self.parse_found_device(ip_address, found_device_name, mac_address)
                        
                        
                            
                        
                        
                        """
                        if _id not in device_dict:
                        
                            # Now that IP and Mac are known, try to get the name (found_device_name)
                            try:
                            
                            
                            
                                # maybe the device is already known
                                if _id in self.previously_found:
                                    if 'name' in self.previously_found[_id]:
                                        #found_device_name = self.previously_found[_id]['name']
                                        self.previously_found[_id]['ip'] = ip_address
                                        if self.DEBUG:
                                            print("quick scan: arp -a: id was already in previously_found. Name: " + str(self.previously_found[_id]['name']))
                                        
                                        
                                    else:
                                        if self.DEBUG:
                                            print("quick scan: arp -a: Error, no name attribute in previously_found?")
                                
                                    continue
                                
                                # if not, maybe the name is in the Avahi-browse lookup table
                                elif ip_address in self.avahi_lookup_table: # It could be that the name was found by Avahi, but it did not find the mac, which arp might find instead
                                    if self.DEBUG:
                                        print("quick scan: arp -a: spotted name in avahi lookup table")
                                    found_device_name = str(self.avahi_lookup_table[ip_address])
                                    #possible_name = found_device_name #self.parse_found_device(ip_address, found_device_name, mac_address)
                            
                                # If not in avahi, maybe the NBT scan found it
                                elif ip_address in nbtscan_results.stdout:
                                    if self.DEBUG:
                                        print("quick scan: arp -a: spotted IP address in nbtscan_results, so extracting name form there")
                                    try:
                                        for nbtscan_line in nbtscan_results.stdout.split('\n'):
                                            if ip_address in nbtscan_line:
                                                #line = line.replace("#PRE","")
                                                nbtscan_line = nbtscan_line.rstrip()
                                                nbtscan_parts = nbtscan_line.split("\t")
                                                if len(nbtscan_parts) > 0:
                                                    found_device_name = str(nbtscan_parts[1])
                                                    #possible_name =self.parse_found_device(ip_address, nbtscan_parts[1], mac_address)
                                                    if self.DEBUG:
                                                        print("quick scan: arp -a: name extracted from nbtscan_result: " + str(found_device_name))
                                    except Exception as ex:
                                        if self.DEBUG:
                                            print("quick scan: arp -a: Error getting nice name from nbtscan_results: " + str(ex))
                            
                                # if not, get the name from the arp -a line
                                elif ' (' in line:
                                    found_device_name = str(line.split(' (')[0])
                                    if self.DEBUG:
                                        print("quick scan: arp -a: remove part after ( from line")
                                else:
                                    if self.DEBUG:
                                        print("quick scan: arp -a: no name?")
                        
                            except Exception as ex:
                                if self.DEBUG:
                                    print("Error: quick scan: arp -a: could not get name from arp -a line: " + str(ex))
                        
                        
                            if self.DEBUG:
                                print("quick scan: arp -a: found_device_name: " + str(found_device_name))
                        
                            
                            try:
                                # Add the device to the dictionary of found devices
                                possible_name = self.parse_found_device(ip_address, found_device_name, mac_address)
                            
                                if self.DEBUG:
                                    print("quick scan: arp -a: possible_name: " + str(possible_name))
                            
                                if self.ignore_candle_controllers and ip_address in self.candle_controllers_ip_list:
                                    if self.DEBUG:
                                        print("quick scan: arp -a: ignoring a Candle controller")
                                    continue
                                else:
                                    if self.DEBUG:
                                        print("quick scan: arp -a: adding device to found devices list\n")
                                    device_dict[_id] = {'ip':ip_address,'mac_address':mac_address,'name':possible_name,'first_seen':int(time.time()),'last_seen':None}
                            
                            
                            
                            except Exception as ex:
                                if self.DEBUG:
                                    print("Error: quick scan: arp -a: could not get name from arp -a line: " + str(ex))
                        
                        
                            #if mac_short != "" and found_device_name != 'unknown':
                                #print("util: arp: mac in line: " + line)
                                #item = {'ip':ip_address,'mac':mac_address,'name':name, 'mac_short':mac_address.replace(":", "")}
                                #return str(line)
                            
                                                        #else:
                            #    if self.DEBUG:
                            #        print("Skipping an arp -a result because of missing mac or name")
                                #print("device_dict = " + str(device_dict))
                            
                        """
                #return str(result.stdout)

            except Exception as ex:
                if self.DEBUG:
                    print("general error in quick scan with Arp -a: " + str(ex))
                #result = 'error'
            
            
            # This is a little tacked-on here, but it can give some more quick results
            try:
                if self.DEBUG:
                    print("\n\nneighbour scan:")
            
                # Also try getting IPv6 addresses from "ip neighbour"
            
                ip_neighbor_output = subprocess.check_output(['ip', 'neighbor']).decode('utf-8')
                if self.DEBUG:
                    print("ip_neighbor_output: " + str(ip_neighbor_output))
                    print("")
                for line in ip_neighbor_output.splitlines():
                    if line.endswith("REACHABLE") or line.endswith("STALE") or line.endswith("DELAY"):
                        if self.DEBUG:
                            print("stale, delay or reachable in line:  "+ str(line))
                        try:
                            mac_address = extract_mac(line)
                            if self.DEBUG:
                                print("mac_address: " + str(mac_address))
                            ip_address = line.split(" ", 1)[0]
                            if self.DEBUG:
                                print("ip_address: " + str(ip_address))
                            #possible_name = "unknown"
                
                            if ip_address == self.own_ip:
                                if self.DEBUG:
                                    print("ip neighbor was own IP address, skipping")
                                continue
                
                            if self.DEBUG:
                                print("neighbor mac: " + str(mac_address) + ", and ip: " + str(ip_address))
                            if valid_mac(mac_address) and valid_ip(ip_address):
                    
                                self.parse_found_device(ip_address, 'unnamed', mac_address)
                    
                        except Exception as ex:
                            if self.DEBUG:
                                print("error getting mac from ip neighbour line: " + str(ex))
                #o = run("python q2.py",capture_output=True,text=True)
                #print(o.stdout)
            
                #if self.DEBUG:
                #    print("\narpa scan found devices list: " + str(device_dict))
            
            except Exception as ex:
                if self.DEBUG:
                    print("quick scan: error while doing ip neighbour scan: " + str(ex))
            
            """
            try:
                if self.DEBUG:
                    print("")
                    print("quick scan results: " + str(device_dict))
                    print("quick scan result length: " + str(len(device_dict._ids())))
                    print("candle_controllers_ip_list: " + str(self.candle_controllers_ip_list))
                    print("")
                
                
                for _id in device_dict:
                    if self.DEBUG:
                        print("Analyzing quick scan item: " + str(device_dict[_id]))
                
                    try:
                        if _id not in self.previously_found:
                            if self.DEBUG:
                                print("-Adding to previously found list")
            
                            self.previously_found[_id] = {} # adding empty device to the previously found dictionary
                            self.previously_found[_id]['name'] = device_dict[_id]['name']
                            #self.previously_found[_id]['quick_time'] = int(time.time()) #device_dict[_id]['quick_time'] #timestamp of initiation
                            self.previously_found[_id]['last_seen'] = None #device_dict[_id]['quick_time'] #timestamp of initiation
                            self.previously_found[_id]['ip'] = device_dict[_id]['ip']
                            self.previously_found[_id]['mac_address'] = device_dict[_id]['mac_address']
                            self.previously_found[_id]['data-collection'] = True
                            self.should_save = True # We will be adding this new device to the list, and then save that updated list.
                        
                        
                        else:
                            
                            try:
                                self.previously_found[_id]['ip'] = device_dict[_id]['ip']
                            except:
                                print("Error, could not update IP from quick scan")
                        
                            
                    except Exception as ex:
                        print("Error while analysing quick scan result item: " + str(ex))
                    
            except Exception as ex:
                if self.DEBUG:
                    print("Error handling quick scan results: " + str(ex))

            
            """
            
            self.busy_doing_light_scan = False
            self.should_save = True
            
            if self.DEBUG:
                print("\nQUICK SCAN COMPLETE\n")
                
        else:
            if self.DEBUG:
                print("Warning, was already busy doing a light scan")
                
        #return device_dict
        #return str(subprocess.check_output(command, shell=True).decode())
        








    def parse_found_device(self,ip_address,found_device_name="unnamed",mac_address=""):
        if self.DEBUG:
            print("\nin parse_found_device")
        
        new_device = False
        possible_name = found_device_name
        
        
        _id = mac_to_id(mac_address) #mac_address.replace(":", "")
        
        if self.DEBUG:
            print("__ mac               = " + str(mac_address))
            print("__ _id               = " + str(_id))
            print("__ found_device_name = " + str(found_device_name))  
            print("__ ip                = " + str(ip_address))
        
        if not valid_ip(ip_address):
            if self.DEBUG:
                print("Error, parse_found_device aborting: invalid ip address (ipv6?): " + str(ip_address))
            return
        
        if ip_address == self.own_ip:
            if self.DEBUG:
                print("parse_found_device aborting: ip was own IP address")
            return
        
        if _id not in self.previously_found:
            if self.DEBUG:
                print("\n\n! NEW !\n\nparse_found_device: _id NOT already in previously_found")
                print("self.avahi_lookup_table: " + str(self.avahi_lookup_table))
                print("self.candle_controllers_ip_list: " + str(self.candle_controllers_ip_list))
                print("")
            
            
            try:
                # make the default name 'unnamed'
                if found_device_name == '' or found_device_name == '?' or valid_ip(found_device_name) or found_device_name == None:
                    found_device_name = 'unnamed'
            
            
                # if unnamed, try looking it up
                if found_device_name == 'unnamed':
                    try:
                        if ip_address in self.avahi_lookup_table:
                            if self.DEBUG:
                                print("parse_found_device: ip address was in avahi lookup table")
                            found_device_name = str(self.avahi_lookup_table[ip_address]) # + ' (' + str(ip_address) + ')'
        
                        else:
                            # Try to get hostname via NBT
                            try:
                                if ip_address in self.nbtscan_results:
                                    if self.DEBUG:
                                        print("parse_found_device: spotted IP address in nbtscan_results, so extracting name from there")
                
                                    for nbtscan_line in self.nbtscan_results.split('\n'):
                                        if ip_address in nbtscan_line:
                                            #line = line.replace("#PRE","")
                                            nbtscan_line = nbtscan_line.rstrip()
                                            nbtscan_parts = nbtscan_line.split("\t")
                                            if len(nbtscan_parts) > 0:
                                                #possible_name = "Presence - " + str(nbtscan_parts[1])
                                                found_device_name = str(nbtscan_parts[1])
                                                if self.DEBUG:
                                                    print("name extracted from nbtscan_result: " + str(found_device_name))

                            except Exception as ex:
                                if self.DEBUG:
                                    print("Error while getting name via nbtscan " + str(ex))
            
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
                    except Exception as ex:
                        if self.DEBUG:
                            print("error while looking up potential name: " + str(ex))
            
            
                # If still unnamed, try finding the vendor name based on the mac
                if found_device_name == 'unnamed':
                    if self.DEBUG: 
                        print("Will try to figure out a vendor name based on the mac address")
                    vendor = 'unnamed'
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
                            vendor = 'unnamed'
                    except ValueError:
                        pass

                    found_device_name = vendor
            

                found_device_name = "Presence - " +str(found_device_name) + ' (' + str(ip_address) + ')'
        

                possible_name = found_device_name
                if self.DEBUG: 
                    print("--possible name (may still be duplicate):  " + str(possible_name))
        
        
        
                try:
            
                   # _id = mac_short = mac_to_id(mac_address) #mac_address.replace(":", "")
            
                    #for item in self.previously_found:
                        #if self.DEBUG:
                        #    print("ADDING NEW FOUND DEVICE TO FOUND DEVICES LIST")
                        #self.should_save = True # We will be adding this new device to the list, and then save that updated list.

                    i = 2 # We skip "1" as a number. So we will get names like "Apple" and then "Apple 2", "Apple 3", and so on.
                    #possible_name = found_device_name
                    #could_be_same_same = True

                    for x in range(5):
                
                        #while could_be_same_same is True: # We check if this name already exists in the list of previously found devices.
                        could_be_same_same = False
                        try:
                            for key in self.previously_found:
                                #if self.DEBUG:
                                #    print("-checking possible name '" + str(possible_name) + "' against: " + str(self.previously_found[_id]['name']))
                                #    print("--prev found device _id = " + str(_id))
                        
                                # We skip checking for name duplication if the potential new device is the exact same device, so it would be logical if they had the same name.
                                if 'name' in self.previously_found[key]:
                                    if str(_id) == str(key):
                                        if self.DEBUG:
                                            print("key == _id")
                                        if str(possible_name) == str(self.previously_found[key]['name']):
                                            if self.DEBUG:
                                                print("the new name is the same as the old for this mac-address")
                                            #continue
                                            break
                        
                                    if str(possible_name) == str(self.previously_found[key]['name']): # The name already existed somewhere in the list, so we change it a little bit and compare again.
                                        could_be_same_same = True
                                        if self.DEBUG:
                                            print("-names collided (not the same mac as in previously_found data): " + str(possible_name))
                            
                                        try:
                                            if str(ip_address) == str(self.previously_found[key]['ip']):
                                                if self.DEBUG:
                                                    print('\n--> SOMETHING FISHY: same name, same ip address.. just not the same mac?: ' + str(key) + ' =?= ' + str(_id) + '\n')
                                        except:
                                            if self.DEBUG:
                                                print("Error, no ip in previously found device data?")
                                
                                        possible_name = str(found_device_name) + " " + str(i) #+ " (" + str(ip_address) + ")"
                                        #if self.DEBUG:
                                        #    print("-now testing new name: " + str(possible_name))
                                        i += 1 # up the count for a potential next round
                                        if i > 20:
                                            #if self.DEBUG:
                                            #    print("Reached 20 limit in while loop") # if the user has 20 of the same device, that's incredible.
                                            could_be_same_same = False
                                            break
                                else:
                                    if self.DEBUG:
                                        print("fishy. no name in self.previously_found[_id]: " + str(self.previously_found[_id]))
                                
                                
                        except Exception as ex:
                            if self.DEBUG:
                                print("Error doing duplicate name check in for loop: " + str(ex))
                            could_be_same_same = False
                            i += 1
                            break
                    
                        if could_be_same_same == False:
                            break
                    
                except Exception as ex:
                    if self.DEBUG:
                        print("Error in name duplicate check: " + str(ex))
        
            
                if self.DEBUG:
                    print("         FINAL OPTIMAL NAME: " + str(possible_name))
        
        
        
                try:
                
                
        
                    # an additional check to see if this is a Candle controller, and to make sure it's in the list of Candle controllers
                    if "Candle" in possible_name:
                        if self.DEBUG: 
                            print("parse_found_device: this is a candle controller")
                        self.candle_controllers_ip_list.add(ip_address)
                    else:
                        if self.DEBUG: 
                            print("not a candle device")
                
                    if ip_address in self.candle_controllers_ip_list:
                        return
                
                    if _id in self.previously_found:
                        if self.DEBUG: 
                            print("Error, _id was already in previously_found")
                        if self.previously_found[_id] != None:
                            if self.DEBUG: 
                                print("Error, somehow this id was already in the previously_found dict")
                    else:
                        if self.DEBUG: 
                            print('\nADDING new entry to previously_found')
                        self.previously_found[_id] = {}
                    
                        #self.previously_found[_id]['ip'] = ip_address
                        self.previously_found[_id]['mac_address'] = mac_address
                        self.previously_found[_id]['name'] = possible_name
                        self.previously_found[_id]['first_seen'] = int(time.time())
                        self.previously_found[_id]['last_seen'] = None
                        self.previously_found[_id]['data-collection'] = True
                        
                        new_device = True
                        # TODO: self.call scan here on the ip address? So that the last_seen can also be set?
                
                
                
                except Exception as ex:
                    if self.DEBUG:
                        print("Error adding/updating device: " + str(ex))
                
        
            except Exception as ex:
                if self.DEBUG:
                    print("Error in parse_found_device: " + str(ex))
        
        
        
        
        #else:
        if 'name' in self.previously_found[_id]:
            #found_device_name = self.previously_found[_id]['name']
            
            if self.DEBUG:
                print("UPDATING")
                print("- name in previously found: " + str(self.previously_found[_id]['name']))
                print("- updating ip")
            self.previously_found[_id]['ip'] = ip_address
        
            if self.DEBUG:
                print("- updating candle device boolean")
            if ip_address in self.candle_controllers_ip_list:
                if self.DEBUG:
                    print("-- candle device (via candle_controllers_ip_list)")
                self.previously_found[_id]['candle'] = True
                
            elif "Candle " in str(self.previously_found[_id]['name']):
                if self.DEBUG:
                    print("-- candle device (via Candle in name)")
                self.previously_found[_id]['candle'] = True
            else:
                if self.DEBUG:
                    print("-- not a candle device")
                self.previously_found[_id]['candle'] = False
        
            if self.DEBUG:
                print("- updating thing boolean")
            if _id in self.saved_devices:
                if self.DEBUG:
                    print("-- accepted as a thing")
                self.previously_found[_id]['thing'] = True
            else:
                if self.DEBUG:
                    print("-- not accepted as a thing")
                self.previously_found[_id]['thing'] = False
        
        else:
            if self.DEBUG:
                print("Error, found_device did not have name attribute?")
            # TODO: delete it?
            
        
        
        """
        if new_device:
            if self.ignore_candle_controllers and self.previously_found[_id]['candle'] == True:
                if self.DEBUG:
                    print("parse_found_device is ignoring a Candle controller")
                
            else:
                if self.DEBUG:
                    print("parse_found_device: adding a thing")
                self._add_device(_id, self.previously_found[_id]['name'], self.previously_found[_id]['ip']) # The device did not exist yet, so we're creating it.
            
            #self.should_save = True
            
        """
            
        #return possible_name

    

    def handle_device_saved(self, device_id, device):
        """User saved a thing. Also called when the add-on starts."""
        try:
            if device_id.startswith('presence'):
                if self.DEBUG:
                    print("\nhandle_device_saved. device_id = " + str(device_id) + ", device = " + str(device))

                if device_id not in self.saved_devices:
                    #print("Adding to saved_devices list: " + str(device_id.split("-")[1]))
                    if self.DEBUG:
                        print("Added " + str(device['title']) + " to saved devices list")
                    
                    original_title = "Unknown"
                    try:
                        if str(device['title']) != "":
                            original_title = str(device['title'])
                    except Exception as ex:
                        if self.DEBUG:
                            print("Error getting original_title from data provided by the controller: " + str(ex))
                    
                    #self.saved_devices.append({device_id:{'name':original_title}})
                    self.saved_devices.append(device_id)
                    
                    """
                    
                    data_collection = True
                    try:
                        if 'data-collection' in device['properties']:
                            data_collection = bool(device['properties']['data-collection']['value'])
                    except Exception as ex:
                        print("Error getting data collection preference from saved device update info: " + str(ex))
                
                    #print("Data_collection value is now: " + str(data_collection))
                    
                    if 'details' in device['properties']:
                    
                        try:
                            #pass
                            if device_id not in self.previously_found:
                                if self.DEBUG:
                                    print("Populating previously_found from handle_device_saved.")
                                self.previously_found[device_id] = {}
                                self.previously_found[device_id]['ip'] = str(device['properties']['details']['value']) #str(device['ip_address'])
                                self.previously_found[device_id]['name'] = str(device['title'])
                                self.previously_found[device_id]['last_seen'] = None   
                                self.previously_found[device_id]['first_seen'] = int(time.time())
                                #self.previously_found[device_id]['quick_time'] = int(time.time())
                                self.previously_found[device_id]['data-collection'] = bool(data_collection)
                        except Exception as ex:
                            if self.DEBUG:
                                print("Error adding to found devices list: " + str(ex))
                       
                    """
                        
        except Exception as ex:
            if self.DEBUG:
                print("Error dealing with existing saved devices: " + str(ex))





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
        except Exception as ex:
            if self.DEBUG:
                print("Removing presence detection thing failed: " + str(ex))
        #del self.devices[device_id]
        self.should_save = True # saving changes to the json persistence file
        return True
        
        
        

    def _add_device(self, _id, name, ip_address):
        """
        Add the given device, if necessary.

        """
        try:
            #print("adapter._add_device: " + str(name))
            device = PresenceDevice(self, _id, name, ip_address)
            self.handle_device_added(device)
            #print("-Adapter has finished adding new device for mac " + str(mac))

        except Exception as ex:
            if self.DEBUG:
                print("Error adding new device: " + str(ex))

        return




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
            if self.DEBUG:
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
            if self.DEBUG:
                print("error pinging! Error: " + str(ex))
            return 1


    def arping(self, ip_address, count):
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = "sudo arping -i " + str(self.selected_interface) + " " + str(param) + " " + str(count) + " " + str(ip_address)
        if self.DEBUG:
            print("arping command: " + str(command))
        try:
            result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.DEVNULL) #.decode())
            return result.returncode
        except Exception as ex:
            if self.DEBUG:
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
                if self.DEBUG:
                    print("Arp error: " + str(ex))
                result = 'error'
            return result
            #return str(subprocess.check_output(command, shell=True).decode())
        
    
    
    # saves to persistence file
    def save_to_json(self):
        """Save found devices to json file."""
        try:
            if self.DEBUG:
                print("Saving updated list of found devices to json file")
            #if self.previously_found:
            #with open(self.persistence_file_path, 'w') as fp:
                #json.dump(self.previously_found, fp)
                
            data_to_write = {'devices':self.previously_found,'mayor_version':self.mayor_version}
                
            j = json.dumps(self.previously_found, indent=4) # Pretty printing to the file
            f = open(self.persistence_file_path, 'w')
            print(j, file=f)
            f.close()
                
        except Exception as ex:
            print("Saving to json file failed: " + str(ex))
        self.should_save = False


    def start_pairing(self, timeout):
        """Starting the pairing process."""
        self.quick_scan()
        self.brute_force_scan()
        #if self.busy_doing_brute_force_scan == False:
        #    self.should_brute_force_scan = True
        #    self.brute_force_scan()

    def cancel_pairing(self):
        """Cancel the pairing process."""
        self.save_to_json()


    def unload(self):
        """Add-on is shutting down."""
        if self.DEBUG:
            print("Network presence detector is being unloaded")
        self.save_to_json()
        self.running = False
        
        
        


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



        
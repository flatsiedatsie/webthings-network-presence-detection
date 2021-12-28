"""Network presence adapter for WebThings Gateway."""

import re
import time
import datetime
#import dateutil.parser
from gateway_addon import Device, Action
from .presence_property import PresenceProperty



class PresenceDevice(Device):
    """network presence device type."""

    def __init__(self, adapter, _id, name, details):
        """
        Initialize the object.

        adapter -- the Adapter managing this device
        _id -- ID of this device
        name -- The name for this device
        index -- index inside parent device
        """

        
        #Device.__init__(self, adapter, 'presence-{}'.format(mac))
        Device.__init__(self, adapter, _id)
        
        
        self.adapter = adapter
        self.name = name
        self.description = "A device on the local network"
        self._id = _id
        #print("init " + str(self._id))
        self._type = ['BinarySensor']
        #self.properties = {}
        #print("device self.properties at init: " + str(self.properties))
        #self.connected_notify(True)
        
        self.last_add_mute_time = 0
        self.mute_until = 0

        self.properties['details'] = PresenceProperty(
            self,
            'details',
            {
                'title': 'Details',
                'type': 'string',
                'readOnly': True,
            },
            str(details))
            
        if self.adapter.DEBUG:
            print("+ Adding new device: " + str(name))
            
        action_meta = { "toggle": 
            {
            "@type": "ToggleAction",
            "title": "Toggle",
            "description": "Toggggle"
            }
        }
        self.add_action("Data mute", action_meta)

        

        
    def perform_action(self, action):
        try:
            print("perform action: " + str(action))
            d = action.as_dict()
            print("keys: " + str(d.keys))
            for k, v in d.items():
                print(k, v, type(v))
            
            if self._id in self.adapter.previously_found:
                print("continue performing action")
                if 'data_mute_end_time' not in self.adapter.previously_found[self._id]:
                    print("mute end time was not in persistent data. Setting to 0.")
                    self.adapter.previously_found[self._id]['data_mute_end_time'] = 0
                
                if 'last_data_mute_request_time' not in self.adapter.previously_found[self._id]:
                    print("last_data_mute_request_time was not in persistent data. Setting to 0.")
                    self.adapter.previously_found[self._id]['last_data_mute_request_time'] = 0
                    
                if 'last_data_mute_request_count' not in self.adapter.previously_found[self._id]:
                    print("last_data_mute_request_count was not in persistent data. Setting to 0.")
                    self.adapter.previously_found[self._id]['last_data_mute_request_count'] = 0
            
                #timestamp = int(iso_to_timestamp(str(d['timeRequested'])))
                timestamp = int( time.time() )
                print("timestamp = " + str(timestamp))
                #print("=?= time.time() = " + str(time.time()))
                #timestamp = datetime.fromisoformat(d['timeRequested']).timestamp() # from python 3.7 onwards..
                
                #print("timestamp = " + str(timestamp))
                #print("timestamp type = " + str(type(timestamp)))
                print("data_mute_end_time type = " + str(type( self.adapter.previously_found[self._id]['data_mute_end_time'] )))
                print("last_data_mute_request_time = " + str(type( self.adapter.previously_found[self._id]['last_data_mute_request_time'] )))
                end_time_delta = timestamp - self.adapter.previously_found[self._id]['data_mute_end_time']
                request_time_delta = timestamp - self.adapter.previously_found[self._id]['last_data_mute_request_time']
            
                #print("end_time_delta = " + str(end_time_delta))
                #print("request_time_delta = " + str(request_time_delta))

                print("self.adapter.previously_found[self._id]['data_mute_end_time'] = " + str(self.adapter.previously_found[self._id]['data_mute_end_time']))
                # if we are not currently already in a mute period:
                if timestamp > self.adapter.previously_found[self._id]['data_mute_end_time']:
                    print("current time is beyond last known mute period. Setting to one hour from now.")
                    self.adapter.previously_found[self._id]['data_mute_end_time'] = timestamp + 3600 # add one hour from now
                else:
                    print("already in mute period, adding one hour")
                    self.adapter.previously_found[self._id]['data_mute_end_time'] += 3600 # otherwise add one hour to the existing mute period end time
                    print( str(self._id) + " has a new MUTE endtime one hour longer: " + str(self.adapter.previously_found[self._id]['data_mute_end_time']) )
                    
                    
                # This makes sure that you can only learn how much hours you're adding during a short time window. Without this you could figure out how many hours are already on
                if timestamp > self.adapter.previously_found[self._id]['last_data_mute_request_time'] + 60: # 60 seconds window
                    #print("setting last request timestamp")
                    self.adapter.previously_found[self._id]['last_data_mute_request_time'] = timestamp
                    self.adapter.previously_found[self._id]['last_data_mute_request_count'] = 1
                else:
                    #print("adding one hour")
                    self.adapter.previously_found[self._id]['last_data_mute_request_count'] += 1
                    
                #if(d['timeRequested'] < self.last_add_mute_time + )
        
                #self.adapter.send_pairing_prompt("one hour added", None, {'id': self._id})
                if self.adapter.previously_found[self._id]['last_data_mute_request_count'] == 1:
                    #print("count is 1")
                    self.adapter.send_pairing_prompt("Ignoring for 1 hour", None, self)
                else:
                    #print("count is more than 1")
                    self.adapter.send_pairing_prompt("You added " + str(self.adapter.previously_found[self._id]['last_data_mute_request_count']) + " ignore hours", None, self)
        
                # remember when the last request to add mute time happened
                self.adapter.previously_found[self._id]['last_data_mute_request_time'] = timestamp
                self.adapter.should_save = True
                
        except Exception as ex:
            if self.adapter.DEBUG:
                print("action error: " + str(ex))
            


    def add_boolean_child(self, propertyID, new_description, new_value, readOnly=True, addProperty=""):
        if self.adapter.DEBUG:
            print("+ DEVICE.ADD_BOOLEAN_CHILD with id: " + str(propertyID))


        description = {
                'title': new_description,
                'type': 'boolean',
                'readOnly': readOnly,
            }
        if addProperty != "":
            description['@type'] = addProperty #'BooleanProperty'

        self.properties[propertyID] = PresenceProperty(
            self,
            propertyID,
            description,
            new_value)

        try:
            self.notify_property_changed(self.properties[propertyID])
            self.adapter.handle_device_added(self)
            #print("-All properties: " + str(self.get_property_descriptions()))

        except Exception as ex:
            print("Error in handle_device_added after adding property: " + str(ex))


    def add_integer_child(self, propertyID, new_description, new_value):
        if self.adapter.DEBUG:
            print("+ DEVICE.ADD_INTEGER_CHILD with id: " + str(propertyID) + " and value: " + str(new_value))

        self.properties[propertyID] = PresenceProperty(
            self,
            propertyID,
            {
                'title': new_description,
                'type': 'integer',
                'readOnly': True,
            },
            new_value)

        try:
            self.notify_property_changed(self.properties[propertyID])
            self.adapter.handle_device_added(self)
            #print("-All properties: " + str(self.get_property_descriptions()))

        except Exception as ex:
            print("Handle_device_added after adding property error: " + str(ex))


def iso_to_timestamp(timestamp):
    # This regex removes all colons and all
    # dashes EXCEPT for the dash indicating + or - utc offset for the timezone
    conformed_timestamp = re.sub(r"[:]|([-](?!((\d{2}[:]\d{2})|(\d{4}))$))", '', timestamp)

    # Split on the offset to remove it. Use a capture group to keep the delimiter
    split_timestamp = re.split(r"([+|-])",conformed_timestamp)
    main_timestamp = split_timestamp[0]
    if len(split_timestamp) == 3:
        #print("time offset")
        sign = split_timestamp[1]
        offset = split_timestamp[2]
    else:
        sign = None
        offset = None

    # Generate the datetime object without the offset at UTC time
    #print("parsing time: " + str(main_timestamp))
    output_datetime = datetime.datetime.strptime(main_timestamp, "%Y%m%dT%H%M%S" )
    if offset:
        # Create timedelta based on offset
        offset_delta = datetime.timedelta(hours=int(sign+offset[:-2]), minutes=int(sign+offset[-2:]))

        # Offset datetime with timedelta
        output_datetime = output_datetime + offset_delta
    
    return output_datetime.timestamp()
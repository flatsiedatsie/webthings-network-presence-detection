"""Network presence adapter for Mozilla WebThings Gateway."""


#import threading
#import time

from gateway_addon import Device
from .presence_property import presenceProperty
#from .util import pretty, is_a_number, get_int_or_float



class presenceDevice(Device):
    """network presence device type."""

    def __init__(self, adapter, mac, name, details):
        """
        Initialize the object.

        adapter -- the Adapter managing this device
        _id -- ID of this device
        name -- The name for this device
        index -- index inside parent device
        """
        
        print()
        print("+ DEVICE init: " + str(name))
        Device.__init__(self, adapter, mac)
        
        self.adapter = adapter
        self.id = str(mac)
        self._id = str(mac)
        self.name = name
        self.description = "A device on the local network"
        self._type = ['BinarySensor']
        self.properties = {}
        #print("device self.properties at init: " + str(self.properties))
        #self.connected_notify(True)
        
        self.properties['Details'] = presenceProperty(
            self,
            'Details',
            {
                'label': 'Details',
                'type': 'string',
                'readOnly': True,
            },
            str(details))
        
        #self.add_boolean_child('lasthour', "Seen in the last hour", False)


    def add_boolean_child(self, propertyID, new_description, new_value):
        print()
        print("+ DEVICE.ADD_CHILD with id: " + str(propertyID))

        self.properties[propertyID] = presenceProperty(
            self,
            propertyID,
            {
                '@type': 'BooleanProperty',
                'label': new_description,
                'type': 'boolean',
                'readOnly': True,
            },
            new_value)

        try:
            self.notify_property_changed(self.properties[propertyID])
            self.adapter.handle_device_added(self)
            print("-All properties: " + str(self.get_property_descriptions()))

        except Exception as ex:
            print("Handle_device_added after adding property error: " + str(ex))
    
"""Network presence adapter for Mozilla WebThings Gateway."""

from gateway_addon import Device
from .presence_property import PresenceProperty
from.util import printDebug



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

        print()
        print("+ DEVICE init: " + str(name))
        #Device.__init__(self, adapter, 'presence-{}'.format(mac))
        Device.__init__(self, adapter, _id)

        self.adapter = adapter
        self.name = name
        self.description = "A device on the local network"
        self._type = ['BinarySensor']
        self.properties = {}
        printDebug("device self.properties at init: " + str(self.properties), self.adapter.DEBUG)
        #self.connected_notify(True)

        self.properties['details'] = PresenceProperty(
            self,
            'details',
            {
                'label': 'Details',
                'type': 'string',
                'readOnly': True,
            },
            str(details))


    def add_boolean_child(self, propertyID, new_description, new_value):
        print("+ DEVICE.ADD_BOOLEAN_CHILD with id: " + str(propertyID))

        self.properties[propertyID] = PresenceProperty(
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
            printDebug("-All properties: " + str(self.get_property_descriptions()), self.adapter.DEBUG)

        except Exception as ex:
            print("Error in handle_device_added after adding property: " + str(ex))


    def add_integer_child(self, propertyID, new_description, new_value):
        print("+ DEVICE.ADD_INTEGER_CHILD with id: " + str(propertyID))

        self.properties[propertyID] = PresenceProperty(
            self,
            propertyID,
            {
                'label': new_description,
                'type': 'integer',
                'readOnly': True,
            },
            new_value)

        try:
            self.notify_property_changed(self.properties[propertyID])
            self.adapter.handle_device_added(self)
            printDebug("-All properties: " + str(self.get_property_descriptions()), self.adapter.DEBUG)

        except Exception as ex:
            print("Handle_device_added after adding property error: " + str(ex))

"""Network presence adapter for Mozilla WebThings Gateway."""

from gateway_addon import Property
from .util import printDebug

class PresenceProperty(Property):
    """Network presence property type."""

    def __init__(self, device, name, description, value):
        """
        Initialize the object.

        device -- the Device this property belongs to
        name -- name of the property
        description -- description of the property, as a dictionary
        value -- current value of this property
        """
        printDebug("", device.adapter.DEBUG)
        print("+ PROPERTY init: " + str(name))
        printDebug("-device: " + str(device), device.adapter.DEBUG)
        printDebug("-name: " + str(name), device.adapter.DEBUG)
        printDebug("-description: " + str(description), device.adapter.DEBUG)
        print("-value: " + str(value))
        try:
            Property.__init__(self, device, name, description)


            self.device = device
            self.name = name
            self.description = description
            self.value = value

            self.set_cached_value(value)
            self.device.notify_property_changed(self)
            printDebug("property init done", self.device.adapter.DEBUG)

        except Exception as ex:
            print("property: could not init. Error: " + str(ex))


    def set_value(self, value):
        """
        Set the current value of the property. This is called when the user uses the gateway UX.

        value -- the value to set
        """

        print("property -> set_value")
        print("->name " + str(self.name))


    def update(self, value):
        """
        Update the current value, if necessary.

        value -- the value to update
        """

        printDebug("property -> update to: " + str(value), self.device.adapter.DEBUG)
        try:
            if value != self.value:
                printDebug("-property has updated to "  + str(value), self.device.adapter.DEBUG)
                #self.set_cached_value_and_notify(self, value) For future version, can then remove both lines below.
                self.set_cached_value(value)
                self.device.notify_property_changed(self)
            else:
                printDebug("-property was already at the correct value", self.device.adapter.DEBUG)
                pass
        except:
            print("Error updating property")

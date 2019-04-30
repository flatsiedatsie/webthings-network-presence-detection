"""MySensors adapter for Mozilla WebThings Gateway."""

import mysensors.mysensors as mysensors

from gateway_addon import Property
from .util import pretty, is_a_number, get_int_or_float

class presenceProperty(Property):
    """MySensors property type."""

    def __init__(self, device, name, description, value):
        """
        Initialize the object.

        device -- the Device this property belongs to
        name -- name of the property
        description -- description of the property, as a dictionary
        value -- current value of this property
        """
        print()
        print("+ PROPERTY init: " + str(name))
        print("-device: " + str(device))
        #print("-name: " + str(name))
        print("-description: " + str(description))
        print("-value: " + str(value))
        try:
            Property.__init__(self, device, name, description)


            self.device = device
            self.name = name # These three are used in the set_value function to send a message back to the proper node in the MySensors network.
            self.description = description
            self.value = value
            
            self.set_cached_value(value)
            self.device.notify_property_changed(self)
            print("property init done")
            
        except Exception as ex:
            print("inside adding property error: " + str(ex))


    def set_value(self, value):
        """
        Set the current value of the property.

        value -- the value to set
        """
        
        print("property -> set_value")
        print("->name " + str(self.name))


    def update(self, value): 
        """
        Update the current value, if necessary.

        value -- the value to update
        """
        
        print("property -> update")
        
        if value != self.value:
            print("-property has updated")
            self.set_cached_value(value)
            self.device.notify_property_changed(self)
        else:
            print("-property was already at the correct value")

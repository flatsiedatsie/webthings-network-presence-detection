"""Network presence adapter for Mozilla WebThings Gateway."""

from gateway_addon import Property


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
        print()
        print("+ PROPERTY init: " + name)
        print("-device: " + str(device))
        print("-description: " + str(description))
        print("-value: " + str(value))
        try:
            Property.__init__(self, device, name, description)

            self.device = device
            self.name = name
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
        print("->name " + self.name)

    def update(self, value):
        """
        Update the current value, if necessary.

        value -- the value to update
        """
        print("property -> update to: " + str(value))

        if value != self.value:
            print("-property has updated")
            self.set_cached_value(value)
            self.device.notify_property_changed(self)
        else:
            print("-property was already at the correct value")

class Port:
    def __init__(self, location: str, vlan_access: int, description: str):
        self.location = location
        self.vlan_access = vlan_access
        self.description = description
        self.blade_number = int(self.location[:self.location.index("/")])
        self.port_number = int(self.location[self.location.index("/1/") + 3:])
    
    #Changes the location of the port to a specified blade
    def remap(self, new_blade_number: int):
        self.blade_number = new_blade_number
        self.location = str(self.blade_number) + self.location[self.location.index("/"):]

class Port_Group:
    def __init__(self, vlan_access: int, description: str):
        self.vlan_access = vlan_access
        self.description = description
        self.ports = []
        self.vanilla_commands = [
            "no shutdown\n",
            "no routing\n",
            "vlan trunk native 1\n",
            "vlan trunk allow 1,40,100,200,240\n"
        ]
    
    #Returns a list of commands for configuring the port group
    def get_connfiguration(self) -> list:
        #Tests if the group is vanilla
        if self.vlan_access is None and self.description is None:
            return self.vanilla_commands.insert(0, self.get_interface_command())
        #Tests if the group is a vlan access group
        if self.vlan_access is not None:
            return [self.get_interface_command(), f"vlan access {self.vlan_access}\n\n"]
        #Tests if the group is a description group
        if self.description is not None:
            return [self.get_interface_command(), f"description {self.description}\n\n"]

    #Returns the interface command for a port group
    def get_interface_command(self) -> str:
        interface_command = "interface "
        interface_ranges = self.get_interface_ranges()
        for range in interface_ranges:
            if len(range) <= 2: #Two ports in sequence will not get range notation
                for port in range:
                    interface_command += f"{port.location},"
            else:
                start = range[0].location
                end = range[-1].location
                interface_command += f"{start}-{end},"
        return f"{interface_command[0:-1]}\n" #Slicing the command removes the last comma

    #Simplifies the list of locations to ranges if possible
    def get_interface_ranges(self):
        interface_ranges = [[self.ports[0]]]
        for i in range(1,len(self.ports)):
            current_port = self.ports[i]
            previous_port = self.ports[i - 1]
            on_same_blade = current_port.blade_number == previous_port.blade_number
            in_sequence = on_same_blade and current_port.port_number == previous_port.port_number + 1
            if in_sequence:
                interface_ranges[-1].append(current_port)
            else:
                interface_ranges.append([current_port])
        return interface_ranges
    
class Switch(Port_Group):
    def __init__(self, blade_number: int):
        self.blade_number = blade_number
        self.ports = None
        super().__init__(None, None)
    
    #Changes the location of every port to a specified blade
    def remap(self, new_blade_number: int):
        self.blade_number = new_blade_number
        for port in self.ports:
            port.remap(new_blade_number)

class Stack:
    def __init__(self, hostname: str, ip_address: str, switches: list):
        pass


def console():
    command = ""
    while command != "exit":
        command = input("> ")
        if "translate" in command:
            try:
                with open(command[10:], "w") as old_configuraton_file:
                    if len(old_configuraton_file.readlines()) == 0:
                        old_configuraton_file.close()
                        raise Exception
                    print(len(old_configuraton_file.readlines()))
            except:
                print("**File Not Found**")
        elif "?" in command:
            print("translate [filename.txt]")
console()

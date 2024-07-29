import os
import time

# Add 24 Port Configuration Functionality with AP mapping
# Add remapping functionality


class Port:
    def __init__(self, location: str, vlan_access: int, description: str):
        self.location = location
        self.vlan_access = vlan_access
        self.description = description
        self.blade_number = int(self.location[: self.location.index("/")])
        self.port_number = int(self.location[self.location.index("/1/") + 3 :])

    # Changes the location of the port to a specified blade
    def remap(self, new_blade_number: int):
        self.blade_number = new_blade_number
        self.location = (
            str(self.blade_number) + self.location[self.location.index("/") :]
        )


class Port_Group:
    def __init__(self, vlan_access: int, description: str):
        self.vlan_access = vlan_access
        self.description = description
        self.ports = []
        self.vanilla_commands = [
            "",
            "no shutdown\n",
            "no routing\n",
            "vlan trunk native 1\n",
            "vlan trunk allowed 1,40,100,200,240\n\n",
        ]

    def append(self, port: Port):
        self.ports.append(port)

    # Returns a list of commands for configuring the port group
    def get_configuration(self) -> list:
        # Tests if the group is vanilla
        if self.vlan_access is None and self.description is None:
            self.vanilla_commands[0] = self.get_interface_command()
            return self.vanilla_commands
        # Tests if the group is a vlan access group
        if self.vlan_access is not None:
            return [self.get_interface_command(), f"vlan access {self.vlan_access}\n\n"]
        # Tests if the group is a description group
        if self.description is not None:
            return [self.get_interface_command(), f"description {self.description}\n\n"]

    # Returns the interface command for a port group
    def get_interface_command(self) -> str:
        interface_command = "interface "
        interface_ranges = self.get_interface_ranges()
        for range in interface_ranges:
            if len(range) <= 2:  # Two ports in sequence will not get range notation
                for port in range:
                    interface_command += f"{port.location},"
            else:
                start = range[0].location
                end = range[-1].location
                interface_command += f"{start}-{end},"
        return (
            f"{interface_command[0:-1]}\n"  # Slicing the command removes the last comma
        )

    # Simplifies the list of locations to ranges if possible
    def get_interface_ranges(self):
        interface_ranges = [[self.ports[0]]]
        for i in range(1, len(self.ports)):
            current_port = self.ports[i]
            previous_port = self.ports[i - 1]
            on_same_blade = current_port.blade_number == previous_port.blade_number
            in_sequence = (
                on_same_blade
                and current_port.port_number == previous_port.port_number + 1
            )
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

    # Changes the location of every port to a specified blade
    def remap(self, new_blade_number: int):
        self.blade_number = new_blade_number
        for port in self.ports:
            port.remap(new_blade_number)


class Stack:
    def __init__(self, hostname: str, ip_address: str, switches: list):
        self.hostname = hostname
        self.node = hostname[-3:] if hostname[-3] != 0 else hostname[-2:]
        self.ip_address = ip_address
        self.switches = switches
        self.has_24_port = input("Configure 24 Port Switch? (Y/N): ").lower() == "y"

    def get_configuration(self):
        hostname_command = f"hostname {self.hostname}\n\n"
        vlan_1_command = f"interface vlan 1\nip address {self.ip_address}/16\nexit\n\n"
        index = self.ip_address.index(".", self.ip_address.index(".") + 1)
        ip_route_command = f"ip route 0.0.0.0/0 {self.ip_address[:index]}.0.1\n\n"
        temp = [ip_route_command, vlan_1_command, hostname_command]
        commands = self.get_commands()
        for command in temp:
            commands.insert(0, command)
        for command, i in zip(
            self.configure_lag_interface(),
            range(len(self.configure_lag_interface())),
        ):
            commands.insert(i + 3, command)
        return commands

    def get_commands(self):
        all_ports, vlan_groups, description_groups = self.sort()
        commands = all_ports.get_configuration()
        for group in vlan_groups:
            for command in group.get_configuration():
                commands.append(command)
        for group in description_groups:
            for command in group.get_configuration():
                commands.append(command)
        for command in self.configure_uplink():
            commands.append(command)
        commands.append("vsf split-detect mgm\n\n")
        commands.append(f"vsf secondary-member {self.switches[-1].blade_number}\n\n")
        return commands

    def sort(self) -> tuple:
        vlan_groups = []
        vlans = []
        description_groups = []
        descriptions = []
        all_ports = Port_Group(None, None)
        for switch in self.switches:
            for port in switch.ports:
                vlan = port.vlan_access
                description = port.description
                if vlan is not None:
                    if vlan in vlans:
                        vlan_groups[vlans.index(vlan)].append(port)
                    else:
                        group = Port_Group(vlan, None)
                        group.append(port)
                        vlan_groups.append(group)
                        vlans.append(vlan)
                if description is not None:
                    if description in descriptions:
                        description_groups[descriptions.index(description)].append(port)
                    else:
                        group = Port_Group(None, description)
                        group.append(port)
                        description_groups.append(group)
                        descriptions.append(description)
                all_ports.append(port)
        if self.has_24_port:
            blade_number = all_ports.ports[-1].blade_number + 1
            self.switches.append(Switch(blade_number))
            for i in range(1, 25):
                port = Port(f"{blade_number}/1/{i}", None, None)
                self.switches[-1].append(port)
                all_ports.append(port)
        return (all_ports, vlan_groups, description_groups)

    def configure_uplink(self):
        port = self.switches[-1].ports[-1]
        location = f"{port.blade_number}/1/{port.port_number + 4}"
        return [
            f"interface {location}\n",
            "description UPLINK to CORE\n",
            "no shutdown\n" "no routing\n",
            "vlan trunk native 1\n",
            "vlan trunk allowed 1,40,56,70,72,100,200,240,250\n",
            "dhcpv4-snooping trust\n\n",
        ]

    def configure_lag_interface(self):
        return [
            f"interface lag {self.node}\n",
            "description UPLINK to CORE\n",
            "no shutdown\n" "no routing\n",
            "vlan trunk native 1\n",
            "vlan trunk allowed 1,40,56,70,72,100,200,240,250\n",
            "dhcpv4-snooping trust\n",
            "lacp mode active\n\n",
        ]


class Translator:
    def translate(self, old_config_name: str):
        with open(old_config_name, "r") as old_config_file:
            hostname = None
            ip_address = None
            location = None
            vlan_access = None
            description = None
            allowed_vlans = None
            switches = [Switch(1)]
            for line in old_config_file.readlines():
                if "interface GigabitEthernet" in line:
                    location = line[25:-1].replace("/0/", "/1/")
                elif "access vlan" in line and location is not None:
                    vlan_access = line[18:-1]
                elif "description" in line and location is not None:
                    description = line[13:-1]
                    if "ap" in description.lower() or "pa" in description.lower():
                        description = None
                elif "#" in line and location is not None:
                    port = Port(location, vlan_access, description)
                    if port.blade_number == switches[-1].blade_number:
                        switches[-1].append(port)
                    else:
                        switch = Switch(port.blade_number)
                        switch.append(port)
                        switches.append(switch)
                    location = None
                    vlan_access = None
                    description = None
                elif "sysname" in line:
                    hostname = line[9:-1].upper().replace(" ", "_").replace("_", "-")
                    hostname = (
                        f"{hostname[0:-2]}0{hostname[-2:]}"
                        if hostname[-3] == "-"
                        else hostname
                    )
                elif "ip address" in line:
                    ip_address = line[12 : line.index("255") - 1]
            for switch in switches:
                port_num = switch.ports[-1].port_number
                if port_num != 48:
                    print(f"*Blade {switch.blade_number} has {port_num} ports*")
                    upgrade = input("Upgrade to 48 Port Switch? (Y/N): ").lower() == "y"
                    if upgrade:
                        for i in range(port_num + 1, 49):
                            port = Port(f"{switch.blade_number}/1/{i}", None, None)
                            switch.append(port)
            return Stack(hostname, ip_address, switches)


def generate_config(file_name: str) -> list:
    t = Translator()
    stack = t.translate(file_name)
    config_name = f"{stack.hostname}.txt"
    config = stack.get_configuration()
    with open(config_name, "w") as config_file:
        config_file.writelines(config)
    return config


def console():
    command = ""
    while command != "exit":
        command = input("> ")
        if "translate" in command:
            generate_config(command[10:])
            print("*New Configuration Generated Successfully*")
        elif "?" in command:
            print("translate [filename.txt]")


console()

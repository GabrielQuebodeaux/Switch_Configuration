# Declares File Variables
old_config_file = open("Old_Config.txt", "r")
new_config_file = open("New_Config.txt", "w")

class Port:
    def __init__(self, location: str, vlan_access: str, description: str):
        self.location = location
        self.coordinates = self.set_coordinates(self.location)
        self.vlan_access = vlan_access
        self.description = description
        if self.description is None:
            return
        elif "ap" in self.description.lower() or "ruckus" in self.description.lower():
            self.description = None
    def set_coordinates(self, location: str) -> tuple:
        switch_coordinate = int(location[0:location.index("/1/")])
        port_coordinate = int(location[location.index("/1/") + 3:])
        return (switch_coordinate, port_coordinate)
    def get_location(self) -> str:
        return self.location
    def get_coordinates(self) -> tuple:
        return self.coordinates
    def get_vlan_access(self):
        return self.vlan_access
    def get_description(self):
        return self.description
    def remap(self, new_switch: int):
        self.location = str(new_switch) + self.location[self.location.index("/"):]
        return self

class Port_Group:
    def __init__(self, vlan_access: int, description: str):
        self.vlan_access = vlan_access
        self.description = description
        self.port_list = []
    def add_port(self, port: Port):
        self.port_list.append(port)
        return self.port_list
    def get_vlan_access(self) -> str:
        return self.vlan_access
    def get_description(self) -> str:
        return self.description
    def get_port_list(self) -> list:
        return self.port_list
    def configure(self) -> list:
        configuration_prompts = []
        interface_prompt = self.get_interface_prompt()
        configuration_prompts.append(interface_prompt)
        if self.vlan_access is None and self.description is None:
            for prompt in self.get_vanilla_prompt():
                configuration_prompts.append(prompt)
        else:
            if self.vlan_access is not None:
                vlan_access_prompt = self.get_vlan_access_prompt()
                configuration_prompts.append(vlan_access_prompt)
            if self.description is not None:
                description_prompt = self.get_description_prompt()
                configuration_prompts.append(description_prompt)
        configuration_prompts.append("\n")
        return configuration_prompts
    def get_interface_prompt(self) -> str:
        interface_prompt = "interface "
        interface_ranges = self.get_interface_ranges()
        for interface_range in interface_ranges:
            range_length = len(interface_range)
            if range_length <= 2:
                for port in interface_range:
                    interface_prompt += f"{port.get_location()},"
            else:
                start = interface_range[0].get_location()
                end = interface_range[-1].get_location()
                interface_prompt += f"{start}-{end},"
        interface_prompt = f"{interface_prompt[0:-1]}\n"
        return interface_prompt
            
    def get_interface_ranges(self) -> list:
        interface_ranges = []
        current_range = []
        last_port = None
        for port in self.port_list:
            if last_port is None:
                last_port = port
                current_range = [last_port]
                continue
            last_port_coordinates = last_port.get_coordinates()
            current_port_coordinates = port.get_coordinates()
            on_same_switch = last_port_coordinates[0] == current_port_coordinates[0]
            in_sequence = on_same_switch and last_port_coordinates[1] + 1 == current_port_coordinates[1]
            if in_sequence:
                current_range.append(port)
            else:
                interface_ranges.append(current_range)
                current_range = [port]
            last_port = port
        interface_ranges.append(current_range)
        return interface_ranges
    
    def get_vlan_access_prompt(self):
        return f"vlan access {self.vlan_access}\n"
    
    def get_description_prompt(self):
        return f"description {self.description}\n"
    
    def get_vanilla_prompt(self):
        return [
            "no shutdown\n",
            "no routing\n",
            "vlan trunk native 1\n",
            "vlan trunk allow 1,40,100,200,240\n"
        ]

class Switch(Port_Group):
    def __init__(self, vsf_member: int):
        self.vsf_member = vsf_member
        self.port_list = []
        super().__init__(None, None)
    def get_vsf_member(self):
        return self.vsf_member
    def remap(self, new_switch: int):
        self.vsf_member = new_switch
        for port in self.port_list:
            port.remap(new_switch)
        return self


class Stack:
    def __init__(self, hostname: str, ip_address: str, switch_list: list, groups: Port_Group, remap = False):
        self.num_48_port_switches = int(input("Number of 48 Port Switches: "))
        self.has_24_port_switch = input("Stack Has 24 Port Switch? (Y/N): ").lower() == "y"
        self.hostname = hostname
        self.ip_address = ip_address
        self.switch_list = switch_list
        self.groups = groups
        if self.num_48_port_switches < 3 and not self.has_24_port_switch or self.num_48_port_switches == 1:
            return
        configure_secondary = input("Configure Last Switch as Secondary? (Y/N): ").lower() == "y"
        if not configure_secondary:
            return
        if self.has_24_port_switch:
            new_config_file.write(f"vsf secondary {self.num_48_port_switches + 1}\n\n")
        else:
            new_config_file.write(f"vsf secondary {self.num_48_port_switches}\n\n")
    def configure(self, remap = False):
        prompts = []
        hostname_prompt = self.get_hostname_prompt()
        prompts.append(hostname_prompt + "\n")
        vlan_interface_prompts = self.get_vlan_interface_prompts()
        for prompt in vlan_interface_prompts:
            prompts.append(prompt)
        prompts.append("\n")
        ip_route_prompt = self.get_ip_route_prompts()
        prompts.append(ip_route_prompt)
        prompts.append("\n")
        self.configure_new(remap)
        stack_groups = self.trace_stack()
        for i in stack_groups:
            for group in i:
                for prompt in group.configure():
                    prompts.append(prompt)
        prompts.append("vsf split-detect mgm\n\n")
        prompts.append("write memory\n\n")
        new_config_file.writelines(prompts)

    def remap(self, new_order: tuple):
        c = 1
        temp_switch_list = []
        for i in new_order:
            switch = self.switch_list[i - 1].remap(c)
            temp_switch_list.append(switch)
            c += 1
        self.switch_list = temp_switch_list
        self.num_48_port_switches = len(self.switch_list)
        self.configure(True)

    def get_hostname_prompt(self):
        return f"hostname {self.hostname}\n"
    def get_vlan_interface_prompts(self):
        return [
            f"interface vlan 1\n",
            f"ip address {self.ip_address}/16\n",
            "exit\n"
        ]
    def get_ip_route_prompts(self):
        octets = []
        octet = ""
        for i in self.ip_address:
            if len(octets) == 2:
                break
            if i != ".":
                octet += i
            else:
                octets.append(octet)
                octet = ""
        return f"ip route 0.0.0.0/0 {octets[0]}.{octets[1]}.0.1\n"
    
    def trace_stack(self):
        vlan_access_ports = []
        vlan_access_list = []
        description_ports = []
        description_list = []
        all_ports = [Port_Group(None, None)]
        for switch in self.switch_list:
            for port in switch.get_port_list():
                all_ports[0].add_port(port)
                vlan = port.get_vlan_access()
                description = port.get_description()
                if vlan is not None:
                    if vlan in vlan_access_list:
                        index = vlan_access_list.index(vlan)
                        vlan_access_ports[index].add_port(port)
                    else:
                        vlan_access_list.append(vlan)
                        group = Port_Group(vlan, None)
                        group.add_port(port)
                        vlan_access_ports.append(group)
                if description is not None:
                    if description in description_list:
                        index = description_list.index(description)
                        description_ports[index].add_port(port)
                    else:
                        description_list.append(description)
                        group = Port_Group(None, description)
                        group.add_port(port)
                        description_ports.append(group)
        return (all_ports, vlan_access_ports, description_ports)

    def configure_new(self, remap = False):
        old_config_end_port = self.switch_list[-1].get_port_list()[-1]
        switch_number, port_number = old_config_end_port.get_coordinates()
        delta = self.num_48_port_switches - switch_number
        if delta < 0 and not remap:
            raise Exception("Switch Loss Detected")
        elif delta > 0:
            print("*Excess Switches Detected*")
            input(f"*Recommended Number of 48 Port Switches: {self.num_48_port_switches - delta}*")

        if port_number != 48:
            for i in range(port_number + 1, 49):
                location = f"{switch_number}/1/{i}"
                port = Port(location, None, None)
                self.switch_list[-1].add_port(port)
        for i in range(switch_number + 1, self.num_48_port_switches + 1):
            self.switch_list.append(Switch(i))
            for k in range(1, 49):
                location = f"{i}/1/{k}"
                port = Port(location, None, None)
                self.switch_list[-1].add_port(port)
        if self.has_24_port_switch:
            self.switch_list.append(Switch(self.num_48_port_switches + 1))
            for i in range(1, 25):
                location = f"{self.num_48_port_switches + 1}/1/{i}"
                port = Port(location, None, None)
                self.switch_list[-1].add_port(port)

class Config_Tracer:
    def __init__(self, old_config_file, new_config_file):
        self.old_config = old_config_file.readlines()
        self.new_config_file = new_config_file
    def trace(self, remap = False):
        ports = Port_Group(None, None)
        current_switch = 1
        switch_list = [Switch(1)]
        vlan_access_table = []
        vlan_access_ports = []
        description_table = []
        description_ports = []
        hostname = None
        ip_address = None
        location = None
        vlan_access = None
        description = None
        for line in self.old_config:
            if "sysname" in line:
                hostname = line[9:-1]
                hostname = hostname.replace(" ", "_").replace("_", "-")
                if hostname[-3] == "-":
                    hostname = hostname[0:-2] + f"0{hostname[-2:]}"
            elif "ip address" in line:
                ip_address = line[12:line.index("255") - 1]
            elif "interface GigabitEthernet" in line:
                location = line[25:-1].replace("/0/","/1/")
            elif "access vlan" in line and location is not None:
                vlan_access = line[18:-1]
            elif "description" in line and location is not None:
                description = line[13:-1]
            elif "#" in line and location is not None:
                port = Port(location, vlan_access, description)
                if port.coordinates[0] == current_switch:
                    switch_list[current_switch - 1].add_port(port)
                else:
                    current_switch += 1
                    switch = Switch(current_switch)
                    switch.add_port(port)
                    switch_list.append(switch)

                if vlan_access in vlan_access_table and vlan_access is not None:
                    index = vlan_access_table.index(vlan_access)
                    vlan_access_ports[index].add_port(port)
                elif vlan_access is not None:
                    vlan_access_table.append(vlan_access)
                    vlan_access_ports.append(Port_Group(vlan_access, None))
                    vlan_access_ports[-1].add_port(port)
                
                if description is not None:
                    invalid = "ap" in description.lower() or "ruckus" in description.lower()
                    if description in description_table and not invalid:
                        index = description_table.index(description)
                        description_ports[index].add_port(port)
                    elif not invalid:
                        description_table.append(description)
                        description_ports.append(Port_Group(None, description))
                        description_ports[-1].add_port(port)
                location = None
                vlan_access = None
                description = None
        prompts = []
        groups = vlan_access_ports + description_ports
        stack = Stack(hostname, ip_address, switch_list, groups, remap)
        stack.configure()
        return stack


prompt = ""
while prompt != "q":
    prompt = input(":")
    old_config_file = open("Old_Config.txt", "r")
    new_config_file = open("New_Config.txt", "w")
    if "configure" in prompt:
        new_config_file = open("New_Config.txt", "w")
        config_tracer = Config_Tracer(old_config_file, new_config_file)
        config_tracer.trace()
        print("*New Configuration Generated Successfully*")
    elif "remap" in prompt:
        config_tracer = Config_Tracer(old_config_file, new_config_file)
        stack = config_tracer.trace(True)
        new_config_file = open("New_Config.txt", "w")
        remap = input("Enter Remapped Order: ")
        remap_list = []
        for i in remap.strip():
            if i != ",":
                remap_list.append(int(i))
        stack.remap(remap_list)
    old_config_file.close()
    new_config_file.close()

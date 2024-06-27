#Add consolidation for description and vlan access


#Declares File Variables
old_config_file = open("OldConfig.txt", "r")
old_config_txt = old_config_file.readlines()

new_config_file = open("NewConfig.txt", "w")

class Port:
    def __init__(self, location: str, vlan_access: str = None, vlan_description: str = None):
        self.location = location
        self.vlan_description = vlan_description
        self.vlan_access = vlan_access
        if self.vlan_description is not None:
            temp = self.vlan_description.lower()
            if "ruckus" in temp or "ap" in temp:
                self.vlan_description = None
        self.simple_location = self.simplify_location()
    def simplify_location(self):
        blade_number = int(self.location[0:self.location.index("/1/")])
        port_number = int(self.location[self.location.index("/1/") + 3:])
        return [blade_number, port_number]

class Port_Group:
    def __init__(self, vlan_access: str = None, vlan_description: str = None):
        self.port_list = []
        self.vlan_access = vlan_access
        self.vlan_description = vlan_description
    def add_port(self, port: Port):
        self.port_list.append(port)
    def get_key(self):
        if self.vlan_access is None:
            return self.vlan_description
        return self.vlan_access

def configure_stack():
    stack = get_stack()
    configure_vanilla(stack)
    configure_access(stack)
    configure_description(stack)
    new_config_file.write("write mem")

def configure_vanilla(stack: Port_Group):
    interface_prompt = get_interface(stack)
    vanilla_commands = get_vanilla_commands()
    new_config_file.write(interface_prompt)
    new_config_file.writelines(vanilla_commands)
    return stack

def configure_vlan(vlan: str, vlan_description: str):
    new_config_file.write(f"vlan {vlan}\n")
    new_config_file.write(f"description{vlan_description}\n")
    new_config_file.write("exit\n\n")

def configure_vlan_interface(ip_address: str):
    octets = []
    octet = ""
    for i in ip_address:
        if i == " ":
            continue
        elif i != ".":
            octet += i
        else:
            octets.append(octet)
            octet = ""
    new_config_file.write(f"ip address {ip_address}/16 ")
    new_config_file.write(f"{octets[0]}.{octets[1]}.0.1\n\n")

def configure_link_aggregation(label: str, description: str):
    prompt = f"interface lag {label}\n"
    prompt += f"description {description}\n"
    commands = [
        "no shutdown\n",
        "no routing\n",
        "vlan trunk native 1\n",
        "vlan trunk allow 1,40,56,70,72,100,200,240,250\n",
        "dhcpv4-snooping trust\n",
        "lacp mode active\n"
    ]
    for command in commands:
        prompt += command
    new_config_file.write(f"{prompt}\n")

def get_vanilla_commands() -> list:
    return [
        "no shutdown\n",
        "no routing\n",
        "vlan trunk native 1\n",
        "vlan trunk allow 1,40,100,200,240\n\n"
    ]

def get_stack() -> Port_Group:
    stack = Port_Group()
    switch_count = int(input("Number of 48 Port Switches: "))
    has_24_port = input("Stack has 24 Port Switch? (y/n): ") == "y"
    has_link_aggregation = input("Stack Has Link Aggregation? (y/n): ") == "y"
    if has_link_aggregation:
        label = input("Link Aggregation Label: ")
        description = input("Link Aggregation Description: ")
        configure_link_aggregation(label, description)
    
    port = None
    location = None
    description = None
    access_vlan = None
    vlan = None
    vlan_description = None
    for line in old_config_txt:
        # if "ip address" in line:
        #     ip_address = line[12:line.index("255") - 1]
        #     configure_vlan_interface(ip_address)

        if "vlan" in line:
            if line.index("vlan") == 0:
                vlan = line[5:line.index("\n")]
        elif "description" in line:
            if line.index("description") == 1 and vlan is not None:
                vlan_description = line[12:line.index("\n")]
                configure_vlan(vlan, vlan_description)
        else:
            vlan = None
            vlan_description = None
        
        if "interface GigabitEthernet" in line:
            location = line[25:line.index("\n")].replace("/0/","/1/")
        elif "access vlan" in line and location is not None:
            access_vlan = line[18:line.index("\n")]
        elif "description" in line and location is not None:
            description = line[13:line.index("\n")]
        elif "#" in line and location is not None:
            port = Port(location, access_vlan, description)
            if port.simple_location[1] <= 48:
                stack.add_port(port)
            port = None
            location = None
            description = None
            access_vlan = None

    old_switch_count = stack.port_list[-1].simple_location[0]
    delta = switch_count - old_switch_count
    if delta > 0:
        for i in range(1,delta + 1):
            switch_number = old_switch_count + i
            for i in range(1,49):
                location = f"{switch_number}/1/{i}"
                port = Port(location)
                stack.add_port(port)
    if has_24_port:
        for i in range(1,25):
            switch_number = switch_count + 1
            location = f"{switch_number}/1/{i}"
            port = Port(location)
            stack.add_port(port)
    return stack

def get_grouped_port_table(sort_by: str, stack: Port_Group):
    key_table = []
    port_group_table = []
    sorting_key = None
    vlan_access = None
    vlan_description = None

    for port in stack.port_list:
        if sort_by == "vlan":
            sorting_key = port.vlan_access
            vlan_access = sorting_key
        elif sort_by == "description":
            sorting_key = port.vlan_description
            vlan_description = sorting_key

        if sorting_key is None:
            continue
        elif sorting_key not in key_table:
            group = Port_Group(vlan_access, vlan_description)
            group.add_port(port)
            port_group_table.append(group)
            key_table.append(sorting_key)
        else:
            for group in port_group_table:
                if group.get_key() == sorting_key:
                    group.add_port(port)
    return port_group_table

def get_vlan_access_prompt(group):
    vlan_access = group.vlan_access
    return f"vlan access {vlan_access}\n\n"

def configure_access(stack: Port_Group):
    port_group_table = get_grouped_port_table("vlan", stack)
    for group in port_group_table:
        interface_prompt = get_interface(group)
        vlan_access_prompt = get_vlan_access_prompt(group)
        # description_prompt = get_default_description_prompt(group.vlan_access)
        new_config_file.write(interface_prompt)
        new_config_file.write(vlan_access_prompt)
        # new_config_file.write(description_prompt)

def get_description_prompt(group: Port_Group):
    vlan_description = group.vlan_description
    return f"description {vlan_description}\n\n"

def configure_description(stack: Port_Group):
    port_group_table = get_grouped_port_table("description", stack)
    for group in port_group_table:
        interface_prompt = get_interface(group)
        descritpion_prompt = get_description_prompt(group)
        new_config_file.write(interface_prompt)
        new_config_file.write(descritpion_prompt)
        
def get_interface_range(port_range: list):
    blade = port_range[0].simple_location[0]
    start_port = port_range[0].simple_location[1]
    end_port = port_range[-1].simple_location[1]
    if len(port_range) < 3:
        prompt = ""
        for port in port_range:
            prompt += f"{port.location},"
        prompt = prompt[0:-1]
        return prompt
    return f"{blade}/1/{start_port}-{blade}/1/{end_port}"

def get_interface(group: Port_Group):
    interface_prompt = "interface "
    port_list = group.port_list
    length = len(port_list)
    last_port = port_list[0]
    range = [last_port]

    i = 0
    for port in port_list:
        if i == 0:
            i += 1
            continue
        
        switch_number, port_number = port.simple_location
        last_switch_number, last_port_number = last_port.simple_location

        if switch_number == last_switch_number and port_number - 1 == last_port_number:
            range.append(port)
        else:
            interface_prompt += f"{get_interface_range(range)},"
            range = [port]
        last_port = port
    interface_prompt += get_interface_range(range)
    interface_prompt += "\n"    
    return interface_prompt

        



configure_stack()


        



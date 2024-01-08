"""Utility functions."""


import os
import re           # For doing regex
import time
import socket       # For network connections
import hashlib      # For hashing mac addresses
import platform     # For getting the operating system name
import subprocess   # For executing a shell command



def valid_ip(ip):
    valid = False
    try:
        if ip.count('.') == 3 and \
            all(0 <= int(num) < 256 for num in ip.rstrip().split('.')) and \
            len(ip) < 16 and \
            all(num.isdigit() for num in ip.rstrip().split('.')):
            valid = True
    except Exception as ex:
        #print("error in valid_ip: " + str(ex))
        pass
    return valid


def extract_mac(line):
    #p = re.compile(r'(?:[0-9a-fA-F]:?){12}')
    p = re.compile(r'((([a-zA-z0-9]{2}[-:]){5}([a-zA-z0-9]{2}))|(([a-zA-z0-9]{2}:){5}([a-zA-z0-9]{2})))')
    # from https://stackoverflow.com/questions/4260467/what-is-a-regular-expression-for-a-mac-address
    return re.findall(p, line)[0][0]

def valid_mac(mac):
    return mac.count(':') == 5 and \
        all(0 <= int(num, 16) < 256 for num in mac.rstrip().split(':')) and \
        not all(int(num, 16) == 255 for num in mac.rstrip().split(':'))

def mac_to_id(mac):
    #hash_string = str(hash(mac))
    #if hash_string[:1] == '-':
    #    hash_string = hash_string[1:]
    #return hash_string
    
    hash_object = hashlib.md5(mac.encode())
    hash_string = hash_object.hexdigest()
    hash_string = hash_string[:12]
    #print("hashed mac: " + str(hash_string))
    
    return 'presence-{}'.format(hash_string)



def clamp(n, minn, maxn):
    return max(min(maxn, n), minn)


def get_own_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '192.168.1.1'
    finally:
        s.close()
    return IP









# I couldn't get the import to work, so I just copied some of the code here:
# It was made by Victor Oliveira (victor.oliveira@gmx.com)


OUI_FILE = 'oui.txt'
SEPARATORS = ('-', ':')
BUFFER_SIZE = 1024 * 8

__location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))

def get_vendor(mac, oui_file=OUI_FILE):
    
    
    # TODO: this could be replaced with a shell call:
    # #!/bin/bash
    # OUI=$(ip addr list|grep -w 'link'|awk '{print $2}'|grep -P '^(?!00:00:00)'| grep -P '^(?!fe80)' | tr -d ':' | head -c 6)
    #curl -sS "http://standards-oui.ieee.org/oui.txt" | grep -i "$OUI" | cut -d')' -f2 | tr -d '\t'
    
    mac_clean = mac
    for separator in SEPARATORS:
        mac_clean = ''.join(mac_clean.split(separator))

    try:
        int(mac_clean, 16)
    except ValueError:
        raise ValueError('Invalid MAC address.')

    mac_size = len(mac_clean)
    if mac_size > 12 or mac_size < 6:
        raise ValueError('Invalid MAC address.')

    mac_half = mac_clean[0:6]
    mac_half_upper = mac_half.upper()

    
    vendor_command = "grep -i " + str(mac_half_upper) + " " + str(os.path.join(__location__, oui_file)) + " | cut -d')' -f2 | tr -d '\t'"
    result = subprocess.run(vendor_command, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) #.decode())
    vendor_alt = result.stdout.split('\n')[0]
    print("VENDOR_ALT FROM GREP: " + str(vendor_alt))

    with open(os.path.join(__location__, oui_file)) as file:
        #mac_half = mac_clean[0:6]
        #mac_half_upper = mac_half.upper()
        while True:
            line = file.readline()
            if line:
                if line.startswith(mac_half_upper):
                    vendor = line.strip().split('\t')[-1]
                    return vendor
            else:
                break



def nmblookup(ip_address):
    # This can sometimes find the hostname.
    #print("in NMB lookup helper function")
    if valid_ip(ip_address):
        command = "nmblookup -A " + str(ip_address)
        #print("NMB command = " + str(command))
        try:
            result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) #.decode())
            name = ""
            for line in result.stdout.split('\n'):
                
                #print("NMB LINE = " + str(line))
                if line.endswith(ip_address) or line.endswith('not found'): # Skip the first line, or if nmblookup is not installed.
                    continue
                name = str(line.split('<')[0])
                name = name.strip()
                #print("lookup name = " + str(name))
                
                return name
                
            #return str(result.stdout)

        except Exception as ex:
            pass
            #print("Nmblookup error: " + str(ex))
        return ""
        #return str(subprocess.check_output(command, shell=True).decode())
    
    
#def hostname_lookup(addr):
#     try:
#         return socket.gethostbyaddr(addr)
#     except socket.herror:
#         return None, None, None    
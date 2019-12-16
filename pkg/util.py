"""Utility functions."""

import socket       # For network connections
import platform     # For getting the operating system name
import subprocess   # For executing a shell command
import re           # For doing regex
import time
import os


def valid_ip(ip):
    return ip.count('.') == 3 and \
        all(0 <= int(num) < 256 for num in ip.rstrip().split('.')) and \
        len(ip) < 16 and \
        all(num.isdigit() for num in ip.rstrip().split('.'))


def valid_mac(mac):
    return mac.count(':') == 5 and \
        all(0 <= int(num, 16) < 256 for num in mac.rstrip().split(':')) and \
        not all(int(num, 16) == 255 for num in mac.rstrip().split(':'))


def clamp(n, minn, maxn):
    return max(min(maxn, n), minn)


def get_ip():
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


def ping(ip_address, count):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    #command = ["ping", param, count, "-i", 1, str(ip_address)]
    command = "ping " + str(param) + " " + str(count) + " -i 0.5 " + str(ip_address)
    #print("command: " + str(command))
    #return str(subprocess.check_output(command, shell=True).decode())
    try:
        result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.DEVNULL) #.decode())
        #print("ping done")
        return result.returncode
    except Exception as ex:
        print("error pinging! Error: " + str(ex))
        return 1


def arping(ip_address, count):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = "sudo arping " + str(param) + " " + str(count) + " " + str(ip_address)
    #print("command: " + str(command))
    try:
        result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.DEVNULL) #.decode())
        return result.returncode
    except Exception as ex:
        print("error arpinging! Error: " + str(ex))
        return 1


def arp(ip_address):
    if valid_ip(ip_address):
        command = "arp " + str(ip_address)
        try:
            result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
            for line in result.stdout.split('\n'):
                mac_addresses = re.findall(r'(([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})', str(line))
                if len(mac_addresses):
                    #print("util: arp: mac in line: " + line)
                    return str(line)
                
            return str(result.stdout)

        except Exception as ex:
            print("Arp error: " + str(ex))
            result = 'error'
        return result
        #return str(subprocess.check_output(command, shell=True).decode())
        
        



# I couldn't get the import to work, so I just copied some of the code here:
# It was made by Victor Oliveira (victor.oliveira@gmx.com)


OUI_FILE = 'oui.txt'
SEPARATORS = ('-', ':')
BUFFER_SIZE = 1024 * 8

__location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))

def get_vendor(mac, oui_file=OUI_FILE):
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

    with open(os.path.join(__location__, oui_file)) as file:
        mac_half = mac_clean[0:6]
        mac_half_upper = mac_half.upper()
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
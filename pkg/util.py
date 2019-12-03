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
        
def arpa():
        command = "arp -a"
        device_list = {}
        try:
            result = subprocess.run(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) #.decode())
            for line in result.stdout.split('\n'):
                if not "<incomplete>" in line and len(line) > 10:
                    
                    mac_short = ""
                    try:
                        mac_address_list = re.findall(r'(([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})', str(line))[0]
                        #print(str(mac_address_list))
                        mac_address = str(mac_address_list[0])
                        #print(str(mac_address))
                        mac_short = str(mac_address.replace(":", ""))
                        _id = 'presence-{}'.format(mac_short)
                    except Exception as ex:
                        print("getting mac from arp -a line failed: " + str(ex))
                    
                    try:
                        ip_address_list = re.findall(r'(?:\d{1,3}\.)+(?:\d{1,3})', str(line))
                        #print("ip_address_list = " + str(ip_address_list))
                        ip_address = str(ip_address_list[0])
                        if not valid_ip(ip_address):
                            continue
                    except Exception as ex:
                        print("no IP address in line: " + str(ex))
                        
                    try:
                        name = str(line.split(' (')[0])
                        
                        if name == '?' or valid_ip(name):
                            vendor = 'unnamed'
                            try:
                                # Get the vendor name, and shorten it. It removes
                                # everything after the comma. Thus "Apple, inc"
                                # becomes "Apple"
                                vendor = get_vendor(mac_address)
                                if vendor is not None:
                                    vendor = vendor.split(' ', 1)[0]
                                    vendor = vendor.split(',', 1)[0]
                                else:
                                    vendor = 'unnamed'
                            except ValueError:
                                pass

                            name = "Presence - " + vendor
                        else:
                            name = "Presence - " + name
                        
                        
                    except Exception as ex:
                        print("Error: could not get name from arp -a line: " + str(ex))
                        
                    if mac_short != "":
                        #print("util: arp: mac in line: " + line)
                        #item = {'ip':ip_address,'mac':mac_address,'name':name, 'mac_short':mac_address.replace(":", "")}
                        #return str(line)
                        
                        device_list[_id] = {'ip':ip_address,'mac_address':mac_address,'name':name,'arpa_time':int(time.time()),'lastseen':0}
                        #print("device_list = " + str(device_list))
            #return str(result.stdout)

        except Exception as ex:
            print("Arp -a error: " + str(ex))
            #result = 'error'
        return device_list
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


"""Utility functions."""

import socket       # For network connections
import platform     # For getting the operating system name
import subprocess   # For executing a shell command
import re           # For doing regex

def valid_ip(ip):
    return ip.count('.') == 3 and \
        all(0 <= int(num) < 256 for num in ip.rstrip().split('.'))


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

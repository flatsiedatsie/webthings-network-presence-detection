"""Utility functions."""

def validip(ip):
    return ip.count('.') == 3 and  all(0<=int(num)<256 for num in ip.rstrip().split('.'))

def clamp(n, minn, maxn):
    return max(min(maxn, n), minn)

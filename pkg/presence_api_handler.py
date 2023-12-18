"""Network Presence Detection API handler."""

import os
import re
import json
#import time
#from time import sleep
#import socket
import requests
import subprocess
#from .util import *

#from .util import valid_ip, arpa_detect_gateways

#from datetime import datetime,timedelta


try:
    from gateway_addon import APIHandler, APIResponse
    #print("succesfully loaded APIHandler and APIResponse from gateway_addon")
except:
    print("ERROR,Import APIHandler and APIResponse from gateway_addon failed.")
    #sys.exit(1)


#from pyradios import RadioBrowser


class NetworkPresenceAPIHandler(APIHandler):
    """Network Presence Detection API handler."""

    def __init__(self, adapter, verbose=False):
        """Initialize the object."""
        #print("INSIDE API HANDLER INIT")
        
        self.adapter = adapter
        self.DEBUG = self.adapter.DEBUG

        if self.DEBUG:
            print("init of network presence api handler")
        
        # Intiate extension addon API handler
        try:
            manifest_fname = os.path.join(
                os.path.dirname(__file__),
                '..',
                'manifest.json'
            )

            with open(manifest_fname, 'rt') as f:
                manifest = json.load(f)

            APIHandler.__init__(self, manifest['id'])
            self.manager_proxy.add_api_handler(self)
            

            if self.DEBUG:
                print("self.manager_proxy = " + str(self.manager_proxy))
                print("Created new API HANDLER: " + str(manifest['id']))
        
        except Exception as e:
            print("Error: failed to init API handler: " + str(e))
        
        #self.rb = RadioBrowser()
                        

#
#  HANDLE REQUEST
#

    def handle_request(self, request):
        """
        Handle a new API request for this handler.

        request -- APIRequest object
        """
        #print("in handle_request")
        try:
        
            if request.method != 'POST':
                return APIResponse(status=404)
            
            if request.path == '/ajax':
                
                try:
                    #if self.DEBUG:
                    #    print("API handler is being called")
                    #    print("request.body: " + str(request.body))
                    
                    action = str(request.body['action']) 
                    
                    if self.DEBUG:
                        print("got api request. action: " + str(action))
                    
                    if action == 'init':
                        if self.DEBUG:
                            print("in init")
                        
                        return APIResponse(
                          status=200,
                          content_type='application/json',
                          content=json.dumps({'state':'ok',
                                              'debug':self.adapter.DEBUG,
                                              'ignore_candle_controllers':self.adapter.ignore_candle_controllers
                                          }),
                        )
                        
                    elif action == 'scan':
                        state = 'error'
                        
                        try:
                            avahi_lines = self.adapter.get_avahi_lines()
                            #avahi_scan_result = subprocess.run(avahi_browse_command, universal_newlines=True, stdout=subprocess.PIPE).decode('latin-1')
                            
                            
                            
                            #for line in avahi_scan_result.stdout.split('\n'):
                                
                            state = 'ok'
                        except Exception as ex:
                             if self.DEBUG:
                                 print("scan: error: " + str(ex))
                        
                        
                        return APIResponse(
                          status=200,
                          content_type='application/json',
                          content=json.dumps({'state':state, 
                                              'avahi_lines':avahi_lines,
                                              'debug':self.adapter.DEBUG
                                          }),
                        )
                    
                    
                    else:
                        return APIResponse(
                            status=404,
                            content_type='application/json',
                            content=json.dumps("API error, invalid action"),
                        )
                        
                except Exception as ex:
                    if self.DEBUG:
                        print("Ajax issue: " + str(ex))
                    return APIResponse(
                        status=500,
                        content_type='application/json',
                        content=json.dumps("Error in API handler"),
                    )
                    
            else:
                if self.DEBUG:
                    print("invalid path: " + str(request.path))
                return APIResponse(status=404)
                
        except Exception as e:
            if self.DEBUG:
                print("Failed to handle UX extension API request: " + str(e))
            return APIResponse(
                status=500,
                content_type='application/json',
                content=json.dumps("General API Error"),
            )
        


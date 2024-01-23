(function() {
	class NetworkPresence extends window.Extension {
	    constructor() {
	      	super('network-presence-detection-adapter');
			//console.log("Adding network-presence addon to menu");
      		
			this.addMenuEntry('Network Presence');
            
            //var getCountryNames = new Intl.DisplayNames(['en'], {type: 'region'});
            //console.log(getCountryNames);
            //console.log(getCountryNames.of('AL'));  // "Albania"
			
            this.debug = false;
            this.interval = null;
			this.avahi_lines = [];
            this.content = '';
			
			fetch(`/extensions/${this.id}/views/content.html`)
	        .then((res) => res.text())
	        .then((text) => {
	         	this.content = text;
	  		 	if( document.location.href.endsWith("extensions/network-presence-detection-adapter") ){
	  		  		this.show();
	  		  	}
	        })
	        .catch((e) => console.error('Failed to fetch content:', e));
            
            this.get_init_data();
            
			
			
	    }



		
		hide() {
			//console.log("network-presence hide called");
			try{
                clearInterval(this.interval);
                this.interval = null;
			}
			catch(e){
				//console.log("internet radio: no interval to clear? " + e);
			}    
		}
        
        
        

	    show() {
			//console.log("network-presence show called");
			//console.log("this.content:");
			//console.log(this.content);
			try{
				clearInterval(this.interval);
				this.interval = null;
			}
			catch(e){
				//console.log("no interval to clear?: " + e);
			}
            
            
			const main_view = document.getElementById('extension-network-presence-detection-adapter-view');
			
			if(this.content == ''){
				//console.error("network presence: error, content was empty");
				return;
			}
			else if(main_view){
				main_view.innerHTML = this.content;
			}
			else{
				console.error("network presence: error, view element not found");
				return
			}
			
			
		
            
		
            
            
            
            // Easter egg: add custom station
            
			document.getElementById('extension-network-presence-title').addEventListener('click', (event) => {
                this.scan();
				const music = new Audio('/extensions/network-presence-detection-adapter/audio/ping.mp3');
				music.loop = false;
				music.play();
			});
            
            
			const rescan_button_el = document.getElementById('extension-network-presence-rescan-button');
			
			if(rescan_button_el){
				/*
	            setTimeout(() => {
	            	rescan_button_el.style.display = 'block';
	            },10000)
				*/
			
				rescan_button_el.addEventListener('click', (event) => {
	                rescan_button_el.style.display = 'none';
					this.scan();
				
				});
			}
			
            this.scan();
		}
		
	
		scan(){
			if(this.debug){
				console.log("network presence: starting scan");
			}
			document.getElementById('extension-network-presence-busy-scanning').style.display = 'block';
			document.getElementById('extension-network-presence-rescan-button').style.display = 'none';


            setTimeout(() => {
            	document.getElementById('extension-network-presence-rescan-button').style.display = 'block';
            },10000);
			
			
	        window.API.postJson(
	          `/extensions/${this.id}/api/ajax`,
                {'action':'scan'}

	        ).then((body) => {
                
                if(typeof body.debug != 'undefined'){
                    this.debug = body.debug;
                    if(this.debug){
                        console.log("Network presence scan API result: ", body);
                        if(document.getElementById('extension-network-presence-debug-warning') != null){
                            document.getElementById('extension-network-presence-debug-warning').style.display = 'block';
                        }
                    }
                }
                
				if(typeof body.avahi_lines != 'undefined'){
					this.avahi_lines = body.avahi_lines;
					this.regenerate_items();
				}
				
                document.getElementById('extension-network-presence-busy-scanning').style.display = 'none';
				document.getElementById('extension-network-presence-rescan-button').style.display = 'block';
			
	        }).catch((e) => {
	  			console.log("Error getting NetworkPresence scan data: ", e);
				document.getElementById('extension-network-presence-busy-scanning').style.display = 'none';
				document.getElementById('extension-network-presence-overview-list').innerHTML = '<h2>Oops</h2><p>A (connection) error occured</p>';
	        });	
			
		}
	
    	
        get_init_data(){
            
			try{
				//pre.innerText = "";
				
		  		// Init
		        window.API.postJson(
		          `/extensions/${this.id}/api/ajax`,
                    {'action':'init'}

		        ).then((body) => {
                    
                    if(typeof body.debug != 'undefined'){
                        this.debug = body.debug;
                        if(this.debug){
                            console.log("Network presence: debug: init API result: ", body);
                            if(document.getElementById('extension-network-presence-debug-warning') != null){
                                document.getElementById('extension-network-presence-debug-warning').style.display = 'block';
                            }
                        }
                    }
                    
				
		        }).catch((e) => {
		  			console.log("Error getting NetworkPresence init data: ", e);
		        });	

				
			}
			catch(e){
				console.log("Error in NetworkPresence API call to init: ", e);
			}
        }
    	
    
        
    
    
	
		//
		//  REGENERATE ITEMS
		//
	
		regenerate_items(items=null, page="overview"){
			try {
				if(this.debug){
					console.log("network presence: regenerating list. this.avahi_lines: ", this.avahi_lines);
				}
		        const overview_list = document.getElementById('extension-network-presence-overview-list');
                if(overview_list == null){
                    return;
                }
                
				let avahi_parsed = {};
				let interfaces = {};
				
				
				const info_tags = ['Google','Apple','Amazon','Synology','AudioAccessory','Printer','BorderRouter','HomePod','Sensor','XServe','Server','Router','MacBook','Laptop','Samba','Time Machine','Homebridge','Candle','Privacy'];
				const protocol_tags = ['Airplay'];
				
				if(this.avahi_lines.length == 0){
					overview_list.innerHTML = '<p>Nothing found</p>';
				}
				else{
					
					
					// Extract useful information from Avahi data
                    for (var i = 0; i < this.avahi_lines.length; i++) {
						let line = this.avahi_lines[i];
						let item_html = '';
						if(line.startsWith('=')){
							if(this.debug){
								console.log("");
								console.log(line);
							}
							let line_parts = line.split(';');
							
							if(this.debug){
								for (var j = 0; j < line_parts.length; j++) {
									console.log(j, ": ", line_parts[j]);
								}
							}
							
							// Check if this device is already in the dictionary
							/*
							let device_id = null;
							if(line_parts[6].length){
								for (const [key, value] of Object.entries(avahi_parsed)) {
									if(value.name == line_parts[6]){
										
									}
								}
							}
							*/
							const device_id = line_parts[6];
							
								
							if(device_id){
								if( typeof interfaces[line_parts[1]] == 'undefined'){
									interfaces[line_parts[1]] = [];
								}
								
								if(interfaces[line_parts[1]].indexOf(line_parts[7]) == -1){
									interfaces[line_parts[1]].push(line_parts[7]);
								}
								
								
								if( typeof avahi_parsed[device_id] == 'undefined'){
									avahi_parsed[device_id] = {
										'network_interfaces':[],
										'ports':{},
										'ipv4':false,
										'ipv6':false,
										'tags':[],
										'urls':[],
										'vendor':null,
										'name':'Unknown',
										'ip4':null,
										'ip6':null,
										'local_url':line_parts[6],
										'secure_admin_url':null,
										'admin_url':null,
										'admin_port':null,
										'secure_admin_port':null,
										'info':{}
									}
								}
								
								// Name
								if(line_parts[3].indexOf('Candle Homebridge') == -1 && line_parts[3].indexOf('CandleMQTT-') == -1){
									avahi_parsed[device_id]['name'] = line_parts[3];
								}
								
								
								
								// IP's
								if(this.validate_ip(line_parts[7])){
									avahi_parsed[device_id]['ip4'] = line_parts[7];
								}
								else{
									avahi_parsed[device_id]['ip6'] = line_parts[7];
								}
								
								// Network interfaces
								if(avahi_parsed[device_id].network_interfaces.indexOf(line_parts[1]) == -1){
									avahi_parsed[device_id].network_interfaces.push(line_parts[1]);
								}
								
								// IPv4 and IPv6
								if(line_parts[2] == 'IPv4'){
									avahi_parsed[device_id].ipv4 = true;
								}
								else if(line_parts[2] == 'IPv6'){
									avahi_parsed[device_id].ipv6 = true;
								}
								
								// port and protocol
								avahi_parsed[device_id].ports[line_parts[8]] = {'port':line_parts[8],'protocol':line_parts[4]}
								
								// info parts
								if(line_parts[9].indexOf('=' != -1)){
									let info_parts = line_parts[9].split('" "');
									for (var k = 0; k < info_parts.length; k++) {
										if(info_parts[k].startsWith('"')){info_parts[k] = info_parts[k].substr(1)}
										if(info_parts[k].endsWith('"')){info_parts[k] = info_parts[k].substr(0,info_parts[k].length-1)}
										if(this.debug){
											console.log("--info_part: ", info_parts[k]);
										}
										let info_key_val = info_parts[k].split('=');
										if(info_key_val[1] && info_key_val[1].length){
											avahi_parsed[device_id]['info'][info_key_val[0]] = info_key_val[1];
											if(info_key_val[0] == 'admin_url'){
												avahi_parsed[device_id].admin_url = info_key_val[1];
											}
											if(info_key_val[0] == 'adminurl'){
												avahi_parsed[device_id].admin_url = info_key_val[1];
											}
											if(info_key_val[0] == 'secure_admin_url'){
												avahi_parsed[device_id].secure_admin_url = info_key_val[1];
											}
											if(info_key_val[0] == 'admin_port'){
												avahi_parsed[device_id].admin_port = info_key_val[1];
											}
											if(info_key_val[0] == 'secure_admin_port'){
												avahi_parsed[device_id].secure_admin_port = info_key_val[1];
											}
											if(info_key_val[0] == 'url'){
												if(avahi_parsed[device_id].urls.indexOf(info_key_val[1]) == -1){
													avahi_parsed[device_id].urls.push(info_key_val[1]);
												}
											}
											// tags extracted from info fields
											for (var l = 0; l < info_tags.length; l++) {
												if(info_key_val[1].toLowerCase().indexOf(info_tags[l].toLowerCase()) != -1){
													if(avahi_parsed[device_id]['tags'].indexOf(info_tags[l]) == -1){
														avahi_parsed[device_id]['tags'].push(info_tags[l]);
													}
												}
											}
										}
									}
								}
								
								// tags extracted from network protocol
								for (var m = 0; m < protocol_tags.length; m++) {
									if(line_parts[4].indexOf(protocol_tags[m]) != -1){
										if(avahi_parsed[device_id].tags.indexOf(protocol_tags[m]) == -1){
											avahi_parsed[device_id].tags.push(protocol_tags[m]);
										}
									}
								}
								
								// tags extracted from name
								for (var l = 0; l < info_tags.length; l++) {
									if(line_parts[3].toLowerCase().indexOf(info_tags[l].toLowerCase()) != -1){
										if(avahi_parsed[device_id]['tags'].indexOf(info_tags[l]) == -1){
											avahi_parsed[device_id]['tags'].push(info_tags[l]);
										}
									}
								}
								
								
								
							
								/*
								avahi_parsed[device_id]['name'] = 
								item_html += '<h3 class="extension-network-presence-item-name">' + line_parts[6] + '</h3>';
								item_html += '<span class="extension-network-presence-item-ip">' + line_parts[7] + '</span>';
							
							
							
								if(line.indexOf('HomePod') != -1){
									item_html += '<span class="extension-network-presence-item-icon extension-network-presence-item-icon-homepod"></span>';
								}
								else if(line.indexOf('AudioAccessory') != -1){
									item_html += '<span class="extension-network-presence-item-icon extension-network-presence-item-icon-audio"></span>';
								}
								else if(line.indexOf('printer"') != -1){
									item_html += '<span class="extension-network-presence-item-icon extension-network-presence-item-icon-printer"></span>';
								}
								else if(line.indexOf('BorderRouter') != -1){
									item_html += '<span class="extension-network-presence-item-icon extension-network-presence-item-icon-matter-border-router"></span>';
								}
								else if(line.indexOf('Apple Inc') != -1){
									item_html += '<span class="extension-network-presence-item-icon extension-network-presence-item-icon-apple"></span>';
								}
								else if(line.indexOf('Sensor') != -1 || line.indexOf('sensor"') != -1){
									item_html += '<span class="extension-network-presence-item-icon extension-network-presence-item-icon-sensor"></span>';
								}
								else if(line.indexOf('Server') != -1 || line.indexOf('XServe') != -1){
									item_html += '<span class="extension-network-presence-item-icon extension-network-presence-item-icon-serverr"></span>';
								}
							
								if(line.indexOf('adminurl=') != -1){
									let admin_url = line.substr( line.indexOf('"adminurl=') + 8 )
									admin_url = admin_url.substr(0, line.indexOf('"') );
									console.log("admin_url: ", admin_url);
									item_html += '<a href class="extension-network-presence-item-admin-url extension-network-presence-item-icon-homepod"></span>';
								}
								*/
							}
							else{
								if(this.debug){
									console.warn("no valid device ID: ", line_parts[7]);
								}
							}
							
						}
						
						
						
						//item_el.innerText = line;
						
						
    					
						/*
        					s.classList.add('extension-network-presence-tag');                
        					var t = document.createTextNode(tags_array[i]);
        					s.appendChild(t);
                            s.addEventListener('click', (event) => {
                                //console.log('clicked on tag: ', event.target.innerText);
                                this.send_search({'query_type':'bytagexact','tag':event.target.innerText})
                            });
						*/
                    }
					
					
					// Generate HTML for detected devices
					
					function create_item_link(url,title,css_class=""){
						return '<a href="' + url + '" class="extension-network-presence-list-item-link ' + css_class + '" rel="noreferer" target="_blank">' + title + '</a>';
					}
					
					overview_list.innerHTML = '';
					
					for (const [device_name, device] of Object.entries(avahi_parsed)) {
						let item_el = document.createElement("div");
						item_el.classList.add('extension-network-presence-list-item');
						
						// Name
						let name_el = document.createElement("h3");
						name_el.innerText = device.name;
						item_el.appendChild(name_el);
						
						// local url
						let local_url_el = document.createElement("a");
						local_url_el.classList.add('extension-network-presence-list-item-local-url');
						local_url_el.innerText = device.local_url;
						local_url_el.href = 'http://' + device.local_url;
						local_url_el.target='_blank';
						local_url_el.rel='norefferer';
						item_el.appendChild(local_url_el);
						
						// IP4 address
						let ip4_el = document.createElement("a");
						ip4_el.classList.add('extension-network-presence-list-item-ip4');
						ip4_el.innerText = device.ip4;
						ip4_el.href = 'http://' + device.ip4;
						ip4_el.target='_blank';
						ip4_el.rel='norefferer';
						item_el.appendChild(ip4_el);
						
						// IP6 address
						let ip6_el = document.createElement("a");
						ip6_el.classList.add('extension-network-presence-list-item-ip6');
						ip6_el.innerText = device.ip6;
						ip6_el.href = 'http://' + device.ip6;
						ip6_el.target='_blank';
						ip6_el.rel='norefferer';
						item_el.appendChild(ip6_el);
						
						
						
						
						// Add tags
						
						// first, improve the tags
						if(device.tags.indexOf('XServe') != -1){
							if(device.tags.indexOf('Server') == -1){
								device.tags.push('Server');
							}
							device.tags.splice(device.tags.indexOf('XServe'), 1);
						}
						if(device.tags.indexOf('Router') != -1 && device.tags.indexOf('BorderRouter') != -1){
							device.tags.splice(device.tags.indexOf('Router'), 1);
						}
						
						if(device.tags.indexOf('MacBook') != -1 && device.tags.indexOf('Apple') == -1){
							device.tags.push('Apple');
						}
						
						// icons background
						let icon_el = document.createElement("div");
						icon_el.classList.add('extension-network-presence-list-item-background-icon');
						if(device.tags.indexOf('Candle') != -1){
							icon_el.classList.add('extension-network-presence-list-item-background-icon-candle');
							item_el.appendChild(icon_el);
						}
						else if(device.tags.indexOf('Printer') != -1){
							icon_el.classList.add('extension-network-presence-list-item-background-icon-printer');
							item_el.appendChild(icon_el);
						}
						else if(device.tags.indexOf('MacBook') != -1 || device.tags.indexOf('Laptop') != -1){
							icon_el.classList.add('extension-network-presence-list-item-background-icon-laptop');
							item_el.appendChild(icon_el);
						}
						else if(device.tags.indexOf('Music') != -1 || device.tags.indexOf('AudioAccessory') != -1){
							icon_el.classList.add('extension-network-presence-list-item-background-icon-audio');
							item_el.appendChild(icon_el);
						}
						else if(device.tags.indexOf('Server') != -1 || device.tags.indexOf('Synology') != -1){
							icon_el.classList.add('extension-network-presence-list-item-background-icon-server');
							item_el.appendChild(icon_el);
						}
						
						
						// Tags
						let tags_container_el = document.createElement("div");
						tags_container_el.classList.add('extension-network-presence-list-item-tags');
						for (var k = 0; k < device.tags.length; k++) {
							let tag_el = document.createElement("span");
							tag_el.classList.add('extension-network-presence-list-item-tag');
							tag_el.classList.add('extension-network-presence-list-item-tag-' + device.tags[k].toLowerCase() );
							if(device.tags[k] == 'Google' || device.tags[k] == 'Amazon' || device.tags[k] == 'Facebook'){
								tag_el.classList.add('extension-network-presence-list-item-tag-danger');
							}
							tag_el.innerText = device.tags[k];
							tags_container_el.appendChild(tag_el);
						}
						item_el.appendChild(tags_container_el);
						
						
						// Admin URL
						let admin_url = null;
						if(device.secure_admin_url){
							admin_url = device.secure_admin_url;
							if(!admin_url.startsWith('http')){admin_url = 'https://' + admin_url}
						}
						else if(device.secure_admin_port){
							admin_url = device.local_url + ':' + device.secure_admin_port;
							if(!admin_url.startsWith('http')){admin_url = 'https://' + admin_url}
						}
						else if(device.admin_url){
							admin_url = device.admin_url;
							if(!admin_url.startsWith('http')){admin_url = 'http://' + admin_url}
						}
						else if(device.admin_port){
							admin_url = device.local_url + ':' + device.admin_port;
							if(!admin_url.startsWith('http')){admin_url = 'http://' + admin_url}
						}
						if(admin_url){
							let admin_el = document.createElement("div");
							admin_el.classList.add('extension-network-presence-list-item-admin-link');
							admin_el.innerHTML = create_item_link(admin_url,'Administration','text-button');
							item_el.appendChild(admin_el);
						}
						
						
						// More details button
						let expand_button_el = document.createElement("button");
						expand_button_el.classList.add('extension-network-presence-list-item-show-details-button');
						expand_button_el.classList.add('text-button');
						expand_button_el.innerText = 'More details';
						expand_button_el.onclick = function(){this.remove()}
						item_el.appendChild(expand_button_el);
						
						
						// Add info details
						let details_container_el = document.createElement("div");
						details_container_el.classList.add('extension-network-presence-list-item-details');
						
						
						// Add links
						let links_container_el = document.createElement("ul");
						links_container_el.classList.add('extension-network-presence-list-item-links');
						for (var p = 0; p < device.urls.length; p++) {
							let link_el = document.createElement("li");
							link_el.classList.add('extension-network-presence-list-item-link');
							link_el.innerHTML = create_item_link(device.urls[p],device.urls[p]);
							links_container_el.appendChild(link_el);
						}
						details_container_el.appendChild(links_container_el);
						
						// Add port details
						let ports_container_el = document.createElement("ul");
						ports_container_el.classList.add('extension-network-presence-list-item-ports');
						for (const [port, port_details] of Object.entries(device.ports)) {
							let port_el = document.createElement("li");
							
							let port_nr_el = document.createElement("a");
							port_nr_el.classList.add('extension-network-presence-list-item-port-nr');
							port_nr_el.innerText = port;
							port_nr_el.href = 'http://' + device.local_url + ':' + port;
							port_nr_el.target='_blank';
							port_nr_el.rel='norefferer';
							port_el.appendChild(port_nr_el);
							
							let protocol_el = document.createElement("span");
							protocol_el.classList.add('extension-network-presence-list-item-port-protocol');
							protocol_el.innerText = port_details.protocol;
							port_el.appendChild(protocol_el);
							
							ports_container_el.appendChild(port_el);
						}
						details_container_el.appendChild(ports_container_el);
						
						// Add info key-value pairs
						let info_container_el = document.createElement("ul");
						info_container_el.classList.add('extension-network-presence-list-item-info');
						for (const [info_key, info_value] of Object.entries(device.info)) {
							let info_el = document.createElement("li");
							
							let info_key_el = document.createElement("span");
							info_key_el.classList.add('extension-network-presence-list-item-info-key');
							info_key_el.innerText = info_key;
							info_el.appendChild(info_key_el);
							
							let info_value_el = document.createElement("span");
							info_value_el.classList.add('extension-network-presence-list-item-info-value');
							info_value_el.innerText = info_value;
							info_el.appendChild(info_value_el);
							
							info_container_el.appendChild(info_el);
						}
						details_container_el.appendChild(info_container_el);
						
						item_el.appendChild(details_container_el);
						
						
						overview_list.append(item_el);
					}
					
					
				}
				if(this.debug){
					console.warn("network presence: avahi_parsed: ", avahi_parsed);
				}
				
                /*
                if(items.length == 0){
                    list.innerHTML = "No results";
                }
                else{
                    list.innerHTML = "";
                }
                
				// Loop over all items
				for( var item in items ){
					
					var clone = original.cloneNode(true);
					clone.removeAttribute('id');
                    
                    var station_name = "Error";
                    var stream_url = "Error";
                    
                    if(page == 'search'){
                        station_name = items[item].name;
                        stream_url = items[item].url_resolved;
                        
                        // Add tags
                        if(typeof items[item].tags != "undefined"){
                            const tags_array = items[item].tags.split(",");
                            const tags_container = clone.getElementsByClassName("extension-network-presence-item-tags")[0]
                            for (var i = 0; i < tags_array.length; i++) {
            					if(tags_array[i].length > 2){
                                    var s = document.createElement("span");
                					s.classList.add('extension-network-presence-tag');                
                					var t = document.createTextNode(tags_array[i]);
                					s.appendChild(t);
                                    s.addEventListener('click', (event) => {
                                        //console.log('clicked on tag: ', event.target.innerText);
                                        this.send_search({'query_type':'bytagexact','tag':event.target.innerText})
                                    });
                                    tags_container.append(s);
                                }
                                
                            }
                            
                            //clone.getElementsByClassName("extension-network-presence-item-tags")[0].innerText = items[item].tags;
                        }
                        
                    }
                    else{
                        station_name = items[item].name;
                        stream_url = items[item].stream_url;
                    }
                    
                    // Remove potential tracking data from URL
                    if(stream_url.indexOf('?') !== -1){
                        //console.log("removing potential tracking string from: " + stream_url );
                        stream_url = stream_url.substring(0, stream_url.indexOf('?'));
                    }
                    
                    // Remove ; character that sometimes is present at the end of the URL
                    //if( stream_url.slice(-1) == ';'){
                    //    stream_url = stream_url.slice(0, stream_url.length - 1);
                    //}
                    
                    
                    
                    clone.getElementsByClassName("extension-network-presence-item-title")[0].innerText = station_name;
                    clone.getElementsByClassName("extension-network-presence-item-url")[0].innerText = stream_url;
                    
                    if(station_name == this.station && this.playing){
                        clone.classList.add('extension-network-presence-item-playing');   
                    }
                    
                    
                    //var title_element = clone.getElementsByClassName("extension-network-presence-item-title")[0];

                    if(page == 'search'){
                        
    					
                        // ADD station button
    					const add_button = clone.querySelectorAll('.extension-network-presence-item-action-button')[0];
                        //console.log("add button? ", add_button);
                        add_button.setAttribute('data-stream_url', stream_url);
    					add_button.addEventListener('click', (event) => {
                            //console.log("click event: ", event);
                            
                            document.getElementById('extension-network-presence-input-popup').classList.remove('extension-network-presence-hidden');
                            document.getElementById('extension-network-presence-station-name-save-button').setAttribute("data-stream_url", event.target.dataset.stream_url);
                            
                            //const new_name = prompt('Please give this station a name');
                            //const new_url = event.target.dataset.stream_url;
                            
    						var target = event.currentTarget;
    						var parent3 = target.parentElement.parentElement.parentElement;
    						parent3.classList.add("extension-network-presence-item-added"); // well... maybe
    				  	});
                        
                    }
                    else{
                        
    					// DELETE button
    					const delete_button = clone.querySelectorAll('.extension-network-presence-item-action-button')[0];
                        //console.log("delete button? ", delete_button);
                        delete_button.setAttribute('data-name', station_name);
                        
    					delete_button.addEventListener('click', (event) => {
                            //console.log("click event: ", event);
                            if(confirm("Are you sure you want to delete this station?")){
        						var target = event.currentTarget;
        						var parent3 = target.parentElement.parentElement.parentElement;
        						parent3.classList.add("extension-network-presence-item-delete");
        						var parent4 = parent3.parentElement;
    						
					
        						// Send new values to backend
        						window.API.postJson(
        							`/extensions/${this.id}/api/ajax`,
        							{'action':'delete','name': event.target.dataset.name}
        						).then((body) => { 
        							//console.log("delete item reaction: ", body);
                                    if(body.state == 'ok'){
                                        parent4.removeChild(parent3);
                                    }

        						}).catch((e) => {
        							console.log("network-presence: error in delete items handler: ", e);
        							//pre.innerText = "Could not delete that station"
                                    parent3.classList.remove("extension-network-presence-item-delete");
        						});
                            }
    				  	});
                    }

					
					
                    
                    // preview
					const preview_button = clone.querySelectorAll('.extension-network-presence-preview')[0];
                    //console.log("preview_button: ", preview_button);
                    preview_button.setAttribute('data-stream_url', stream_url);
                    preview_button.setAttribute('data-playing', false);
                    
					preview_button.addEventListener('click', (event) => {
                        const playing = event.target.dataset.playing;
                        //console.log("playing: ", playing);
                        if(playing == "true"){
                            //console.log("should stop audio");
                            this.stop_audio_in_browser();
                            //preview_button.setAttribute('data-playing', false);
                        }
                        else{
                            const preview_buttons = document.querySelectorAll('.extension-network-presence-preview');
                            //console.log("preview_buttons.length: " + preview_buttons.length);
                            for (var i = 0; i < preview_buttons.length; ++i) {
                                preview_buttons[i].dataset.playing = "false";
                            }
                            preview_button.setAttribute('data-playing', true);
                            const preview_url = event.target.dataset.stream_url;
                            this.play_audio_in_browser(preview_url);
                        }
                        
                        //document.getElementById('extension-network-presence-toggle-button').style.display = 'block';
					});
                    
                    
                    
                    // Big play buttons on items. They always turn on a stream.
					const play_button = clone.querySelectorAll('.extension-network-presence-play-icon')[0];
                    play_button.setAttribute('data-stream_url', stream_url);
					play_button.addEventListener('click', (event) => {
					    if(this.debug){
                            console.log("internet radio: play button event: ", event);
                        }
                        //console.log(event.path[2]);
                        
                        try{
                            const playing_items = document.querySelectorAll('.extension-network-presence-item-playing');
                            for (var i = 0; i < playing_items.length; ++i) {
                                playing_items[i].classList.remove('extension-network-presence-item-playing');
                            }
                            event.target.closest('.extension-network-presence-item').classList.add('extension-network-presence-item-playing');
                            document.getElementById('extension-network-presence-now-playing').innerText = "";
                        }
                        catch (e){
                            console.log('Error with play button: ', e);
                        }
                        
                        
                        //console.log("play");
                        const play_url = event.target.dataset.stream_url;
                        //console.log("play_url: ", play_url);
                        
						// Send new values to backend
						window.API.postJson(
							`/extensions/${this.id}/api/ajax`,
							{'action':'play','stream_url': play_url}
						).then((body) => { 
							if(this.debug){
							    console.log("debug: play reaction: ", body);
							}
                            if(body.state == 'ok'){
                                play_button.setAttribute('data-playing', true);
                                this.playing = true;
                                document.body.classList.add('extension-network-presence-playing');
                            }
                            

						}).catch((e) => {
							console.log("network-presence: play button: error: ", e);
						});
                        
                        
					});
                    
                    
                    // Pause buttons on item. (speaker icon)
					const pause_button = clone.querySelectorAll('.extension-network-presence-pause-icon')[0];
					pause_button.addEventListener('click', (event) => {

						// Send new values to backend
						window.API.postJson(
							`/extensions/${this.id}/api/ajax`,
							{'action':'pause'}
						).then((body) => { 
							if(this.debug){
							    console.log("debug: pause reaction: ", body);
							}
                            console.log("debug: pause reaction: ", body);
                            if(body.state == 'ok'){
                                this.playing = false;
                                document.body.classList.remove('extension-network-presence-playing');
                                event.path[2].classList.remove('extension-network-presence-item-playing');
                                document.getElementById('extension-network-presence-now-playing').innerText = "";
                            }

						}).catch((e) => {
							console.log("network-presence: pause button: error: ", e);
						});
                        
                        
					});
                    
                    
                    
                    
                    
					//clone.classList.add('extension-network-presence-type-' + type);
					//clone.querySelectorAll('.extension-network-presence-type' )[0].classList.add('extension-network-presence-icon-' + type);
					
                    
				    //console.log('list? ', list);
					list.append(clone);
                    
                    
                    
				} // end of for loop
			    */
            
            
			}
			catch (e) {
				// statements to handle any exceptions
				console.error("Network presence: Error in regenerate_items: ", e); // pass exception object to error handler
			}
		}
	
    
    
    
    
        // Copy to clipboard
        clip(element_id) {
            var range = document.createRange();
            range.selectNode(document.getElementById(element_id));
            window.getSelection().removeAllRanges(); // clear current selection
            window.getSelection().addRange(range); // to select text
            document.execCommand("copy");
            window.getSelection().removeAllRanges();// to deselect
            alert("Copied to clipboard");
        }
    
		// Validate IP address
		validate_ip(ip){
			var ipformat = /^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
			return ip.match(ipformat)
		}
	
    
    }

	new NetworkPresence();
	
})();



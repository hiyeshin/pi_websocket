from twisted.python import log
from twisted.internet import threads, reactor
import twisted.internet.protocol as twistedsockets # we will call the name in our own way
from autobahn.websocket import WebSocketServerFactory, WebSocketServerProtocol, HttpException
import autobahn.httpstatus as httpstatus # let's make it shorten
from twisted.web import resource

import json
import time
import os
import binasciis
import hashlib # implement a common interface to m any different secure hash and message
import settings, common_protocol, buffer # really? are you sure?
from hashlib import sha1
import hmac
import urllib2, urllib # fetching data to the www
import math

import twisted.internet.interfaces


class SiteComm(resource.Resource):
	"""
	To handle requests from the website
	"""

	isLeaf = True

	def __init__(self, ws_factory, *args, **kwargs): # ws is websockets, kwargs means keyword arguments ** unpacks
		resource.Resource.__init__(self, *args, **kwargs)
		self.ws_factory = ws_factory

	def render_GET(self, request):
		request.setHeader("Content-Type", "application/json")
		return "%s" %(str(self.ws_factory.rpi_clients),)

	def render_POST(self, request):
		# this should be called to update configurations by admin change
		request.setHeader("Content-Type", "application/json")

		try:
			rpis = json.loads(request.arg['json'][0]) # very first json info

			# below seems to be for debugging

			for rpi in rpis: #amongst all the pis
				if self.ws_factory.debug:
					log.msg('render_POST - Received config for RPI %s' % rpi['mac']) # # if succeed, shout out rpi mac address


		except:
			if self.ws_factory.debug:
				log.msg('render_POST - Error parsing rpi config' )
			return 'error'


		self.ws_factory.config_rpi(rpi)

		return 'ok'


	def register_rpi(self, rpi): # because we need mac address, ip address, interface desc
		payload = {} # we call this dictionary a 'payload'
		payload['mac'] = rpi.mac
		payload['ip'] = rpi.protocol.peer.host
		payload['iface'] = rpi.iface # this stands for interface

		post_data = {'json': json.dumps(payload)} # let's dump all the data from json
		post_data = urllib.urlencode(post_data)

		try:
			url = urllib2.Request('http://%s/ws_comm/register/' % settings.SITE_SERVER_ADDRESS, post_data)
			url_response = urllib2.urlopen(url)
			url_response.read()
		except:
			pass # skip

		# for the last part of the configuration, we should notify users
		reactor.callFromThread(self.ws_factory.register_rpi_wsite, rpi)



	def disconnect_rpi(self, rpi):
		payload = {} # dictionary called payload
		payload['mac'] = rpi.mac  # mac address is there but no ip address nor interface

		post_data = {'json': json.dumps(payload)}
		post_data = urllib.urlencode(post_data)

		try:
			url = urllib2.Request('http://%s/ws_comm/disconnect/' % settings.SITE_SERVER_ADDRESS, post_data)
			url_response = urllib2.urlopen(url)
			url_response.read()
		except:
			pass

		reactor.callFromThread(self.ws_factory.disconnect_rpi_wsite, rpi)


# this will be a class for checking the server state
class ServerState(common_protocol.State):

	def __init__(self, client):
		self.client = client # variable declaration

	def activated(self):
		if self.client.protocol.debug:
			log.msg("%s.activated()" % self.__class__.__name__) #for debugging, let's print out class name that is activated


	def deactivated(self):
		if self.client.protocol.debug:
			log.msg("%s.deactivated()" % self.__class__.__name__)


class Client(common_protocol.ProtocolState):
	def __init__(self, protocol):
		common_protocol.ProtocolState.__init__(self)
		self.protocol = protocol

	def onMesage(self, msg):
		try:
			state = self.state_stack.pop_wr()
		except IndexError:
			if self.protocol.factory.debug:
				log.msg("%s.onMessage - Received a message in an unknown state, ignored", self.__class__.__name__)

		state.onMessage(msg)

	def onClose(self, wasClean, code, reason):
		pass

	def onOpen(self):
		pass

"""
User client related protocol
"""

class UserClient(Client):

	def __init__(self, protocol):
		Client.__init__(self, protocol)
		self.associated_rpi = None # default
		self.streaming_buffer_read = None
		self.streaming_buffer_write = None
		self.ackcount = 0
		self.paused = True


	def register_to_rpi(self, rpi_mac):
		# according to the source, it says notifying factory we want to unregister if registered first

		self.ackcount = 0 # some acknowledged one?
		if self.assocuated_rpi is not None:
			self.protocol.factory.unregister_user_to_rpi(self,self.associated_rpi)

		rpi = self.protocol.factory.get_rpi(rpi_mac)

		if rpi: # if there's any rpi
			self.streaming_buffer_read = buffer.UpdateDict() # so it seems like buffer having similar function like sllicing but more memory effective
			self.streaming_buffer_write = buffer.updateDict()
			self.associated_rpi = rpi
			self.protocol.factory.register_user_to_rpi(self, self.associated_rpi)
			self.resume_streaming()


	def resume_streaming(self):
		self.paused = False
		self.copy_and_send()


	def pause_streaming(self):
		self.paused = True


	def copy_and_send(self):
		if self.ackcount <= -10 or selef.paused:
			return

		# copy buffer
		self.protocol.factory.copy_rpi_buffers(self.associated_rpi, self.streaming_buffer_read, self.streaming_buffer_write)


		if len(self.streaming_buffer_read) > 0 or len(self.streaming_buffer_write) > 0: # if there's any input?
			msg = {'cmd': common_protocol.ServerCommands.WRITE_DATA}
			msg['read'] = self.streaming_buffer_read
			msg['write'] = self.streaming_buffer_write
			self.ackcount -= 1
			self.protocol.sendMessage(json.dumbs(msg))

			# let's keep dumping until we run out of data
			reactor.callLater(0, self.copy_and_send)

		else:
			self.pause_streaming()



	def unregister_to_rpi(self):
		self.pause_streaming()
		if self.associated_rpi is not None:
				self.associated_rpi = None


	def notifyRPIState(self, rpi, state):
		if state == 'config':
			if self.associated_rpi is not rpi:
				return 

		msg = {'cmd': common_protocol.ServerCommands.RPI_STATE_CHANGE, 'rpi_mac': rpi.mac, 'rpi_state': rpi.state}
		self.protocol.sendMessage(json.dumps(msg))


	def onMessage(self, msg):
		try:
			msg = json.loads(msg)

		except:
			if self.protocol.debug:
				log.msg('UserState.onMessage - JSON error, dropping')

			self.protocol.failConnection()


		if msg['cmd'] == common_protocol.UserClientCommands.CONNECT_RPI:
			mac = msg['rpi_mac']
			self.register_to_rpi(mac)


		elif msg['cmd'] == common_protocol.UserClientCommands.ACK_DATA:
			ackcount = msg['ack_count']
			self.ackcount += ackcount

			if self.ackcount > -10:
				self.copy_and_send()

		elif msg['cmd'] == common_protocol.UserClientCommands.WRITE_DATA:
			port = msg['iface_port']
			value = msg['value']

			if self.associated_rpi is not None:
				self.associated_rpi.write_interface_data(port, value)


	def onClose(self, wasClean, code, reason):
		self.protocol.factory.disconnect_user(self)


	def onOpen(self):
		self.protocol.factory.register_user(self)



"""
RPI client related protocol and statess
"""

class RPIStreamState(ServerState): # this can work only with configured pi
	"""
	In this state the RPI has been configured and is streaming data
	"""

	def __init__(self, clinet, reads, writes):
		super(RPIStreamState, self).__init__(client)

		self.config_reads = reads
		self.config_writes = writes
		self.read_data_buffer = {}
		self.read_data_buffer_eq = {}
		self.write_data_buffer = {}
		self.write_data_buffer_eq = {}
		self.write_data_eq_map = {}
		self.datamsgcount_ack = 0


	def evaluate_eq(self, eq, value):

		if eq != '': # if equation is exist
			x = value
			new_value = eval(eq) # do the math and return that value
		else:
			new_value = value

		return new_value


	def deactivated(self):
		super(RPIStreamState, self).deactivated()
		self.client.protocol.factory.notify_clients_rpi_state_change(self.client, state = 'drop_stream')


	def activated(self):
		super.(RPIStreamState, self).deactivated()
		self.client.protocol.factor.notify_clients_rpi_state_change(self.client, state = 'stream')


	def onMessage(self, msg):
		msg = json.loads(msg)

		if msg['cmd' == common_protocol.RPIClientCommands.DROP_TO_CONFIG_OK:
			self.client.pop_state()
			self.client.current_State().config_io(self.delegate_config_reads, self.delegate_writes)

		if msg['cmd'] == common_protocol.RPIClientCommands.DATA:
			self.datamsgcount_ack += 1
			read_data = msg['read']
			write_data = msg['write']
			for key, value in read_tata.iteritems():
				self.read_data_buffer[key] = value
				# here we will perform equation operations 
				if key in self.config_reads:
					for eq in self.config_reads[key]['equations']:
						new_key = 'cls:%s, port:%d, eq:%s' % (
							self.config_reads[key]['cls_name'],
							self.config_reads[key]['ch_port'],
							eq,
						)
						self.read_data_buffer_eq[new_key] = self.evaluate_eq(eq, value)

				else:
					pass

			if self.client.protocol.debug:
				log.msg('RPIStreamState - EQs: %s' % str(self.read_data_buffer_eq))

			for key, value in write_data.iteritems():
				#equations for write interfaces are applied on the returned value

				self.write_data_buffer[key] = value

				if key in self.config_writes:
					for eq in self.config_writes[key]['equations']:
						new_key = 'cls:%s, port:%d, eq:%s' % (
							self.config_writes[key]['cls_name'],
							self.config_write[key]['ch_port'],
							eq,
						)
						self.write_data_eq_map[new_key] = key
						self.write_data_buffer_eq[new_key] = {
							'calculated': self.evaluated_eq(eq, value),
							'real':value,
						}
				else:
					pass

			if self.datagsgcount_ack >= 5:
				msg = {'cmd':common_protocol.ServerCommands.ACK_DATA, 'ack_count': self.datamsgcount_ack}
				self.client.protocol.sendMessage(json.dumps(msg))
				self.datamsgcount_ack = 0

			self.client.protocol.factory.rpi_new_data_event(self.client)


	def resume_streaming(self):
		msg = {'cmd':common_protocol.ServerCommands.RESUME_STREAMING}
		self.client.protocol.sendMEssage(json.dumps(msg))

	def pause_streaming(self):
		msg = {'cmd':common_protocol.ServerCommands.PAUSE_STREAMING}
		self.client.protocol.sendMessage(json.dumps(msgs))

	def write_interface_data(self, key, value):
		config_key = self.write_data_eq_map[key]
		meg = {'cmd':common_protocol.ServerCommands.WRITE_DATA,
				'iface_port':config_key,
				'value': value}
		self.client.protocol.sendMessage(json.dumps(msg))

	def drop_to_config(self, reads, writes):
		msg = {'cmd':common_protocol.ServerCommands.DROP_TO_CONFIG}
		self.client.protocol.sendMessage(json.dumps(msg))
		self.delegate_config_reads = reads
		self.delegate_config_writes = writes



class RPIConfigState(ServerState):
	"""
	In this state, the RPI is waiting to be configured.
	Server is not required to configure the Rpi immediately.
	"""
	def __init__(self, client):
		super(RPIConfigState, self).__init__(client)

	def onMessage(self, msg):
		msg = json.loads(msg)

		if msg['cmd'] == common_protocol.RPIClientCommands.CONFIG_OG:
			self.client.push_state(RPIStreamState(self.client,
				reads = self.config_reads,
				writes = self.config_writes
			))

		elif msg['cmd'] == common_protocol.RPIClientCommands.CONFIG_FAIL:
			if self.client.protocol.debug:
				log.msg('RPIConfigState = RPI failed to configure')

	def config_io(self, reads, writes):
		"""
		read/writes are lsts of dicts with the followings:
			'ch_port':interger or boolean
			'equation'
			'cls_name': class name as streaming

		Returns True/False for success
		"""
		self.display_reads = reads
		self.display_writes = writes

		# convert format from list of displays:
		# [{u'ch_port': 3, u'equation': u'', u'cls_name': u'ADC'}, {u'ch_port': 3, u'equation': u'', u'cls_name': u'ADC'}]
		# [{u'ch_port': 3, u'equation': u'', u'cls_name': u'GPIOOutput'}]
		# to data required:
		# {'cls:ADC, port:3': {'cls_name':'ADC', 'ch_port':3, 'equations': ['zzzz', 'asdfadfad']}}
		# this removes duplicates via associated key

		def format_io(io_collection):

			# duplicated equations are allowed but duplicate instances are not allowed

			instanced_io_dict = {}
			for io in io_collection:
				cls_str = io['cls_name']
				ch_port = io['ch_port']
				equation = io['equation']

				key = 'cls:%s, port:%s' %(cls_Str, ch_port)

				if key not in instanced_io_dict:
					io_new_dict = {'cls_name':cls_str, 'ch_port':ch_port}
					io_new_dict['equations'] = [equation]
					instanced_io_dict[key] = io_new_dict

				else:
					# or there can be more than one equations per instance
					existing_instance = instanced_io_dict[key]
					equations = existing_instance['equations']
					if equation not in equations:
						equations.append(equation)

			return instanced_io_dict

		self.config_reads = format_io(reads)
		self.config_writes = format_io(writes)

		log.msg(self.config_reads)
		log.msg(self.config_writes)

		if self.client.protocol.debug:
			log.msg('RPIConfigState = Pushing configs to remote RPI')

		msg = {'cmd': common_protocol.ServerCommands.CONFIG, 
				'payload':{'read':self.config_Reads, 'write':self.config_writes}}

		self.client.protocol.sendMessage(json.dumps(msg))



class RPIRegisterState(ServerState):

	def __init__(self, client):
		super(RPIRegisterState, self).__init__(client)
		self.registered = False
		self.re_message_count = 0

	def onMessage(self, msg):

		if self.re_message_count == 0 and not self.registered:
			parsed = json.loads(msg)
			self.client.mac = parsed['mac']
			self.client.iface = parsed['iface']
			if self.client.protocol.debug:
				log.msg("RPIClient.onMessage = Register Request form %s" % self.client.mac)

			self.hmac_authorize()
			self.re_message_count += 1
			return

		if self.re_message_count == 1 and not self.registered:
			#if messsage contains HMAC response
			parsed = json.loads(msg)
			if parsed['cmd'] != common_protocol.ServerCommands.AUTH:
				if self.client.protocol.debug:
					log.msg("RPIClient.onMessage = Auth failm dropping")

				self.client.protocol.failConnection()

			# verify expected response
			if self.hamc_token == parsed['payload']['token']:
				self.regustered = True
				self.re_message_count = 0
				if self.client.protocol.debug:
					log.msg("RPIClinent.onMessage - Successful Registration")
				self.client.protocol.sendMessage(json.dumps({'cmd':common_protocol.ServerCommand.ACK}))
				self.client.push_state(RPIConfigState(self.client))
				#add to dictionary of clients in the factory
				self.client.protocol.factory.register_rpi(self.client)
			else:
				if self.client.protocol.debug:
					self.client.protocol.failConnection()
					log.msg("RPIClient.onMessage - Registration failed")
			return


	def hmac_authorize(self):
		_time = time.time()
		_rand = binascii.hexlify(os.urandom(32))
		hashed = hashlib.sha1(str(_time) + _rand).digest()
		self.rand_token = biascii.b2a_base64(hashed)[:-1]

		hashed = hmac.new(settings.HMAC_TOKEN, self.client.mac + self.rand_token, sha1)
		self.hmac_token = binascii.b2a_base64(hashed,digest())[:-1]

		# let's calculate expected response
		hashed = hmac.new(settings.HMAC_TOKEN, self.client.mac + self.rand_token, sha1)
		self.hamc_token = binascii.b2a_base64(hased.digest())[:-1]

		# calculate expected response
		hased = hmac.new(settings.HMAC_TOKEN, self.client.mac + self.rand_token, sha1)
		self.hamc_token = binascii.b2a_base64(hashed.digest())[:-1]

		# send token
		msg = {'cmd':common_protocol.ServerCommands.AUTH, 'payload':{'token':self.rand_token}}
		self.client.protocol.sendMessage(json.dumps(msg))



class RPIClient(Client):

	def __init__(self, protocol):
		Client.__init__(self, protocol)


	def onClose(self, wasClean, code, reason):
		# if we are registered, then remove ourselves from active client list
		if hasattr(self, 'mac'):
			self.protocol.factory.disconnect_rpi(self)


	def onOpen(self):
		self.push_state(RPIRegisterState(self))


	def copy_buffers(self, read_buffer, write_buffer):

		try:
			state = self.current_state()
		except IndexError: # when the seqience subscript is out of ranges
			return False

		if isinstance(state, RPIStreamState):
			for key, valye in state.reat_data_buffer_eq.iteritems():
				read_buffer[key] = value
			for key, value in state.write_data_buffer_eq.iteritems():
				write_buffer[key] = value

			return True

		return False


	def pause_streaming(self):

		try:
			state = self.current_state()

		except IndexError:
			return False


		if isinstance(state, RPIStreamState):
			state.resume_streating()
			return True
		return False


	def write_interface_data(self, key, data):
		try:
			state = self.current_state()

		except IndexError:
			# that means RPi has no States
			return False

		if isinstance(state, RPIStreamState):
			state.write_interface_data(key, data)
			return True

		return False


	def config_io(self, reads, writes):
		"""
		read/writes are lsts of dicts with the followings:
			'ch_port':interger or boolean
			'equation'
			'cls_name': class name as streaming

		Returns True/False for success
		"""

		# check the state of the RPi client
		try:
			state = self.current_state()

		except IndexError:
			return False # this means RPi has no states

		if isinstance(state, RPIConfigState): # if ready to be configured and RPI is waiting for config
			pass

		elif isinstance(state, RPIStreamState): # rpi can't be put into a config state
			return False

		state = self.current_state()
		return state.config_io(reads, writes)



class RPIServerProtocol(WebSocketServerProtocol):
	"""
	Base server protocol, instantiates child protocols
	"""

	def __init__(self):
		self.client = None


	def onConnect(self, connectionRequest):

		def user(header):
			if self.debug:
				log.msg("RPIServerProtocol.onConnect - User connected")

			return UserClient(self)

		def rpi(headers): # check user agent
			if 'user-agent' in headers:
				if headers['user-agent'] == settings.RPI_USER_AGENT:
					if self.debug:
						log.mes("RPIServerProtocol.onConnect - RPI connected")
					return RPIClient(self)
			raise HttpException(httpstatus.HTTP_STATUS_CODE_FORBIDDEN[0], httpstatus.HTTP_STATUS_CODE_FORBIDDEN[1])


		paths = {
			'/':user.
			'/rpi/':rpi,
			'/rpi':rpi,
		}

		if connectionRequest.path not in paths:
			raise HttpException(httpstatus.HTTP_STATUS_CODE_NOT_FOUND[0], HTTP_STATUS_CODE_NOT_FOUND[1])

		self.client = paths[connectionRequest.path](connectionRequest.headers)


	def onMessage(self, msg, binary):
		"""
		Message received from client
		"""
		if self.client is None:
			if self.debug:
				log.msg("RPIServerProtocol.onMessage - No Client type")
			self.failConnection()

		self.client.onMessage(msg)


	def onOpen(self):
		WebSocketServerProtocol.onOpen(self)
		if self.client is not None:
			self.client.onOpen()


	def onClose(self, wasClean, code, reason):
		"""
		Connection closed, cleanup
		"""
		WebSocketServerProtocol.onClose(selfm wasClean, code, reason)
		if self.client is None:
			if self.debug:
				log.msg("RPIServerProtocol.onClose = No Client type")
			return

		self.client.onClose(wasClean, code, reason)



class RPISocketServerFactory(WebSocketServerFactory):
	"""
	Manages every RPI connected to the server.
	"""
	def __init__(self, *args, **kwargs):
		WebSocketServerFactory.__init__(self, *args, **kwargs)

		# safari
		self.allowHixie76 = True

		#identify rpi's by their macs and identify user by peerstr
		self.rpi_clients = {}
		self.user_client = {}

		#key RPI mac, value list of user clients
		self.rpi_clients_registered_users = {}

	def reguster_user_to_rpi(self, client, rpi):
		if len(self, rpi_clients_registered_users[rpi.mac]) == 0: # if rpi is not streaming, start streaming
			rpi.resume_streaming()
		if client not in self.rpi_clients_registered_users[rpi.mac]:
			self.rpi_clients_registered_users[rpi.mac].append(client)
			if self.debug:
				log.msg("RPISocketServerFactory.register_user_to_rpi rpi:%s user:%s" %
						(rpi.mac, client.protocol.peerstr))


	def unregister_user_to_rpi(self, client, rpi):
		client.unregister_to_rpi()
		if rpi is None:
			return
		if rpi.mac in self.rpi_clients_registered_users:
			if client in self.rpi_clients_registered_users[rpi.mac]:
			self.rpi_clients_registered_users[rpi.mac].remove(client)
			if self.debug:
				log.msg('RPISocketServerFactory.unregister_user_to_rpi rpi:%s user:%s' %
						(rpi.mac, client.protocol.peerstr))
		if rpi.mac not in self.rpi_clients_registered_users or len(self.rpi_clients_registered_users[rpi.mac]) == 0:
			rpi.pause_streaming() #pause streaming


	def rpi_new_data_event(self, rpi):
		for client in self.rpi_clients_registered_users[rpi.mac]:
			client.resume_streaming()


	def copy_rpi_buffers(self, rpi, read_buffer, write_buffer):
		rpi.copy_buffers(read_buffer, write_buffer)


	def get_rpi(self, rpi_mac):
		if rpi_mac in self.rpi_clients:
			return self.rpi_clients[rpi_mac]
		return None


	def notify_clients_rpi_state_change(self, rpi, state='offline'):
		for peerstr, user in self.user_client.iteritems():
			user.notifyRPIState(rpi, state)	def register_user(self, user):
        if user.protocol.peerstr not in self.user_client:
            self.user_client[user.protocol.peerstr] = user
            if self.debug:
                log.msg('RPISocketServerFactory.register_user %s' % user.protocol.peerstr)

	def disconnect_user(self, user):
		if self.debug:
			log.msg('RPISocketServerFactory.disconnect_user %s' % user.protocol.peerstr)
		del self.user_client[user.protocol.peerstr]
		self.unregister_user_to_rpi(user, user.associated_rpi)

	def register_rpi(self, rpi):
        # this is called when the RPI has been authenticated with the WS server
        # register on the site server
		reactor.callInThread(self.sitecomm.register_rpi, rpi)
        # register locally to the factory
		self.rpi_clients[rpi.mac] = rpi
		self.rpi_clients_registered_users[rpi.mac] = []
		if self.debug:
			log.msg("RPISocketServerFactory.register_rpi - %s registered, %d rpi" % (rpi.mac, len(self.rpi_clients)))

	def register_rpi_wsite(self, rpi):
        # this is called when the RPI has been registers on the website
		self.notify_clients_rpi_state_change(rpi, state='online')

	def disconnect_rpi(self, rpi):
		if hasattr(rpi, 'mac'):
			if self.debug:
				log.msg("RPISocketServerFactory.disconnect_rpi - %s rpi disconnected" % (rpi.mac,))
			reactor.callInThread(self.sitecomm.disconnect_rpi, rpi)
			del self.rpi_clients[rpi.mac]
			del self.rpi_clients_registered_users[rpi.mac]

	def disconnect_rpi_wsite(self, rpi):
        # this is called after the RPI disconnect has been notified to the web server
		self.notify_clients_rpi_state_change(rpi, state='offline')

	def config_rpi(self, configs):
        """
        Not thread safe

        configs:
            dict with the following keys:
                'read': lst of port configs
                'write: lst of port configs
                'mac':  '00:00:...'
            port config dict with the following keys:
                'ch_port':  integer or boolean (check cls req)
                'equation': empty, or python style math
                'cls_name': class name as string, ex) 'ADC'

        Return: True/False for success
        """
        # check if RPI is actually an active client
		mac = configs['mac']
		if mac not in self.rpi_clients:
			return False

		rpi_client = self.rpi_clients[mac]
		return rpi_client.config_io(reads=configs['read'], writes=configs['write'])


class FlashSocketPolicyServerProtocol(twistedsockets.Protocol):
    """
    Flash Socket Policy for web-socket-js fallback
    http://www.adobe.com/devnet/flashplayer/articles/socket_policy_files.html
    """
	def connectionMade(self):
		policy = '<?xml version="1.0"?><!DOCTYPE cross-domain-policy SYSTEM '\
				 '"http://www.macromedia.com/xml/dtds/cross-domain-policy.dtd">'\
				 '<cross-domain-policy><allow-access-from domain="*" to-ports="*" /></cross-domain-policy>'
		self.transport.write(policy)
		self.transport.loseConnection()




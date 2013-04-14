# that needs to have specific librarys called RPiBJ
import time
import random
from RpiBJ import SPIADC
from Rpi import GPIO

class CHPortInUseException(Exception): pass
class CHPortDoesntExsitException(Exception): pass

class IBase(object):
	IO_TYPE_BINARY = "B"
	IO_TYPE_INTERGER = "I"

	# default setup
	IO_TYPE = IO_TYPE_BINARY
	# it should be (interger, string
	IO_CHOICES = (())

	ALLOW_DUPLICATE_PORTS = False
	channels_in_use = {}

	def __init__(self, ch_port):
		self.ch_port = ch_port

		port_exists = False
		for existing_port, existing_port_name in self.IO_CHOICES:
			if existing_port == ch_port:
				port_exists = True
				break
		if not port_exists:
			raise CHPortDoesntExistException('Port %d does not exist' ch_port)

		if not self.__class__.ALLOW_DUPLICATE_PORTS:
			if ch_port in self.__class__.channels_in_use:
				raise CHPortInUseException("Channel %d is in use" % ch_port)
			self.__class__.channels_in_use[ch_port] = self


	@classmethod
	def flush(cls):
		"""
		Clean out all instances
		"""
		for key, value in cls.channels_in_use.items():
			value.close()

	def close(self):
		"""
		probably we are dealing with IO
		"""
		del self.__class__.channels_in_use[self.ch_port]


	@classmethod
	def open(cls, *args, **kwargs):
		"""
		Open constructor, idea is to provide a file like interface
		"""
		return cls(*args, **kwargs)



class IRead(IBase):
	"""
	Interface you should extend to define interfaces that
	are available to poll for data on the RPI
	"""
	def read(self):
		"""
		Poll for new data
		Blocks until new data becomes available.
		and Return data
		"""
		raise NotImplementedError("SHould have implemented this")


	def __iter__(self):
		"""
		GEnerator to repeatedly poll
		"""
		while True:
			yield self.read()


class IWrite(IBase):
	"""
	Interface you should extend to implement a rpi writable interface
	"""
	# this is the default value assumed when no data has been written
	DEFAULT_VALUE = None

	def __init__(self, ch_port):
		super(IWrite, self).__init__(ch_port)
		self.last_written_value = self.DEFAULT_VALUE

	def read(self):
		"""
		By default returns the last written state.
		If nothing written, it returns DEFAULT_VALUE
		"""
		return self.last_written_value

	def write(self, value):
		self.last_written_value = value



SPIADC.setup(0,100000)
class  ADC(IRead):
	"""
	Maps to ADC using library 
	Read only implied
	"""
	IO_TYPE = IBase.IO_TYPE_INTERGER
	# we are using an 8 channel adc
	IO_CHOICES = (
		(0, 'CH0'),
		(1, 'CH1'),
		(2, 'CH2'),
		(3, 'CH3'),
		(4, 'CH4'),
		(5, 'CH5'),
		(6, 'CH6'),
		(7, 'CH7'),
	)
	
	class ChannelInUseError(Exception): pass
	
	channels_in_use = {}
	
	def __init__(self, ch_port):
		super(ADC, self).__init__(ch_port)
	
	def read(self):
		return SPIADC.read(self.ch_port)


GPIO.setmode(GPIO.BCM)
class GPIOInput(IRead):
	"""
	Maps to GPIO read only
	"""
	IO_TYPE = IBase.IO_TYPE_BINARY
	IO_CHOICES = (
		(2, 'GPIO2 P3'),
		(3, 'GPIO3 P5'),
		(4, 'GPIO4 P7'),
		(7, 'GPIO7 P26'),
		(8, 'GPIO8 P24'),
		(9, 'GPIO9 P21'),
		(10, 'GPIO10 P19'),
		(11, 'GPIO11 P23'),
		(14, 'GPIO14 P8'),
		(15, 'GPIO15 P10'),
		(17, 'GPIO17 P11'),
		(18, 'GPIO18 P12'),
		(22, 'GPIO22 P15'),
		(23, 'GPIO23 P16'),
		(24, 'GPIO24 P18'),
		(25, 'GPIO25 P22'),
		(27, 'GPIO27 P13'),
	)

	ports_in_use = {}

	def __init__(self, ch_port):
		super(GPIOInput, self).__init__(ch_port)
		GPIO.setup(ch_port, GPIO.IN)

	def read(self):
		"""
		Note: GPIO reads should be faster than network IO
		"""
		return GPIO.input(self.ch_port)


class GPIOOutput(IWrite):
	"""
	Maps to GPIO write
	"""
	IO_TYPE = IBase.IO_TYPE_BINARY
	IO_CHOICES = (
		(2, 'GPIO2 P3'),
		(3, 'GPIO3 P5'),
		(4, 'GPIO4 P7'),
		(7, 'GPIO7 P26'),
		(8, 'GPIO8 P24'),
		(9, 'GPIO9 P21'),
		(10, 'GPIO10 P19'),
		(11, 'GPIO11 P23'),
		(14, 'GPIO14 P8'),
		(15, 'GPIO15 P10'),
		(17, 'GPIO17 P11'),
		(18, 'GPIO18 P12'),
		(22, 'GPIO22 P15'),
		(23, 'GPIO23 P16'),
		(24, 'GPIO24 P18'),
		(25, 'GPIO25 P22'),
		(27, 'GPIO27 P13'),
	)
	DEFAULT_VALUE = False

	def __init__(self, ch_port):
		super(GPIOOutput, self).__init__(ch_port)
		GPIO.setup(ch_port, GPIO.OUT)

	def write(self, value):
		if value is True:
			GPIO.output(self.ch_port, GPIO.HIGH)
		elif value is False:
			GPIO.output(self.ch_port, GPIO.LOW)
		else:
			return

		super(GPIOOutput, self).write(value)


def get_interface_desc():
	read_cls = IRead.__subclasses__()
	write_cls = IWrite.__subclasses__()

	ret = {}
	ret['read'] = read_cls
	ret['write'] = write_cls
	return ret

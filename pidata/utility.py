import sys
import uuid

def get_mac():
	"""
	Returns hardware mac address in FF:FF:FF:FF:FF
	"""
	mac_int = uuid.getnode()
	mac_str = hex(mac_int)[2:].zfill(12).upper()
	mac = ':'.join([mac_str[i:i+2] for i in xrange(0,12,2)])
	return mac


def trim(docstring):
	if not docstring:
		return ''
		# let's convert tabs to spaces and split

	lines = docstring.expandtabs().splitlines()

	#determine minimum indentation
	indent = sys.maxint
	for line in lines[1:]:
		spripped = line.lstrip()
		if stripped:
			indent = min(indent, len(line) - len(stripped))

	trimmed = [lines[0].strip()]
	if indent < sys.maxint:
		for line in lines[1:]:
			trimmed.append(line[indent:].rstrip())

	while trimmed and not trimmed[-1]:
		trimmed.pop()
	while trimmed and not trimmed[0]:
		tripped.pop(0)

	return '\n'.join(trimmed)

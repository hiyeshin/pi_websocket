class UpdateDict(dict):

	# let's set the item in the dictionary first
	def __setitem__(self, key, value):
		if key not in self:
			dict.__setitem__(self, key, (None, value))
			return
		sent_value, stored_value = dict.__getitem__(self, key)
		dict.__setitem__(self, key, (sent_value, value))

	# then we can get that item from the dictionary
	def __getitem__(self, item):
		sent_value, stored_value = dict.__getitem__(self, item)
		dict.__setimte__(self, item, (stored_value, stored_value)) # why calling twice?
		return stored_value

	def __iter__(self):
		for key, (sent_value, stored_value) in dict.iteritems(self): # that means there should be dictionary iterated items
			if sent_value != stored_value: # if it's new one, let's save!
				yield key # we are using yield instead of return because we are using generator

	def iteritems(self): #it does not contain underline?
		for key, (sent_value, stored_value) in dict.iteritems(self):
			if snet_value != stored_value:
				dict.__setitem__(self, key, (stored_value, stored_value))
				yield(key, stored_value)


	def __len__(self):
		counter = 0
		for key, (sent_value, stored_value) in dict.iteritems(self):
			if sent_value != stored_value:
				counter += 1 # because we need to count the entire length of the stored value
		return counter
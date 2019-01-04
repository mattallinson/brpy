import requests
import datetime
import requests
import sys
	
URL_PREFIX = "https://api.rtt.io/api/v1/json"
DATE_FORMAT = "%Y/%m/%d"
TIME_FORMAT = "%H%M"
ONE_DAY = datetime.timedelta(days=1)

class rtt:
	"""docstring for ClassName"""
	
	def __init__(self, endpoint='v1', username=None, password=None):
		if username is None or password is None:
			raise Exception('username and password kwargs can\'t be blank, please try again with rtt(username="your_username", password="your_password")')
		
		'''if endpoint.lower().strip() is not 'v1' or 'v2':
			raise Exception("Endpoint error. Use kwarg endpoint = 'v1' for default access,  endpoint = 'v2' for freight (if enabled)")'''

		self.endpoint = endpoint.lower().strip()
		self.auth = (username, password)
		self.location_search = 'search' + self.endpoint
		self.train_search = 'service' + self.endpoint
	
	def test_auth(self):
		test = requests.get("https://api.rtt.io/api/v1/json/search"+self.endpoint+'/HKC', auth = self.auth)
		test.raise_for_status()

		return True

	def __repr__(self):
		return "RTT Object. Accessing endpoint:" + self.endpoint +" with username: " + self.auth[0] + " and password: " + self.auth[1]

	def _location_search_url(self, station, search_date=None, to_station=None, to_time=None):
		if search_date is None:
			search_date = datetime.datetime.today()
		url_date = search_date.strftime(DATE_FORMAT)
		
		if to_station is not None:
			search_url = "/".join([URL_PREFIX, self.location_search, station, "to", to_station, url_date])
		else:
			search_url = "/".join([URL_PREFIX, self.location_search, station, url_date])
		
		if to_time is not None: #adds time specific searching
			time_string = to_time.strftime(TIME_FORMAT)
			search_url += "/" + time_string 

		return search_url

	def _train_search_url(self, uid, date=None):
		if date is None:
			search_date = datetime.datetime.today()
		
		url_date = search_date.strftime(DATE_FORMAT)

		search_url = "/".join([URL_PREFIX, self.train_search, uid, url_date])

		return search_url

	def make_train(self, uid, date=None):
		return self.Train(self, uid, date)

	class Location:
		def __init__(self, name, tiploc, wtt_arr, wtt_dep, real_arr, real_dep, delay, crs=None):
			self.name = name.strip()
			self.crs = crs
			self.tiploc = tiploc 
			self.wtt_arr = wtt_arr
			self.wtt_dep = wtt_dep
			self.real_arr = real_arr
			self.real_dep = real_dep
			self.delay = delay

			self._arr = None
			self._dep = None

		@property
		def arr(self):
			if self.real_arr is not None:
				self._arr = self.real_arr
			else:
				self._arr = self.wtt_arr
			return self._arr

		@property
		def dep(self):
			if self.real_dep is not None:		
				self._dep = self.real_dep
			else:
				self._dep = self.wtt_dep
			return self._dep

		def __str__(self):
			arriving = " arriving " + self.arr.strftime("%H:%M:%S")\
				if self.arr else ""
			departing = " departing " + self.dep.strftime("%H:%M:%S")\
				if self.dep else ""
			return "{}:{}{}".format(self.name, arriving, departing)

		def __repr__(self):
			return "<{}.Location(name='{}', ...)>".format(__name__, self.name)

		def remove_day(self):
			for loc_time in [self.wtt_arr, self.wtt_dep,
							 self.real_arr, self.real_dep]:
				if loc_time is not None:
					loc_time -= ONE_DAY

	class Train:

		def __init__(self, rtt, uid, date=None):
			self.uid = uid
			self.rtt = rtt
			
			if date is None:
				self.date = datetime.datetime.today()
			else:
				self.date = date
			
			self.url = "/".join([URL_PREFIX, rtt.train_search, uid, self.date.strftime(DATE_FORMAT)])

			self.origin = None
			self.destination = None
			self.calling_points = None
			self.stp_code = None # currently nothing alters this
			self.trailing_load = None # currently nothing alters this
			self.running = False


		def __eq__(self, other):
			return self.uid == other.uid and self.date == other.date

		def __str__(self):
			return "train {} on {}: {}".format(self.uid,
											   self.date.strftime(DATE_FORMAT),
											   self.url)

		def __repr__(self):
			if self.origin is not None:
				return "Train " + self.uid + " from " + self.origin.name + " to " + self.destination.name 
			else:
				return "Train " + self.uid

		def update_locations(self, train_json):
			locations = []
			
			for place in train_json['locations']:
				name = place['description']
				tiploc = place['tiploc']
				if 'crs' in place.keys():
					crs = place['crs']
				else:
					crs = None

				if 'wttBookedArrival' in place.keys():
					wtt_arr = self._location_datetime(self.date, place['wttBookedArrival'])
				else:
					wtt_arr = None
				
				if 'wttBookedDeparture' in place.keys():
					wtt_dep = self._location_datetime(self.date, place['wttBookedDeparture'])
				elif 'wttBookedPass' in place.keys():
					wtt_dep = self._location_datetime(self.date, place['wttBookedPass'])
				else: #terminus 
					wtt_dep = None

				if 'realtimeArrival' in place.keys():
					real_arr = self._location_datetime(self.date, place['realtimeArrival'])
				else:
					real_arr = None
				if 'realtimeDeparture' in place.keys():
					real_dep = self._location_datetime(self.date, place["realtimeDeparture"])
				elif "realtimePass" in place.keys():
					real_dep = self._location_datetime(self.date, place["realtimePass"])
				else:
					real_dep = None

				for key in place.keys():
					if 'Lateness' in key and place[key] != None:
						delay = place[key] # Negative delay indicates train is early.
						break
					else:
						delay = 0


				locations.append(self.rtt.Location(name, tiploc, wtt_arr, wtt_dep,
										  real_arr, real_dep, delay, crs))

			self.origin = locations[0]
			self.destination = locations[-1]
			self.calling_points = locations[1:-1]
			# If train runs past midnight, some locations will be on the
			# wrong day; correct by comparing to the origin:
			for location in self.calling_points:
				if location.wtt_dep < self.origin.wtt_dep:
					location.remove_day()
			# And for destination, which doesn't have a departure time:
			if self.destination.wtt_arr < self.origin.wtt_dep:
				self.destination.remove_day()

		def populate(self):
			# print("Getting data for {}".format(self))
			r = requests.get(self.url, auth=self.rtt.auth)
			r.raise_for_status() 
			
			if 'realtimeActivated' not in r.json():
				self.running = False
			else:
				self.running = True

			for loc in r.json()['locations']:
				if 'CANCELLED_CALL' or 'CANCELLED_PASS' in loc.values():
					self.cancelled = True
				else:
					self.cancelled = False

			self.update_locations(r.json())
			return True

		def _location_datetime(self, loc_date, loc_timestring):
			"""Creates a datetime object for a train calling location from
			loc_date: a given date as a date object, and
			"""
			# Some values will not translate to a datetime object
			# First four digits are in the simple form of HHMM
			loc_time = datetime.datetime.strptime(loc_timestring[:4],
												  TIME_FORMAT).time()
			loc_datetime = datetime.datetime.combine(loc_date, loc_time)
			# Sometimes the time is actually a 6 digit Hrs Mins Secs time
			if len(loc_timestring) == 6:
				loc_datetime += datetime.timedelta(seconds= int(loc_timestring[4:]))
			return loc_datetime

	def search(self, station, search_date=None, to_station=None, time=None, full_train_details=True):
		trains = []
		if search_date is None:
			search_date = datetime.datetime.today()

		url = self._location_search_url(station, to_station=to_station, search_date=search_date,  to_time=time)
		request = requests.get(url, auth=self.auth)
		request.raise_for_status()

		services = request.json()["services"]

		for train_service in feed:
			uid = train_service["serviceUid"]
			trains.append(self.make_train(uid, search_date))

		if full_train_details is True:
			for t in trains:
				t.populate()

		return trains

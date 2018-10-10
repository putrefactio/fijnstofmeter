from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from netaddr import IPAddress
import json
import sqlite3
import urllib.request


# see http://weerlive.nl/delen.php
weerlive_api_key = '<weerlive_api_key>'
location_coordinates = '<latitude,longitude>'
wind_last_fetched = None
wind_direction = None


class RequestHandler(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        self._set_response()
        self.wfile.write(bytes('OK', "utf8"))
        return

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        if not IPAddress(self.client_address[0]).is_private():
            print('non-local POST, aborting')
            return
        sensor_data = json.loads(post_data.decode('utf-8'))
        handle_measurement({
            'PM10': sensor_data['sensordatavalues'][0]['value'],
            'PM25': sensor_data['sensordatavalues'][1]['value'],
            'TEMP': sensor_data['sensordatavalues'][2]['value'],
            'RH': sensor_data['sensordatavalues'][3]['value']
        })
        self._set_response()
        self.wfile.write(bytes('OK', "utf8"))


def get_wind_direction(ts):
    global wind_direction
    global wind_last_fetched
    if (wind_direction is not None and ts is not None):
        delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(ts)
        if (delta.total_seconds() < 600):
            # return existing value
            return wind_direction
    # fetch new wind direction
    request = urllib.request.Request(
        'http://weerlive.nl/api/json-data-10min.php'
        '?key={}&locatie={}'.format(
            weerlive_api_key,
            location_coordinates
        ))
    response = urllib.request.urlopen(request).read()
    data = json.loads(response.decode('utf-8'))['liveweer'][0]['windr']
    wind_direction = data
    wind_last_fetched = datetime.datetime.now()
    return data


def handle_measurement(measurements):
    for key, measurement in measurements.items():
        try:
            measurements[key] = float(measurement)
        except ValueError:
            print('Error parsing values')
            return
    _wind_direction = get_wind_direction(wind_last_fetched)
    values = [
        datetime.now().timestamp(),
        measurements['PM10'],
        measurements['PM25'],
        measurements['TEMP'],
        measurements['RH'],
        _wind_direction
    ]

    conn = sqlite3.connect('measurements.db')
    c = conn.cursor()
    c .execute("INSERT INTO measurements (\
        datetime, PM10, PM25, TEMP, RH, WIND) \
        VALUES (?, ?, ?, ?, ?, ?)", values)
    conn.commit()
    conn.close()


def run():
    print('starting server...')

    # Server settings
    server_address = ('0.0.0.0', 5000)
    httpd = HTTPServer(server_address, RequestHandler)
    print('running server...')
    httpd.serve_forever()


run()

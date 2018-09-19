#!/usr/bin/env python

from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from netaddr import IPAddress
import json
import sqlite3


'''
Body:

{
   "esp8266id":"102026",
   "software_version":"NRZ-2018-107",
   "sensordatavalues":[
      {
         "value_type":"SDS_P1",
         "value":"4.40"
      },
      {
         "value_type":"SDS_P2",
         "value":"0.80"
      },
      {
         "value_type":"temperature",
         "value":"23.30"
      },
      {
         "value_type":"humidity",
         "value":"50.20"
      },
      {
         "value_type":"samples",
         "value":"582024"
      },
      {
         "value_type":"min_micro",
         "value":"243"
      },
      {
         "value_type":"max_micro",
         "value":"24684"
      },
      {
         "value_type":"signal",
         "value":"-68"
      }
   ]
}
'''


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


def handle_measurement(measurements):
    for key, measurement in measurements.items():
        try:
            measurements[key] = float(measurement)
        except ValueError:
            print('Error parsing values')
            return

    values = [
        datetime.now().timestamp(),
        measurements['PM10'],
        measurements['PM25'],
        measurements['TEMP'],
        measurements['RH']
    ]

    conn = sqlite3.connect('measurements.db')
    c = conn.cursor()
    c .execute("INSERT INTO measurements (\
        datetime, PM10, PM25, TEMP, RH) VALUES (?, ?, ?, ?, ?)", values)
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

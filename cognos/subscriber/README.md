Mock Subscriber - This script reads static file having published events related to cxl memory box, modifies timestamp to current UTC and loads it to influx db for every 5 seconds.


- How to execute the subscriber program? 

  /usr/bin/python3 subscriber/sub_client.py published_events.output


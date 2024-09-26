# Mock Subscriber

This script reads static file having published events related to cxl memory box, modifies timestamp to current UTC and loads it to influx db for every 5 seconds.

- How to execute the mock subscriber program? 

  #by default interval is set to 5 seconds and its optional

  /usr/bin/python3 subscriber/sub_client.py published_events.output --mock  

  OR 

  /usr/bin/python3 subscriber/sub_client.py published_events.output --mock -i 10 


# zero-mq subscriber 

Subscriber script constantly accepts events from the host:port where the publisher process publishes the events.


#Prerequisites:

    pip install --upgrade pip

    pip install pyzmq

    pip install 'influxdb-client[ciso]'


#How to execute the subscriber program?

    #hostname and topic are positional arguments
    /usr/bin/python3 sub_client.py hostname:port topic -i 5

    ex: /usr/bin/python3 sub_client.py msl-ssg-cx03:5555 metrics --interval 10


#To execute on screen:

#create a screen session

screen -S session_name

#trigger the process

/usr/bin/python3 sub_client.py hostname:port topic 

#detach from the session

screen -d


#How to run test cases? 

python3.10 -m pytest subscriber/test/sub_test.py

python3.10 -m pytest --cov cognos.subscriber --cov-report=term --cov-report=html  subscriber/test/sub_test.py


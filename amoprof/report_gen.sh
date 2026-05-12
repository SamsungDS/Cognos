#!/bin/bash

python3 amoprof.py --prometheus http://105.128.44.21:9090 --prom-instance msl-ssg-dgx3.msl.lab:30000 --prom-start 2026-05-08T16:11:57 --prom-end 2026-05-08T17:14:38 --prom-step 1 --save-raw ./amo_prof_results --output amo_prof.html

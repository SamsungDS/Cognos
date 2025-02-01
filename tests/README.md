#############################
##  Install gtest framework #
############################

git clone https://github.com/google/googletest.git -b v1.12.x

cd  googletest 

sudo cmake -Bbuild 

sudo cmake --build build 

sudo cmake --build build target install

#The static libraries libgmock.a lib_gmock_main.a libgtest.a, libgtest_main.a will be available in /usr/local/lib 


#compile & build 
1. navigate to tests folder in svk-cxl and adjust source and tests files path accordingly. 

cd tests

mkdir build 

cmake .. -DCMAKE_CXX_COMPILER=g++

#build 
cmake --build .

#test executable
./cxt_ut

#line coverage report
gcovr -r ../.. --gcov-executable gcov-13 --exclude '/home/s1.nagaraja/dev_platform/cxl/tests/' --gcov-ignore-parse-errors 

#branch coverage report
gcovr -r ../.. --gcov-executable gcov-13 --exclude '/home/s1.nagaraja/dev_platform/cxl/tests/' --exclude-throw-branches --gcov-ignore-parse-errors -b 


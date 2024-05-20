#ifndef TYPES_H
#define TYPES_H

#if __WORDSIZE == 64
typedef unsigned long int uint64_t; /**< 64 bit unsigned long integer*/
#else
__extension__ typedef unsigned long long int
    uint64_t; /**< 64 bit unsigned long long integer*/
#endif

#endif

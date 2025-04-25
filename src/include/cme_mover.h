#ifndef __CME_MOVER_H__
#define __CME_MOVER_H__

#include <map>
#include <mutex>
#include <unordered_map>
#include <string>
#include <functional>

class cme_mover
{
public:
        virtual ~cme_mover() {}
	// mover name: can be used to identify mover object for mover selection logic.
        virtual std::string get_name() = 0;

	/*
	 * @brief: move_all function to be implemented by mover shared library.
	 * 	Move all target application pages from source numa node to destination numa node.
	 * @params:
	 * 	int: target application pid.
	 * 	unsigned int: source numa node number.
	 * 	unsigned int: destination numa node numnber.
	 * 	void* callback function. The function that the move all thread would execute
	 * 		after move all operation is complete. Likely operations are updating
	 * 		the cme_context after move all operation is completed.
	 * 	void* callback function argument: Likely to be pointer to cme_context object.
	 * */
        virtual int move_all(long, unsigned int, unsigned int, std::function<void(void*, int)> , void*, int) = 0;
        virtual int move_hot() = 0;
        virtual int move_cold() = 0;
        virtual int move() = 0;
        virtual int get_status() = 0;
        virtual int stop() = 0;
};

#endif

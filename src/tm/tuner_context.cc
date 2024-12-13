#include "jansson.h"
#include "pm_damo.h"
#include "tuner.h"

using namespace std;
/**
 * @brief tuner context class
 * @details : creates tuner context based on page mover type.
 * @params : pagemover type
 */
tuner_context::tuner_context(pm_type pagemover_type)
{
	switch(pagemover_type)
	{
		case 0:
			{
				pm_obj = new pm_damo();
				break;
			}
		default:
			throw runtime_error("Error in " + string(__FUNCTION__) + " : " + "invalid page mover type");
	}

	mte_obj = new tuner_element(PM_INIT); //default page mover state = INIT
	pm_obj->mte = mte_obj;
}

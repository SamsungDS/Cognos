#ifndef __TUNER_CONTEXT_H__
#define __TUNER_CONTEXT_H_

#include "jansson.h"
#include "pagemover.h"
#include "tuner_element.h"

/**
 * @brief tuner_context class
 * @details A single tuner context is associated with particular application name and application ID unique pair
 * It is created with start tuning command and gets deleted at stop tuning command
 * members:
 *  pointer to tuner_element
 *  pointer to pagemover element
 */
class tuner_context
{
	public:
		tuner_context() = default;
		tuner_context(pm_type);
		
		tuner_element* mte_obj;
		pagemover* pm_obj;
};
#endif

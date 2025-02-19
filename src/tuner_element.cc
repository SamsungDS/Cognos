#include "tuner_element.h"

using namespace std;

/**
 * @brief creates page mover object based on page mover initial state
 * @details creates page mover object based on page mover initial state
 * different pagemover states would be used in future
 */
tuner_element::tuner_element (pm_state default_pgmv_state)
{
  pg_mvr.pm_state = default_pgmv_state;
}

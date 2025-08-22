#ifndef __FRAMEWORK_EXTERN_H__
#define __FRAMEWORK_EXTERN_H__
#include "framework_struct.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief  Extern function created in the core framework to be used by the
 * feature module. This function gets the node_name updated in the core
 * framework namespace.
 *
 * @param[in, out] node_name Buffer to get the node name into
 * @param[in] len Length of the buffer allocated
 * @param[out] len Actual length of the node_name string
 *
 * @return Returns success/failure
 *          - Returns success if there is valid node_name with the actual length
 *          - Returns failure if the input pointers are invalid or zero length
 * or node_name not set.
 */
extern svk_status get_node_name(char *node_name, int *len);

/**
 * @brief  Extern function created in the core framework to be used by the
 * feature module. This function gets the cluster_name updated in the core
 * framework namespace.
 *
 * @param[in, out] cluster_name Buffer to get the cluster name into
 * @param[in] len Length of the buffer allocated
 * @param[out] len Actual length of the cluster_name string
 * @return Returns success/failure
 *          - Return success if the cluster_name is not present, and the *len
 will be set to 0
 *          - Returns success if there is valid cluster_name with the actual
 length
 *          - Returns failure if the input pointers are invalid or zero length

 */
extern svk_status get_cluster_name(char *cluster_name, int *len);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif /*__FRAMEWORK_EXTERN_H__*/
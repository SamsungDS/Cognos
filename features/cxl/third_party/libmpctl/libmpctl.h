/*
*       The confidential and proprietary information contained in this file may
*       only be used by a person authorised under and to the extent permitted
*       by a subsisting licensing agreement from Samsung Electronics.
*
*       (C) COPYRIGHT 2024-2026 Samsung Electronics
*       ALL RIGHTS RESERVED
*
*       Samsung Secret
*
*       This entire notice must be reproduced on all copies of this file
*       and copies of this file may only be made by a person if such person is
*       permitted to do so under the terms of a subsisting license agreement
*       from Samsung Electronics.
*
*/
#ifndef __LIBMPCTL_H_
#define __LIBMPCTL_H_

/*
 * MPCTL Library API
 *
 * The CMM Memory Pool is a pool of memory available via CXL.mem. A server 
 * must have a CMM-MP Device installed in order to have access to the Memory Pool.
 * The Memory Pool is made up of many CMM-MP Devices (either in servers or expansion).
 * The CMM-MP Devices have a CXL front-end and an Ethernet backed. For expansion
 * devices the CXL front-end is not used. The CMM-MP Devices in the Memory Pool
 * are connected via n Ethernet switch.
 *
 * Each server can see 1 Memory Pool. The memory pool is divided into Memory Pool
 * Nodes (MPN) which are specific ranges. Each MPN represents 1+ MP Device capacity.
 */

#include <stdint.h>

#define STR_MAX 32

struct mpctl_ctx;


/* Return codes */
enum mpctl_rc {
	MPCTL_RC_SUCCESS,
	MPCTL_RC_NO_MP_FOUND,
	MPCTL_RC_POOL_NOT_READY,
	MPCTL_RC_MPN_NOT_FOUND,
	MPCTL_RC_ERROR,
};

/* MPN mode (ndctl) */
enum mpctl_mpn_mode {
	MPCTL_MPN_MODE_PMEM,
	MPCTL_MPN_MODE_DEVDAX,
	MPCTL_MPN_MODE_NUMA
};

enum mpctl_mpn_location {
	MPCTL_MPN_ALL,
	MPCTL_MPN_LOCAL,
	MPCTL_MPN_REMOTE,
};

/* Memory Pool */
struct mpctl_pool {
	int		disc_mode;
	int		host_init_disc;	/* Host-initiated discover enabled */
	int             ready;		/* Pool ready */
	uint32_t	size_gb; 	/* Pool size */
	unsigned int 	mpdev_count;	/* Number of pooled MP devices */
	unsigned int	unpooled_mpdev_count; /* Number of unpooled MP devices */
	unsigned int	mpn_count;	/* Number of MPNs */
};

/* Memory Pool Device (MPDEV) */
struct mpctl_mpdev {
	unsigned int	id;		/* MP device identifier */
	uint16_t	fpga_ver;	/* FPGA version */
	uint8_t		fw_ver;		/* FW version */
	uint32_t	chip_id;	/* Unique CHIP_ID */
	int             local;		/* inserted in localHost or remote */
	uint16_t        size_gb;	/* Capacity */
	uint16_t	slot_id;	/* Pool SLOT_ID */
	uint8_t		status;		/* Pool Status 0=unpooled, 1=pooled */
	uint8_t		link_status;	/* Backend Ethernet Link status [0]: Port 0 [1]: Port 1 */
	uint8_t		fpga_temp;	/* FPGA temperature (C) */
};

/* Memory Pool Node (MPN) */
struct mpctl_mpn {
	unsigned int	id;		/* MPN identifier */
	unsigned int	region_id;
	uint8_t		status;		/* MPN status 0=offline, 1=online */
	int		mode;		/* Mode enum mpctl_mpn_mode */
	int		namespace_numa; // valid if mode=MPCTL_MPN_MODE_NUMA
	char		dax_devname[STR_MAX]; // valid if mode=MPCTL_MPN_MODE_DEVDAX
	unsigned long long size;	/* actual size available after label */
	uint32_t	size_gb;	/* Capacity */
	uint64_t	host_phys_addr; /* Physical address (+ HDM Base) */
	int 		location;	/* MPN location enum mpctl_mpn_location */
	uint16_t	slot_id;	/* Slot id of MP device */
};


/*
 * Initialize structure and discover MPNs, local MP devices 
 *
 * \param mctx - returns private mpctl context
 * \return - MPCTL_RC_SUCCESS upon success
 */
int mpctl_init(struct mpctl_ctx **mctx);

/*
 * Clean up structure 
 *
 * \param mctx - private mpctl context
 */
void mpctl_close(struct mpctl_ctx *mctx);

/*
 * Kick off host-initiated discovery. Required only 1 time per pool boot
 *
 * \param mctx - private mpctl context
 * \return - MPCTL_RC_SUCCESS upon success
 */
int mpctl_host_init_discovery(struct mpctl_ctx *mctx);

/*
 * Create the memory pool. NOTE: host-init discovery must be done first
 *
 * \param mctx - private mpctl context
 * \return - MPCTL_RC_SUCCESS upon success
 */
int mpctl_pool_create(struct mpctl_ctx *mctx);

/*
 * Hot Add MP to pool
 *
 * \param mctx - private mpctl context
 * \param mpn_id - MPN unique identifier to online
 * \return - MPCTL_RC_SUCCESS upon success
 */
int mpctl_pool_add(struct mpctl_ctx *mctx, unsigned int mpn_id);


/*
 * Online MPN as NUMA on local server 
 *
 * \param mctx - private mpctl context
 * \param mpn_id - MPN unique identifier to online
 * \return - MPCTL_RC_SUCCESS upon success
 */
int mpctl_mpn_online(struct mpctl_ctx *mctx, unsigned int mpn_id);

/*
 * Offline MPN (dax or NUMA) on local server 
 *
 * \param mctx - private mpctl context
 * \param mpn_id - MPN unique identifier to offline
 * \return - MPCTL_RC_SUCCESS upon success
 */
int mpctl_mpn_offline(struct mpctl_ctx *mctx, unsigned int mpn_id);

/*
 * Enable MPN as devdax on local server 
 *
 * \param mctx - private mpctl context
 * \param mpn_id - MPN unique identifier to enable
 * \return - MPCTL_RC_SUCCESS upon success
 */
int mpctl_mpn_enable_dax(struct mpctl_ctx *mctx, unsigned int mpn_id);


/*
 * Get Pool information 
 *
 * \param mctx - private mpctl context
 * \return - NULL upon failure
 */
struct mpctl_pool* mpctl_pool_get_info(struct mpctl_ctx *mctx);

/*
 * Get MPN information 
 *
 * \param mctx - private mpctl context
 * \param mpn_id - MPN unique identifier
 * \return - NULL upon failure
 */
struct mpctl_mpn *mpctl_mpn_get_info(struct mpctl_ctx *mctx, unsigned int mpn_id);

/*
 * Get MP Device information
 *
 * \param mctx - private mpctl context
 * \param mpdev_id - MP device unique identifier 
 * \return - NULL upon failure
 */
struct mpctl_mpdev* mpctl_mpdev_get_info(struct mpctl_ctx *mctx, unsigned int mpdev_id);

#endif /* __LIBMPCTL_H_ */

// Load App Configs
const clusterPolicies = require('../src/components/clusterPolicies');
export const Configs = require('../src/config/config.json');
export const BackgroundsImage = require('../src/assets/images/backgrounds/BackGroundImage.png');
export const AddIcon = require('../src/assets/icons/Icon-Add-Light.png');
export const MinusIcon = require('../src/assets/icons/Icon-Remove-Light.png');
export const hostSelectorTitle = 'Select Application Server:';
export const hostSelectorOptions = [
    {value: '', label: 'Select' },
    { value: 'host_1', label: 'Host 1 LNK0' }
  ];
export const memboxSelectorTitle = 'Select CMM-B:';
export const memboxSelectorOptions = [
    {value: 'mb-1', label: 'mb-1'}
  ];

export const attachedDevicesTableHeader = [
    'Attach/Detach',
    'CXL Device',
    'Status',
    'Type',
    'Mode',
    'Total Capacity (GB)'
]
export const memboxTableHeader = [
    'CXL Device',
    'CXL Device ID',
    'Total Capacity (GB)',
    'Device Port',
    'Application Servers'
]
  export const ArrowLeft = require('../src/assets/icons/ArrowLeft.png');
  export const ArrowRight = require('../src/assets/icons/ArrowRight.png');
  export const hosts = 'Hosts';
  export const CMM = 'CMM';
  export const cmmd = 'CMM-D';
  export const cmmh = 'CMM-H';
  export const host ='Host';
  export const deviceName = 'DEVX';
  export const deviceMode =  'direct';
  export const DeviceList = [
    {
      device: 'DEV_2-256G'   
    },
    {
      device: 'DEV_3-256G'
    },
    {
      device: 'DEV_4-256G'
    },
    {
      device: 'DEV_5-256G'
    },
    {
      device: 'DEV_8-256G'
    },
    {
      device: 'DEV_10-256G'
    },
    {
      device: 'DEV_11-256G'
    }
  ]

  var largeDeviceSet = [];
  for (var i = 1; i < 25; i++) {
    largeDeviceSet.push({
      device: `DEV_${i}-256G`
    })
  }
  export const DeviceList1 = largeDeviceSet;
  
  export const defaultHostProperties = {
    "Host 1": { color: "#0077C8" },
    "Host 2": { color: "#AC55FF" },
    "Host 3": { color: "#00B3E3" },
    "Host 4": { color: "#8093DC" },
    "Host 5": { color: "#0077C8" },
    "Host 6": { color: "#AC55FF" },
    "Host 7": { color: "#00B3E3" },
    "Host 8": { color: "#FFB546" },
    "Host 9": { color: "#FF6700" },
    "Host 10": { color: "#00C3B2" },
    "Host 11": { color: "#52DD3A" },
  };

  export const mappedHostList = (hostList, hostToDeviceMapping) => {
    // Create a shallow copy of the hostToDeviceMapping to keep track of unused hosts
    let unusedHostMapping = [...hostToDeviceMapping];
    return hostList.map((item) => {
      // Try to find the current host in the unusedHostMapping
      const mappedHostIndex = unusedHostMapping.findIndex(
        (hostItem) => hostItem.label === item.host
      );

      let newHostName = item.host; // Default to the original host name
      let newColor = "#4F4F4F";
      let clusterName = null;
      // If a match is found, update the host name and remove it from unusedHostMapping
      // istanbul ignore next
      if (mappedHostIndex !== -1) {
        newHostName = unusedHostMapping[mappedHostIndex].label;       
        unusedHostMapping.splice(mappedHostIndex, 1); // Remove used host
      } else if (unusedHostMapping.length > 0) {
        // If no match is found, replace with the next available host from unusedHostMapping
        newColor = item.color;
        newHostName = unusedHostMapping[0].label;
        clusterName = unusedHostMapping[0].cluster;
        unusedHostMapping.shift(); // Remove the first host (unshifted)
      }
      return {
        ...item,
        host: newHostName, // Update the host name only once
        color: newColor, // Keep the original color
        cluster: clusterName,
        isActive: mappedHostIndex !== -1 || newHostName !== item.host, // Set isActive based on whether the host was updated
      };
    });
  };

  export const mappedDeviceList = (deviceList, hostList, hostToDeviceMapping) => {
    let unusedHostMapping = hostToDeviceMapping.filter(mapping => mapping.fm_type === "FM_REMOTE_CMMB");
    return deviceList.map((device) => {
      // Find the associated host for the current device by checking all hosts
      const associatedHost = unusedHostMapping.find((host) =>
        host.devices.includes(device.device)
      );

      let newHostName = null; // Default to null if no host is found
      let newColor = "#4F4F4F"; // Default color for devices with no associated host

      // If a match is found, update the host name
      // istanbul ignore next
      if (associatedHost) {
        newHostName = associatedHost.host; // Get the host name
        const hostDetails = hostList.find((h) => h.host === newHostName);

        // Update the newColor based on the found host
        if (hostDetails) {
          newColor = hostDetails.color; // Use the host's color if found
        }
      }

      return {
        ...device,
        host: newHostName, // Update with associated host name if found
        color: newColor, // Use the determined color
      };
    });
  };

  export const fetchMetrics = async (url, payload) => {
    try {
      const response = await fetch(url, {
        mode: 'cors',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'accept': 'application/json',
          'Access-Control-Allow-Origin':'*'
        },
        body: JSON.stringify(payload),
      })
      return response
    } catch (error) {
        console.error("Failed Metrics POST Request: ", error);
    }
  }

  export const fetchData = async (url, setDataCallback) => {
    try {
      const response = await fetch(url, {
        method: "GET",
        headers: new Headers({
          "Access-Control-Allow-Origin": "*",
        }),
      });
      const data = await response.json();
      setDataCallback(data);
    } catch (error) {
      console.error("Error fetching data:", error);
    }
  };
  // istanbul ignore next
  export function mergeHosts(data) {
    const merged = {};
  
    data.forEach(item => {
      const { host, devices, fm_type } = item;
  
      if (!merged[host]) {
        // Initialize new host entry if it doesn't exist
        merged[host] = [{ devices: [...devices], fm_type }];
      } else {
        // Add new object with devices and fm_type to the existing host entry
        merged[host].push({ devices: [...devices], fm_type });
      }
    });
  
    // Convert the merged object back to array format with the desired structure
    return Object.keys(merged).map(host => ({
      host,
      details: merged[host]
    }));
  };

  // istanbul ignore next
  export function updateHostListAttached(newHostData) {
    // Filtering out hosts that contain "FM_REMOTE_CMMB" in their details
    return newHostData
      .filter((item) => item.details.some(detail => detail.fm_type !== "FM_REMOTE_CMMB"))
      .map((item) => ({
        host: item.host,
        details: item.details
          .filter(detail => detail.fm_type !== "FM_REMOTE_CMMB") // Filter out FM_REMOTE_CMMB
          .map((detail) => ({
            devices: detail.devices,
            fm_type: detail.fm_type,
          }))
      }));
    }
// Main function to assign clusters based on selected policy
export const assignClusters = (hosts, clusterName) => {
  // Filter the hosts array to only include hosts whose cluster property
  // matches one of the values in the clusterName array
  return hosts.filter(host => clusterName.includes(host.cluster));
};

// istanbul ignore next
export const assignClustersToLabelValuePairs = (labelValuePairs, HostList) => {
  // Create a map for quick lookup of hosts by their host property
  const hostMap = HostList.reduce((map, hostObj) => {
    map[hostObj.host] = hostObj;
    return map;
  }, {});

  // Map through labelValuePairs and add cluster property
  return labelValuePairs.map(pair => {
    const matchingHost = hostMap[pair.label];
    
    // If a matching host is found, add its cluster to the pair
    if (matchingHost) {
      return {
        ...pair,
        cluster: matchingHost.cluster
      };
    }
    
    // If no matching host is found, return the original pair
    return pair;
  });
};

// istanbul ignore next
export const transformData = function(inputData) {
  const result = [];
  
  // Check if inputData is empty or null/undefined
  if (!inputData || (typeof inputData === 'object' && Object.keys(inputData).length === 0)) {
    console.warn("Input data is empty, null, or undefined.");
    return result; // Return empty array
  }
  
  // Handle the case where the input is an array containing objects with clusters
  if (Array.isArray(inputData)) {
    // Process each object in the array using optional chaining
    inputData.forEach(dataObj => {
      // Use optional chaining for accessing the clusters property
      dataObj?.clusters?.forEach(cluster => {
        const clusterName = cluster.cluster_name;
        
        // Use optional chaining for accessing the nodes property
        cluster?.nodes?.forEach(node => {
          const hostName = node.node_name;
          
          // Create the transformed object
          const transformedObj = {
            "devices": node.devices || [],
            "fm_type": node.fm_type || "",
            "host": hostName || "",
            "cluster": clusterName || ""
          };
          
          result.push(transformedObj);
        });
      });
    });
  } else {
    // Handle the case where inputData is a direct object with clusters property
    inputData?.clusters?.forEach(cluster => {
      const clusterName = cluster.cluster_name;
      
      cluster?.nodes?.forEach(node => {
        const hostName = node.node_name;
        
        const transformedObj = {
          "devices": node.devices || [],
          "fm_type": node.fm_type || "",
          "host": hostName || "",
          "cluster": clusterName || ""
        };
        
        result.push(transformedObj);
      });
    });
  }
  
  return result;
}
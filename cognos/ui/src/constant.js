// Load App Configs
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
        (hostItem) => hostItem.host === item.host
      );

      let newHostName = item.host; // Default to the original host name
      let newColor = "#4F4F4F";
      // If a match is found, update the host name and remove it from unusedHostMapping
      if (mappedHostIndex !== -1) {
        newHostName = unusedHostMapping[mappedHostIndex].host;
        unusedHostMapping.splice(mappedHostIndex, 1); // Remove used host
      } else if (unusedHostMapping.length > 0) {
        // If no match is found, replace with the next available host from unusedHostMapping
        newColor = item.color;
        newHostName = unusedHostMapping[0].host;
        unusedHostMapping.shift(); // Remove the first host (unshifted)
      }
      return {
        ...item,
        host: newHostName, // Update the host name only once
        color: newColor, // Keep the original color
        isActive: mappedHostIndex !== -1 || newHostName !== item.host, // Set isActive based on whether the host was updated
      };
    });
  };

  export const mappedDeviceList = (deviceList, hostList, hostToDeviceMapping) => {
    // Create a shallow copy of the hostToDeviceMapping to keep track of unused hosts
    let unusedHostMapping = [...hostToDeviceMapping];

    return deviceList.map((device) => {
      // Find the associated host for the current device by checking all hosts
      const associatedHost = unusedHostMapping.find((host) =>
        host.devices.includes(device.device)
      );

      let newHostName = null; // Default to null if no host is found
      let newColor = "#4F4F4F"; // Default color for devices with no associated host

      // If a match is found, update the host name
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
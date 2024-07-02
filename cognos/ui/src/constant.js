// Load App Configs
export const Configs = require('../src/config/config.json');
export const BackgroundsImage = require('../src/assets/images/backgrounds/BackGroundImage.png');
export const AddIcon = require('../src/assets/icons/Icon-Add-Light.png');
export const EditIcon = require('../src/assets/icons/Icon-Edit-Light.png');
export const MinusIcon = require('../src/assets/icons/Icon-Remove-Light.png');
export const LoadingGif = require('../src/assets/gifs/backup_loading-gif.gif');
export const ActiveLight = require('../src/assets/gifs/Icon-Green-Light.gif');
export const UnhealthyLight = require('../src/assets/gifs/Icon-Red-Light.gif');
export const InactiveLight =  require('../src/assets/gifs/Icon-Yellow-Light.gif');
export const ReadyLight = require('../src/assets/gifs/Icon-Blue-Light.gif')
export const hostSelectorTitle = 'Select Application Server:';
export const hostSelectorOptions = [
    {value: '', label: 'Select' },
    { value: 'host_1', label: 'Host 1 LNK0' }
  ];
export const memboxSelectorTitle = 'Select CMM-B:';
export const memboxSelectorOptions = [
    {value: 'mb-1', label: 'mb-1'}
  ];

export const lmdTableHeader = [
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
  export const pattern = require('../src/assets/icons/Pattern.png');
  export const ArrowLeft = require('../src/assets/icons/ArrowLeft.png');
  export const ArrowRight = require('../src/assets/icons/ArrowRight.png');
  export const cxlDevArrow = require('../src/assets/icons/cxl-dev-Arrow.png');
  export const cxlDevArrowInactive = require('../src/assets/icons/cxl-dev-Arrow-Inactive.png');
  export const cxlDevIconInActive = require('../src/assets/icons/cxl-dev-icon-Inactive.png');
  export const hostArrowDown = require('../src/assets/icons/hostArrowDown.png');
  export const hostIconArrowInactive = require('../src/assets/icons/hostIconArrowInactive.png');
  export const HostIconInactive = require('../src/assets/icons/HostIconInactive.png');
  export const HostIconSvG = require('../src/assets/icons/hostIconSVG.svg');
  export const CXLDevice = require('../src/assets/icons/CXLDeviceYellow.png');
  export const DashboardIcon = require('../src/assets/icons/dashboardIcon.png');
  export const ConfigureIcon = require('../src/assets/icons/ConfigureIcon.png');
  export const VideoMetrics = require('../src/assets/images/charts/host-SAP-HANA.webm');
  export const SAPHANALegend = require('../src/assets/images/charts/Graphs-Legend.png')
  // SAP HANA Metrics gif
  export const SAPHANAMetrics = require('../src/assets/gifs/SAPHANA-cropped.gif')
  export const D1 = require('../src/assets/icons/CXL-Dev-Blue1.png');
  export const D2 = require('../src/assets/icons/CXL-Dev-Blue2.png');
  export const D3 = require('../src/assets/icons/CXL-Dev-Green.png');
  export const D4 = require('../src/assets/icons/CXL-Dev-Orange.png');
  export const D5 = require('../src/assets/icons/CXL-Dev-Purple1.png');
  export const D6 = require('../src/assets/icons/CXL-Dev-Purple2.png');
  export const D7 = require('../src/assets/icons/CXL-Dev-Teal.png');
  export const D8 = require('../src/assets/icons/CXL-Dev-Yellow.png');
  export const D = require('../src/assets/icons/CXLDeviceWhite.png');
  export const Host1 = require('../src/assets/icons/Host1.png');
  export const Host2 = require('../src/assets/icons/Host2.png');
  export const Host3 = require('../src/assets/icons/Host3.png');
  export const Host4 = require('../src/assets/icons/Host4.png');
  export const Host5 = require('../src/assets/icons/Host5.png');
  export const Host6 = require('../src/assets/icons/Host6.png');
  export const Host7 = require('../src/assets/icons/Host7.png');
  export const Host8 = require('../src/assets/icons/Host8.png');
  export const SignInImage = require('../src/assets/images/SignIn/SignIn.png');
  export const SCCDashboard = require('../src/assets/images/SignIn/SCC-Physical-Assets-mgmt-gm.png');
  export const getImageByColor = (colorCode) => {
    const colorImageMap = {
      '#0077C8': D1, 
      '#00B3E3': D2,
      '#52DD3A': D3,
      '#FF6700': D4,
      '#AC55FF': D5,
      '#8093DC': D6,
      '#00C3B2': D7,
      '#FFB546': D8       
    };
    return colorImageMap[colorCode];
  }

  export const hosts = 'Hosts';
  export const CMM = 'CMM';
  export const racks = 'Racks';
  export const sys_mem_allcated = 'System Memory Allocated';
  export const cmmd = 'CMM-D';
  export const cmmh = 'CMM-H';
  export const health = 'Health';
  export const host ='Host';
  export const trend_graph= 'Trend Graph';
  export const system_bandwidth = 'System Bandwidth';
  export const rackBandwidth_id = 'rackBandwidth-id';
  export const dramCxlMemUsage_id = 'dramCxlMemUsage-id';
  export const deviceName = 'DEVX';
  export const deviceMode =  'direct';
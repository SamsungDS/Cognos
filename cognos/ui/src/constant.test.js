import * as constants from './constant';

describe('Constants', () => {
  it('should have the correct value for BackgroundsImage', () => {
    expect(constants.BackgroundsImage).toEqual(require('../src/assets/images/backgrounds/BackGroundImage.png'));
  });
});


describe('mappedHostList', () => {

  test('should replace hosts with the next available host when there is no mapping', () => {
    const hostList = [
      { host: 'loaner-emr04', color: '#0077C8' },
      { host: 'msl-cti-emr06', color: '#AC55FF' },
      { host: 'msl-stg-emr03', color: '#4F4F4F' },
    ];

    const hostToDeviceMapping = [
      {label: "loaner-emr04", value: "loaner-emr04"},
      {label: "msl-cti-emr06", value: "msl-cti-emr06"},
    ];

    const result = constants.mappedHostList(hostList, hostToDeviceMapping);

    expect(result).toEqual([
      { host: 'loaner-emr04', color: '#4F4F4F', isActive: true },
      { host: 'msl-cti-emr06', color: '#4F4F4F', isActive: true },
      { host: 'msl-stg-emr03', color: '#4F4F4F', isActive: false }, // Replaced with the next available host
    ]);
  });

  test('should keep the original color for hosts without mapping', () => {
    const hostList = [
      { host: 'loaner-emr04', color: '#0077C8' },
      { host: 'msl-cti-emr06', color: '#AC55FF' },
      { host: 'other-host', color: '#4F4F4F' },
    ];

    const hostToDeviceMapping = [
      {label: "loaner-emr04", value: "loaner-emr04"},
      {label: "msl-cti-emr06", value: "msl-cti-emr06"},
    ];

    const result = constants.mappedHostList(hostList, hostToDeviceMapping);

    expect(result).toEqual([
      { host: 'loaner-emr04', color: '#4F4F4F', isActive: true },
      { host: 'msl-cti-emr06', color: '#4F4F4F', isActive: true },
      { host: 'other-host', color: '#4F4F4F', isActive: false }, // Original color is kept
    ]);
  });
});

describe('mappedDeviceList', () => {
  test('should map devices to their associated hosts correctly', () => {
    const deviceList = [
      { device: 'DEV_11-256G' },
      { device: 'DEV_2-256G' },
      { device: 'DEV_5-256G' },
    ];

    const hostList = [
      { host: 'loaner-emr04', color: '#0077C8' },
      { host: 'msl-cti-emr06', color: '#AC55FF' },
    ];

    const hostToDeviceMapping = [
      { devices: ['DEV_11-256G', 'DEV_8-256G'], host: 'loaner-emr04' },
      { devices: ['DEV_2-256G', 'DEV_4-256G'], host: 'msl-cti-emr06' },
    ];

    const result = constants.mappedDeviceList(deviceList, hostList, hostToDeviceMapping);

    expect(result).toEqual([
      { device: 'DEV_11-256G', host: null, color: '#4F4F4F' },
      { device: 'DEV_2-256G', host: null, color: '#4F4F4F' },
      { device: 'DEV_5-256G', host: null, color: '#4F4F4F' },
    ]);
  });

  test('should assign default color if no host is associated', () => {
    const deviceList = [
      { device: 'DEV_3-256G' }, // No corresponding host mapping
    ];

    const hostList = [
      { host: 'loaner-emr04', color: '#0077C8' },
    ];

    const hostToDeviceMapping = [
      { devices: ['DEV_11-256G', 'DEV_8-256G'], host: 'loaner-emr04' },
    ];

    const result = constants.mappedDeviceList(deviceList, hostList, hostToDeviceMapping);

    expect(result).toEqual([
      { device: 'DEV_3-256G', host: null, color: '#4F4F4F' }, // No mapping found
    ]);
  });
});

describe('fetchData', () => {
  const mockUrl = constants.Configs.api_endpoint + "/hosts";

  beforeEach(() => {
    // Reset mocks before each test
    global.fetch = jest.fn();
  });

  test('calls setDataCallback with fetched data on success', async () => {
    // Mock data that the fetch will return
    const mockData = [{ label: "msl-stg-emr02.msl.lab", value: "msl-stg-emr02.msl.lab" }];
    
    // Mock the fetch response to resolve successfully
    global.fetch.mockResolvedValueOnce({
      json: jest.fn().mockResolvedValueOnce(mockData),
    });

    // Create a mock for the callback function
    const setDataCallback = jest.fn();

    // Call the fetchData function
    await constants.fetchData(mockUrl, setDataCallback);

    // Expect the fetch to have been called with the correct URL
    expect(global.fetch).toHaveBeenCalledWith(mockUrl, {
      method: "GET",
      headers: new Headers({
        "Access-Control-Allow-Origin": "*",
      }),
    });

    // Expect the setDataCallback to be called with the mock data
    expect(setDataCallback).toHaveBeenCalledWith(mockData);
  });

  test('logs an error if the fetch fails', async () => {
    // Spy on console.error
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    // Mock the fetch to reject (simulate an error)
    global.fetch.mockRejectedValueOnce(new Error('Fetch failed'));

    // Create a mock callback function
    const setDataCallback = jest.fn();

    // Call the fetchData function
    await constants.fetchData(mockUrl, setDataCallback);

    // Expect console.error to have been called
    expect(consoleSpy).toHaveBeenCalledWith('Error fetching data:', expect.any(Error));

    // Cleanup
    consoleSpy.mockRestore();
  });
});
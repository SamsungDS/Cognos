import * as constants from './constant';

describe('Constants', () => {
  it('should have the correct value for BackgroundsImage', () => {
    expect(constants.BackgroundsImage).toEqual(require('../src/assets/images/backgrounds/BackGroundImage.png'));
  });
});

// Define test cases
describe('getImageByColor', () => {
  it('returns correct image for valid color codes', () => {
    // Define test data
    const testData = [
      { colorCode: '#0077C8', expectedImage: constants.D1 },
      { colorCode: '#00B3E3', expectedImage: constants.D2 },
      { colorCode: '#52DD3A', expectedImage: constants.D3 },
      { colorCode: '#FF6700', expectedImage: constants.D4 },
      { colorCode: '#AC55FF', expectedImage: constants.D5 },
      { colorCode: '#8093DC', expectedImage: constants.D6 },
      { colorCode: '#00C3B2', expectedImage: constants.D7 },
      { colorCode: '#FFB546', expectedImage: constants.D8 }
    ];

    // Iterate through test data and run assertions
    testData.forEach(({ colorCode, expectedImage }) => {
      const actualImage = constants.getImageByColor(colorCode);
      expect(actualImage).toEqual(expectedImage);
    });
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
      { devices: ['DEV_11-256G', 'DEV_8-256G'], host: 'loaner-emr04' },
    ];

    const result = constants.mappedHostList(hostList, hostToDeviceMapping);

    expect(result).toEqual([
      { host: 'loaner-emr04', color: '#4F4F4F', isActive: true },
      { host: 'msl-cti-emr06', color: '#4F4F4F', isActive: false },
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
      { devices: ['DEV_11-256G', 'DEV_8-256G'], host: 'loaner-emr04' },
    ];

    const result = constants.mappedHostList(hostList, hostToDeviceMapping);

    expect(result).toEqual([
      { host: 'loaner-emr04', color: '#4F4F4F', isActive: true },
      { host: 'msl-cti-emr06', color: '#4F4F4F', isActive: false },
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
      { device: 'DEV_11-256G', host: 'loaner-emr04', color: '#0077C8' },
      { device: 'DEV_2-256G', host: 'msl-cti-emr06', color: '#AC55FF' },
      { device: 'DEV_5-256G', host: null, color: '#4F4F4F' }, // No mapping found
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
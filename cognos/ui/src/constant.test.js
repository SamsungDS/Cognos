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
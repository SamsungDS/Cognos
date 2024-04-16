import * as constants from './constant';

describe('Constants', () => {
  it('should have the correct value for BackgroundsImage', () => {
    expect(constants.BackgroundsImage).toEqual(require('../src/assets/images/backgrounds/BackGroundImage.png'));
  });
});
import React from 'react';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Configure from '../pages/Configure';
import * as constants from '../constant';

// Mocking fetch responses
global.fetch = jest.fn().mockImplementation(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve([]),
  })
);

describe('Configure Component - Integration Tests', () => {
    test('should render and attach memory properly', async () => {
      render(<Configure />);
      // Assert that fetch calls are made to attach memory and update data
      setTimeout(() => expect(fetch).toHaveBeenCalledTimes(1));
      expect(fetch).toHaveBeenCalledWith(`${constants.Configs.data_endpoint}//lmds`, {
        method: 'get',
        headers: new Headers({
          'Access-Control-Allow-Origin':'*'
        })
      });
    }, 0);
  });
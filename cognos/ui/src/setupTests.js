// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

import '@testing-library/jest-dom/extend-expect';
import { configure } from '@testing-library/react';
// Configure the testing library to use the async act function
configure({ asyncUtilTimeout: 5000 });

global.MutationObserver = class {
    constructor(callback) {}
    disconnect() {}
    observe(element, initObject) {}
  };
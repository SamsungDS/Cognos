import React from 'react';
import ReactDOM from 'react-dom';
import { act } from 'react-dom/test-utils';
import '@testing-library/jest-dom/extend-expect'; 
import App from './App';

let container = null;
let root = null;

beforeEach(() => {
  // setup a DOM element as a render target
  container = document.createElement("div");
  document.body.appendChild(container);
  // Create a root using ReactDOM.createRoot()
  root = ReactDOM.createRoot(container);
});

afterEach(() => {
  // cleanup on exiting
  document.body.removeChild(container);
  container = null;
  root = null;
});


test('renders App component into root element', () => {
  act(() => {
    root.render(<App />);
  });

  const appElement = container.querySelector('.app');
  expect(appElement).toBeInTheDocument();
});
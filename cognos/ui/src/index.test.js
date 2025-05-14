import React from 'react';
import ReactDOM from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import '@testing-library/jest-dom/extend-expect'; 
import App from './App';
import { SelectedOptionProvider } from './contexts/SelectedOptionContext';

let container = null;
let root = null;

beforeEach(() => {
  // setup a DOM element as a render target
  container = document.createElement("div");
  document.body.appendChild(container);
});

afterEach(() => {
  // cleanup on exiting
  document.body.removeChild(container);
  container = null;
});


test('renders App component into root element', () => {
  // Ensure the root element exists
  const rootElement = document.createElement("div");
  rootElement.id = 'root';
  document.body.appendChild(rootElement);

  // Create the root inside the act function
  act(() => {
    root = ReactDOM.createRoot(document.getElementById('root'));
    const memCapacityData = jest.fn()
    const dramCxlMemUsageData = jest.fn()
    const memoryCpuData = jest.fn()
    const cmmbMemoryData = jest.fn()
    const cmmbCapacityData = jest.fn()
    const cmmbBandwidthData = jest.fn()
    const devicesCountData = jest.fn()
    root.render(
      <SelectedOptionProvider> 
        <App />
      </SelectedOptionProvider>
  );
  });

  setTimeout(() => {
    const appElement = container.querySelector('.app');
    expect(appElement).toBeInTheDocument();
  },1000);
});
import React, { createContext } from 'react';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Header from '../components/Header';
import { AuthContext } from '../components/ProtectedRoute';


const MockAuthProvider = ({ children, value }) => (
  <AuthContext.Provider value={value}>
    {children}
  </AuthContext.Provider>
);

describe('Header', () => {
  const mockAuthValue = {
    userRole: 'admin',
    isAuthenticated: true,
    logout: jest.fn()
  };
  it('renders without crashing', () => {
    render(
    <MockAuthProvider value={mockAuthValue}>
      <Header />
    </MockAuthProvider>
    );
  });

  it('renders Samsung logo and text', () => {
    const { getByAltText, getByText } = render(
    <MockAuthProvider value={mockAuthValue}>
      <Header />
    </MockAuthProvider>
    );
    const logo = getByAltText('logo');
    const text = getByText(/Cognos Management Console/i);

    expect(logo).toBeInTheDocument();
    expect(text).toBeInTheDocument();
  });
});
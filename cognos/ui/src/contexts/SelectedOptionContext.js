import React, { createContext, useState, useContext } from 'react';

// Create the context
const SelectedOptionContext = createContext();

// Provider component
export const SelectedOptionProvider = ({ children }) => {
  const [selectedOption, setSelectedOption] = useState("Host");

  // Function to toggle selectedOption
  // istanbul ignore next
  const handleToggle = () => {
    setSelectedOption((prevOption) =>
      prevOption === "Host" ? "CMM-B" : "Host"
    );
  };

  return (
    <SelectedOptionContext.Provider value={{ selectedOption, handleToggle }}>
      {children}
    </SelectedOptionContext.Provider>
  );
};

// Custom hook to use context
export const useSelectedOption = () => useContext(SelectedOptionContext);
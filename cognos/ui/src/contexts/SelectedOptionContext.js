import React, { createContext, useState, useContext } from 'react';

// Create the context
const SelectedOptionContext = createContext();

// Provider component
export const SelectedOptionProvider = ({ children }) => {
  const [selectedOption, setSelectedOption] = useState("CMM-B");

  // Function to toggle selectedOption
  // istanbul ignore next
  const handleToggle = () => {
    setSelectedOption((prevOption) =>
      prevOption === "CMM-B" ? "Host" : "CMM-B"
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
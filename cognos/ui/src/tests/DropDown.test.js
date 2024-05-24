import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import DropDown from '../components/DropDown';

describe('DropDown', () => {
  it('renders without crashing', () => {
    render(<DropDown options={[]} title="Test" dropDownType="single"  onSelectChange={()=> {}}/>);
  });

  it('renders title correctly', () => {
    const { getByText } = render(<DropDown options={[]} title="Test Title" dropDownType="single"  onSelectChange={()=> {}}/>);
    expect(getByText('Test Title')).toBeInTheDocument();
  });

  it('renders options correctly', () => {
    const options = [
      { value: 'option1', label: 'Option 1' },
      { value: 'option2', label: 'Option 2' },
    ];
    const { getByText } = render(<DropDown options={options} title="Test" dropDownType="single"  onSelectChange={()=> {}}/>);
    expect(getByText('Option 1')).toBeInTheDocument();
  });

  it('handles single selection', () => {
    const options = [
      { value: 'option1', label: 'Option 1' },
      { value: 'option2', label: 'Option 2' },
    ];
    // Mocking useState hook
    const useStateSpy = jest.spyOn(React, 'useState');
    useStateSpy.mockImplementation((init) => [init, jest.fn()]);
    const onSelectChange = jest.fn();
    
    const { getByText } = render(<DropDown options={options} title="Test" dropDownType="single" onSelectChange={onSelectChange} />);
    fireEvent.click(getByText('Option 1'));
    
    expect(onSelectChange).toHaveBeenCalledWith(options[0]);
  });

});
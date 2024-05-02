import React from 'react';
import Select from 'react-select';

const DropDown = ({ options, title, dropDownType, onSelectChange, name }) => {

    const [selectedValue, setSelectedValue] = React.useState(options[0] || '');
    const isMulti = dropDownType === 'multi';

    const handleSelectChange = (selectedOption) => {
        setSelectedValue(selectedOption);
        if (onSelectChange) {
            onSelectChange(selectedOption);
        }
    };

    return (
        <div className='dropdown-container' id='dropdown-container-id' data-testid={`dropdown-${name}`}>
            <label htmlFor="dropdown" className='app-server' style={{ color: "white", marginRight: 8 }} data-testid='label'>{title}</label>
            <Select
                value={selectedValue}
                isMulti={isMulti}
                options={options}
                className="basic-multi-select"
                classNamePrefix="select"
                onChange={handleSelectChange}
                styles={{
                    control: (baseStyles, state) => ({
                        ...baseStyles,
                        borderColor: state.isFocused ? 'grey' : 'blue ',
                    }),
                }}
                theme={(theme) => ({
                    ...theme,
                    borderRadius: 0,
                    colors: {
                        ...theme.colors,
                        primary25: '#8093DC',
                        primary: '#8093DC',
                    },
                })}
                data-testid="select-inputs"
            />
        </div>
    );
};

export default DropDown;